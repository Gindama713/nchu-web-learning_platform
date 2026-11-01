"""T018 SPEC-018 worker/scoring/preflight units against the real DBD schema.

覆盖来源标注（PRD 第13节 T018 / 第7节 / 第7.1节）：
AC-03 结构预检 / AC-05 引擎与系统故障 / AC-11 限额终态固定 /
R18 幂等与重复请求语义外的执行路径 / R29 租约与回收 / 评分组固定模板。
真实引擎 CLI 冒烟属 TV-01（固定 JAR 后执行），此处用注入执行器验证平台管道。
"""

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.engines import grading as engine
from backend.models.grading import (
    SCORING_TEMPLATES,
    compute_score,
    preflight_basic,
    preflight_circ,
    scoring_groups_json,
    template_for,
    validate_cases,
)
from backend.shared.api import ApiError
from backend.shared.db import connect, migrate

AT = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)

CIRC = """<?xml version="1.0" encoding="UTF-8"?>
<logisim-evolution version="5.0.0">
  <circuit name="alu8">
    <comp name="Pin" loc="(10,10)"><a name="label" val="A"/><a name="width" val="8"/></comp>
    <comp name="Pin" loc="(10,40)"><a name="label" val="B"/><a name="width" val="8"/></comp>
    <comp name="Pin" loc="(300,10)"><a name="label" val="Y"/><a name="width" val="8"/>
      <a name="output" val="true"/></comp>
    <comp name="Adder" loc="(150,10)"/>
  </circuit>
</logisim-evolution>
"""


def profile_row(port_schema=None, components=None):
    return {
        "top_circuit": "alu8",
        "port_schema_json": json.dumps(port_schema or {"inputs": {"A": 8, "B": 8},
                                                       "outputs": {"Y": 8}}),
        "allowed_components_json": json.dumps(components or ["Adder"]),
    }


class ScoringTest(TestCase):
    def test_prd71_fixed_templates(self):
        # 覆盖 T018/PRD 第7.1节：评分组满分由固定模板生成，恒为 10000。
        for code, expected_sum in (("EXP-01", 10000), ("EXP-02", 10000), ("EXP-04", 10000)):
            groups, _ = template_for(code)
            self.assertEqual(sum(groups.values()), expected_sum, code)
        self.assertEqual(SCORING_TEMPLATES["EXP-01"]["ALU"]["add"], 1250)
        self.assertEqual(SCORING_TEMPLATES["EXP-02"]["REG"]["reset"], 2500)
        self.assertEqual(SCORING_TEMPLATES["EXP-04"]["CPU"]["reset"], 800)
        self.assertEqual(SCORING_TEMPLATES["EXP-04"]["CPU"]["nop"], 1000)
        payload = json.loads(scoring_groups_json("EXP-01"))
        self.assertEqual(len(payload["groups"]), 8)

    def test_group_equal_weight_and_single_rounding(self):
        # 覆盖 PRD 第7.1节：组内等权、Fraction 求和后统一四舍五入一次（half-up）。
        groups = {"ALU": 100}
        cases = [{"id": i, "group_code": "ALU"} for i in (1, 2, 3)]
        self.assertEqual(compute_score(groups, cases, {1, 2}), 67)  # 100*2/3=66.67
        self.assertEqual(compute_score(groups, cases, {1}), 33)  # 100/3=33.33
        half = [{"id": 1, "group_code": "ALU"}, {"id": 2, "group_code": "ALU"}]
        self.assertEqual(compute_score(groups, half, {1}), 50)
        # 全过满分、全败 0 分。
        self.assertEqual(compute_score(groups, cases, {1, 2, 3}), 100)
        self.assertEqual(compute_score(groups, cases, set()), 0)

    def test_cases_validation_rejects_weight_and_bad_groups(self):
        # 覆盖 R13：测试集不接受 weight，用例必须命中模板组。
        groups, _template = template_for("EXP-01")
        with self.assertRaises(ApiError):
            validate_cases([{"label": "a", "visibility": "public", "group_code": "add",
                             "steps": [], "weight": 5}], groups)
        with self.assertRaises(ApiError):
            validate_cases([{"label": "a", "visibility": "public", "group_code": "nope",
                             "steps": [{"step_no": 1, "inputs": {"A": 1},
                                        "expected": {"Y": 1}, "clock_event": "none"}]}],
                           groups)
        ok = validate_cases([{"label": "a", "visibility": "hidden", "group_code": "add",
                               "steps": [{"step_no": 1, "inputs": {"A": 1},
                                          "expected": {"Y": 1}, "clock_event": "none"}]}],
                            groups)
        self.assertEqual(ok[0]["group_code"], "add")

    def test_steps_contract(self):
        # 覆盖 APIC 第7节 steps 契约：CLK 禁止、step_no 连续、X/Z 仅 expected、边沿交替。
        groups, _template = template_for("EXP-01")
        schema = {"inputs": {"A": 8}, "outputs": {"Y": 8}}
        with self.assertRaises(ApiError):
            validate_cases([{"label": "a", "visibility": "public", "group_code": "add",
                             "steps": [{"step_no": 1, "inputs": {"CLK": 1},
                                        "expected": {"Y": 1}, "clock_event": "none"}]}],
                           groups, schema)
        with self.assertRaises(ApiError):  # 相同方向边沿连续出现
            validate_cases([{"label": "a", "visibility": "public", "group_code": "add",
                             "steps": [
                                 {"step_no": 1, "inputs": {"A": 1}, "expected": {"Y": 1},
                                  "clock_event": "rising"},
                                 {"step_no": 2, "inputs": {"A": 2}, "expected": {"Y": 2},
                                  "clock_event": "rising"}]}], groups, schema)
        with self.assertRaises(ApiError):  # inputs 不允许 X
            validate_cases([{"label": "a", "visibility": "public", "group_code": "add",
                             "steps": [{"step_no": 1, "inputs": {"A": "X"},
                                        "expected": {"Y": 1}, "clock_event": "none"}]}],
                           groups, schema)
        ok = validate_cases([{"label": "a", "visibility": "public", "group_code": "add",
                              "steps": [{"step_no": 1, "inputs": {"A": 5},
                                         "expected": {"Y": "X"}, "clock_event": "none"}]}],
                            groups, schema)
        self.assertEqual(ok[0]["steps"][0]["expected"]["Y"], "X")


