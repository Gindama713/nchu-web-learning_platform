# 石佰合模块 Bug 检查报告

**检查日期**: 2026-10-26
**负责人**: 石佰合 (shibaihe, 24201737)
**检查范围**: SPEC-003 教学资源、SPEC-009 实验辅助、SPEC-018 电路在线评测、SPEC-010D 评测统计
**测试结果**: 78 个单元测试全部通过（不覆盖以下边界场景）

---

## 严重级别说明

| 级别 | 含义 |
|------|------|
| P0 | 生产环境会崩溃或产生错误结果 |
| P1 | 特定条件下崩溃或限制失效 |
| P2 | 防御性缺陷或代码异味 |

---

## P0 — 教师配置的资源限制完全失效

**文件**: `backend/engines/grading.py` 第 103 行
**函数**: `run_in_sandbox`

### 问题描述

`run_in_sandbox` 始终使用 `MAX_LIMITS`（平台最大限额），完全忽略了教师在 judge_profile 中配置的 `limits_json`。教师设置的 `cpu_seconds`、`memory_mib`、`output_bytes` 从未生效。

```python
# 当前代码（第103行）
limits = MAX_LIMITS  # 永远用平台最大值，profile_snapshot_json 被忽略

# 应该读取 run_row 中的 profile_snapshot
# run_row["profile_snapshot_json"] 包含完整的 profile 快照（含 limits）
```

### 影响

- 教师设置 `cpu_seconds=5`，沙箱实际允许 10 秒
- 教师设置 `memory_mib=256`，Java 实际获得 `-Xmx512m`
- 教师设置 `output_bytes=524288`，实际上限 1048576
- 违反 PRD 第7节："引擎自动测试向量能力须对该版本实测"

### 修复方向

```python
def run_in_sandbox(run_row, submission_path, cases, execute):
    try:
        snapshot = json.loads(run_row["profile_snapshot_json"])
        profile_limits = snapshot.get("limits", {})
        limits = {k: profile_limits.get(k, MAX_LIMITS[k]) for k in MAX_LIMITS}
    except (TypeError, ValueError, KeyError):
        limits = MAX_LIMITS
    ...
```

---

## P1 — 沙箱执行器 stdout 为 None 时崩溃

**文件**: `backend/engines/grading.py` 第 117 行
**函数**: `run_in_sandbox`

### 问题描述

运算符优先级导致防御检查遗漏 `stdout=None, code=0` 的场景：

```python
# 当前代码（第117行）— Python 中 and 优先级高于 or
if code == 127 or stdout is None and code != 0:
    # 等价于: if (code == 127) or (stdout is None and code != 0):
    # 当 stdout=None 且 code=0 时，条件为 False，不返回
    return {"error_code": "ENGINE_UNAVAILABLE", ...}

# 第119行 — stdout=None 时会崩溃
parsed = parse_engine_output(stdout, [case])
# parse_engine_output 内部: raw.splitlines() → AttributeError: 'NoneType'
```

### 验证

```
stdout=None, code=0 → 条件=False → 执行 parse_engine_output(None) → 崩溃
```

### 影响

生产环境中 `real_executor` 只在 `code=127` 时返回 `None`，但一旦执行器行为变化或测试注入 `(None, 0)`，会导致未捕获的 `AttributeError`，run 卡在 running 状态直到租约过期。

### 修复方向

```python
# 将条件改为先检查 stdout is None，不依赖 code 值
if code == 127 or stdout is None:
    return {"error_code": "ENGINE_UNAVAILABLE", "results": results, "executed": executed}
```

---

## P1 — Windows 环境缺少 SYSTEMROOT 导致 Java 启动失败

**文件**: `backend/engines/grading.py` 第 149 行
**函数**: `real_executor`

### 问题描述

```python
env={"PATH": os.environ.get("PATH", ""), "JAVA_HOME": os.environ.get("JAVA_HOME", "")},
```

沙箱子进程只传入 `PATH` 和 `JAVA_HOME`，缺少 Windows 关键环境变量 `SYSTEMROOT`、`TEMP`、`TMP`。

### 验证

```
env keys: ['JAVA_HOME', 'PATH']
SYSTEMROOT missing: True
TEMP missing: True
```

### 影响

