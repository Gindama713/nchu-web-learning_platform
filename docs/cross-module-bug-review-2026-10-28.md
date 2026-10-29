# 跨模块接口 Bug 检查报告

**检查日期**: 2026-10-28
**负责人**: 石佰合 (shibaihe, 24201737)
**检查范围**: 石佰合模块与其他成员模块的接口重叠区域
**涉及模块**: SPEC-003 资源、SPEC-009 实验、SPEC-018 评测、SPEC-010D 统计 ↔ SPEC-004 备课(罗浩铭)、SPEC-006 习题(黄俊诚)、SPEC-008 随堂测(黄俊诚)、SPEC-017 连线(罗浩铭)、SPEC-010A/C 统计(姜苏豪/罗浩铭)

---

## 接口重叠关系图

```
SPEC-003 资源 (石佰合)
  ├──→ SPEC-006 习题 (黄俊诚)    题库导入 import_questions → save_version
  ├──→ SPEC-004 备课 (罗浩铭)    update_resource 查询 preparation_resource
  └──→ SPEC-010D 统计 (石佰合)   resource_event → resource_analysis

SPEC-009 实验 (石佰合)
  ├──→ SPEC-017 连线 (罗浩铭)    wiring_attempt 依赖 experiment_version
  ├──→ SPEC-018 评测 (石佰合)    grading 依赖 experiment_version publish
  └──→ SPEC-007 演示 (罗浩铭)    demo 引用实验

SPEC-018 评测 (石佰合)
  ├──→ SPEC-009 实验 (石佰合)    publish_version 创建 experiment_grading
  └──→ SPEC-010D 统计 (石佰合)   grading_run → grading_analysis

SPEC-010D 统计 (石佰合)
  ├──→ SPEC-010A/C (姜苏豪/罗浩铭) 共享 analysis_run 表、analytics.py 分发
  ├──→ SPEC-010B (黄俊诚)         共享 authorize/identifier 函数
  └──→ statistics_csv.py          共享 CSV 导出
```

---

## P0 — 连线模块完全缺失实验版本访问控制

**接口**: SPEC-009 (experiment_version) → SPEC-017 (wiring_attempt)
**文件**: `backend/apis/wiring.py` 第 69-98 行 (`create_attempt`)
**对比**: `backend/apis/grading.py` 第 459-541 行 (`create_submission`)

### 问题描述

`wiring.py create_attempt` 对 `experiment_version` 的访问控制严重缺失，与 `grading.py create_submission` 的严格检查形成鲜明对比：

| 检查项 | grading.py (SPEC-018) | wiring.py (SPEC-017) |
|--------|----------------------|---------------------|
| 版本状态 = published | ✅ 第473行 | ❌ 缺失 |
| submission_modes 含目标模式 | ✅ 第471行 | ❌ 缺失 |
| 提交窗口 (start_at/end_at) | ✅ 第477-479行 | ❌ 缺失 |
| 冻结名单 (experiment_participant) | ✅ 第480-484行 | ❌ 缺失 |

```python
# wiring.py create_attempt — 当前代码
row = _row(db, "experiment_version", version_id)
if not row:
    raise ApiError(404, "NOT_FOUND", "Experiment version not found")
exp = _row(db, "experiment", row["experiment_id"])
course_access(exp["course_id"])
if user["role"] != "student":
    raise ApiError(403, "FORBIDDEN", "Only students can create wiring attempts")
# 直接创建 attempt，未检查上述任何条件
```

### 影响

学生可以：
1. 对 **draft 版本** 创建连线尝试（绕过发布流程）
2. 对 **circuit-only 版本**（如 EXP-04）创建连线尝试（模式不匹配）
3. 在提交窗口外（开始前/结束后）创建连线尝试
4. 不在冻结名单内也能创建连线尝试（绕过选课约束）

这直接破坏了 SPEC-009 实验模块的数据完整性，且影响 SPEC-010C 连线统计的分母（完成率计算会包含不该有的提交）。

### 修复方向

在 `wiring.py create_attempt` 中补齐与 `grading.py` 一致的检查：

```python
row = _row(db, "experiment_version", version_id)
if not row:
    raise ApiError(404, "NOT_FOUND", "Experiment version not found")
exp = _row(db, "experiment", row["experiment_id"])
course_access(exp["course_id"])
if user["role"] != "student":
    raise ApiError(403, "FORBIDDEN", "Only students can create wiring attempts")

# 补充以下检查
from backend.apis.experiments import load_json
modes = load_json(row["submission_modes_json"], "submission_modes")
if "wiring" not in modes:
    raise ApiError(409, "STATE_CONFLICT", "This version does not accept wiring submissions")
if row["status"] != "published":
    raise ApiError(404, "NOT_FOUND", "Experiment version not found")
from backend.shared.api import now, stamp
current = now()
if not (row["start_at"] and row["end_at"]
        and row["start_at"] <= stamp(current) < row["end_at"]):
    raise ApiError(409, "WINDOW_CLOSED", "Submission window is closed")
allowed = db.execute(
    "SELECT 1 FROM experiment_participant WHERE experiment_version_id=? AND student_id=?",
    (version_id, user["id"])).fetchone()
if not allowed:
    raise ApiError(403, "FORBIDDEN", "Not on the frozen participant list")
```

