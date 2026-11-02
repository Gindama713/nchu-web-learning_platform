"""SPEC-018 ci-grader 冒烟：用固定 JAR 真实执行电路，不 mock、不跳过。

依据 README 附录 A.4：ci-grader 必须"固定JAR真实运行ALU/REG/CPU的公开测试电路，
覆盖错误和零用例；只有mock不足"。本脚本因此：
  · 校验固定 JAR 的 SHA256，下载/替换过的 JAR 直接失败；
  · 用 backend.engines.grading 里**真正的适配函数**拼命令、解析输出，
    避免冒烟脚本自己实现一套解析而与生产路径分叉；
  · 分别验证「正确电路通过」「错误电路必须判错」「零用例必须 system_error」。

用法（Linux CI 需要虚拟显示，见文末说明）：
    LOGISIM_JAR_PATH=/opt/logisim-evolution-5.0.0-all.jar python scripts/ci_grader_smoke.py
    python scripts/ci_grader_smoke.py --jar <path> --engine-only

--engine-only 只做通道自检（JAR + 显示 + CLI + 解析），用于快速定位环境问题。
完整模式还要求 ALU/REG/CPU 公开样例齐备，缺失即失败。
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.engines import grading as engine
from backend.models.grading import MAX_LIMITS

ENGINE_VERSION = "5.0.0"
# 固定发布产物 logisim-evolution-5.0.0-all.jar 的 SHA256（TV-01 锁定项）。
JAR_SHA256 = "6b368e894742c04cc83aa9830f869bcab0190ede4df43ad6fecdb89b3a23a41c"
FIXTURES = ROOT / "tests" / "fixtures" / "logisim"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_engine(jar, circuit_name, vector_path, circuit_path, timeout=120):
    """按生产环境同一套命令构造与解析逻辑执行一次。

    返回 (通过与否, 明细, 原始输出)。注意：引擎失败时退出码仍是 0，
    所以判定只能看输出汇总行（engine.parse_engine_output 已处理）。
    """
    argv = engine.engine_command(str(jar), circuit_name, str(vector_path),
                                 str(circuit_path), MAX_LIMITS)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, check=False)
    except FileNotFoundError:
        return False, "找不到 java（需要 Java 21 基线）", ""
    raw = (proc.stdout or "") + (proc.stderr or "")
    if "HeadlessException" in raw:
        return False, "引擎报 HeadlessException：本 job 缺少虚拟显示（CI 用 xvfb-run）", raw
    parsed = engine.parse_engine_output(raw, [{"id": 1}])
    if parsed is None:
        return False, "输出无法解析为 Passed/Failed 汇总", raw
    return parsed[1]["passed"], parsed[1].get("actual") or [], raw


def check_engine(jar):
    """JAR 身份与版本：哈希不符或版本不符一律失败，不做降级。"""
    problems = []
    if not Path(jar).is_file():
        return [f"固定 JAR 不存在：{jar}"]
    digest = sha256_of(jar)
    if digest != JAR_SHA256:
        problems.append(f"JAR SHA256 不符：实际 {digest}，期望 {JAR_SHA256}")
    try:
        proc = subprocess.run(["java", "-jar", str(jar), "-v"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=120, check=False)
    except FileNotFoundError:
        return problems + ["找不到 java（需要 Java 21 基线）"]
    banner = (proc.stdout or "") + (proc.stderr or "")
    if ENGINE_VERSION not in banner:
        first_line = next((line for line in banner.splitlines() if line.strip()), "")
        problems.append(f"引擎版本不是 {ENGINE_VERSION}（实际首行：{first_line}）")
    return problems


# (名称, 电路名, 电路文件, 向量文件, 期望通过)
CHAIN_CASES = [
    ("通道通过", "pipeline", "pipeline.circ", "pipeline_ok.txt", True),
    ("通道反例", "pipeline", "pipeline.circ", "pipeline_bad.txt", False),
    ("零用例", "pipeline", "pipeline.circ", "pipeline_zero.txt", False),
]
# README 附录 A.4 要求真实运行 ALU/REG/CPU 公开电路；这些样例补齐前 ci-grader 不得算通过。
REQUIRED_CASES = [
    ("ALU8 正确电路", "alu8", "alu8.circ", "alu8_ok.txt", True),
    ("ALU8 错误电路", "alu8", "alu8_wrong.circ", "alu8_wrong.txt", False),
    ("REG8 连续时序", "reg8", "reg8.circ", "reg8_seq.txt", True),
    ("CPU8 连续时序", "cpu8", "cpu8.circ", "cpu8_seq.txt", True),
]


def run_cases(jar, cases):
    failures = []
    for label, circuit_name, circ_name, vector_name, expect_pass in cases:
        circuit, vector = FIXTURES / circ_name, FIXTURES / vector_name
        if not circuit.is_file() or not vector.is_file():
            failures.append(f"{label}：缺样例文件 {circ_name} / {vector_name}")
            continue
        passed, detail, _raw = run_engine(jar, circuit_name, vector, circuit)
        if passed != expect_pass:
            want = "通过" if expect_pass else "判错"
            got = "通过" if passed else "判错"
            failures.append(f"{label}：期望 {want}，实际 {got}（{detail}）")
        else:
            print(f"  [ok] {label:<16} {'通过' if passed else '判错'}")
    return failures


def main():
    parser = argparse.ArgumentParser(description="SPEC-018 ci-grader 真实引擎冒烟")
    parser.add_argument("--jar", default=os.environ.get("LOGISIM_JAR_PATH"),
                        help="固定 JAR 路径（默认取 LOGISIM_JAR_PATH）")
    parser.add_argument("--engine-only", action="store_true",
                        help="只做通道自检，不要求 ALU/REG/CPU 样例")
    args = parser.parse_args()
    if not args.jar:
        print("失败：未提供固定 JAR（--jar 或 LOGISIM_JAR_PATH）")
        return 2

    print("SPEC-018 ci-grader 真实引擎冒烟")
    problems = check_engine(args.jar)
    if problems:
        for problem in problems:
            print(f"  失败：{problem}")
        return 1

    failures = run_cases(args.jar, CHAIN_CASES)
    if not args.engine_only:
        failures += run_cases(args.jar, REQUIRED_CASES)

    if failures:
        print("\n冒烟失败：")
        for failure in failures:
            print(f"  - {failure}")
        if not args.engine_only and any(
                name in failure
                for failure in failures for name in ("alu8", "reg8", "cpu8")):
            print("\nALU/REG/CPU 公开样例是 README 附录 A.4 的 ci-grader 硬要求，"
                  "不能用通道自检或 mock 代替。")
        return 1
    print("\n冒烟通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
