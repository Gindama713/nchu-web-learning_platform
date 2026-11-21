"""Reconcile the existing 131 rows against the reviewed postmerge evidence.

Only statuses supported by the finite recheck change. Original changed fields
are retained per row; every other original field must round-trip byte-for-value.
This script does not run business tests or approve course/release acceptance.
"""

import argparse
import copy
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "2973bef7bfadb429fe8b17cfadf2d3a2685c796a"
JSON_PATH = "docs/evidence/c12a/acceptance-matrix.json"
MD_PATH = "docs/evidence/c12a/acceptance-matrix.md"
EVIDENCE = "docs/evidence/postmerge-20261019"
REPORT = "docs/SPEC-010B_POSTMERGE_ACCEPTANCE.md"


def source(path):
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT).decode("utf-8")


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counts(rows):
    return {key: dict(Counter(row[key] for row in rows)) for key in ("结果", "集成结果")}


def reconcile(proof):
    assert proof["baseline"] == BASE and proof["validation_passed"] is True
    assert proof["handler_tests"] == 17 and proof["expected_failures"] == 0
    assert proof["backend"]["failed"] == proof["frontend"]["failed"] == 0
    assert proof["backend"]["tests"] > 0 and proof["frontend"]["tests"] > 0
    assert proof["browser_groups_per_channel"] == {"r37": 6, "i03": 7, "qa": 9, "recommendation": 7}
    assert proof["all_merge_ancestry_passed"] and proof["all_formal_dirty_paths_empty"]
    original = json.loads(source(JSON_PATH))
    rows = copy.deepcopy(original)
    assert len(rows) == 131 and len({row["编号"] for row in rows}) == 131
    promoted = {"SPEC-005/R20", *(f"SPEC-011/{key}" for key in
                ("AC-02", "R20", "R35", "R46", "NF-SEC", "NF-UI")),
                *(f"SPEC-012/{key}" for key in
                ("AC-01", "AC-02", "AC-03", "AC-04", "R20", "R34", "R35", "R46", "NF-SEC"))}
    gaps = {
        "R22": "本人基础、统计、难点及合入证据齐备；全组CP/M9及教师检查尚缺实际结论，组长协调。",
        "R45": "本人算法与重放证据已登记；固定引擎、全组技术验证和实际工时不由本包代验。",
        "R47": "#27—#35已由#38审计整合；该记录不替代逐项完整课程非作者复核、问题关闭及教师结论。",
        "NF-PERF": "仍缺Linux4核8GB/50会话/真实worker及API p95测量；本机测试耗时不代替目标性能。",
        "NF-DATA": "受控SQLite恢复证据保留；生产数据库/资源/电路同点恢复及课程验收后90天治理仍未完成。",
        "NF-ISOLATION": "018/010D代码已合入；固定JAR真实运行、无网络/主库/他人文件隔离仍缺实际环境证据，石佰合主责。",
    }
    ui_gaps = {
        "SPEC-005/NF-UI": "005图文仍缺003授权图片与知识资源引用契约；本包未放开img/链接，黄俊诚与石佰合对接。",
        "SPEC-006/R01": "资源/全部旧版/备课API保护证据保留，R37两项接口已复验通过；仍缺004备课页面及完整I-03角色链。",
        "SPEC-008/R01": "资源/全部旧版/备课API保护证据保留，R37两项接口已复验通过；仍缺004备课页面及完整I-03角色链。",
        "SPEC-006/R02": "007列表和真实revision复验通过；仍缺007课堂演示页面及从演示进入知识/quiz的可操作入口。",
        "SPEC-008/R02": "007列表和真实revision复验通过；仍缺007课堂演示页面及从演示进入知识/quiz的可操作入口。",
        "SPEC-008/R37": "R37-004-01/02已修复，8项handler及双浏览器各6组通过；004备课页面仍缺，完整R37不关闭。",
        "SPEC-006/R44": "本人错题→010B→011及004/008接口子链复验通过；004/007页面及完整I-03故障分支仍缺。",
        "SPEC-008/R44": "本人错题→010B→011及004/008接口子链复验通过；004/007页面及完整I-03故障分支仍缺。",
    }
    changes = []
    for old, row in zip(original, rows, strict=True):
        identifier = row["编号"]
        suffix = identifier.split("/")[-1]
        if identifier in promoted:
            row["集成结果"] = "通过"
            if identifier == "SPEC-005/R20":
                row["结果"] = "通过"
            row["队友环境或剩余缺口"] = "本人适用子能力已在合入后的develop复验；完整跨链、共通/NF与课堂另行判定。"
            row["本轮补验"] += "；2026-10-19合入后复验见 ../../SPEC-010B_POSTMERGE_ACCEPTANCE.md；005/R20仅005基础标记/revision→011索引适用部分，不代验014/016。"
        elif suffix in gaps:
            row["队友环境或剩余缺口"] = gaps[suffix]
        elif identifier in ui_gaps:
            row["队友环境或剩余缺口"] = ui_gaps[identifier]
            row["本轮补验"] += "；合入后已修复的接口与仍缺页面分别登记，见 ../../SPEC-010B_POSTMERGE_ACCEPTANCE.md。"
        changed = {key: old[key] for key in old if row[key] != old[key]}
        if changed:
            row["POSTMERGE_原字段"] = changed
            row["POSTMERGE_核对"] = {
                "基线": BASE, "执行人": "黄俊诚授权的Codex自动核对，非课程批准",
                "日期": proof["date"], "证据": f"{REPORT}; {EVIDENCE}/verification-summary.json",
                "范围": "修复项实际复验、已合入011/012本人适用范围及剩余依赖核对；完整SPEC未关闭",
            }
            changes.append({"编号": identifier, "改变字段": sorted(changed),
                            "原结果": old["结果"], "结果": row["结果"],
                            "原集成结果": old["集成结果"], "集成结果": row["集成结果"]})
        restored = {key: row[key] for key in old}
        restored.update(changed)
        assert restored == old, identifier
    assert len(promoted) == 16
    assert counts(rows) == {"结果": {"通过": 81, "阻断": 50}, "集成结果": {"通过": 81, "阻断": 50}}
    md = source(MD_PATH)
    current = ("\n> 2026-10-19合入后收口：131行，本地81通过/50阻断，集成81通过/50阻断。"
               "16行集成、其中1行本地改判；42行共通/环境及8行页面/整链仍阻断。"
               "下方旧日期数字保留为历史，当前依据[收口报告](../../SPEC-010B_POSTMERGE_ACCEPTANCE.md)。\n")
    md = md.replace("\n", "\n" + current, 1)
    by_id = {row["编号"]: row for row in rows}
    changed_ids = {change["编号"] for change in changes}
    for line in md.splitlines():
        if not line.startswith("| SPEC-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        row = by_id.get(cells[0])
        if row is None or cells[0] not in changed_ids:
            continue
        row["POSTMERGE_核对"]["原Markdown行"] = line
        # Keep the original evidence cell, including branch-specific additions.
        cells[3] += "；合入后收口见 ../../SPEC-010B_POSTMERGE_ACCEPTANCE.md"
        cells[4] = row["结果"] + " / " + row["集成结果"]
        cells[5] = row["队友环境或剩余缺口"]
        md = md.replace(line, "| " + " | ".join(cells) + " |")
    assert len(re.findall(r"^\| SPEC-", md, re.MULTILINE)) == 131
    current_lines = {line.split("|")[1].strip(): line for line in md.splitlines()
                     if line.startswith("| SPEC-")}
    for old_line in source(MD_PATH).splitlines():
        if old_line.startswith("| SPEC-"):
            identifier = old_line.split("|")[1].strip()
            if identifier not in changed_ids:
                assert current_lines[identifier] == old_line
            else:
                assert by_id[identifier]["POSTMERGE_核对"]["原Markdown行"] == old_line
    audit = {"baseline": BASE, "rows": len(rows), "before": counts(original), "after": counts(rows),
             "promoted_integration": sorted(promoted), "changed_rows": changes,
             "original_fields_restorable": True,
             "baseline_json_sha256": hashlib.sha256(source(JSON_PATH).encode()).hexdigest(),
             "by_spec": {spec: counts([row for row in rows if row["spec"] == spec])
                         for spec in dict.fromkeys(row["spec"] for row in rows)}}
    return rows, md, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write reviewed reconciliation; otherwise verify")
    args = parser.parse_args()
    proof = json.loads((ROOT / EVIDENCE / "verification-summary.json").read_text(encoding="utf-8"))
    rows, md, audit = reconcile(proof)
    if args.write:
        dump(ROOT / JSON_PATH, rows)
        (ROOT / MD_PATH).write_text(md, encoding="utf-8")
        dump(ROOT / EVIDENCE / "reconciliation.json", audit)
    else:
        assert json.loads((ROOT / JSON_PATH).read_text(encoding="utf-8")) == rows
        assert (ROOT / MD_PATH).read_text(encoding="utf-8") == md
        assert json.loads((ROOT / EVIDENCE / "reconciliation.json").read_text(encoding="utf-8")) == audit
    print(json.dumps({"rows": audit["rows"], "after": audit["after"],
                      "promoted_integration": len(audit["promoted_integration"]),
                      "original_fields_restorable": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