---

## P1 — 资源模块查询备课表未做存在性检查

**接口**: SPEC-003 (resources) → SPEC-004 (preparation)
**文件**: `backend/apis/resources.py` 第 334-339 行 (`update_resource`)
**对比**: `backend/apis/preparations.py` 第 126-128 行 (`_resource_table_exists`)

### 问题描述

`resources.py update_resource` 在将资源从 `students` 改为 `teacher_only` 时，直接查询备课模块的表：

```python
# resources.py 第334-339行 — 直接查询，未检查表是否存在
refs = db.execute(
    "SELECT pr.preparation_id FROM preparation_resource pr "
    "JOIN preparation p ON p.id=pr.preparation_id "
    "WHERE pr.resource_version_id IN "
    "(SELECT id FROM resource_version WHERE resource_id=?) "
    "AND p.status='published'", (resource_id,)).fetchall()
```

如果 SPEC-004 备课模块尚未安装（`preparation_resource` / `preparation` 表不存在），此查询抛出 `sqlite3.OperationalError: no such table: preparation_resource`，导致 500 错误。

而备课模块对资源表有对等的存在性检查：

```python
# preparations.py 第126-128行 — 优雅降级
def _resource_table_exists(db):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='resource_version'"
    ).fetchone() is not None

# 使用时
if not _resource_table_exists(db):
    raise ApiError(503, "RESOURCE_MODULE_NOT_READY", "Resource module (SPEC-003) is not available yet")
```

### 影响

部署顺序不确定时（SPEC-003 先于 SPEC-004 安装），教师修改资源可见性会触发 500 错误，而非优雅降级。

### 修复方向

```python
# resources.py update_resource 中，查询前先检查表是否存在
def _preparation_tables_exist(db):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='preparation_resource'"
    ).fetchone() is not None

# 在 update_resource 中
if visibility == "teacher_only" and _preparation_tables_exist(db):
    refs = db.execute(...)
    if refs:
        raise ApiError(409, "RESOURCE_IN_USE", ...)
```

---

## P1 — 题库导入的前置表检查不完整

**接口**: SPEC-003 (resources) → SPEC-006 (question) / SPEC-008 (paper)
**文件**: `backend/apis/resources.py` 第 371 行 (`import_questions`)
**依赖**: `backend/models/question.py` → `check_knowledge` / `save_version` / `ensure_practice_unreserved`

### 问题描述

`import_questions` 的前置表检查只覆盖了直接依赖：

```python
# resources.py 第371行
require_tables(db, {"question", "question_version", "question_knowledge",
                    "idempotency_record"}, "题库模块未接入，暂不能导入")
```

但 `save_version` 内部还会调用：
- `check_knowledge` → 需要 `chapter`, `knowledge_point` 表（SPEC-005 知识模块）
- `ensure_practice_unreserved`（当 `practice_available=True`）→ 需要 `paper`, `paper_item` 表（SPEC-008 随堂测模块）

如果这些表不存在，导入在创建第一题时就会失败，错误信息指向知识/试卷模块而非题库导入本身。

### 影响

- 知识模块未安装时：所有包含知识点标签的题目导入失败
- 试卷模块未安装时：包含 `practice_available: true` 的题目导入失败
- 题库已校验通过的题目在创建阶段失败，事务回滚，但错误消息误导用户

### 修复方向

```python
# 扩展前置检查
require_tables(db, {"question", "question_version", "question_knowledge",
                    "idempotency_record", "chapter", "knowledge_point"},
               "题库或知识模块未接入，暂不能导入")
# 如果任何题目可能 practice_available=True，还需检查 paper 表
if any(item.get("practice_available") for item in items if isinstance(item, dict)):
    require_tables(db, {"paper", "paper_item"}, "随堂测模块未接入，不能导入公开练习题目")
```

---

## P1 — 资源模块缺少 IntegrityError 处理器

**接口**: SPEC-003 (resources) `resource_event` 表 UNIQUE 约束
**文件**: `backend/apis/resources.py`（整个蓝图缺少 errorhandler）
**对比**: `backend/apis/preparations.py` 第 357-359 行

### 问题描述

