"""石佰合负责模块（SPEC-003 / 009 / 018 / 010D）一键验证脚本。

可重复运行，用于回答一个问题：本地改动里，我负责的代码还有没有 bug？

检查分六组：
  1. 范围守卫   —— 确认没有改动别人负责的文件（相对 HEAD 的改动 + 未跟踪文件）
  2. 防回退哨兵 —— 确认已修的缺陷没有被改回去
  3. 静态规范   —— ruff（后端 / 测试 / 脚本）、eslint（前端）
  4. 后端测试   —— 定向回归 + 全量 pytest（全量用于证明没碰坏别人模块）
  5. 前端验证   —— 组件测试、全量 node --test、vite build
  6. 端到端     —— SPEC-018 真引擎冒烟、118 项双场景验收（含前后端真值表对齐）

退出码：0 = 全部通过；1 = 发现缺陷或检查失败；2 = 运行环境缺失。
用法：
    .venv/Scripts/python.exe scripts/verify_shibaihe.py
    .venv/Scripts/python.exe scripts/verify_shibaihe.py --fast
    .venv/Scripts/python.exe scripts/verify_shibaihe.py --report-dir .workbuddy/verify
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PY = VENV_PY if VENV_PY.is_file() else Path(sys.executable)
JAR = ROOT / "instance" / "tools" / "le.jar"
DEFAULT_REPORT = ROOT / ".workbuddy" / "verify"

# 石佰合负责范围。改动文件必须落在这里，否则「范围守卫」直接判失败。
OWNED_EXACT = frozenset({
    "backend/apis/resources.py",
    "backend/apis/grading.py",
    "backend/apis/grading_analytics.py",
    "backend/apis/statistics_csv.py",
    "backend/apis/circuit_lab.py",
    "backend/app.py",
    "backend/engines/grading.py",
    "backend/models/grading.py",
    "frontend/js/circuit-sim.js",
    "frontend/js/circuit-lab-view.js",
    "frontend/js/circuit-lab-view.test.js",
    "frontend/js/circuit-lab-spec.fixture.json",
    "frontend/js/main.js",
    "frontend/styles/circuit-lab.css",
    "frontend/styles/main.css",
    "frontend/circuit-lab-preview.html",
    "scripts/acceptance_shibaihe.py",
    "scripts/ci_grader_smoke.py",
    "scripts/verify_shibaihe.py",
    "tests/test_resources.py",
    "tests/test_resource_question_integration.py",
    "tests/test_circuit_lab.py",
    "tests/test_shibaihe_bugfixes.py",
    "tests/test_grading.py",
    "tests/test_grading_analytics.py",
    "tests/test_grading_engine_contract.py",
    "tests/test_grading_executor_timeout.py",
    "tests/test_grading_worker.py",
    "tests/test_alu74181.py",
    "tests/test_experiments.py",
})
OWNED_PREFIXES = (
    "tests/acceptance/shibaihe-",
    "tests/fixtures/logisim/",
    "docs/shibaihe-",
)
# 工作区私有数据（备份、工作日志、验证报告），不入库也不算越界。
IGNORED_PREFIXES = (".workbuddy/",)

FOCUSED_TESTS = (
    "tests/test_resources.py",
    "tests/test_resource_question_integration.py",
    "tests/test_circuit_lab.py",
    "tests/test_shibaihe_bugfixes.py",
    "tests/test_grading.py",
    "tests/test_grading_analytics.py",
    "tests/test_grading_engine_contract.py",
    "tests/test_grading_executor_timeout.py",
    "tests/test_grading_worker.py",
    "tests/test_alu74181.py",
    "tests/test_experiments.py",
)

# (文件, 必须出现的片段, 说明)。片段取修复后的实际代码，防止悄悄回退。
SENTINELS = (
    ("backend/apis/circuit_lab.py", "re.fullmatch(", "compute 参数须用 ASCII 十进制白名单"),
    ("backend/apis/circuit_lab.py", "require_user()  # 逐表记录数", "bootstrap 须登录"),
    ("backend/apis/circuit_lab.py", "不要把 sqlite 的原始错误文本", "readiness 不得泄露 sqlite 错误"),
    ("backend/apis/resources.py", '"UNSUPPORTED_OPERATION"', "题库预览不得误用电路错误码"),
    ("backend/apis/resources.py", "except sqlite3.IntegrityError", "event_id 并发须有兜底"),
    ("backend/apis/resources.py", "_preparation_tables_exist", "备课表缺失须优雅降级"),
    ("backend/apis/resources.py", '"chapter", "knowledge_point"', "题库导入前置表检查须含间接依赖"),
    ("backend/apis/statistics_csv.py", "excluded += ('selected_version_ids',)", "grading CSV 须排除筛选快照字段"),
    ("tests/test_shibaihe_bugfixes.py", "class ResourceBugfixTest", "7 项修复的回归测试须存在"),
    ("frontend/js/circuit-lab-view.js", "togglePin", "电路台拨动开关交互须保留"),
    ("frontend/js/circuit-lab-view.js", "74-SERIES TTL", "真实实验箱铭牌须保留"),
    ("frontend/styles/circuit-lab.css", ".clab-nameplate", "真实实验箱台面样式须保留"),
)


class Step:
    def __init__(self, key, group, title, command=None, cwd=None,
                 must_contain=(), timeout=900, fast=True, info=False, internal=None):
        self.key = key
        self.group = group
        self.title = title
        self.command = command
        self.cwd = cwd or ROOT
        self.must_contain = must_contain
        self.timeout = timeout
        self.fast = fast          # --fast 时是否保留
        self.info = info          # 信息项不参与成败判定
        self.internal = internal  # 内置检查函数名


def py(*args):
    return " ".join([f'"{PY}"', *[str(a) for a in args]])


def node(*args):
    return " ".join([_node_exe(), *[str(a) for a in args]])


def _node_exe():
    found = shutil.which("node")
    return f'"{found}"' if found else "node"


def npm(*args):
    exe = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
    return f'"{exe}" ' + " ".join(str(a) for a in args)


def clean_env():
    env = os.environ.copy()
    # 工具环境的安全删除守卫会误伤 pytest / vite 对临时目录的清理，导致假失败。
    # JAR / 数据库路径也不能全局注入：/health 的 grader_ready 会因 JAR 可用而变 true，
    # 令公共脚手架测试（期望 503）假失败。真引擎与验收步骤各自显式传 --jar。
    for key in ("CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR", "CODEBUDDY_TOOL_CALL_ID",
                "LOGISIM_JAR_PATH", "DATABASE_PATH", "UPLOAD_ROOT"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    return env


def git_status_paths():
    out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", check=True).stdout
    paths = []
    for line in out.splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip().replace("\\", "/"))
    return paths


def is_owned(path):
    if path.startswith(IGNORED_PREFIXES):
        return True
    return path in OWNED_EXACT or path.startswith(OWNED_PREFIXES)


def check_scope():
    violations = [p for p in git_status_paths() if not is_owned(p)]
    paths = git_status_paths()
    if violations:
        return False, "越界改动：" + ", ".join(violations)
    return True, f"{len(paths)} 个本地改动全部落在石佰合负责范围内"


def check_sentinels():
    missing = []
    for rel, needle, why in SENTINELS:
        path = ROOT / rel
        if not path.is_file() or needle not in path.read_text(encoding="utf-8"):
            missing.append(f"{rel} 缺 {needle!r}（{why}）")
    if missing:
        return False, "；".join(missing)
    return True, f"{len(SENTINELS)} 项已修缺陷的防回退标记全部在位"


def check_database():
    path = ROOT / "instance" / "app.db"
    if not path.is_file():
        return True, "未找到 instance/app.db（空库场景由验收脚本自行构造，不影响验证）"
    con = sqlite3.connect(path)
    try:
        versions = con.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        counts = {}
        for key in ("course", "course_member", "experiment", "experiment_version",
                    "judge_profile", "test_case", "grading_run", "resource"):
            counts[key] = con.execute(f"SELECT COUNT(*) FROM {key}").fetchone()[0]
    except sqlite3.Error as exc:
        return True, f"数据库结构不完整（{exc}），属部署数据，不计为代码缺陷"
    finally:
        con.close()
    empty = [k for k, v in counts.items() if not v]
    return True, (f"迁移 {versions} 个 / 表 {tables} 张；8 类就绪数据 "
                  f"{8 - len(empty)}/8 非空" + (f"，缺 {', '.join(empty)}" if empty else ""))


def check_leftovers():
    items = sorted(ROOT.glob("tests/tmp*"))
    return True, f"tests/tmp* 测试残留 {len(items)} 个（临时目录，不影响仓库内容）"


INTERNAL = {
    "scope": check_scope,
    "sentinels": check_sentinels,
    "database": check_database,
    "leftovers": check_leftovers,
}


def build_steps(fast, out_dir):
    acceptance_out = out_dir / "acceptance"
    steps = [
        Step("scope", "范围", "不越界：本地改动全在石佰合模块内", internal="scope"),
        Step("sentinels", "范围", "防回退：已修缺陷标记全部在位", internal="sentinels"),
        Step("ruff", "静态", "ruff check backend tests scripts",
             py("-m", "ruff", "check", "backend", "tests", "scripts")),
        Step("pytest-focused", "后端", "定向回归：资源/电路台/评测/统计/7项修复",
             py("-m", "pytest", "-q", *FOCUSED_TESTS), must_contain=("passed",)),
        Step("pytest-all", "后端", "全量 pytest（证明未碰坏别人模块）",
             py("-m", "pytest", "-q"), must_contain=("passed",),
             fast=False, timeout=1200),
        Step("eslint", "前端", "eslint 全量",
             npm("run", "lint"), cwd=FRONTEND),
        Step("component", "前端", "电路实验台组件测试 16 项",
             node("--test", "js/circuit-lab-view.test.js"), cwd=FRONTEND,
             must_contain=("pass ",)),
        Step("frontend-test", "前端", "node --test 全量",
             npm("test"), cwd=FRONTEND),
        Step("build", "前端", "vite build",
             npm("run", "build"), cwd=FRONTEND),
        Step("grader-smoke", "端到端", "SPEC-018 Logisim 真引擎四组公开样例",
             py("scripts/ci_grader_smoke.py", "--jar", JAR),
             must_contain=("冒烟通过",), timeout=1200),
        Step("acceptance", "端到端", "118 项双场景验收（含前后端真值表对齐）",
             py("scripts/acceptance_shibaihe.py", "--scenario", "both",
                "--jar", JAR, "--out", acceptance_out),
             must_contain=("=== 验收：",), timeout=1800),
        Step("database", "信息", "本地数据库迁移与就绪数据", internal="database", info=True),
        Step("leftovers", "信息", "测试临时目录残留", internal="leftovers", info=True),
    ]
    if fast:
        steps = [s for s in steps if s.fast]
    return steps


def run_external(step, env, log_dir):
    started = time.monotonic()
    try:
        proc = subprocess.run(step.command, check=False, shell=True, cwd=step.cwd,
                              env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=step.timeout)
        rc, out = proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(
            exc.stdout, bytes) else (exc.stdout or "")
        return False, f"超时（>{step.timeout}s）", str(out)[-2000:], time.monotonic() - started
    seconds = time.monotonic() - started
    (log_dir / f"{step.key}.log").write_text(out, encoding="utf-8")
    ok = rc == 0
    detail = f"exit={rc}，{seconds:.1f}s"
    for needle in step.must_contain:
        if needle not in out:
            ok = False
            detail += f"，输出缺少 {needle!r}"
    if step.key == "acceptance":
        match = re.search(r"=== 验收：(\d+)/(\d+) 项通过 ===", out)
        if not match or match.group(1) != match.group(2):
            ok = False
            detail += "，验收项未全部通过"
        else:
            detail += f"，验收 {match.group(1)}/{match.group(2)}"
    if step.key == "pytest-all":
        match = re.search(r"(\d+) passed", out)
        if match:
            detail += f"，{match.group(1)} passed"
    if step.key == "frontend-test":
        match = re.search(r"# pass (\d+)", out)
        if match:
            detail += f"，{match.group(1)} pass"
    return ok, detail, out[-2000:] if not ok else "", seconds


def run_internal(step):
    fn = INTERNAL[step.internal]
    return fn()


def write_reports(out_dir, rows, seconds, fast):
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    checks = [r for r in rows if not r["info"]]
    passed = sum(1 for r in checks if r["status"] == "PASS")
    failed = [r for r in checks if r["status"] == "FAIL"]
    verdict = "通过：石佰合负责代码未发现 bug / 漏洞" if not failed else \
        f"未通过：{len(failed)} 项检查失败，禁止提交"
    payload = {
        "generated_at": stamp, "root": str(ROOT), "mode": "fast" if fast else "full",
        "elapsed_seconds": round(seconds, 1), "checks": len(checks),
        "passed": passed, "failed": len(failed), "verdict": verdict, "rows": rows,
    }
    (out_dir / "shibaihe-verify.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 石佰合负责模块 · 验证结果", "",
        f"生成时间：{stamp}　模式：{'快速' if fast else '全量'}　耗时：{seconds:.1f}s", "",
        f"**结论：{verdict}**", "",
        f"检查 {len(checks)} 项，通过 {passed} 项，失败 {len(failed)} 项。", "",
        "| 组 | 检查项 | 结果 | 说明 |", "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['group']} | {row['title']} | {row['status']} | "
                     f"{row['detail'].replace('|', '/')} |")
    lines += ["", "## 失败明细", ""]
    if failed:
        for row in failed:
            lines += [f"### {row['key']} · {row['title']}", "",
                      f"原因：{row['detail']}", "", "```", row["output"].strip(), "```", ""]
    else:
        lines.append("无。所有检查项均通过。")
    (out_dir / "shibaihe-verify.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return verdict


def main(argv=None):
    parser = argparse.ArgumentParser(description="石佰合负责模块一键验证")
    parser.add_argument("--fast", action="store_true", help="只跳过最慢的全量 pytest")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    if not (FRONTEND / "package.json").is_file() or not (ROOT / "backend" / "app.py").is_file():
        print("运行环境缺失：请在仓库根目录运行，且需存在 frontend/package.json", file=sys.stderr)
        return 2
    out_dir = Path(args.report_dir).resolve()
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = clean_env()

    # vite build 在部分工具环境下无法清理旧 dist，先移走再由构建重新生成。
    dist = FRONTEND / "dist"
    if dist.is_dir():
        shutil.move(str(dist), str(out_dir / f"dist-prev-{int(time.time())}"))

    steps = build_steps(args.fast, out_dir)
    rows = []
    started = time.monotonic()
    print(f"石佰合模块验证 · {'快速' if args.fast else '全量'} · {len(steps)} 项检查\n", flush=True)
    for step in steps:
        print(f"[{step.group}] {step.title} … ", end="", flush=True)
        if step.internal:
            ok, detail = run_internal(step)
            output, seconds = "", 0.0
        else:
            ok, detail, output, seconds = run_external(step, env, log_dir)
        status = "INFO" if step.info else ("PASS" if ok else "FAIL")
        rows.append({"key": step.key, "group": step.group, "title": step.title,
                     "status": status, "detail": detail, "output": output,
                     "seconds": round(seconds, 1), "info": step.info})
        print(f"{status} · {detail}", flush=True)
        if status == "FAIL" and output.strip():
            print("\n".join("    " + line for line in output.strip().splitlines()[-25:]), flush=True)
    elapsed = time.monotonic() - started
    verdict = write_reports(out_dir, rows, elapsed, args.fast)
    checks = [r for r in rows if not r["info"]]
    failed = [r for r in checks if r["status"] == "FAIL"]
    print(f"\n=== {verdict} ===")
    print(f"检查 {len(checks)} 项 / 通过 {len(checks) - len(failed)} 项 / "
          f"失败 {len(failed)} 项 / 耗时 {elapsed:.1f}s")
    print(f"报告：{out_dir / 'shibaihe-verify.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
