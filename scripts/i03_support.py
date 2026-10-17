"""Small evidence helpers for the bounded I-03 seams, never business fixtures."""

import json
from contextlib import closing
from pathlib import Path

from backend.shared.db import connect

ROOT = Path(__file__).resolve().parents[1]
SECRET_FIELDS = {'password', 'password_hash', 'csrf_token', 'token', 'session_id', 'secret_key'}


def redact(value):
    if isinstance(value, dict):
        return {key: '[redacted]' if key.lower() in SECRET_FIELDS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def facts(path):
    tables = ('course', 'course_member', 'chapter', 'knowledge_point', 'knowledge_progress',
              'question', 'question_version', 'question_knowledge', 'paper', 'paper_item',
              'paper_participant', 'attempt', 'answer', 'wrong_question', 'analysis_run',
              'qa_index', 'qa_query', 'demo_session', 'audit_event')
    with closing(connect(path)) as db:
        present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {table: [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                  for table in tables if table in present}
        result['foreign_key_check'] = [list(r) for r in db.execute('PRAGMA foreign_key_check')]
        result['integrity_check'] = db.execute('PRAGMA integrity_check').fetchone()[0]
        return result


def record(records, actor, method, path, payload, status, response, transport='handler'):
    records.append(redact({'actor': actor, 'transport': transport, 'method': method, 'path': path,
                           'request': payload, 'status': status, 'response': response}))
