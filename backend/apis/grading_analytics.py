"""SPEC-010D grading branch of the shared analytics endpoint; one analysis_run per query."""

import json
import sqlite3

from backend.apis.knowledge_analytics import authorize, identifier
from backend.models import grading_analysis as model
from backend.shared.api import ApiError, date_range, result, stamp
from backend.shared.auth import require_user
from backend.shared.db import get_db, write


def create(course_id, args):
    if set(args) - {'dimension', 'from', 'to', 'student_id'} or any(
            len(args.getlist(key)) != 1 or not args[key] for key in args):
        raise ApiError(400, 'VALIDATION_ERROR', 'Invalid grading filters')
    requested = identifier(args['student_id'], 'student_id') if 'student_id' in args else None
    # Prime the session before BEGIN: the shared authenticator refreshes its expiry once.
    require_user()
    start, end = date_range()
    if start == end:
        raise ApiError(400, 'VALIDATION_ERROR', 'Empty date range')
    db = get_db()
    try:
        db.execute('BEGIN')
        try:
            user, role, subject = authorize(course_id, requested)
            cutoff = stamp()
            snapshot = model.extract(db, course_id, start, end, cutoff, subject)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        try:
            data = model.calculate(snapshot, start, end, cutoff)
        except Exception as exc:
            raise ApiError(503, 'ANALYSIS_UNAVAILABLE', 'Grading calculation failed; retry') from exc
        data['generated_at'] = stamp()
        scope = 'class' if subject is None else 'self' if role == 'student' else 'student'
        parameters = {'from': start, 'to': end, 'student_id': subject,
                      'selected_version_ids': data['metrics']['selected_version_ids']}
        data['filters'] = parameters
        with write() as db:
            authorize(course_id, requested)
            cursor = db.execute(
                'INSERT INTO analysis_run(course_id,creator_id,scope,subject_student_id,kind,algorithm_version,'
                'parameters_json,source_until,generated_at,sample_size,result_json,input_snapshot_json,created_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (course_id, user['id'], scope, subject, 'grading', model.VERSION, json.dumps(parameters),
                 cutoff, data['generated_at'], data['sample_size'], '{}',
                 json.dumps(snapshot, ensure_ascii=False, allow_nan=False), data['generated_at']))
            data['analysis_run_id'] = cursor.lastrowid
            db.execute('UPDATE analysis_run SET result_json=? WHERE id=?',
                       (json.dumps(data, ensure_ascii=False, allow_nan=False), cursor.lastrowid))
    except ApiError:
        raise
    except (sqlite3.Error, ValueError, ArithmeticError) as exc:
        raise ApiError(503, 'ANALYSIS_UNAVAILABLE', 'Grading analysis could not be saved; retry') from exc
    return result(data)
