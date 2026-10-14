"""010B knowledge branch of the shared analytics endpoint; no parallel snapshot table."""

import json
import sqlite3

from backend.models import knowledge_analysis as model
from backend.shared.api import ApiError, date_range, positive_int, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write


def identifier(value, field):
    number = positive_int(value, field)
    if number > 2**63 - 1:
        raise ApiError(400, 'VALIDATION_ERROR', f'{field} is too large')
    return number


def authorize(course_id, requested):
    user = require_user()
    _, role = course_access(course_id)
    if role == 'student' and requested not in (None, user['id']):
        raise ApiError(403, 'FORBIDDEN', 'Only own analytics are visible')
    if requested is not None and role == 'teacher' and not get_db().execute(
        'SELECT 1 FROM course_member m JOIN user u ON u.id=m.user_id '
        "WHERE m.course_id=? AND m.user_id=? AND m.member_role='student' AND m.active=1 "
        "AND u.active=1 AND u.role='student'", (course_id, requested)).fetchone():
        raise ApiError(404, 'NOT_FOUND', 'Student not found')
    return user, role, user['id'] if role == 'student' else requested


def create(course_id, args):
    if set(args) - {'dimension', 'from', 'to', 'student_id'} or any(
            len(args.getlist(key)) != 1 or not args[key] for key in args):
        raise ApiError(400, 'VALIDATION_ERROR', 'Invalid knowledge filters')
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
            raise ApiError(503, 'ANALYSIS_UNAVAILABLE', 'Knowledge calculation failed; retry') from exc
        data['generated_at'] = stamp()
        scope = 'class' if subject is None else 'self' if role == 'student' else 'student'
        parameters = {'from': start, 'to': end, 'student_id': subject,
                      'knowledge_ids': [row['id'] for row in snapshot['knowledge']]}
        with write() as db:
            authorize(course_id, requested)
            cursor = db.execute(
                'INSERT INTO analysis_run(course_id,creator_id,scope,subject_student_id,kind,algorithm_version,'
                'parameters_json,source_until,generated_at,sample_size,result_json,input_snapshot_json,created_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (course_id, user['id'], scope, subject, 'knowledge', model.VERSION,
                 json.dumps(parameters), cutoff, data['generated_at'], data['sample_size'], '{}',
                 json.dumps(snapshot, ensure_ascii=False, allow_nan=False), data['generated_at']))
            data['analysis_run_id'] = cursor.lastrowid
            db.execute('UPDATE analysis_run SET result_json=? WHERE id=?',
                       (json.dumps(data, ensure_ascii=False, allow_nan=False), cursor.lastrowid))
    except ApiError:
        raise
    except (sqlite3.Error, ValueError, ArithmeticError) as exc:
        raise ApiError(503, 'ANALYSIS_UNAVAILABLE', 'Knowledge analysis could not be saved; retry') from exc
    return result(data)
