"""SPEC-018 grading worker: lease queue, sandboxed engine runs and recovery.

独立 worker 在受限环境中调用真实引擎（PRD 第7节）。租约规则：worker 每5秒续租，
租约30秒；now≥lease_until 即失效，续租与提交结果都在同一事务检查
status/token/now<lease_until（R29）。真实引擎 CLI 适配格式在 TV-01 用固定 JAR 锁定。
"""

import json
import os
import re
import subprocess
import tempfile
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
    "Splitter", "Constant", "Register", "Comparator", "Adder", "Subtractor",
    "Multiplexer", "Demultiplexer", "Decoder", "Priority Encoder", "Encoder",
    "Bit Extender", "ROM", "RAM", "LED", "Button", "Clock", "Text", "Tunnel",
})


def jar_path():
    return os.environ.get("LOGISIM_JAR_PATH")


def grader_ready():
    """health 的 grader_ready：固定 JAR 存在且可执行身份校验通过。"""
    path = jar_path()
    return bool(path) and Path(path).is_file()


def engine_command(jar, vector_path, circuit_path, limits):
    """真实引擎调用命令；向量转换与输出格式由 TV-01 锁定后固化。

    默认按 logisim-evolution test-vector 语法构造，平台不拼接 shell、
    不使用上传文件名（AC-03/第7节）。
    """
    return ["java", f"-Xmx{limits['memory_mib']}m", "-Djava.awt.headless=true",
            "-jar", str(jar), "-test", "vector", str(vector_path), str(circuit_path)]


def write_vector_file(directory, case):
    """把平台 steps 契约转换为引擎测试向量文件（APIC 第7节：转换由适配层承担）。"""
    steps = json.loads(case["steps_json"])
    inputs = sorted({label for step in steps for label in step.get("inputs", {})})
    outputs = sorted({label for step in steps for label in step.get("expected", {})})
    lines = ["\t".join(inputs + outputs)]
    for step in steps:
        row = []
        for label in inputs:
            row.append(str(step.get("inputs", {}).get(label, 0)))
        for label in outputs:
            row.append(str(step.get("expected", {}).get(label, "X")))
        lines.append("\t".join(row))
    path = Path(directory) / f"vector-{case['id']}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


OUTPUT_LINE = re.compile(r"^\{.*\}$")


def parse_engine_output(raw, cases):
    """解析引擎输出为按 case 的结果。

    适配层约定：引擎包装输出 JSON 行（每 case 一行 {case_id, passed, actual, error}）。
    输出不可解析属于 system_error（AC-05），不会给学生误判 0 分。
    """
    results = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or not OUTPUT_LINE.match(line):
            continue
        try:
            payload = json.loads(line)
            results[int(payload["case_id"])] = payload
        except (KeyError, TypeError, ValueError):
            return None
    if set(results) != {case["id"] for case in cases}:
        return None
    return results


def run_in_sandbox(run_row, submission_path, cases, execute):
    """无网络、非 root、独立临时目录、只读运行时、资源受限的沙箱执行。

    execute(argv, cwd, timeout, max_output) 注入执行器：生产环境为受限子进程，
    单元测试注入受控替身验证平台管道（超时终止、输出上限、退出码路径）。
    """
    limits = MAX_LIMITS
    with tempfile.TemporaryDirectory(prefix="grading-") as directory:
        workspace = Path(directory)
        (workspace / "submission.circ").write_bytes(Path(submission_path).read_bytes())
        results, executed, notes = {}, 0, None
        for case in cases:
            vector = write_vector_file(workspace, case)
            argv = engine_command(jar_path(), vector, workspace / "submission.circ", limits)
            try:
                stdout, code = execute(argv, workspace, limits["cpu_seconds"], limits["output_bytes"])
            except SandboxTimeout:
                return {"error_code": "TIME_LIMIT", "results": results, "executed": executed}
            except SandboxOutputLimit:
                return {"error_code": "OUTPUT_LIMIT", "results": results, "executed": executed}
            if code == 127 or stdout is None and code != 0:
                return {"error_code": "ENGINE_UNAVAILABLE", "results": results, "executed": executed}
            parsed = parse_engine_output(stdout, [case])
            if parsed is None:
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
    try:
        process = subprocess.Popen(
            argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            env={"PATH": os.environ.get("PATH", ""), "JAVA_HOME": os.environ.get("JAVA_HOME", "")},
        )
    except OSError:
        return None, 127
    output, truncated = [], False
    try:
        for chunk in iter(lambda: process.stdout.readline() or None, None):
            output.append(chunk)
            if sum(len(line) for line in output) > max_output:
                truncated = True
                break
        if truncated:
            _terminate(process)
            raise SandboxOutputLimit()
        try:
            process.wait(timeout=max(0, timeout))
        except subprocess.TimeoutExpired:
            _terminate(process)
            raise SandboxTimeout() from None
    finally:
        if process.poll() is None:
            _terminate(process)
    return "".join(output), process.returncode


def _terminate(process):
    try:
        process.kill()
    except OSError:
        pass
    process.wait(timeout=5)


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
            except OSError:
                continue

    thread = threading.Thread(target=loop, daemon=True, name="grading-reclaim")
    thread.start()
    return thread


def current_app_db_path():
    return current_app.config["DATABASE_PATH"]