`resource_event` 表有 `UNIQUE(user_id, event_id)` 约束。`get_content` 的 check-then-insert 模式存在竞态窗口：

```python
# resources.py 第293-307行
existing = db.execute("SELECT ... WHERE user_id=? AND event_id=?", ...).fetchone()
if existing:
    ...  # 冲突检查
else:
    with write() as wdb:
        wdb.execute("INSERT INTO resource_event ...")  # 可能触发 IntegrityError
```

两个并发请求使用相同 `(user_id, event_id)` 但不同 `intent` 时，第二个 INSERT 触发 `sqlite3.IntegrityError`，返回 500。

备课模块有优雅处理：

```python
# preparations.py 第357-359行
@bp.errorhandler(sqlite3.IntegrityError)
def integrity_error(_error):
    return result({}, 409)
```

资源模块没有对等的 errorhandler。

### 修复方向

```python
# resources.py 蓝图级添加
import sqlite3

@bp.errorhandler(sqlite3.IntegrityError)
def integrity_error(_error):
    return result({}, 409)
```

或在 INSERT 处捕获并重新检查：

```python
try:
    with write() as wdb:
        wdb.execute("INSERT INTO resource_event ...")
except sqlite3.IntegrityError:
    existing = db.execute("SELECT ... WHERE user_id=? AND event_id=?", ...).fetchone()
    if existing and (existing["event_type"] != intent or existing["resource_version_id"] != version_id):
        raise ApiError(409, "EVENT_CONFLICT", "event_id already used with different intent or version")
    # 同 intent+version 的并发重放，幂等返回
```

---

## P2 — preparation_resource 外键约束缺失

**接口**: SPEC-004 (preparation) → SPEC-003 (resource_version)
**文件**: `backend/migrations/004_preparation.sql` 第 27-31 行

### 问题描述

```sql
CREATE TABLE preparation_resource (
    preparation_id INTEGER NOT NULL REFERENCES preparation(id),
    resource_version_id INTEGER NOT NULL,  -- 无 REFERENCES resource_version(id)
    PRIMARY KEY(preparation_id, resource_version_id)
);
```

迁移文件注释明确说明："resource_version_id 暂不加外键，待 SPEC-003 资源模块落地后补齐约束"。但 SPEC-003 已实现，外键从未补齐。

### 影响

- 数据库层面不阻止引用已删除的 `resource_version` 行
- 应用层有 `_assert_same_course` 做运行时校验，但直接操作数据库可插入脏数据
- `resources.py update_resource` 查询 `preparation_resource` 时可能引用不存在的版本

### 修复方向

新增迁移补齐外键：

```sql
-- migration: 004b_preparation_fk.sql
-- SQLite 不支持 ALTER TABLE ADD FOREIGN KEY，需重建表
-- 或在应用层确保一致性（当前方案）
```

由于 SQLite 不支持直接添加外键约束到已有表，实际需要重建表。短期可保持应用层校验，长期在全新部署时补齐。

---

## P2 — 连线模块未使用 experiments.version_row

**接口**: SPEC-017 (wiring) → SPEC-009 (experiments)
**文件**: `backend/apis/wiring.py` 第 32-33 行

### 问题描述

```python
# wiring.py 使用自己的 _row 函数
def _row(db, table, rid):
    return db.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()

# 而非 experiments.py 的 version_row（已 JOIN experiment + judge_profile）
def version_row(db, version_id):
    row = db.execute("SELECT " + VERSION_COLUMNS + VERSION_SOURCE + " WHERE v.id=?", ...)
```

`wiring.py` 在 `create_attempt`、`save_attempt`、`validate_attempt`、`submit_attempt` 中都使用 `_row(db, "experiment_version", ...)` 加载版本，然后单独查询 experiment 获取 course_id。而 `grading.py` 直接使用 `version_row` 一次性获取所有需要的信息。

### 影响

- 每次连线操作多一次数据库查询（性能浪费）
- 无法获取 `judge_profile_id`（虽然连线不需要，但不一致）
- 鼓励了 P0 问题中的检查缺失（因为 `_row` 返回的是原始 experiment_version 行，没有 experiment 的 course_id，需要额外查询）

### 修复方向

统一使用 `from backend.apis.experiments import version_row` 替代 `_row(db, "experiment_version", ...)`。

---

## P2 — 统计模块鉴权严格度不一致

**接口**: SPEC-010A (attendance) vs SPEC-010B/D (knowledge/grading/resources)
**文件**: `backend/apis/analytics.py` 第 328-331 行 vs `backend/apis/knowledge_analytics.py` 第 24-29 行

### 问题描述

考勤统计的鉴权查询较简单：