在 Windows 上，Java 运行时需要 `SYSTEMROOT`（通常 `C:\Windows`）来加载 `ntdll.dll` 等系统 DLL。缺少时 Java 可能直接退出（code 1 或 127），被误判为 `ENGINE_UNAVAILABLE` 或 `ENGINE_CRASH`，学生提交得到 `system_error` 而非真实评测结果。

### 修复方向

```python
env = {
    "PATH": os.environ.get("PATH", ""),
    "JAVA_HOME": os.environ.get("JAVA_HOME", ""),
}
# Windows 必需变量
for key in ("SYSTEMROOT", "TEMP", "TMP"):
    if os.environ.get(key):
        env[key] = os.environ[key]
```

---

## P1 — 后台扫描线程异常处理不完整

**文件**: `backend/engines/grading.py` 第 346-354 行
**函数**: `start_scanner` → `loop`

### 问题描述

```python
def loop():
    while True:
        time.sleep(5)
        try:
            scan_once(app.config["DATABASE_PATH"])
        except RuntimeError:  # 只捕获这两种
            return
        except OSError:
            continue
        # sqlite3.Error、MemoryError 等未捕获 → 线程静默退出
```

### 影响

`scan_once` 在数据库锁竞争时会抛出 `sqlite3.OperationalError`（`BEGIN IMMEDIATE` 冲突）。该异常不在捕获范围内，会导致扫描线程静默退出。此后：
- 过期的 running 任务不会被回收为 `system_error`
- 排队超时的任务不会被清理
- 失效 worker 的结果不会被拒绝

### 修复方向

```python
        except RuntimeError:
            return
        except (OSError, sqlite3.Error):
            continue  # 数据库临时错误，下次重试
```

---

## P1 — 重评接口未检查 profile 是否存在

**文件**: `backend/apis/grading.py` 第 697-706 行
**函数**: `regrade_submission`

### 问题描述

```python
profile = _profile_of(db, row["experiment_version_id"])  # 可能返回 None
run_id = db.execute(
    "INSERT INTO grading_run(...,profile_snapshot_json,...) VALUES(...)",
    (..., json.dumps(_profile_json(profile), sort_keys=True), ...))
    # _profile_json(None) → TypeError: 'NoneType' object is not subscriptable
```

### 验证

```
_profile_json(None) → TypeError: 'NoneType' object is not subscriptable
```

### 影响

正常流程中，已发布 circuit 版本必定有 profile（`publish_version` 强制检查）。但若数据库被直接操作删除了 profile 行，重评接口会抛出未捕获的 `TypeError`（500 错误），而非优雅的 409。

### 修复方向

```python
profile = _profile_of(db, row["experiment_version_id"])
if not profile:
    raise ApiError(409, "STATE_CONFLICT", "Judge profile is missing; cannot regrade")
```

---

## P1 — .circ 文件落盘非原子写入

**文件**: `backend/apis/grading.py` 第 103-113 行
**函数**: `_persist_file`

### 问题描述

```python
# grading.py — 直接写入，非原子
target = root / storage_key
target.write_bytes(content)

# 对比 resources.py save_file — 原子写入
tmp = target.with_suffix(".tmp")
tmp.write_bytes(content)
tmp.replace(target)  # 原子替换
```

### 影响

进程在 `write_bytes` 期间崩溃（断电、OOM Kill）会留下不完整的文件。后续 `send_file` 读取时可能返回截断的 XML，引擎解析失败判 `system_error`。`resources.py` 已有原子写入的先例，grading 模块未对齐。

### 修复方向

```python
target = root / storage_key
tmp = target.with_suffix(".tmp")
tmp.write_bytes(content)
tmp.replace(target)  # 原子重命名
return {...}, target
```

---

## P2 — 资源模块使用错误的错误码

**文件**: `backend/apis/resources.py` 第 274 行
**函数**: `get_content`

### 问题描述

```python
if rv["kind"] == "question_bank" and intent != "download":
    raise ApiError(422, "INVALID_CIRCUIT", "Question bank is download-only")
    #                    ^^^^^^^^^^^^^^^^ 错误码是电路相关的，此处是资源模块
```

### 影响

前端按 `code` 字段做错误分支时，资源接口返回了电路相关的错误码，可能导致错误处理逻辑混乱。

