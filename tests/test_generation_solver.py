"""C08 deterministic solver compared with an independent exhaustive oracle."""

import itertools
import random
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from backend.models.generation_input import Candidate, Constraints, Snapshot
from backend.models.generation_solver import allocate, solve, validate_solution
from backend.shared.api import ApiError

UNTIL = '2026-10-13T12:00:00.000Z'


def candidate(version_id, *, question_id=None, tags=(1,), difficulty='easy', c=0, n=0, key=None):
    return Candidate(question_id or version_id, version_id, 'single', difficulty, tuple(sorted(tags)), c, n,
                     key or format(version_id, '016x'))


def snapshot(rows, *, count=1, quotas=None, tags=(1,), total=1001):
    return Snapshot(1, 42, UNTIL, Constraints('homework', count, total, tuple(sorted(tags)),
                    quotas or (count, 0, 0), False, UNTIL), tuple(sorted(rows, key=Candidate.order_key)))


def exhaustive(value):
    p = value.parameters
    for combination in itertools.combinations(value.candidates, p.count):
        if (len({r.question_id for r in combination}) == p.count
                and tuple(sum(r.difficulty == d for r in combination) for d in ('easy', 'medium', 'hard')) == p.difficulty_counts
                and set(p.knowledge_ids) <= {tag for r in combination for tag in r.knowledge_ids}):
            return tuple(r.version_id for r in combination)
    return None


class GenerationSolverTest(TestCase):
    def test_backtracking_first_valid_solution_and_multitag_coverage(self):
        value = snapshot([candidate(1, tags=(1,)), candidate(2, tags=(1, 2)), candidate(3, tags=(3,))],
                         count=2, tags=(1, 2, 3))
        result = solve(value)
        self.assertEqual(result.selected_version_ids, (2, 3))
        self.assertEqual(result.coverage, (1, 2, 3))
        self.assertEqual(result.points_hundredths, (501, 500))
        validate_solution(value, result)
        with self.assertRaises(ApiError):
            validate_solution(value, replace(result, points_hundredths=(500, 500)))

    def test_never_select_two_versions_of_one_question(self):
        value = snapshot([candidate(1), candidate(2, question_id=1, tags=(2,)), candidate(3, tags=(2,))],
                         count=2, tags=(1, 2))
        self.assertEqual(solve(value).selected_version_ids, (1, 3))
        with self.assertRaises(ApiError) as caught:
            solve(replace(value, candidates=value.candidates[:2]))
        self.assertEqual((caught.exception.status, caught.exception.code), (422, 'INFEASIBLE_CONSTRAINTS'))

    def test_exact_rate_order_then_frozen_key_then_version_and_null_last(self):
        value = snapshot([candidate(5), candidate(1, c=1, n=3, key='0000000000000002'),
                          candidate(2, c=2, n=6, key='0000000000000001'),
                          candidate(3, c=1, n=4), candidate(4, c=1, n=3, key='0000000000000001')], count=5)
        self.assertEqual(solve(value).selected_version_ids, (3, 2, 4, 1, 5))

    def test_quota_and_coverage_pruning_proves_infeasibility_at_root(self):
        for value in (snapshot([candidate(1)], count=2),
                      snapshot([candidate(1)], quotas=(0, 1, 0)),
                      snapshot([candidate(1)], tags=(2,)),
                      snapshot([candidate(1), candidate(2, difficulty='medium', tags=(2,))], tags=(2,))):
            with self.subTest(value=value), self.assertRaises(ApiError) as caught:
                solve(value, node_limit=1)
            self.assertEqual((caught.exception.status, caught.exception.code, caught.exception.details['search_nodes']),
                             (422, 'INFEASIBLE_CONSTRAINTS', 1))

    def test_budget_boundary_is_not_reported_as_infeasible(self):
        value = snapshot([candidate(1)])
        with self.assertRaises(ApiError) as caught:
            solve(value, node_limit=1)
        self.assertEqual((caught.exception.status, caught.exception.code, caught.exception.details['search_nodes']), (503, 'SEARCH_LIMIT', 1))
        self.assertEqual(solve(value, node_limit=2).search_nodes, 2)
        for invalid in (0, True, 100001):
            with self.assertRaises(ValueError):
                solve(value, node_limit=invalid)

    def test_real_100000_node_budget(self):
        # 11 disjoint tags need at least 11 questions, but request is 10.
        # Quota/union bounds alone cannot prove it until exploring combinations.
        value = snapshot([candidate(i + 1, tags=(i % 11 + 1,)) for i in range(33)],
                         count=10, tags=tuple(range(1, 12)))
        with self.assertRaises(ApiError) as caught:
            solve(value)
        self.assertEqual((caught.exception.status, caught.exception.code, caught.exception.details['search_nodes']),
                         (503, 'SEARCH_LIMIT', 100000))

    def test_integer_remainders_and_100_question_boundary(self):
        self.assertEqual(allocate(1001, 3), (334, 334, 333))
        for count in (1, 3, 7, 100):
            for total in (100, 1001, 100000):
                points = allocate(total, count)
                self.assertEqual(sum(points), total)
                self.assertGreaterEqual(min(points), 1)
                self.assertLessEqual(max(points) - min(points), 1)
        value = snapshot([candidate(i + 1) for i in range(500)], count=100, total=100)
        result = solve(value)
        self.assertEqual(result.selected_version_ids, tuple(range(1, 101)))
        self.assertEqual(result.points_hundredths, (1,) * 100)
        with self.assertRaises(ApiError):
            allocate(2, 3)

    def test_200_small_cases_match_independent_exhaustive_search(self):
        rng = random.Random(13)
        for case in range(200):
            rows = [candidate(i + 1, question_id=rng.randint(1, 6),
                              tags=tuple(k for k in (1, 2, 3) if rng.randrange(2)),
                              difficulty=rng.choice(('easy', 'medium', 'hard')),
                              c=rng.randrange(3), n=3) for i in range(rng.randrange(1, 9))]
            count = rng.randrange(1, 5)
            easy = rng.randrange(count + 1)
            medium = rng.randrange(count - easy + 1)
            value = snapshot(rows, count=count, quotas=(easy, medium, count - easy - medium),
                             tags=tuple(k for k in (1, 2, 3) if rng.randrange(2)))
            expected = exhaustive(value)
            with self.subTest(case=case):
                if expected is None:
                    with self.assertRaises(ApiError) as caught:
                        solve(value)
                    self.assertEqual(caught.exception.code, 'INFEASIBLE_CONSTRAINTS')
                else:
                    self.assertEqual(solve(value).selected_version_ids, expected)

    def test_serialized_recalculation_without_numpy_rng(self):
        value = snapshot([candidate(1), candidate(2), candidate(3)], count=2)
        original = solve(value)
        with (patch('backend.models.generation_input.np.random.Generator', side_effect=AssertionError('no RNG')),
              patch('backend.models.generation_input.secrets.randbits', side_effect=AssertionError('no seed RNG'))):
            restored = Snapshot.loads(value.dumps(), value.input_sha256)
            self.assertEqual(solve(restored), original)
