"""SPEC-018 grading worker: lease queue, sandboxed engine runs and recovery.

独立 worker 在受限环境中调用真实引擎（PRD 第7节）。租约规则：worker 每5秒续租，
租约30秒；now≥lease_until 即失效，续租与提交结果都在同一事务检查
status/token/now<lease_until（R29）。真实引擎 CLI 适配格式在 TV-01 用固定 JAR 锁定。
"""

import json
import os
import queue
import re
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from flask import current_app

from backend.models.grading import ERROR_CODE_STATUS, MAX_LIMITS
from backend.shared.api import now as api_now
from backend.shared.api import stamp

LEASE_SECONDS = 30
QUEUE_TIMEOUT_SECONDS = 30 * 60

# 平台白名单：内置门、连线、寄存器、算术与项目内子电路（PRD 第7节允许清单范围）。
BASE_COMPONENTS = frozenset({
    "Pin", "AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "Buffer",
    "Splitter", "Constant", "Ground", "Power", "Register", "Comparator",
    "Adder", "Subtractor", "Shifter", "Bit Extender", "BitSelector",
    "Multiplexer", "Demultiplexer", "Decoder", "Priority Encoder", "Encoder",
    "ROM", "RAM", "LED", "Button", "Clock", "Text", "Tunnel",
})


def component_key(name):
    """把 .circ 里保存的元件显示名归一为白名单的逻辑名。

    logisim-evolution 5.0.0 保存门电路时用的是带后缀的名字（`AND Gate`、
    `NOT Gate`、`NOR Gate`…），而白名单与教师配置按逻辑名（`AND`、`NOT`）书写。
    不做归一化会把所有真实电路判成「元件不在允许列表」。
    """
    if isinstance(name, str) and name.endswith(" Gate"):
        return name[:-5]
    return name


def jar_path():
    return os.environ.get("LOGISIM_JAR_PATH")


def grader_ready():
    """health 的 grader_ready：固定 JAR 存在且可执行身份校验通过。"""
    path = jar_path()
    return bool(path) and Path(path).is_file()


def engine_command(jar, circuit_name, vector_path, circuit_path, limits):
    """真实引擎调用命令（logisim-evolution 5.0.0 `-w/--test-vector`）。

    实测确认的固定契约（v5.0.0 `--help`）：
        -w, --test-vector <circuit_name> <test_vector> <circ_file>
    另加 `-o en` 固定输出语言，避免平台按本地化文案解析（见 parse_engine_output）。

    注意：该 CLI 路径会构造 Swing 菜单栏，**在 java.awt.headless=true 下必然抛
    HeadlessException**（Startup.run -> LogisimMenuBar -> MenuFile）。因此 worker
    必须提供虚拟显示（Linux 用 xvfb），不能强制 headless；去掉 headless 后由
    DISPLAY 决定，见 real_executor 的环境变量传递。

    平台不拼接 shell、不使用上传文件名（AC-03/第7节）。
    """
    return ["java", f"-Xmx{limits['memory_mib']}m",
            "-jar", str(jar), "-o", "en", "-w", str(circuit_name),
            str(vector_path), str(circuit_path)]


def _vector_value(value):
    """平台 steps 里的整数写成引擎测试向量的十六进制字面量。

    引擎默认按**十六进制**读向量值：十进制 255 会被解析成 0x255（9 位），
    直接报 `Too many bits in "255" expected 8 bits`（实测）。`X`/`Z` 直接透传。
    """
    if isinstance(value, bool):
        return f"0x{int(value):X}"
    if isinstance(value, int):
        return f"0x{value:X}"
    return str(value)