### 修复方向

```python
raise ApiError(422, "UNSUPPORTED_OPERATION", "Question bank is download-only")
```

---

## P2 — 访问事件记录存在竞态条件

**文件**: `backend/apis/resources.py` 第 293-307 行
**函数**: `get_content`

### 问题描述

```python
# 先读检查（read 连接）
existing = db.execute("SELECT ... WHERE user_id=? AND event_id=?", ...)
if existing:
    ...
else:
    # 再写插入（write 连接）— 两个连接之间有窗口
    with write() as wdb:
        wdb.execute("INSERT INTO resource_event ...")
```

### 影响

同一用户并发请求使用相同 `event_id` 但不同 `intent` 时，两个请求都可能通过读检查，第二个 INSERT 触发唯一约束 `IntegrityError`（500 错误）。实际触发概率低（需客户端复用 event_id 并发），但不符合幂等语义。

### 修复方向

在 `with write()` 事务内做 check-then-insert，利用事务隔离避免竞态；或捕获 `IntegrityError` 后重新检查并返回 409。

---

## P2 — 统计 CSV 导出包含非指标字段

**文件**: `backend/apis/statistics_csv.py` 第 33 行

### 问题描述

```python
keys = [key for key in metrics if key not in ('items', 'score_bins', 'suites')]
# grading dimension 的 metrics 包含 'selected_version_ids'（列表类型）
# 该字段被当作指标导出，CSV cell 中序列化为 JSON 字符串
```

### 影响

CSV 消费方（如 Excel 脚本）解析时，`selected_version_ids` 列含 JSON 数组字符串，与其他数值列格式不一致，可能导致解析异常。

### 修复方向

```python
keys = [key for key in metrics
        if key not in ('items', 'score_bins', 'suites', 'selected_version_ids')]
```

---

## P2 — 冗余导入

**文件**: `backend/apis/grading.py` 第 475 行

```python
# 模块顶部第38行已导入 now
from backend.shared.api import (..., now, ...)

# 函数内部第475行重复导入
from backend.shared.api import now  # 冗余
current = now()
```

### 影响

无功能影响，但增加维护噪音，可能误导读者以为 `now` 的导入来源有变化。

### 修复方向

删除第 475 行的局部导入。

---

## 跨模块依赖关系检查

### 已确认无问题

| 依赖关系 | 状态 |
|---------|------|
| grading.py → experiments.py (`load_json`, `version_row`) | 单向依赖，无循环 |
| grading_analytics.py → knowledge_analytics.py (`authorize`, `identifier`) | 共享鉴权函数，行为一致 |
| grading.py → shared/api.py (`ApiError`, `audit`, `body`, `now`, `stamp` 等) | 接口契约稳定 |
| grading.py → shared/auth.py (`course_access`, `require_user`) | 鉴权链路完整 |
| grading_analysis.py → numpy/pandas | 统计计算无数值溢出风险（Fraction 精确求和） |
| experiments.py publish → grading tables (`judge_profile`, `experiment_grading`) | 同事务原子写入 |

### 关注点

1. **`analytics.py` 第 292-293 行**: `permitted_run` 对 `kind in ('knowledge','scores','resources','grading')` 统一调用 `knowledge_analytics.authorize`。若各统计模块对鉴权有差异化需求（如 grading 需要 teacher 强制），当前统一鉴权可能不够精确。
2. **`grading.py` `_save_circ`**: 与 `resources.py` `save_file` 各自实现文件上传逻辑，未复用。两处对大小限制、MIME 校验、原子写入的处理方式不一致（grading 非原子，resources 原子）。

---

## 总结

| 严重级别 | 数量 | 关键问题 |
|---------|------|---------|
| P0 | 1 | 教师配置资源限制完全失效 |
| P1 | 5 | 沙箱 stdout 崩溃、Windows 环境缺失、扫描线程异常退出、重评 profile 空指针、非原子文件写入 |
| P2 | 4 | 错误码错用、竞态条件、CSV 格式问题、冗余导入 |

**优先修复**: P0（#1 限制失效）→ P1（#2 崩溃、#3 Windows 环境、#4 扫描线程、#5 重评空指针、#6 原子写入）
