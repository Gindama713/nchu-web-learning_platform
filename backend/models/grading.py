"""SPEC-018 grading domain: suite validation, .circ preflight, scoring, run models.

评分组满分由 PRD 第7.1节固定模板生成，不接受客户端 weight；
.circ 结构预检按 PRD 第7节执行，解析成功不等于功能正确（功能判定在真实引擎）。
"""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from fractions import Fraction

from backend.shared.api import ApiError

# PRD 第7节：仅接受 Logisim-evolution 5.0.0 基线；具体补丁版本与 JAR 哈希在 TV-01 锁定。
ENGINE_VERSION = "logisim-evolution 5.0.0"
# 平台管理员允许的最大沙箱限额（初始：1核/512MiB/10s/输出1MiB/并发1）。
MAX_LIMITS = {"cpu_seconds": 10, "memory_mib": 512, "output_bytes": 1048576, "processes": 1}
# PRD 第7.1节公开终态码 -> 运行状态映射。
ERROR_CODE_STATUS = {
    "ACCEPTED": "accepted",
    "WRONG_ANSWER": "wrong_answer",
    "TIME_LIMIT": "timeout",
    "MEMORY_LIMIT": "resource_limit",
    "OUTPUT_LIMIT": "resource_limit",
    "CIRCUIT_LOAD_ERROR": "invalid_circuit",
    "ENGINE_UNAVAILABLE": "system_error",
    "ENGINE_CRASH": "system_error",
    "INCOMPLETE_RESULT": "system_error",
    "WORKER_LOST": "system_error",
}
EFFECTIVE_STATUSES = ("accepted", "wrong_answer", "timeout", "resource_limit", "invalid_circuit")
MAX_CIRC_BYTES = 2 * 1024 * 1024
MAX_COMPONENTS = 2000
MAX_NESTING = 20

# PRD 第7.1节固定评分模板（单位：百分之一分；每实验模板组合恒为 10000）。
SCORING_TEMPLATES = {
    "EXP-01": {"ALU": {code: 1250 for code in
                       ("add", "sub", "and", "or", "xor", "not", "shl", "shr")}},
    "EXP-02": {"REG": {code: 2500 for code in ("reset", "hold", "load", "edge")}},
    "EXP-04": {"CPU": {**{code: 1000 for code in
                          ("nop", "ldi", "addi", "subi", "andi", "ori", "jmp", "hlt")},
                       "reset": 800, "hold": 600, "invalid": 600}},
}


def invalid(message):
    return ApiError(400, "INVALID_CIRCUIT", message)


def bad(message):
    return ApiError(400, "VALIDATION_ERROR", message)


def template_for(experiment_code):
    template = SCORING_TEMPLATES.get(experiment_code)
    if template is None:
        raise bad(f"experiment code {experiment_code} has no scoring template")
    # 展开为 group_code -> 组满分；组内多 case 等权（PRD 第7.1节固定模板）。
    groups = {}
    for weights in template.values():
        groups.update(weights)
    return groups, template


def scoring_groups_json(experiment_code):
    groups, _ = template_for(experiment_code)
    return json.dumps({"groups": [{"code": code, "max_hundredths": maximum}
                                  for code, maximum in sorted(groups.items())]}, ensure_ascii=False)


def validate_port_schema(value):
    """port_schema：顶层端口标签 -> 方向与位宽；CLK 禁止（APIC 第7节 steps 约定）。"""
    if not isinstance(value, dict):
        raise bad("port_schema must be an object")
    ports = {}
    for direction in ("inputs", "outputs"):
        side = value.get(direction)
        if not isinstance(side, dict) or not side:
            raise bad(f"port_schema.{direction} must be a non-empty object")
        for label, width in side.items():
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", label):
                raise bad(f"port label {label!r} is invalid")
            if label.upper() == "CLK":
                raise bad("port label CLK is reserved and not allowed")
            if isinstance(width, bool) or not isinstance(width, int) or not 1 <= width <= 8:
                raise bad(f"port {label} width must be an integer between 1 and 8")
            ports[label] = (direction, width)
    if set(value) - {"inputs", "outputs"}:
        raise bad("port_schema accepts only inputs and outputs")
    return value


def validate_allowed_components(value):
    from backend.engines.grading import BASE_COMPONENTS
    if not isinstance(value, list) or not value:
        raise bad("allowed_components must be a non-empty array")
    if len(set(value)) != len(value):
        raise bad("allowed_components must not contain duplicates")
    unknown = [name for name in value if name not in BASE_COMPONENTS]
    if unknown:
        raise bad(f"allowed_components outside the platform whitelist: {unknown}")
    return sorted(value)