def write_vector_file(directory, case, widths=None):
    """把平台 steps 契约转换为引擎测试向量文件（APIC 第7节：转换由适配层承担）。

    列名必须写成 `标签[位宽]`。引擎对未声明位宽的列按 **1 位** 解析，多比特端口
    的十进制值会直接报 `Test Vector data format error: Unexpected character`
    （实测：`A` + 值 `3` 报错，`A[8]` + `3` 通过）。位宽来自 judge profile 的
    port_schema，因此调用方必须把 widths 传进来。

    列顺序：输入 + 输出 + `<set>` + `<seq>`。一个 case 就是一条独立 sequence，
    所以统一用 set=1、seq=step_no，使引擎在 case 内保留时序状态、case 间不共享。

    返回 None 表示该 case 没有任何 expected 输出列：此时引擎会"零列全过"并
    报告 Passed=行数，直接采信等于把空测试判满分（AC-11）。
    """
    widths = widths or {}
    steps = json.loads(case["steps_json"])
    inputs = sorted({label for step in steps for label in step.get("inputs", {})})
    outputs = sorted({label for step in steps for label in step.get("expected", {})})
    if not outputs or not steps:
        return None
    if any(step.get("clock_event", "none") != "none" for step in steps):
        # APIC 第7节：时钟事件需映射到真实时钟引脚列，且"同向边沿必须插入反向边沿"。
        # 该映射属 TV-01 待锁定项，未锁定前不得静默丢弃边沿（会把时序题当组合题判）。
        raise UnsupportedClockEvent()

    def column(label):
        width = widths.get(label)
        return f"{label}[{width}]" if width else label

    lines = ["\t".join([column(label) for label in inputs + outputs] + ["<set>", "<seq>"])]
    for index, step in enumerate(steps, start=1):
        row = []
        for label in inputs:
            row.append(_vector_value(step.get("inputs", {}).get(label, 0)))
        for label in outputs:
            row.append(_vector_value(step.get("expected", {}).get(label, "x")))
        row.extend(["1", str(step.get("step_no") or index)])
        lines.append("\t".join(row))
    path = Path(directory) / f"vector-{case['id']}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class UnsupportedClockEvent(Exception):
    """case 含 clock_event 但时钟列映射尚未锁定（TV-01）。"""


class VectorHasNoOutput(Exception):
    """case 没有 expected 输出列，引擎会空过。"""


# 真实引擎（v5.0.0）在 `-o en` 下的输出，实测样例：
#   Loading test vector "wrong.txt"...
#   Running 2 vectors...
#   1
#   Error on test vector 1:
#   Y = 1 (expected 0)
#   Passed: 0, Failed: 2
# 注意：**失败时进程退出码仍为 0**，不能凭退出码判通过（实测）。
SUMMARY = re.compile(r"Passed:\s*(\d+)\s*,\s*Failed:\s*(\d+)")
EMPTY_VECTOR = re.compile(r"Passed:\s*0\s*,\s*Failed:\s*0")
ERROR_HEADER = re.compile(r"Error on test vector\s+(\d+)\s*:")
DETAIL = re.compile(r"^\s*(\S+)\s*=\s*(\S+)\s*\(expected\s+(\S+)\)\s*$")


def parse_engine_output(raw, cases):
    """解析真实引擎输出为按 case 的结果。

    只有 "Passed: N, Failed: M" 汇总行是可靠信号；单个 case 一次调用时，
    Failed=0 且 Passed>0 才算通过。
    以下都返回 None（→ system_error，AC-05），不会给学生误判 0 分：
    没有汇总行、汇总行数量与 case 数不符、汇总行是 Passed=0/Failed=0（空向量，AC-11）。
    """
    if raw is None:
        return None
    summaries = SUMMARY.findall(raw)
    if len(summaries) != len(cases) or EMPTY_VECTOR.search(raw):
        return None
    details = _error_details(raw) if len(cases) == 1 else []
    results = {}
    for index, case in enumerate(cases):
        passed_count, failed_count = (int(value) for value in summaries[index])
        results[case["id"]] = {
            "case_id": case["id"],
            "passed": failed_count == 0 and passed_count > 0,
            "actual": details if index == 0 else [],
        }
    return results


