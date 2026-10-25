"""Knowledge facts and course isolation; authentication remains owned by SPEC-001."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import numpy as np

from backend.models.knowledge_migration import CHECKSUM, VERSION


class KnowledgeError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def invalid(message="请求字段或类型不合法"):
    raise KnowledgeError(400, "VALIDATION_ERROR", message)


def positive_id(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        invalid("ID 必须为数据库可表示的正整数")
    return value


class SafeHTML(HTMLParser):
    # Attribute-free teaching markup. Images/URLs/active content are not allowed.
    allowed = frozenset({"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li",
               "pre", "code", "blockquote", "sub", "sup", "h2", "h3"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.allowed:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in self.allowed and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(escape(data))


def text(value, maximum, minimum=0, markup=False):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        invalid("文本长度不合法")
    value = value.strip()
    if markup:
        parser = SafeHTML()
        parser.feed(value)
        parser.close()
        value = "".join(parser.parts)
    return value


def payload(body, allowed, required=()):
    if type(body) is not dict or set(body) - set(allowed) or not set(required) <= set(body):
        invalid()
    if not body:
        invalid("更新字段不能为空")
    result = {}
    for key, value in body.items():
        if key in {"published", "is_foundational", "bookmarked", "completed"}:
            if type(value) is not bool:
                invalid("状态必须为 JSON 布尔值")
            result[key] = int(value)
        elif key == "title":
            result[key] = text(value, 100, 1)
        elif key in {"content", "example"}:
            result[key] = text(value, 5000, 1 if key == "content" else 0, markup=True)
        else:
            result[key] = value
    return result


class KnowledgeStore:
    def __init__(self, path, verify_transaction=None):
        self.path = Path(path)
        self.verify_transaction = verify_transaction

    @contextmanager
    def transaction(self, user_id, write=False):
        connection = None
        try:
            # mode=rw prevents requests from silently initializing an empty database.
            connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw",
                                         uri=True, timeout=5, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            migration = connection.execute(
                "SELECT checksum FROM schema_migration WHERE version=?", (VERSION,)
            ).fetchone()
            if not migration or migration[0] != CHECKSUM:
                raise KnowledgeError(503, "MAINTENANCE", "知识模块迁移尚未接入或校验失败")
            user = connection.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
            if not user or not user["active"]:
                raise KnowledgeError(401, "UNAUTHENTICATED", "请重新登录")
            if self.verify_transaction:
                self.verify_transaction(connection, user)
            yield connection, user
            connection.commit()
        except sqlite3.OperationalError as error:
            locked = "locked" in str(error).lower() or "busy" in str(error).lower()
            raise KnowledgeError(503, "DB_BUSY" if locked else "MAINTENANCE",
                                 "数据库忙，请重试" if locked else "知识模块数据库尚未就绪") from error
        finally:
            if connection:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    @staticmethod
    def access(db, user, course_id, operation=None):
        positive_id(course_id)
        course = db.execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
        member = db.execute(
            "SELECT * FROM course_member WHERE course_id=? AND user_id=? AND active=1",
            (course_id, user["id"]),
        ).fetchone()
        role = user["role"]
        valid_member = member and member["member_role"] == role and role in {"teacher", "student"}
        if not course or not (role == "admin" or valid_member):
            raise KnowledgeError(404, "NOT_FOUND", "课程不存在或不可见")
        if operation and (not valid_member or role != operation):
            raise KnowledgeError(403, "FORBIDDEN", "无此操作权限")
        return course, role

    def chapter(self, db, user, chapter_id, operation=None):
        positive_id(chapter_id)
        chapter = db.execute("SELECT * FROM chapter WHERE id=?", (chapter_id,)).fetchone()
        if not chapter:
            raise KnowledgeError(404, "NOT_FOUND", "章节不存在或不可见")
        self.access(db, user, chapter["course_id"], operation)
        return chapter

    def knowledge(self, db, user, knowledge_id, operation=None):
        positive_id(knowledge_id)
        item = db.execute(
            "SELECT k.*, c.course_id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
            "WHERE k.id=?", (knowledge_id,),
        ).fetchone()
        if not item:
            raise KnowledgeError(404, "NOT_FOUND", "知识点不存在或不可见")
        self.access(db, user, item["course_id"])
        if user["role"] == "student" and not item["published"]:
            raise KnowledgeError(404, "NOT_FOUND", "知识点不存在或不可见")
        if operation:
            self.access(db, user, item["course_id"], operation)
        return item

    @staticmethod
    def model(item):
        result = {key: item[key] for key in (
            "id", "chapter_id", "title", "content", "example", "published",
            "is_foundational", "content_revision")}
        for key in ("published", "is_foundational"):
            result[key] = bool(result[key])
        return result

    def chapters(self, user_id, course_id, page, size):
        with self.transaction(user_id) as (db, user):
            course, role = self.access(db, user, course_id)
            clause = "course_id=?"
            if role == "student":
                clause += " AND EXISTS(SELECT 1 FROM knowledge_point k WHERE k.chapter_id=chapter.id AND k.published=1)"
            total = db.execute(f"SELECT count(*) FROM chapter WHERE {clause}", (course_id,)).fetchone()[0]
            rows = db.execute(f"SELECT id,title,position FROM chapter WHERE {clause} ORDER BY position LIMIT ? OFFSET ?",
                              (course_id, size, (page-1)*size)).fetchall()
            return [dict(row) for row in rows], total, course["chapters_revision"]

    def add_chapter(self, user_id, course_id, body):
        values = payload(body, {"title"}, {"title"})
        with self.transaction(user_id, True) as (db, user):
            course, _ = self.access(db, user, course_id, "teacher")
            position = db.execute("SELECT count(*) FROM chapter WHERE course_id=?", (course_id,)).fetchone()[0]
            cursor = db.execute("INSERT INTO chapter(course_id,title,position) VALUES(?,?,?)",
                                (course_id, values["title"], position))
            db.execute("UPDATE course SET chapters_revision=chapters_revision+1 WHERE id=?", (course_id,))
            return {"id": cursor.lastrowid, "title": values["title"], "position": position,
                    "chapters_revision": course["chapters_revision"]+1}

    def rename_chapter(self, user_id, chapter_id, body):
        values = payload(body, {"title"}, {"title"})
        with self.transaction(user_id, True) as (db, user):
            chapter = self.chapter(db, user, chapter_id, "teacher")
            db.execute("UPDATE chapter SET title=? WHERE id=?", (values["title"], chapter_id))
            return {"id": chapter_id, "title": values["title"], "position": chapter["position"]}

    def reorder(self, user_id, course_id, body):
        values = payload(body, {"chapters_revision", "chapter_ids"}, {"chapters_revision", "chapter_ids"})
        revision, ids = values["chapters_revision"], values["chapter_ids"]
        if type(revision) is not int or revision < 0 or type(ids) is not list:
            invalid()
        for item in ids:
            positive_id(item)
        if len(ids) != len(set(ids)):
            invalid("章节 ID 不能重复")
        with self.transaction(user_id, True) as (db, user):
            course, _ = self.access(db, user, course_id, "teacher")
            if revision != course["chapters_revision"]:
                raise KnowledgeError(409, "REVISION_CONFLICT", "章节已变化，请刷新完整列表再排序")
            rows = db.execute("SELECT id,title,position FROM chapter WHERE course_id=?", (course_id,)).fetchall()
            if set(ids) != {row["id"] for row in rows}:
                invalid("必须提交本课程完整章节 ID 集合")
            offset = max((row["position"] for row in rows), default=-1)+1
            db.execute("UPDATE chapter SET position=position+? WHERE course_id=?", (offset, course_id))
            for position, chapter_id in enumerate(ids):
                db.execute("UPDATE chapter SET position=? WHERE id=?", (position, chapter_id))
            db.execute("UPDATE course SET chapters_revision=chapters_revision+1 WHERE id=?", (course_id,))
            titles = {row["id"]: row["title"] for row in rows}
            return {"chapters_revision": revision+1, "items": [
                {"id": item, "title": titles[item], "position": index} for index, item in enumerate(ids)]}

    def save_knowledge(self, user_id, object_id, body, create=False):
        fields = {"title", "content", "example", "published", "is_foundational"}
        values = payload(body, fields, {"title", "content", "published"} if create else ())
        with self.transaction(user_id, True) as (db, user):
            if create:
                self.chapter(db, user, object_id, "teacher")
                cursor = db.execute(
                    "INSERT INTO knowledge_point(chapter_id,title,content,example,published,is_foundational) "
                    "VALUES(?,?,?,?,?,?)", (object_id, values["title"], values["content"],
                    values.get("example", ""), values["published"], values.get("is_foundational", 0)))
                knowledge_id = cursor.lastrowid
            else:
                item = self.knowledge(db, user, object_id, "teacher")
                knowledge_id = object_id
                if any(item[key] != value for key, value in values.items()):
                    # Keys are drawn exclusively from the fixed fields allowlist.
                    assignments = ",".join(f"{key}=?" for key in values)
                    db.execute(f"UPDATE knowledge_point SET {assignments}, content_revision=content_revision+1 WHERE id=?",
                               (*values.values(), object_id))
            return self.model(self.knowledge(db, user, knowledge_id))

    def list_knowledge(self, user_id, course_id, page, size, q="", chapter_id=None):
        q = text(q, 100)
        with self.transaction(user_id) as (db, user):
            _, role = self.access(db, user, course_id)
            where, args = ["c.course_id=?"], [course_id]
            if role == "student":
                where.append("k.published=1")
            if chapter_id is not None:
                chapter = self.chapter(db, user, chapter_id)
                if chapter["course_id"] != course_id:
                    invalid("章节不属于本课程")
                where.append("k.chapter_id=?")
                args.append(chapter_id)
            if q:
                where.append("(instr(k.title,?)>0 OR instr(k.content,?)>0 OR instr(k.example,?)>0)")
                args.extend([q]*3)
            clause = " AND ".join(where)
            base = f"FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id WHERE {clause}"
            total = db.execute(f"SELECT count(*) {base}", args).fetchone()[0]
            items = db.execute(f"SELECT k.* {base} ORDER BY c.position,k.id LIMIT ? OFFSET ?",
                               (*args, size, (page-1)*size)).fetchall()
            return [self.model(item) for item in items], total

    def detail(self, user_id, knowledge_id):
        with self.transaction(user_id) as (db, user):
            result = self.model(self.knowledge(db, user, knowledge_id))
            result["is_bookmarked"] = bool(db.execute(
                "SELECT 1 FROM bookmark WHERE user_id=? AND knowledge_id=?", (user_id, knowledge_id)).fetchone())
            row = db.execute("SELECT completed,completed_at FROM learning_progress WHERE user_id=? AND knowledge_id=?",
                             (user_id, knowledge_id)).fetchone()
            result["progress"] = {"completed": bool(row and row[0]), "completed_at": row[1] if row else None}
            return result

    def personal_state(self, user_id, knowledge_id, body, kind):
        field = "bookmarked" if kind == "bookmark" else "completed"
        value = payload(body, {field}, {field})[field]
        with self.transaction(user_id, True) as (db, user):
            self.knowledge(db, user, knowledge_id, "student")
            if kind == "bookmark":
                if value:
                    db.execute("INSERT INTO bookmark(user_id,knowledge_id) VALUES(?,?) ON CONFLICT(user_id,knowledge_id) DO NOTHING",
                               (user_id, knowledge_id))
                else:
                    db.execute("DELETE FROM bookmark WHERE user_id=? AND knowledge_id=?", (user_id, knowledge_id))
                return {field: bool(value)}
            now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
            db.execute("INSERT INTO learning_progress(user_id,knowledge_id,completed,completed_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(user_id,knowledge_id) DO UPDATE SET completed=excluded.completed, "
                       "completed_at=CASE WHEN learning_progress.completed=excluded.completed THEN learning_progress.completed_at "
                       "ELSE excluded.completed_at END", (user_id, knowledge_id, value, now if value else None))
            return {field: bool(value), "updated_at": now}

    def progress_facts(self, user_id, course_id):
        """C06 input only: current published IDs and their real completion facts."""
        with self.transaction(user_id) as (db, user):
            self.access(db, user, course_id, "student")
            rows = db.execute(
                "SELECT k.id, k.content_revision, k.is_foundational, COALESCE(p.completed,0) completed "
                "FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
                "LEFT JOIN learning_progress p ON p.knowledge_id=k.id AND p.user_id=? "
                "WHERE c.course_id=? AND k.published=1 ORDER BY k.id", (user_id, course_id)).fetchall()
            return [dict(row) for row in rows]

    # ---------- SPEC-015 知识图谱 ----------

    def _course_knowledge_ids(self, db, course_id, role):
        """返回课程内可见的知识点 ID 列表（学生仅可见已发布）。"""
        where = ["c.course_id=?"]
        args = [course_id]
        if role == "student":
            where.append("k.published=1")
        clause = " AND ".join(where)
        rows = db.execute(
            f"SELECT k.id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id WHERE {clause} ORDER BY k.id",
            args).fetchall()
        return [row[0] for row in rows]

    def _prerequisite_matrix(self, db, node_ids):
        """根据先修边构建邻接矩阵，返回 (matrix, id_to_idx)。"""
        id_to_idx = {kid: idx for idx, kid in enumerate(node_ids)}
        n = len(node_ids)
        matrix = np.zeros((n, n), dtype=np.int8)
        if n == 0:
            return matrix, id_to_idx
        marks = ",".join("?" for _ in node_ids)
        edges = db.execute(
            f"SELECT source_id,target_id FROM knowledge_edge WHERE type='prerequisite' "
            f"AND source_id IN ({marks}) AND target_id IN ({marks})",
            (*node_ids, *node_ids)).fetchall()
        for edge in edges:
            s, t = id_to_idx.get(edge[0]), id_to_idx.get(edge[1])
            if s is not None and t is not None:
                matrix[s, t] = 1
        return matrix, id_to_idx

    @staticmethod
    def _reachable(matrix):
        """计算传递闭包：Warshall 算法，返回 reachable[i][j] 表示 i 可达 j。"""
        n = matrix.shape[0]
        reach = matrix.copy()
        for k in range(n):
            reach = reach | (reach[:, [k]] & reach[[k], :])
        return reach

    def add_edge(self, user_id, course_id, body):
        values = payload(body, {"source_id", "target_id", "type"}, {"source_id", "target_id", "type"})
        source_id = positive_id(values["source_id"])
        target_id = positive_id(values["target_id"])
        edge_type = values["type"]
        if edge_type not in ("prerequisite", "contains"):
            invalid("type 必须为 prerequisite 或 contains")
        if source_id == target_id:
            invalid("边两端不能指向同一知识点")
        with self.transaction(user_id, True) as (db, user):
            self.access(db, user, course_id, "teacher")
            src = self.knowledge(db, user, source_id, "teacher")
            tgt = self.knowledge(db, user, target_id, "teacher")
            if src["course_id"] != course_id or tgt["course_id"] != course_id:
                raise KnowledgeError(422, "CROSS_COURSE_EDGE", "边两端必须属于同一课程")
            if edge_type == "prerequisite":
                node_ids = self._course_knowledge_ids(db, course_id, "teacher")
                matrix, id_to_idx = self._prerequisite_matrix(db, node_ids)
                if source_id in id_to_idx and target_id in id_to_idx:
                    reach = self._reachable(matrix)
                    if reach[id_to_idx[target_id], id_to_idx[source_id]]:
                        raise KnowledgeError(422, "PREREQUISITE_CYCLE", "先修关系存在环")
            now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
            db.execute(
                "INSERT INTO knowledge_edge(source_id,target_id,type,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(source_id,target_id,type) DO NOTHING",
                (source_id, target_id, edge_type, now))
            return {"source_id": source_id, "target_id": target_id, "type": edge_type}

    def knowledge_graph(self, user_id, course_id, root_id=None):
        with self.transaction(user_id) as (db, user):
            _, role = self.access(db, user, course_id)
            node_ids = self._course_knowledge_ids(db, course_id, role)
            if not node_ids:
                return {"nodes": [], "edges": [], "prerequisite_paths": []}
            marks = ",".join("?" for _ in node_ids)
            mastery_rows = db.execute(
                f"SELECT k.id,k.title,k.is_foundational,COALESCE(p.completed,0) completed "
                f"FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
                f"LEFT JOIN learning_progress p ON p.knowledge_id=k.id AND p.user_id=? "
                f"WHERE k.id IN ({marks})", (user_id, *node_ids)).fetchall()
            nodes = [{"id": r[0], "title": r[1], "is_foundational": bool(r[2]),
                      "mastery": 1.0 if r[3] else 0.0} for r in mastery_rows]
            edge_rows = db.execute(
                f"SELECT source_id,target_id,type FROM knowledge_edge "
                f"WHERE source_id IN ({marks}) AND target_id IN ({marks})",
                (*node_ids, *node_ids)).fetchall()
            edges = [{"source": r[0], "target": r[1], "type": r[2]} for r in edge_rows]
            matrix, id_to_idx = self._prerequisite_matrix(db, node_ids)
            idx_to_id = {v: k for k, v in id_to_idx.items()}
            reach = self._reachable(matrix)
            prerequisite_paths = []
            for i in range(len(node_ids)):
                for j in range(len(node_ids)):
                    if i != j and reach[i, j]:
                        prerequisite_paths.append({"from": idx_to_id[i], "to": idx_to_id[j]})
            result = {"nodes": nodes, "edges": edges, "prerequisite_paths": prerequisite_paths}
            if root_id is not None:
                root_id = positive_id(root_id)
                if root_id not in id_to_idx:
                    raise KnowledgeError(404, "NOT_FOUND", "根知识点不存在或不可见")
                root_idx = id_to_idx[root_id]
                related = {root_id}
                for j in range(len(node_ids)):
                    if reach[root_idx, j] or reach[j, root_idx]:
                        related.add(idx_to_id[j])
                result["nodes"] = [n for n in nodes if n["id"] in related]
                result["edges"] = [e for e in edges if e["source"] in related and e["target"] in related]
                result["root_id"] = root_id
            return result