```python
# analytics.py (attendance) — 简单查询
if requested and role == "teacher" and not get_db().execute(
    "SELECT 1 FROM course_member WHERE course_id=? AND user_id=? AND member_role='student'",
    (course_id, requested)).fetchone():
    raise ApiError(404, "NOT_FOUND", "Student not found")
```

而 grading/resources 统计使用 `knowledge_analytics.authorize`，查询更严格：

```python
# knowledge_analytics.authorize — JOIN user 表，检查 active 和 role
if requested is not None and role == 'teacher' and not get_db().execute(
    'SELECT 1 FROM course_member m JOIN user u ON u.id=m.user_id '
    "WHERE m.course_id=? AND m.user_id=? AND m.member_role='student' AND m.active=1 "
    "AND u.active=1 AND u.role='student'", (course_id, requested)).fetchone():
    raise ApiError(404, 'NOT_FOUND', 'Student not found')
```

### 影响

- 考勤统计可能接受已停用 (`active=0`) 或角色已变更的成员作为查询对象
- 不同统计维度对同一学生的存在性判断不一致
- 影响较小（仅在学生被停用后立即查询的场景）

### 修复方向

统一使用 `knowledge_analytics.authorize` 进行学生存在性校验，或将鉴权逻辑提取到 `shared/auth.py` 作为公共函数。

---

## P2 — 题库导入中 check_knowledge 被重复调用

**接口**: SPEC-003 (resources) → SPEC-006 (question)
**文件**: `backend/apis/resources.py` 第 403 行 + `backend/models/question.py` 第 177 行

### 问题描述

```python
# resources.py import_questions — 校验阶段调用一次
values = validate_question(item)
check_knowledge(db, resource["course_id"], values["knowledge_ids"])  # 第一次

# 然后 save_version 内部又调用一次
question_version_ids = [save_version(db, resource["course_id"], values)["version_id"]
                        for values in validated]
# save_version 内部:
def save_version(db, course_id, values, current=None):
    check_knowledge(db, course_id, values['knowledge_ids'])  # 第二次（相同查询）
```

### 影响

每个知识点 ID 多一次数据库查询（N 题目 × M 知识点 的额外查询）。对 500 题的导入，可能多上千次查询。功能无影响，纯属性能浪费。

### 修复方向

`import_questions` 的校验阶段调用 `validate_question` 但不调用 `check_knowledge`，让 `save_version` 统一负责知识归属校验。

---

## 跨模块数据库一致性检查结果

### 已确认一致

| 表 | 创建迁移 | 引用方 | 一致性 |
|----|---------|--------|--------|
| `experiment_version` | 009 (石佰合) | 017 wiring, 018 grading | ✅ 外键一致 |
| `experiment_participant` | 009 (石佰合) | 018 grading (检查) | ✅ 字段一致 |
| `judge_profile` | 009 建表 + 018 加列 | 009 version_row, 018 put_judge_profile | ✅ ALTER TABLE 依赖 009 先执行 |
| `experiment_grading` | 018 (石佰合) | 009 publish_version (INSERT), 018 set_active_suite | ✅ 主键 = experiment_version_id |
| `test_suite` / `grading_run` | 018 (石佰合) | 010D grading_analysis (SELECT) | ✅ 字段名一致 |
| `resource` / `resource_version` | 003 (石佰合) | 004 preparation (引用), 010D resource_analysis | ✅ 字段一致 |
| `resource_event` | 003 (石佰合) | 003 get_content (INSERT), 010D resource_analysis (SELECT) | ✅ 字段一致 |
| `analysis_run` | 010A (姜苏豪) | 010B/D (黄俊诚/石佰合) 共享写入 | ✅ 13 列结构一致 |

### 存在问题

| 表 | 问题 | 严重级别 |
|----|------|---------|
| `preparation_resource` | `resource_version_id` 无外键约束 | P2 |
| `wiring_attempt` | 创建时不检查 `experiment_participant` 成员关系 | P0 |

---

## 总结

| 严重级别 | 数量 | 核心问题 |
|---------|------|---------|
| P0 | 1 | 连线模块完全缺失实验版本访问控制 |
| P1 | 3 | 资源查询备课表未检查存在性、题库导入前置检查不完整、资源缺 IntegrityError 处理 |
| P2 | 4 | preparation_resource 无外键、连线未用 version_row、统计鉴权不一致、check_knowledge 重复调用 |

**最关键发现**: SPEC-017 连线模块 (`wiring.py`) 的 `create_attempt` 没有做任何与 SPEC-009 实验版本相关的访问控制（版本状态、提交模式、时间窗口、参与者名单），而同类的 SPEC-018 评测模块 (`grading.py`) 的 `create_submission` 做了完整的 5 项检查。这是跨模块安全一致性的最大缺口，直接影响实验数据完整性。