class PreflightTest(TestCase):
    def test_valid_circ_passes_and_malformed_rejected(self):
        # 覆盖 AC-03：伪 XML、DTD/外部实体、外部文件引用一律 4xx 预检失败。
        profile = profile_row()
        self.assertTrue(preflight_circ(CIRC, profile))
        for content in ("not xml at all",
                        CIRC.replace("<logisim-evolution", "<!DOCTYPE logisim-evolution SYSTEM 'x'><logisim-evolution"),
                        CIRC.replace('name="Adder" loc="(150,10)"',
                                     'name="Adder" loc="(150,10)"><a name="ImagePath" val="https://evil/x.png"/></comp><comp name="Adder" loc="(160,10)"'),
                        CIRC.replace('name="alu8"', 'name="other"'),
                        CIRC.replace('val="A"', 'val="A2"'),
                        CIRC.replace('name="output" val="true"', 'name="output" val="false"'),
                        CIRC.replace('name="Adder"', 'name="HDLLoader"')):
            with self.assertRaises(ApiError, msg=content[:60]):
                preflight_circ(content, profile)
        self.assertTrue(preflight_basic(CIRC))
        with self.assertRaises(ApiError):
            preflight_basic("<notlogisim><circuit name='x'/></notlogisim>")

    def test_scale_and_recursion_limits(self):
        # 覆盖 PRD 第7节：元件数≤2000、子电路嵌套≤20 层、递归引用拒绝。
        profile = profile_row(components=["Adder", "Register"])
        many = CIRC.replace(
            '<comp name="Adder" loc="(150,10)"/>',
            "".join(f'<comp name="Adder" loc="({150 + i},10)"/>' for i in range(2100)))
        with self.assertRaises(ApiError):
            preflight_circ(many, profile)
        recursive = CIRC.replace(
            '<comp name="Adder" loc="(150,10)"/>',
            '<comp name="alu8" loc="(150,10)"/>')
        with self.assertRaises(ApiError):
            preflight_circ(recursive, profile)
        # 25 层子电路链：main → inner → deep0..deep24 超过 20 层。
        circuits = ['<circuit name="inner"><comp name="deep0" loc="(10,10)"/></circuit>']
        circuits += [f'<circuit name="deep{index}"><comp name="deep{index + 1}" loc="(10,10)"/></circuit>'
                     for index in range(25)]
        deep = CIRC.replace(
            '<comp name="Adder" loc="(150,10)"/>',
            '<comp name="inner" loc="(150,10)"/>').replace(
            "</logisim-evolution>", "".join(circuits) + "</logisim-evolution>")
        with self.assertRaises(ApiError):
            preflight_circ(deep, profile)


