"""SPEC-011 deterministic retrieval. Cache is disposable; published facts own revision."""

import hashlib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from backend.models.knowledge import (
    KnowledgeError,
    KnowledgeStore,
    invalid,
    payload,
    text,
)

ALGORITHM = "qa-tfidf-v1"
SQL = Path(__file__).resolve().parents[1] / "migrations" / "011_qa.sql"
CHECKSUM = hashlib.sha256(SQL.read_text(encoding="utf-8").encode()).hexdigest()
ALIASES = {"acc": "累加器", "alu": "算术逻辑单元", "pc": "程序计数器", "ir": "指令寄存器"}
# English word boundaries, including digits/underscore, also work adjacent to Chinese.
ALIAS_PATTERN = re.compile(r"(?<![a-z0-9_])(?:acc|alu|pc|ir)(?![a-z0-9_])")


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(value):
    parser = PlainText()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)


def preprocess(value):
    value = unicodedata.normalize("NFKC", strip_html(unicodedata.normalize("NFKC", value))).lower()
    value = ALIAS_PATTERN.sub(lambda match: ALIASES[match[0]], value)
    return re.sub(r"\s+", " ", value).strip()


def rank_matches(rows, similarities, top_k):
    # Filter and sort raw doubles before display rounding; never round at the threshold.
    ranked = sorted(((row, float(score)) for row, score in zip(rows, similarities, strict=True)
                     if score >= 0.10), key=lambda item: (-item[1], item[0]["id"]))[:top_k]
    matches = [{"knowledge_id": row["id"], "excerpt": strip_html(row["content"])[:200],
                "similarity": round(min(1.0, score), 6)} for row, score in ranked]
    return matches, [score for _, score in ranked]


@dataclass(frozen=True)
class Index:
    revision: str
    rows: tuple
    vectorizer: object
    matrix: object
    built_at: str

    def search(self, question, top_k):
        if self.vectorizer is None:
            return [], []
        vector = self.vectorizer.transform([preprocess(question)])
        if vector.nnz == 0:
            return [], []
        scores = (self.matrix @ vector.T).toarray().ravel()
        return rank_matches(self.rows, scores, top_k)


def build_index(revision, rows):
    texts = [preprocess(" ".join(row[key] for key in ("title", "content", "example"))) for row in rows]
    vectorizer, matrix = None, None
    if any(texts):
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), min_df=1,
                                     smooth_idf=True, norm="l2", lowercase=False,
                                     strip_accents=None, sublinear_tf=False)
        matrix = vectorizer.fit_transform(texts)
    return Index(revision, tuple(rows), vectorizer, matrix,
                 datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"))


class IndexCache:
    def __init__(self):
        self.lock = threading.RLock()
        self.items = {}


class QAStore(KnowledgeStore):
    def __init__(self, path, verify_transaction, cache):
        super().__init__(path, verify_transaction)
        self.cache = cache

    def corpus(self, db, user, course_id):
        self.access(db, user, course_id)
        migration = db.execute("SELECT checksum FROM schema_migration WHERE version='011_qa'").fetchone()
        if not migration or migration[0] != CHECKSUM:
            raise KnowledgeError(503, "INDEX_UNAVAILABLE", "检索索引尚未就绪，请稍后重试")
        rows = [dict(row) for row in db.execute(
            "SELECT k.id,k.title,k.content,k.example,k.content_revision FROM knowledge_point k "
            "JOIN chapter c ON c.id=k.chapter_id WHERE c.course_id=? AND k.published=1 ORDER BY k.id",
            (course_id,))]
        revision = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
        return revision, rows

    @staticmethod
    def save_index(db, course_id, revision, built_at, failed=False):
        now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        db.execute(
            "INSERT INTO qa_index(course_id,corpus_revision,algorithm_version,built_at,status,error_code,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET "
            "corpus_revision=excluded.corpus_revision,algorithm_version=excluded.algorithm_version,"
            "built_at=excluded.built_at,status=excluded.status,error_code=excluded.error_code,updated_at=excluded.updated_at",
            (course_id, revision, ALGORITHM, built_at, "failed" if failed else "ready",
             "INDEX_UNAVAILABLE" if failed else None, now, now))

    def ask(self, user_id, course_id, body):
        values = payload(body, {"question", "top_k"}, {"question"})
        question = text(values["question"], 500, 1)
        top_k = values.get("top_k", 3)
        if type(top_k) is not int or not 1 <= top_k <= 5:
            invalid("top_k 必须为 1—5 的整数")
        # Per-app lock serializes replacement. Other processes have their own disposable
        # cache and must pass the same database revision/permission gate before serving.
        with self.cache.lock:
            for _ in range(3):
                with self.transaction(user_id) as (db, user):
                    revision, rows = self.corpus(db, user, course_id)
                index = self.cache.items.get(course_id)
                if index and index.revision != revision:
                    del self.cache.items[course_id]
                    index = None
                failure = False
                try:
                    # No write transaction while fitting or searching.
                    index = index or build_index(revision, rows)
                    matches, raw_scores = index.search(question, top_k)
                except Exception:  # noqa: BLE001 -- any fit/search failure must fail closed without stale text.
                    # No exception text, paths, query text or obsolete excerpts cross the API.
                    failure = True
                    self.cache.items.pop(course_id, None)
                with self.transaction(user_id, True) as (db, user):
                    current, _ = self.corpus(db, user, course_id)
                    if current != revision:
                        self.cache.items.pop(course_id, None)
                        continue
                    self.save_index(db, course_id, revision,
                                    datetime.now(UTC).isoformat().replace("+00:00", "Z") if failure else index.built_at,
                                    failure)
                    if not failure:
                        db.execute(
                            "INSERT INTO qa_query(user_id,course_id,question,matched_ids_json,similarities_json,"
                            "index_revision,algorithm_version,created_at) VALUES(?,?,?,?,?,?,?,?)",
                            (user_id, course_id, question,
                             json.dumps([match["knowledge_id"] for match in matches]), json.dumps(raw_scores),
                             revision, ALGORITHM, datetime.now(UTC).isoformat().replace("+00:00", "Z")))
                if failure:
                    break
                # Publish the complete object only after both index metadata and query commit.
                self.cache.items[course_id] = index
                return {"matches": matches, "found": bool(matches),
                        "reason": "matched" if matches else "no_match" if rows else "empty_corpus",
                        "index_version": revision, "algorithm_version": ALGORITHM}
        raise KnowledgeError(503, "INDEX_UNAVAILABLE", "检索索引暂时不可用，请稍后重试")