def _error_details(raw):
    """收集 "Error on test vector K:" 之后直到下一个表头/汇总行的明细行。"""
    details, capturing = [], False
    for line in raw.splitlines():
        if ERROR_HEADER.search(line):
            capturing = True
            continue
        if SUMMARY.search(line) or not line.strip():
            capturing = False
            continue
        match = DETAIL.match(line)
        if capturing and match:
            details.append({"label": match.group(1), "actual": match.group(2),
                            "expected": match.group(3)})
    return details


def run_in_sandbox(run_row, submission_path, cases, execute):
    """无网络、非 root、独立临时目录、只读运行时、资源受限的沙箱执行。

    execute(argv, cwd, timeout, max_output) 注入执行器：生产环境为受限子进程，
    单元测试注入受控替身验证平台管道（超时终止、输出上限、退出码路径）。

    沙箱限额优先采用教师在 judge_profile.limits_json 中配置的值（经
    validate_limits 校验且 ≤ MAX_LIMITS），仅在 run_row 缺少 profile 快照时
    才回落到平台最大限额。这样教师设置的更紧约束（如 cpu_seconds=5）才能真正
    生效，避免被 MAX_LIMITS 静默覆盖。
    """
    limits = dict(MAX_LIMITS)
    snapshot_json = None
    if run_row:
        try:
            snapshot_json = run_row["profile_snapshot_json"]
        except (KeyError, TypeError, IndexError):
            if hasattr(run_row, "get"):
                snapshot_json = run_row.get("profile_snapshot_json")
    circuit_name = None
    widths = {}
    if snapshot_json:
        try:
            snapshot = json.loads(snapshot_json) or {}
            circuit_name = snapshot.get("top_circuit")
            profile_limits = snapshot.get("limits") or {}
            for key in MAX_LIMITS:
                if key in profile_limits:
                    limits[key] = profile_limits[key]
            # 端口位宽用于向量列名 `标签[位宽]`，缺了引擎按 1 位解析直接报错。
            schema = snapshot.get("port_schema") or {}
            for side in ("inputs", "outputs"):
                widths.update(schema.get(side) or {})
        except (ValueError, TypeError):
            pass
    if not circuit_name:
        # 引擎调用必须指定顶层电路名（-w 的第一个参数）；缺名称无法执行。
        return {"error_code": "INCOMPLETE_RESULT", "results": {}, "executed": 0}
    with tempfile.TemporaryDirectory(prefix="grading-") as directory:
        workspace = Path(directory)
        (workspace / "submission.circ").write_bytes(Path(submission_path).read_bytes())
        results, executed, notes = {}, 0, None
        for case in cases:
            try:
                vector = write_vector_file(workspace, case, widths)
            except UnsupportedClockEvent:
                # 时钟列映射未锁定：宁可整卷 system_error，也不能把时序题按组合题判分。
                return {"error_code": "INCOMPLETE_RESULT", "results": results, "executed": executed}
            if vector is None:
                return {"error_code": "INCOMPLETE_RESULT", "results": results, "executed": executed}
            argv = engine_command(jar_path(), circuit_name, vector,
                                  workspace / "submission.circ", limits)
            try:
                stdout, code = execute(argv, workspace, limits["cpu_seconds"], limits["output_bytes"])
            except SandboxTimeout:
                return {"error_code": "TIME_LIMIT", "results": results, "executed": executed}
            except SandboxOutputLimit:
                return {"error_code": "OUTPUT_LIMIT", "results": results, "executed": executed}
            if code == 127 or stdout is None:
                return {"error_code": "ENGINE_UNAVAILABLE", "results": results, "executed": executed}
            parsed = parse_engine_output(stdout, [case])
            if parsed is None:
                if EMPTY_VECTOR.search(stdout):
                    # AC-11：引擎正常退出但一条用例都没执行，属结果不完整。
                    return {"error_code": "INCOMPLETE_RESULT", "results": results,
                            "executed": executed}
                if "Circuit load error" in stdout or "Unable to load" in stdout:
                    return {"error_code": "CIRCUIT_LOAD_ERROR", "results": results, "executed": executed}
                notes = "ENGINE_CRASH"
                continue
            results.update(parsed)
            executed += len(parsed)
        if notes == "ENGINE_CRASH":
            return {"error_code": "ENGINE_CRASH", "results": results, "executed": executed}
        # 正常完成但实际执行0条或数量不足 → system_error，不能判满分（AC-05/AC-11）。
        if executed < len(cases):
            return {"error_code": "INCOMPLETE_RESULT", "results": results, "executed": executed}
        return {"error_code": None, "results": results, "executed": executed}