class EngineOutputTest(TestCase):
    def test_parse_output_contract(self):
        # 覆盖 AC-05：输出不可解析归 system_error，不给学生误判满分。
        cases = [{"id": 7, "steps_json": "[]"}, {"id": 8, "steps_json": "[]"}]
        good = '{"case_id": 7, "passed": true, "actual": [{"Y": 3}]}\n{"case_id": 8, "passed": false, "actual": [{"Y": 4}]}'
        parsed = engine.parse_engine_output(good, cases)
        self.assertEqual(parsed[7]["passed"], True)
        self.assertIsNone(engine.parse_engine_output("garbage", cases))
        self.assertIsNone(engine.parse_engine_output('{"case_id": 7, "passed": true}', cases))

    def test_sandbox_executor_paths(self):
        # 覆盖平台管道（非引擎结果冒充）：超时→TIME_LIMIT、输出超限→OUTPUT_LIMIT。
        submission = Path(TemporaryDirectory().name)
        self.addCleanup(lambda: submission.unlink(missing_ok=True))
        with TemporaryDirectory() as directory:
            target = Path(directory)/"s.circ"
            target.write_text(CIRC, encoding="utf-8")
            case = {"id": 1, "steps_json": json.dumps(
                [{"step_no": 1, "inputs": {"A": 1}, "expected": {"Y": 2}, "clock_event": "none"}])}
            slow = engine.run_in_sandbox({}, target, [case], execute=lambda *a: (_ for _ in ()).throw(
                engine.SandboxTimeout()))
            self.assertEqual(slow["error_code"], "TIME_LIMIT")
            loud = engine.run_in_sandbox({}, target, [case], execute=lambda *a: (_ for _ in ()).throw(
                engine.SandboxOutputLimit()))
            self.assertEqual(loud["error_code"], "OUTPUT_LIMIT")
            missing = engine.run_in_sandbox({}, target, [case],
                                            execute=lambda *a: (None, 127))
            self.assertEqual(missing["error_code"], "ENGINE_UNAVAILABLE")
            partial = engine.run_in_sandbox({}, target, [case], execute=lambda *a: ("noise", 0))
            self.assertEqual(partial["error_code"], "ENGINE_CRASH")


class LeaseQueueTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name)/"grading.db"
        migrate(self.path)
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO user(id,student_no,name,password_hash,role,created_at,updated_at) "
                       "VALUES(1,'S1','S','x','student',?,?)", ("x", "x"))
            db.execute("INSERT INTO course(id,title,teacher_id,created_at,updated_at) "
                       "VALUES(1,'C',1,'x','x')")
            db.execute("INSERT INTO experiment(id,course_id,code,title,created_at,updated_at) "
                       "VALUES(1,1,'EXP-01','ALU','x','x')")
            db.execute("INSERT INTO experiment_version(id,experiment_id,version,title,objectives,"
                       "instructions,submission_modes_json,status,definition_sha256,created_at,"
                       "updated_at) VALUES(1,1,1,'t','o','i','[\"circuit\"]','draft','x','x','x')")
            db.execute("INSERT INTO file_object(id,owner_id,storage_key,original_name,media_type,"
                       "size_bytes,sha256,purpose,created_at) "
                       "VALUES(1,1,'k','a.circ','application/xml',10,'h','grading_submission','x')")
            db.execute("INSERT INTO submission(id,experiment_version_id,student_id,file_id,"
                       "file_sha256,size_bytes,filename,created_at) "
                       "VALUES(1,1,1,1,'h',10,'a.circ',?)", ("2026-10-13T08:00:00Z",))
            db.execute("INSERT INTO test_suite(id,experiment_version_id,version,status,"
                       "content_sha256,scoring_groups_json,created_at) "
                       "VALUES(1,1,1,'draft','c','{}','x')")
            for identifier, group in enumerate(("add", "sub", "and", "or", "xor", "not", "shl", "shr")):
                db.execute("INSERT INTO test_case(id,suite_id,label,visibility,group_code,steps_json) "
                           "VALUES(?,?,?,'public',?,'[]')", (identifier + 1, 1, f"case{identifier}", group))
            db.execute("INSERT INTO grading_run(id,submission_id,suite_id,engine_version,status,"
                       "total_count,profile_snapshot_json,profile_sha256,suite_sha256,created_at) "
                       "VALUES(1,1,1,'logisim-evolution 5.0.0','queued',8,'{}','p','c',?)",
                       ("2026-10-13T08:00:00Z",))
            db.commit()

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, run_id=1):
        with closing(connect(self.path)) as db:
            return db.execute("SELECT * FROM grading_run WHERE id=?", (run_id,)).fetchone()

    def test_claim_renew_submit_lifecycle(self):
        # 覆盖 R29：领取签发租约，续租与提交同事务检查 token/lease。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            run = engine.claim_run(db, AT)
            self.assertEqual(run["status"], "running")
            self.assertTrue(engine.renew_lease(db, run["id"], run["worker_token"], AT))
            results = [{"case_id": index, "passed": True, "actual": [{"Y": 1}]}
                       for index in range(1, 9)]
            self.assertTrue(engine.submit_run_result(
                db, run["id"], run["worker_token"], AT, None, results))
            db.commit()
        finished = self._run()
        self.assertEqual(finished["status"], "accepted")
        self.assertEqual(finished["score_hundredths"], 10000)
        self.assertEqual(finished["passed_count"], 8)

    def test_wrong_answer_partial_score(self):
        # 覆盖 PRD 第7.1节：部分通过按组等权给分，状态 wrong_answer。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            run = engine.claim_run(db, AT)
            results = [{"case_id": index, "passed": index <= 6, "actual": []}
                       for index in range(1, 9)]
            engine.submit_run_result(db, run["id"], run["worker_token"], AT, None, results)
            db.commit()
        finished = self._run()
        self.assertEqual(finished["status"], "wrong_answer")
        self.assertEqual(finished["score_hundredths"], 7500)
        self.assertEqual(finished["passed_count"], 6)

    def test_stale_worker_cannot_resurrect_or_overwrite(self):
        # 覆盖 R29：过期未扫描任务不能被旧 worker 复活；迟到结果不覆盖已终结任务。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            run = engine.claim_run(db, AT)
            token = run["worker_token"]
            db.commit()
            # 租约到期后回收 → system_error WORKER_LOST。
            late = AT + timedelta(seconds=engine.LEASE_SECONDS + 1)
            db.execute("BEGIN IMMEDIATE")
            engine.reclaim_expired(db, late)
            db.commit()
            self.assertEqual(self._run()["status"], "system_error")
            # 旧 worker 续租与提交都失败，二次回收不重复改写。
            db.execute("BEGIN IMMEDIATE")
            self.assertFalse(engine.renew_lease(db, run["id"], token, late))
            self.assertFalse(engine.submit_run_result(
                db, run["id"], token, late, None,
                [{"case_id": index, "passed": True, "actual": []} for index in range(1, 9)]))
            engine.reclaim_expired(db, late)
            db.commit()
        finished = self._run()
        self.assertEqual(finished["status"], "system_error")
        self.assertEqual(finished["error_code"], "WORKER_LOST")
        self.assertIsNone(finished["score_hundredths"])

    def test_queue_timeout_and_terminal_immutable(self):
        # 覆盖 PRD 第7节/AC-11：排队超30分钟 system_error；限额终态固定不可变。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            engine.reclaim_expired(db, AT + timedelta(minutes=31))
            db.commit()
            self.assertEqual(self._run()["status"], "system_error")
            # 已终态任务领取不到（claim 只领 queued）。
            db.execute("BEGIN IMMEDIATE")
            self.assertIsNone(engine.claim_run(db, AT))
            db.commit()

    def test_zero_executed_is_system_error_not_full_score(self):
        # 覆盖 AC-05/AC-11：引擎完成但实际执行 0 条 → INCOMPLETE_RESULT，不判满分。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            run = engine.claim_run(db, AT)
            engine.submit_run_result(db, run["id"], run["worker_token"], AT,
                                     "INCOMPLETE_RESULT", [])
            db.commit()
        finished = self._run()
        self.assertEqual(finished["status"], "system_error")
        self.assertEqual(finished["error_code"], "INCOMPLETE_RESULT")
        self.assertIsNone(finished["score_hundredths"])

    def test_validation_lifecycle(self):
        # 覆盖 DBD 第7节：验证 passed 需标准全过 + 反例功能失败。
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO file_object(id,owner_id,storage_key,original_name,media_type,"
                       "size_bytes,sha256,purpose,created_at) "
                       "VALUES(2,1,'k2','b.circ','application/xml',10,'h2','grading_reference:correct','x')")
            db.execute("INSERT INTO reference_file(id,experiment_version_id,file_id,kind,sha256,"
                       "created_at) VALUES(1,1,1,'correct','r','x')")
            db.execute("INSERT INTO reference_file(id,experiment_version_id,file_id,kind,sha256,"
                       "created_at) VALUES(2,1,2,'known_wrong','n','x')")
            db.execute("INSERT INTO test_suite_validation(id,suite_id,profile_sha256,suite_sha256,"
                       "jar_sha256,reference_file_id,reference_sha256,negative_file_id,"
                       "negative_sha256,status,created_at) "
                       "VALUES(1,1,'p','c',NULL,1,'r',2,'n','queued','x')")
            db.commit()
            db.execute("BEGIN IMMEDIATE")
            row = engine.claim_validation(db, AT)
            self.assertEqual(row["status"], "running")
            self.assertTrue(engine.submit_validation_result(
                db, row["id"], row["worker_token"], AT, True, True))
            self.assertFalse(engine.submit_validation_result(
                db, row["id"], row["worker_token"], AT, True, True))
            db.commit()
        with closing(connect(self.path)) as db:
            row = db.execute("SELECT * FROM test_suite_validation WHERE id=1").fetchone()
            self.assertEqual(row["status"], "passed")
            self.assertEqual(json.loads(row["result_json"])["reference"], "all_passed")