def validate_limits(value):
    if not isinstance(value, dict):
        raise bad("limits must be an object")
    if set(value) - set(MAX_LIMITS):
        raise bad("limits accepts only cpu_seconds, memory_mib, output_bytes, processes")
    limits = {}
    for key, maximum in MAX_LIMITS.items():
        raw = value.get(key, maximum)
        if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= maximum:
            raise bad(f"limits.{key} must be an integer between 1 and {maximum}")
        limits[key] = raw
    return limits


def canonical_profile_sha256(top_circuit, port_schema, allowed_components, engine_version, limits):
    """DBD 第7节：包含端口、白名单、限制、引擎身份的规范化哈希。"""
    canonical = {
        "top_circuit": top_circuit,
        "port_schema": {"inputs": dict(sorted(port_schema["inputs"].items())),
                        "outputs": dict(sorted(port_schema["outputs"].items()))},
        "allowed_components": sorted(allowed_components),
        "engine_version": engine_version,
        "limits": {key: limits[key] for key in sorted(limits)},
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _value_for(width, value, field):
    """expected 允许整型或明确的 X/Z；inputs 只允许整型。"""
    if isinstance(value, str) and field == "expected" and value in ("X", "Z"):
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise bad(f"{field} value must be an integer or X/Z")
    if not 0 <= value < (1 << width):
        raise bad(f"{field} value must fit in {width} bits")
    return value


def validate_steps(steps, port_schema=None):
    """APIC 第7节 steps 契约：先稳定输入、施加边沿、传播后采样；CLK 禁止。

    port_schema 为空（草稿尚未配置 judge profile）时仅做类型/范围/边沿校验，
    端口标签与位宽留待验证阶段按 profile 复核。
    """
    if not isinstance(steps, list) or not steps:
        raise bad("steps must be a non-empty array")
    if port_schema:
        widths = {**{label: width for label, width in port_schema["inputs"].items()},
                  **{label: width for label, width in port_schema["outputs"].items()}}
    else:
        widths = None
    last_edge = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise bad("steps items must be objects")
        if set(step) - {"step_no", "inputs", "expected", "clock_event"}:
            raise bad("steps accept only step_no, inputs, expected, clock_event")
        number = step.get("step_no")
        if isinstance(number, bool) or not isinstance(number, int) or number != index + 1:
            raise bad("step_no must be consecutive integers starting at 1")
        inputs, expected = step.get("inputs"), step.get("expected")
        if not isinstance(inputs, dict):
            raise bad("step inputs must be an object")
        for label, value in inputs.items():
            if label.upper() == "CLK":
                raise bad("inputs must not include CLK")
            if port_schema and label not in port_schema["inputs"]:
                raise bad(f"unknown input label {label!r}")
            _value_for(widths[label] if widths else 8, value, "inputs")
        if not isinstance(expected, dict) or not expected:
            raise bad("step expected must be a non-empty object")
        for label, value in expected.items():
            if port_schema and label not in widths:
                raise bad(f"unknown expected label {label!r}")
            _value_for(widths[label] if widths else 8, value, "expected")
        event = step.get("clock_event")
        if event not in ("none", "rising", "falling"):
            raise bad("clock_event must be none, rising or falling")
        if event != "none":
            # 相同方向边沿连续出现必须显式插入反向边沿，不隐式制造边沿。
            if last_edge == event:
                raise bad(f"consecutive {event} edges require an explicit reverse edge")
            last_edge = event
    return steps


def validate_cases(cases, groups, port_schema=None):
    """测试集用例校验；位宽校验依赖 port_schema（无 profile 时留待验证阶段）。

    groups 为展开后的 group_code -> 组满分映射（不接受客户端 weight，R13）。
    """
    if not isinstance(cases, list) or not cases:
        raise bad("cases must be a non-empty array")
    labels = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"label", "visibility", "group_code", "steps"}:
            raise bad("cases accept exactly label, visibility, group_code, steps")
        label = case["label"]
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
            raise bad("case label must be 1-100 characters")
        if label in labels:
            raise bad(f"duplicate case label {label!r}")
        labels.add(label.strip())
        if case["visibility"] not in ("public", "hidden"):
            raise bad("case visibility must be public or hidden")
        if case["group_code"] not in groups:
            raise bad(f"unknown group_code {case['group_code']!r} for this experiment template")
        validate_steps(case["steps"], port_schema)
    return cases


