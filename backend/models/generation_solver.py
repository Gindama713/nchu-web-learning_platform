"""C08 bounded deterministic include-first backtracking and integer allocation."""

from dataclasses import dataclass

from backend.models.generation_input import DIFFICULTIES, MAX_NODES, validate_snapshot
from backend.shared.api import ApiError


@dataclass(frozen=True)
class Solution:
    selected_version_ids: tuple[int, ...]
    points_hundredths: tuple[int, ...]
    coverage: tuple[int, ...]
    search_nodes: int


def allocate(total_hundredths, count):
    if type(total_hundredths) is not int or type(count) is not int or not 1 <= count <= 100 or total_hundredths < count:
        raise ApiError(422, 'INFEASIBLE_CONSTRAINTS', '每题至少须配一个百分之一分')
    base, remainder = divmod(total_hundredths, count)
    return tuple(base + (position < remainder) for position in range(count))


def solve(snapshot, *, node_limit=MAX_NODES):
    """No database, RNG or wall-clock deadline: the frozen inputs alone determine output.

    Count a node on entry (including root/pruned/terminal states). An exhausted
    tree at exactly the budget is 422; only a required extra visit is 503.
    node_limit is an internal test hook; production cannot exceed MAX_NODES.
    """
    validate_snapshot(snapshot)
    if type(node_limit) is not int or not 1 <= node_limit <= MAX_NODES:
        raise ValueError('node_limit must be between 1 and 100000')
    parameters = snapshot.parameters
    rows = snapshot.candidates
    quotas = list(parameters.difficulty_counts)
    required = frozenset(parameters.knowledge_ids)
    selected, identities = [], set()
    visited = 0
    difficulty = [DIFFICULTIES.index(row.difficulty) for row in rows]
    tags = [frozenset(row.knowledge_ids) for row in rows]

    def visit(position, covered):
        nonlocal visited
        if visited == node_limit:
            raise ApiError(503, 'SEARCH_LIMIT', '搜索预算耗尽，请缩小约束', {'search_nodes': visited})
        visited += 1
        remaining = parameters.count - len(selected)
        if remaining == 0:
            return required <= covered
        # Per-difficulty distinct identities bound the remaining quota. Only
        # eligible difficulties may supply missing coverage; multi-tag overlap
        # is a union, not an invented one-tag-per-question requirement.
        available = [set() for _ in DIFFICULTIES]
        possible_coverage = set(covered)
        all_identities = set()
        for i in range(position, len(rows)):
            row = rows[i]
            d = difficulty[i]
            if row.question_id not in identities and quotas[d] > 0:
                available[d].add(row.question_id)
                all_identities.add(row.question_id)
                possible_coverage.update(tags[i])
        if (len(all_identities) < remaining or any(len(available[d]) < quotas[d] for d in range(3))
                or not required <= possible_coverage):
            return False
        row = rows[position]
        d = difficulty[position]
        if quotas[d] and row.question_id not in identities:
            selected.append(position)
            identities.add(row.question_id)
            quotas[d] -= 1
            if visit(position + 1, covered | tags[position]):
                return True
            quotas[d] += 1
            identities.remove(row.question_id)
            selected.pop()
        return visit(position + 1, covered)

    if not visit(0, frozenset()):
        raise ApiError(422, 'INFEASIBLE_CONSTRAINTS', '题量、难度或知识覆盖无可行解', {'search_nodes': visited})
    coverage = tuple(sorted(set().union(*(tags[i] for i in selected))))
    return Solution(tuple(rows[i].version_id for i in selected),
                    allocate(parameters.total_hundredths, parameters.count), coverage, visited)


def validate_solution(snapshot, result):
    """Storage guard: a caller cannot persist a partial or nonconforming paper."""
    validate_snapshot(snapshot)
    rows = {row.version_id: (i, row) for i, row in enumerate(snapshot.candidates)}
    try:
        positions = [rows[v][0] for v in result.selected_version_ids]
        selected = [rows[v][1] for v in result.selected_version_ids]
        coverage = tuple(sorted({k for row in selected for k in row.knowledge_ids}))
        p = snapshot.parameters
        valid = (len(selected) == p.count and positions == sorted(set(positions))
                 and len({row.question_id for row in selected}) == p.count
                 and tuple(sum(row.difficulty == d for row in selected) for d in DIFFICULTIES) == p.difficulty_counts
                 and set(p.knowledge_ids) <= set(coverage) and result.coverage == coverage
                 and result.points_hundredths == allocate(p.total_hundredths, p.count)
                 and type(result.search_nodes) is int and 1 <= result.search_nodes <= MAX_NODES)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ApiError(422, 'INFEASIBLE_CONSTRAINTS', '选题结果不符合冻结约束') from exc
    if not valid:
        raise ApiError(422, 'INFEASIBLE_CONSTRAINTS', '选题结果不符合冻结约束')
