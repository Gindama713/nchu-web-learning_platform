"""C08a actual 001/005/006 facts plus isolated snapshot validation."""

from contextlib import closing
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from backend.models.generation_input import Snapshot, freeze, normalize
from backend.shared.api import ApiError
from backend.shared.db import connect
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase

UNTIL = '2026-10-13T12:00:00.000Z'


def parameters(**values):
    return {'kind': 'homework', 'count': 1, 'total_points': 10.01, 'knowledge_ids': [1],
            'difficulty_counts': {'easy': 1, 'medium': 0, 'hard': 0}, 'seed': 42, **values}


class GenerationValidationTest(TestCase):
    def test_strict_parameters_and_defaults(self):
        for values in ({'count': True}, {'count': 101}, {'seed': True}, {'seed': 2**63},
                       {'total_points': 1.001}, {'total_points': float('nan')}, {'total_points': 1000.01},
                       {'knowledge_ids': [1, 1]}, {'knowledge_ids': [True]}, {'confidential': 1},
                       {'difficulty_counts': {'easy': 0, 'medium': 0, 'hard': 0}},
                       {'history_until': '2026-10-13T12:00:00.001Z'}, {'replay_of': 1}):
            with self.subTest(values=values), self.assertRaises(ApiError) as caught:
                normalize(parameters(**values), UNTIL)
            self.assertEqual(caught.exception.status, 400)
        p, seed, _ = normalize(parameters(kind='exam', seed=-1), UNTIL)
        self.assertTrue(p.confidential)
        self.assertEqual(seed, -1)
        self.assertEqual(p.total_hundredths, 1001)


class GenerationFactsTest(QuestionApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def freeze(self, **values):
        with closing(connect(self.path)) as db:
            result = freeze(db, self.course_id, parameters(**values), source_until=UNTIL)
            self.assertFalse(db.in_transaction)
            return result

    def submit_fact(self, path, body):
        response = self.student.post('/api/v1' + path, json=body, headers={
            'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['data']

    def test_latest_unarchived_same_course_and_all_candidates_frozen(self):
        old = self.create()
        new = self.call(self.teacher, 'PATCH', f"/questions/{old['id']}", {'stem': 'new'}).json['data']
        archived = self.create()
        third = self.create(knowledge_ids=[1, 2])
        with closing(connect(self.path)) as db:
            # Archive has no HTTP operation in 006; this state is an explicit fixture.
            db.execute('UPDATE question SET archived=1 WHERE id=?', (archived['id'],))
            other = self.call(self.admin, 'POST', '/courses', {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
            db.execute('INSERT INTO question(id,course_id) VALUES(99,?)', (other,))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(99,99,1,'boolean','cross','[]','true','easy')")
        snapshot = self.freeze()
        self.assertEqual({r.version_id for r in snapshot.candidates}, {new['version_id'], third['version_id']})
        self.assertEqual(len(snapshot.candidates), 2)  # Not just count=1 selected input.
        self.assertEqual(snapshot, self.freeze())
        with patch('backend.models.generation_input.np.random.Generator', side_effect=AssertionError('no RNG')):
            self.assertEqual(Snapshot.loads(snapshot.dumps(), snapshot.input_sha256), snapshot)
        with self.assertRaises(ApiError) as caught:
            Snapshot.loads(snapshot.dumps().replace('new', 'changed') + ' ', 'bad')
        self.assertEqual(caught.exception.code, 'SNAPSHOT_UNAVAILABLE')

    def test_confidential_excludes_identity_history_practice_and_exposed_paper(self):
        public = self.create(practice_available=True)
        self.call(self.teacher, 'PATCH', f"/questions/{public['id']}", {'practice_available': False})
        exposed = self.create()
        draft = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': 'opened', 'kind': 'homework', 'items': [{'question_version_id': exposed['version_id'], 'points': 1}]}, 201).json['data']
        self.call(self.teacher, 'POST', f"/papers/{draft['id']}/publish", {
            'start_at': '2026-10-13T10:00:00.000Z', 'end_at': '2026-10-13T13:00:00.000Z',
            'review_at': '2026-10-13T14:00:00.000Z'})
        self.call(self.teacher, 'PATCH', f"/questions/{exposed['id']}", {'stem': 'private latest'})
        private = self.create()
        self.assertEqual([r.question_id for r in self.freeze(confidential=True).candidates], [private['id']])
        self.assertEqual(len(self.freeze(confidential=False).candidates), 3)

    def test_actual_history_cutoff_omissions_short_and_partial_paper(self):
        objective = self.create(practice_available=True)
        other = self.create(practice_available=True)
        short = self.create(type='short', options=[], answer='answer')
        for value in ('A', 'B', None):
            self.submit_fact(f"/questions/{objective['id']}/practice-attempts", {
                'question_version_id': objective['version_id'], 'answer': value})
        draft = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': 'partial', 'kind': 'homework', 'items': [
                {'question_version_id': q['version_id'], 'points': 1} for q in (objective, other, short)]}, 201).json['data']
        self.call(self.teacher, 'POST', f"/papers/{draft['id']}/publish", {
            'start_at': '2026-10-13T10:00:00.000Z', 'end_at': '2026-10-13T13:00:00.000Z',
            'review_at': '2026-10-13T14:00:00.000Z'})
        data = self.submit_fact(f"/papers/{draft['id']}/attempts", {'answers': [
            {'question_version_id': objective['version_id'], 'value': 'B'},
            {'question_version_id': short['version_id'], 'value': 'response'}]})
        self.assertEqual(data['status'], 'partial')
        snapshot = self.freeze()
        by_id = {r.version_id: r for r in snapshot.candidates}
        self.assertEqual((by_id[objective['version_id']].correct_count, by_id[objective['version_id']].sample_size), (1, 3))
        for q in (other, short):
            self.assertEqual(by_id[q['version_id']].sample_size, 0)
            self.assertIsNone(by_id[q['version_id']].correct_rate)
        self.assertEqual(snapshot.candidates[0].version_id, objective['version_id'])
        earlier = self.freeze(history_until='2026-10-13T11:59:59.999Z')
        self.assertTrue(all(r.sample_size == 0 for r in earlier.candidates))
        new = self.call(self.teacher, 'PATCH', f"/questions/{objective['id']}", {'stem': 'version-specific'}).json['data']
        self.assertEqual(next(r for r in self.freeze().candidates if r.version_id == new['version_id']).sample_size, 0)
        self.assertEqual(Snapshot.loads(snapshot.dumps(), snapshot.input_sha256), snapshot)

    def test_500_bound_rejects_instead_of_truncating(self):
        with closing(connect(self.path)) as db:
            for value in range(1, 502):
                db.execute('INSERT INTO question(id,course_id) VALUES(?,?)', (value, self.course_id))
                db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                           "VALUES(?,?,1,'boolean','q','[]','true','easy')", (value, value))
            with self.assertRaises(ApiError) as caught:
                freeze(db, self.course_id, parameters(), source_until=UNTIL)
            self.assertEqual(caught.exception.status, 400)
            self.assertFalse(db.in_transaction)
            db.execute('UPDATE question SET archived=1 WHERE id=501')
            self.assertEqual(len(freeze(db, self.course_id, parameters(), source_until=UNTIL).candidates), 500)
