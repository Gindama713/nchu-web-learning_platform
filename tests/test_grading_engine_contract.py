"""SPEC-018 真实引擎契约测试（logisim-evolution 5.0.0 实测基准）。

这些断言来自对固定 JAR（v5.0.0，sha256
6b368e894742c04cc83aa9830f869bcab0190ede4df43ad6fecdb89b3a23a41c）的实测，
不是平台自拟的协议。改动前请先用真实 JAR 复核，否则会重新回到"单测全绿、真机必挂"。

覆盖：AC-03（不使用上传文件名拼命令）/ AC-05（输出不可解析归 system_error）/
AC-11（空向量不得判满分）/ 第7节（沙箱不得拼 shell）。
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.engines import grading as engine
from backend.models.grading import MAX_LIMITS

# 实测录制的引擎输出（-o en）。
PASS_OUTPUT = 'Loading test vector "v.txt"...\nRunning 2 vectors...\n1\n2\nPassed: 2, Failed: 0\n'
FAIL_OUTPUT = ('Loading test vector "v.txt"...\nRunning 2 vectors...\n1\n'
               'Error on test vector 1:\nY = 1 (expected 0)\n2\n'
               'Error on test vector 2:\nY = 0 (expected 1)\nPassed: 0, Failed: 2\n')


def case(case_id=1, steps=None):
    return {"id": case_id, "steps_json": json.dumps(steps or [
        {"step_no": 1, "inputs": {"A": 1, "B": 2}, "expected": {"Y": 3}, "clock_event": "none"}])}


class EngineCommandTest(TestCase):
    def test_uses_fixed_test_vector_cli(self):
        # 实测 v5.0.0：-w, --test-vector <circuit_name> <test_vector> <circ_file>
        argv = engine.engine_command("/opt/fixed.jar", "alu8", "/t/v.txt",
                                     "/t/submission.circ", MAX_LIMITS)
        self.assertEqual(argv[0], "java")
        self.assertIn("-jar", argv)
        position = argv.index("-w")
        self.assertEqual(argv[position + 1:position + 4], ["alu8", "/t/v.txt", "/t/submission.circ"])
        # 输出语言固定为英文，避免按本地化文案解析。
        self.assertEqual(argv[argv.index("-o") + 1], "en")
        # 内存上限来自沙箱限额。
        self.assertIn(f"-Xmx{MAX_LIMITS['memory_mib']}m", argv)

    def test_no_shell_and_no_uploaded_filename(self):
        # AC-03/第7节：显式 argv，不拼 shell，不使用学生上传的文件名。
        argv = engine.engine_command("j", "alu8", "v.txt", "submission.circ", MAX_LIMITS)
        self.assertNotIn("/bin/sh", argv)
        self.assertNotIn("sh", argv)
        self.assertTrue(all(isinstance(part, str) for part in argv))


class VectorWriterTest(TestCase):
    def test_rewrites_steps_with_set_and_seq(self):
        with TemporaryDirectory() as directory:
            path = engine.write_vector_file(directory, case(steps=[
                {"step_no": 1, "inputs": {"A": 1, "B": 2}, "expected": {"Y": 3}},
                {"step_no": 2, "inputs": {"A": 4, "B": 5}, "expected": {"Y": 9}},
            ]))
            lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines[0].split("\t"), ["A", "B", "Y", "<set>", "<seq>"])
            # 一个 case 是一条 sequence：set 固定，seq 用 step_no。
            self.assertEqual(lines[1].split("\t"), ["1", "2", "3", "1", "1"])
            self.assertEqual(lines[2].split("\t"), ["4", "5", "9", "1", "2"])

    def test_case_without_expected_outputs_is_rejected(self):
        # AC-11：没有 expected 列时引擎会"零列全过"，采信即等于判满分。
        with TemporaryDirectory() as directory:
            self.assertIsNone(engine.write_vector_file(directory, case(steps=[
                {"step_no": 1, "inputs": {"A": 1}, "expected": {}}])))

    def test_clock_event_is_not_silently_dropped(self):
        # 时序题的时钟列映射属 TV-01 待锁定项，未锁定前必须显式失败。
        with TemporaryDirectory() as directory, self.assertRaises(engine.UnsupportedClockEvent):
            engine.write_vector_file(directory, case(steps=[
                {"step_no": 1, "inputs": {"A": 1}, "expected": {"Y": 3},
                 "clock_event": "rising"}]))


class RealOutputParseTest(TestCase):
    def test_pass_and_fail_recording(self):
        # 实测：引擎失败时退出码仍为 0，只能靠汇总行判定。
        good = engine.parse_engine_output(PASS_OUTPUT, [case()])
        self.assertTrue(good[1]["passed"])
        bad = engine.parse_engine_output(FAIL_OUTPUT, [case()])
        self.assertFalse(bad[1]["passed"])
        self.assertEqual(bad[1]["actual"][0], {"label": "Y", "actual": "1", "expected": "0"})

    def test_unparseable_output_returns_none(self):
        # AC-05：不可解析 → system_error，不得误判 0 分。
        self.assertIsNone(engine.parse_engine_output(None, [case()]))
        self.assertIsNone(engine.parse_engine_output("Exception in thread main", [case()]))
        self.assertIsNone(engine.parse_engine_output(
            "Passed: 1, Failed: 0\nPassed: 1, Failed: 0\n", [case()]))


class SandboxGuardTest(TestCase):
    def test_missing_top_circuit_is_system_error(self):
        # 没有顶层电路名就无法拼出 -w 参数，必须显式 system_error 而不是"执行 0 条"。
        with TemporaryDirectory() as directory:
            target = Path(directory) / "s.circ"
            target.write_text("<project/>", encoding="utf-8")
            outcome = engine.run_in_sandbox({}, target, [case()],
                                            execute=lambda *a: ("Passed: 1, Failed: 0", 0))
            self.assertEqual(outcome["error_code"], "INCOMPLETE_RESULT")

    def test_zero_executed_rows_is_incomplete(self):
        # AC-11：引擎正常退出但报告 Passed=0/Failed=0 时不能判满分。
        with TemporaryDirectory() as directory:
            target = Path(directory) / "s.circ"
            target.write_text("<project/>", encoding="utf-8")
            run_row = {"profile_snapshot_json": json.dumps({"top_circuit": "alu8"})}
            outcome = engine.run_in_sandbox(
                run_row, target, [case()],
                execute=lambda *a: ("Running 0 vectors...\nPassed: 0, Failed: 0\n", 0))
            self.assertEqual(outcome["error_code"], "INCOMPLETE_RESULT")