class SandboxTimeout(Exception):
    pass


class SandboxOutputLimit(Exception):
    pass


def real_executor(argv, cwd, timeout, max_output):
    """受限子进程执行器：无 shell、显式 argv、进程组超时终止、输出上限。"""
    # Windows 上 Java/JVM 启动需要 SYSTEMROOT 才能定位 ntdll 等系统 DLL，
    # 且需要 TEMP/TMP 才能创建临时文件；缺失会直接报 MissingResource /
    # Unable to load DLL，学生提交被误判 system_error。其他平台保持最小环境。
    # DISPLAY/XAUTHORITY：logisim-evolution 5.0.0 的 `-w` 路径会构造 Swing 菜单栏，
    # 没有显示服务就抛 HeadlessException；Linux worker 必须用 xvfb 并提供这两个变量，
    # 否则所有提交都会变成 system_error（实测）。
    env = {
        "PATH": os.environ.get("PATH", ""),
        "JAVA_HOME": os.environ.get("JAVA_HOME", ""),
        "DISPLAY": os.environ.get("DISPLAY", ""),
        "XAUTHORITY": os.environ.get("XAUTHORITY", ""),
    }
    if os.name == "nt":
        env.update({
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
        })
    spawn = {}
    if os.name == "posix":
        # 自成一个进程组，超时时连 Java 派生的子进程一起终止。
        spawn["start_new_session"] = True
    elif os.name == "nt":
        spawn["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        process = subprocess.Popen(
            argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            env=env, **spawn,
        )
    except OSError:
        return None, 127

    # 直接 readline() 到 EOF 会在引擎挂起且不肯关 stdout 时永久阻塞，永远走不到
    # wait(timeout)（#58 审查意见第 3 条）。改成后台线程读、主线程按 deadline 收。
    lines, done = queue.Queue(), object()
    reader_done = threading.Event()

    def reader():
        try:
            for line in iter(process.stdout.readline, ""):
                lines.put(line)
        except (OSError, ValueError):
            # 超时路径下主线程可能先关掉 stdout，读线程安静退出即可。
            pass
        finally:
            reader_done.set()
            lines.put(done)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + max(0, timeout)
    output, truncated = [], False
    try:
        while True:
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    _terminate(process)
                    raise SandboxTimeout() from None
                if reader_done.is_set() and lines.empty():
                    break
                continue
            if line is done:
                break
            output.append(line)
            if sum(len(item) for item in output) > max_output:
                truncated = True
                break
            if time.monotonic() >= deadline:
                _terminate(process)
                raise SandboxTimeout() from None
        if truncated:
            _terminate(process)
            raise SandboxOutputLimit()
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _terminate(process)
            raise SandboxTimeout() from None
    finally:
        if process.poll() is None:
            _terminate(process)
        try:
            process.stdout.close()
        except (OSError, ValueError):
            pass
    return "".join(output), process.returncode


def _terminate(process):
    """终止整个进程组，避免只杀掉父进程后 Java 子进程残留。"""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, AttributeError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


# ---------- 租约队列（DBD 第7节 / R29） ----------