def suite_content_sha256(cases):
    payload = json.dumps(
        [{"label": case["label"].strip(), "visibility": case["visibility"],
          "group_code": case["group_code"], "steps": case["steps"]} for case in cases],
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------- .circ 结构预检（AC-03） ----------

FORBIDDEN_MARKERS = ("<!DOCTYPE", "<!ENTITY", "SYSTEM ", "PUBLIC ")
PATH_ATTRIBUTE = re.compile(r"^(\.\./|/|[A-Za-z]:\\|https?://)")


def preflight_basic(content):
    """无 judge profile 时的基础隔离校验：合法项目 XML、禁止 DTD/外部实体与文件引用。"""
    if not content.lstrip().startswith("<"):
        raise invalid("file must be a Logisim project XML document")
    head = content[:4096].upper()
    for marker in FORBIDDEN_MARKERS:
        if marker in head:
            raise invalid("circuit file must not contain DTD or external entity references")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise invalid(f"circuit file is not valid XML: {exc}") from exc
    if root.tag not in ("logisim-evolution", "logisim"):
        raise invalid("circuit file must be a Logisim project document")
    for comp in root.iter("comp"):
        for attribute in comp.iter("a"):
            name, value = attribute.get("name") or "", attribute.get("val") or ""
            if name in ("ImagePath", "file") or PATH_ATTRIBUTE.match(value):
                raise invalid("external file references are not allowed")
    return True


def preflight_circ(content, profile):
    """按 PRD 第7节做结构预检：禁止 DTD/外部实体与文件引用、白名单、
    顶层名/端口标签/方向/位宽、元件规模、子电路嵌套与递归引用。
    解析成功不等于功能正确；功能判定只发生在真实引擎。
    """
    if not content.startswith("<?xml") and not content.lstrip().startswith("<"):
        raise invalid("file must be a Logisim project XML document")
    head = content[:4096].upper()
    for marker in FORBIDDEN_MARKERS:
        if marker in head:
            raise invalid("circuit file must not contain DTD or external entity references")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise invalid(f"circuit file is not valid XML: {exc}") from exc
    if root.tag not in ("logisim-evolution", "logisim"):
        raise invalid("circuit file must be a Logisim project document")
    circuits = {element.get("name"): element for element in root.findall("circuit")}
    top_name = profile["top_circuit"]
    if top_name not in circuits:
        raise invalid(f"top circuit {top_name!r} not found")
    # 元件规模与文件引用检查（全部电路）。
    total = 0
    for circuit in circuits.values():
        for comp in circuit.iter("comp"):
            total += 1
            if total > MAX_COMPONENTS:
                raise invalid(f"circuit exceeds the {MAX_COMPONENTS} component limit")
            for attribute in comp.iter("a"):
                name, value = attribute.get("name") or "", attribute.get("val") or ""
                if name in ("ImagePath", "file") or PATH_ATTRIBUTE.match(value):
                    raise invalid("external file references are not allowed")
    # 子电路嵌套深度与递归引用（链上重复即递归；菱形共享不判递归）。
    subcircuits = {}
    for circuit in circuits.values():
        names = {comp.get("name") for comp in circuit.iter("comp")} & set(circuits)
        subcircuits[circuit.get("name")] = names

    def check_depth(name, level, path):
        if level > MAX_NESTING:
            raise invalid(f"sub-circuit nesting exceeds {MAX_NESTING} levels")
        for child in subcircuits.get(name, ()):
            if child == name or child in path:
                raise invalid("recursive sub-circuit references are not allowed")
            check_depth(child, level + 1, path | {name})

    check_depth(top_name, 1, frozenset())
    # 顶层端口：标签、方向与位宽必须与 port_schema 一致。
    port_schema = json.loads(profile["port_schema_json"])
    found = {}
    for comp in circuits[top_name].iter("comp"):
        if comp.get("name") != "Pin":
            continue
        attributes = {attribute.get("name"): attribute.get("val")
                      for attribute in comp.iter("a")}
        label = attributes.get("label")
        if not label:
            raise invalid("top circuit pins must carry labels")
        if label in found:
            raise invalid(f"duplicate top circuit pin {label!r}")
        direction = "outputs" if attributes.get("output") == "true" else "inputs"
        try:
            width = int(attributes.get("width", "1"))
        except ValueError as exc:
            raise invalid(f"pin {label!r} has an invalid width") from exc
        found[label] = (direction, width)
    expected = {**port_schema["inputs"], **port_schema["outputs"]}
    for label, (direction, width) in found.items():
        if label not in expected:
            raise invalid(f"unexpected top circuit pin {label!r}")
        if direction != ("outputs" if label in port_schema["outputs"] else "inputs"):
            raise invalid(f"pin {label!r} direction mismatches the judge profile")
        if width != expected[label]:
            raise invalid(f"pin {label!r} width must be {expected[label]}")
    if set(found) != set(expected):
        missing = sorted(set(expected) - set(found))
        raise invalid(f"top circuit is missing pins: {missing}")
    # 元件白名单（Pin 由端口模型控制；子电路已按嵌套规则处理）。
    allowed = set(json.loads(profile["allowed_components_json"])) | {"Pin"} | set(circuits)
    for circuit in circuits.values():
        for comp in circuit.iter("comp"):
            if comp.get("name") not in allowed:
                raise invalid(f"component {comp.get('name')!r} is not in the allowed list")
    return True


def compute_score(groups_max, cases, passed_case_ids):
    """组内等权，组满分固定；Fraction 精确求和后统一四舍五入一次（half-up）。"""
    totals = {group: [0, 0] for group in groups_max}
    for case in cases:
        counter = totals.get(case["group_code"])
        if counter is None:
            continue
        counter[1] += 1
        if case["id"] in passed_case_ids:
            counter[0] += 1
    total = Fraction(0)
    for group, (passed, count) in totals.items():
        if count:
            total += Fraction(groups_max[group] * passed, count)
    # 分组得分相加后统一四舍五入至两位小数（百分之一分）。
    return (2 * total.numerator + total.denominator) // (2 * total.denominator)


def suite_json(row, cases=None, validation=None):
    data = {"id": row["id"], "experiment_version_id": row["experiment_version_id"],
            "version": row["version"], "status": row["status"],
            "total_count": None, "scoring_groups": json.loads(row["scoring_groups_json"]),
            "published_at": row["published_at"], "published_validation_id": row["published_validation_id"]}
    if cases is not None:
        data["total_count"] = len(cases)
        data["cases"] = [{"label": case["label"], "visibility": case["visibility"],
                          "group_code": case["group_code"], "steps": json.loads(case["steps_json"])}
                         for case in cases]
    if validation is not None:
        data["validation"] = validation
    return data


def run_json(run, cases, results, suite_version):
    """APIC 第7节 Run 公开模型；隐藏用例仅给汇总，不回传输入向量或标准答案。"""
    public, hidden_total, hidden_passed, hidden_groups = [], 0, 0, set()
    result_map = {result["case_id"]: result for result in results}
    for case in cases:
        result = result_map.get(case["id"])
        passed = bool(result and result["passed"])
        if case["visibility"] == "public":
            steps = json.loads(case["steps_json"])
            actual = json.loads(result["actual_json"]) if result and result["actual_json"] else None
            public.append({
                "label": case["label"], "group_code": case["group_code"], "passed": passed,
                "input": [step.get("inputs", {}) for step in steps],
                "expected": [step.get("expected", {}) for step in steps],
                "actual": actual,
            })
        else:
            hidden_total += 1
            if passed:
                hidden_passed += 1
            elif result and result["error_code"]:
                hidden_groups.add(result["error_code"])
            else:
                hidden_groups.add("WRONG_ANSWER")
    return {
        "id": run["id"], "submission_id": run["submission_id"], "status": run["status"],
        "score": None if run["score_hundredths"] is None else run["score_hundredths"] / 100,
        "passed_count": run["passed_count"], "executed_count": run["executed_count"],
        "total_count": run["total_count"],
        "public_cases": public,
        "hidden_summary": {"total": hidden_total, "passed": hidden_passed,
                           "failures": sorted(hidden_groups)},
        "engine_version": run["engine_version"], "test_suite_version": suite_version,
        "started_at": run["started_at"], "finished_at": run["finished_at"],
        "error_code": run["error_code"],
        "retry_of": run["retry_of"], "reason": run["reason"],
    }


def submission_json(row, latest_run=None, effective_run=None):
    data = {"id": row["id"], "experiment_version_id": row["experiment_version_id"],
            "student_id": row["student_id"], "filename": row["filename"],
            "file_sha256": row["file_sha256"], "file_size": row["size_bytes"],
            "created_at": row["created_at"],
            "latest_run": latest_run, "effective_run": effective_run}
    return data