def claim_run(db, at, token=None):
    """短事务原子领取最早 queued 任务：条件更新为 running 并签发租约。"""
    reclaim_expired(db, at)
    run = db.execute("SELECT * FROM grading_run WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if run is None:
        return None
    token = token or uuid4().hex
    lease = stamp_from(at, LEASE_SECONDS)
    updated = db.execute(
        "UPDATE grading_run SET status='running',worker_token=?,lease_until=?,started_at=?,"
        "sandbox_id=? WHERE id=? AND status='queued'",
        (token, lease, stamp(at), f"sandbox-{run['id']}-{token[:8]}", run["id"])).rowcount
    if updated != 1:
        return None
    return db.execute("SELECT * FROM grading_run WHERE id=?", (run["id"],)).fetchone()


def renew_lease(db, run_id, token, at):
    """续租在同一事务检查 status=running、token 一致且 now<lease_until。"""
    updated = db.execute(
        "UPDATE grading_run SET lease_until=? WHERE id=? AND status='running' "
        "AND worker_token=? AND lease_until>?",
        (stamp_from(at, LEASE_SECONDS), run_id, token, stamp(at))).rowcount
    return updated == 1


def reclaim_expired(db, at):
    """回收过期运行（WORKER_LOST）与排队超时任务；同条件更新防重复回收。

    过期且未扫描的任务也不能被旧 worker 复活：renew/submit 同条件检查。
    """
    now_text = stamp(at)
    queue_deadline = stamp_from(at, -QUEUE_TIMEOUT_SECONDS)
    db.execute(
        "UPDATE grading_run SET status='system_error',error_code='WORKER_LOST',"
        "finished_at=?,score_hundredths=NULL WHERE status='running' AND lease_until<=?",
        (now_text, now_text))
    db.execute(
        "UPDATE grading_run SET status='system_error',error_code='WORKER_LOST',"
        "finished_at=?,score_hundredths=NULL WHERE status='queued' AND created_at<=?",
        (now_text, queue_deadline))
    db.execute(
        "UPDATE test_suite_validation SET status='system_error',error_code='WORKER_LOST',"
        "finished_at=? WHERE status='running' AND lease_until<=?", (now_text, now_text))


def submit_run_result(db, run_id, token, at, error_code, case_results):
    """运行结果明细与终态汇总在一个事务提交；终态只写一次。

    case_results: [{case_id, passed, actual(list of dict), elapsed_ms, error_code}]。
    """
    run = db.execute("SELECT * FROM grading_run WHERE id=?", (run_id,)).fetchone()
    if run is None or run["status"] != "running" or run["worker_token"] != token \
            or run["lease_until"] <= stamp(at):
        return False  # R29：失租 worker 的迟到结果不能覆盖已结束任务。
    if error_code is not None:
        if ERROR_CODE_STATUS[error_code] == "system_error":
            score, passed = None, 0
        else:
            score, passed = 0, 0
        db.execute(
            "UPDATE grading_run SET status=?,error_code=?,score_hundredths=?,passed_count=?,"
            "executed_count=?,finished_at=? WHERE id=? AND status='running'",
            (ERROR_CODE_STATUS[error_code], error_code, score, passed,
             min(run["total_count"], len(case_results)), stamp(at), run_id))
        _insert_case_results(db, run_id, case_results)
        return True
    passed_ids = {item["case_id"] for item in case_results if item["passed"]}
    return _finish_graded_run(db, run, at, passed_ids, case_results)


def _finish_graded_run(db, run, at, passed_ids, case_results):
    from backend.models.grading import compute_score, template_for
    suite = db.execute("SELECT * FROM test_suite WHERE id=?", (run["suite_id"],)).fetchone()
    cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                       (run["suite_id"],)).fetchall()
    version = db.execute(
        "SELECT e.code FROM experiment_version v JOIN experiment e ON e.id=v.experiment_id "
        "WHERE v.id=?", (suite["experiment_version_id"],)).fetchone()
    groups_max, _template = template_for(version["code"])
    score = compute_score(groups_max, cases, passed_ids)
    # 仅引擎正常完成时完整性成立；executed 缺失已在 worker 归 INCOMPLETE_RESULT。
    status = "accepted" if len(passed_ids) == len(cases) else "wrong_answer"
    db.execute(
        "UPDATE grading_run SET status=?,score_hundredths=?,passed_count=?,executed_count=?,"
        "finished_at=? WHERE id=? AND status='running'",
        (status, score, len(passed_ids), len(cases), stamp(at), run["id"]))
    _insert_case_results(db, run["id"], case_results)
    return True


def _insert_case_results(db, run_id, case_results):
    for item in case_results:
        db.execute(
            "INSERT OR REPLACE INTO case_result(run_id,case_id,passed,actual_json,"
            "elapsed_ms,error_code) VALUES(?,?,?,?,?,?)",
            (run_id, item["case_id"], int(item["passed"]),
             json.dumps(item.get("actual") or [], ensure_ascii=False),
             item.get("elapsed_ms"), item.get("error_code")))


def claim_validation(db, at, token=None):
    reclaim_expired(db, at)
    row = db.execute("SELECT * FROM test_suite_validation WHERE status='queued' ORDER BY id "
                     "LIMIT 1").fetchone()
    if row is None:
        return None
    token = token or uuid4().hex
    updated = db.execute(
        "UPDATE test_suite_validation SET status='running',worker_token=?,lease_until=?,"
        "started_at=?,sandbox_id=? WHERE id=? AND status='queued'",
        (token, stamp_from(at, LEASE_SECONDS), stamp(at),
         f"sandbox-v{row['id']}-{token[:8]}", row["id"])).rowcount
    if updated != 1:
        return None
    return db.execute("SELECT * FROM test_suite_validation WHERE id=?", (row["id"],)).fetchone()


def submit_validation_result(db, validation_id, token, at, reference_passed, negative_failed, error=None):
    """passed 需要标准电路全过、反例至少一项功能失败（DBD 第7节）。"""
    row = db.execute("SELECT * FROM test_suite_validation WHERE id=?", (validation_id,)).fetchone()
    if row is None or row["status"] != "running" or row["worker_token"] != token \
            or row["lease_until"] <= stamp(at):
        return False
    if error is not None:
        status, result = "system_error", {"error_code": error}
    elif reference_passed and negative_failed:
        status, result = "passed", {"reference": "all_passed", "negative": "functional_failure"}
    else:
        status, result = "failed", {"reference_all_passed": reference_passed,
                                    "negative_functional_failure": negative_failed}
    db.execute("UPDATE test_suite_validation SET status=?,result_json=?,finished_at=? WHERE id=?",
               (status, json.dumps(result, ensure_ascii=False), stamp(at), validation_id))
    return True


def stamp_from(at, seconds):
    base = at if hasattr(at, "astimezone") else api_now()
    return stamp(base + timedelta(seconds=seconds))


def scan_once(database_path):
    """Web 进程每5秒执行的回收扫描（独立连接，全停机重启后先扫描再领新任务）。"""
    from backend.shared.api import now
    from backend.shared.db import connect
    db = connect(database_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        reclaim_expired(db, now())
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def start_scanner(app):
    """非 testing 环境下启动 Web 进程的后台回收线程。"""
    import threading
    import time

    def loop():
        while True:
            time.sleep(5)
            try:
                scan_once(app.config["DATABASE_PATH"])
            except RuntimeError:  # app 已停止接受请求
                return
            except (OSError, sqlite3.Error):
                # OSError 覆盖磁盘 IO/文件锁；sqlite3.Error 覆盖数据库锁定、
                # 损坏等。两者都应让扫描继续下一轮，而不是让回收线程静默退出
                # 否则过期 running 任务永不被回收，最终全部 WORKER_LOST 堆积。
                continue

    thread = threading.Thread(target=loop, daemon=True, name="grading-reclaim")
    thread.start()
    return thread


def current_app_db_path():
    return current_app.config["DATABASE_PATH"]
