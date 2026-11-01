"""Build the teacher's per-SPEC reading folders from the canonical PRD tables.

Run after editing PRD; review the diff before committing generated documents.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRD = ROOT / "docs" / "PRD.md"
SPECS = ROOT / "specs"

SLUGS = {
    "001": "user-auth", "002": "attendance", "003": "resources",
    "004": "preparation", "005": "knowledge", "006": "exercises",
    "007": "cpu-demo", "008": "quiz", "009": "experiments",
    "010": "analytics", "010A": "attendance-analytics",
    "010B": "knowledge-analytics", "010C": "wiring-analytics",
    "010D": "grading-analytics", "011": "qa", "012": "recommendations",
    "013": "paper-generation", "014": "warnings", "015": "knowledge-graph",
    "016": "recognition", "017": "wiring", "018": "logisim-grading",
    "019": "engineering-delivery",
}
OWNERS = {
    "姜苏豪": {"001", "002", "010A", "014", "016", "019"},
    "黄俊诚": {"005", "006", "008", "010B", "011", "012", "013"},
    "罗浩铭": {"004", "007", "010C", "015", "017"},
    "石佰合": {"003", "009", "010D", "018"},
}
SCREENS = {
    "001": "登录/注册、课程成员与个人资料", "002": "教师签到任务、学生签到、请假审批",
    "003": "资源列表、版本与预览/下载", "004": "备课编辑、发布、学生预习入口",
    "005": "章节目录、知识点阅读与收藏", "006": "题库、作答、错题本与人工评分",
    "007": "教师投屏控制与学生同步视图", "008": "限时答卷、统计与讲评",
    "009": "实验列表、版本指导与提交入口", "010": "四维学习分析入口与筛选",
    "010A": "考勤率、趋势和表现关联", "010B": "掌握度、错题分布、进度与成绩",
    "010C": "实验完成率与连线错误趋势", "010D": "电路通过率、成绩分布与故障",
    "011": "提问、检索片段与出处", "012": "推荐卡片、理由与空结果",
    "013": "教师组卷约束、草稿与重放", "014": "预警列表、原因与处理标记",
    "015": "知识关系图与先修路径", "016": "图片识别预览、置信度与人工确认",
    "017": "实验箱端子、导线、输入开关与运行记录",
    "018": ".circ 上传、排队状态、评测报告与教师重评",
    "019": "PR 检查、发布记录与 Gitea 归档（工程界面）",
}
FLOWS = {
    "001": "注册/登录 → 选择课程 → 查看本人身份；教师管理成员，管理员授权教师。",
    "002": "教师发布时窗与码 → 学生签到/请假 → 教师审批与关闭 → 查看可审计结果。",
    "003": "教师上传并分类 → 发布版本 → 学生筛选、预览或下载 → 教师查看访问统计。",
    "004": "教师编辑关联知识/资源/题目/随堂测 → 校验发布 → 学生阅读预习入口。",
    "005": "教师维护章节与知识点 → 发布 → 学生检索、阅读、收藏并记录完成。",
    "006": "教师建题/发布 → 学生答题 → 客观判分或简答待批 → 错题重练。",
    "007": "教师选预设并单步/复位 → 服务端更新 revision → 学生只读同步投屏。",
    "008": "教师发布窗口 → 学生限时提交 → 教师逐题统计 → 显式讲评后才展示解析。",
    "009": "教师建实验草稿与版本 → 发布 → 学生读指导并进入连线或电路提交。",
    "010": "选课程/时间/维度 → 获取不可变分析快照 → 图表与 CSV 使用同一 ID。",
    "010A": "选择考勤区间 → 看应到/出勤/请假分母和周趋势 → 配对样本关联。",
    "010B": "选择知识或测评类型 → 看掌握度/错题/已发布集合进度 → 查看空样本。",
    "010C": "选择实验版本 → 查看去重完成率、接线错误和尝试趋势。",
    "010D": "选择电路实验/测试集 → 查看有效教学成绩与独立的系统故障统计。",
    "011": "输入 CPU 问题 → 展示真实相似度、已发布片段和出处 → 无结果提示。",
    "012": "按本人错题与进度生成候选 → 显示推荐理由 → 完成/冷启动/空结果。",
    "013": "教师填写数量/分值/难度/覆盖 → 生成草稿 → 核对快照与重放。",
    "014": "教师生成预警批次 → 查看规则与聚类原因/样本数 → 标记已处理。",
    "015": "选择知识点 → 展示先修关系及可复算路径 → 教师维护关系。",
    "016": "上传标准图片 → 查看坐标与置信度 → 人工确认草稿，不直接运行或评分。",
    "017": "选发布实验 → 接线/断线/开关/时钟 → 保存重开 → 结构校验与功能提交。",
    "018": "选发布实验 → 上传 .circ → 查看队列/运行 → 浏览判分报告与重评历史。",
    "019": "feature PR → develop 检查 → release 冒烟 → main 发布 → Gitea 同 SHA 归档。",
}


def table_rows(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.search(r"SPEC-(\d{3}[A-D]?)", cells[0])
        if match:
            rows.setdefault(match.group(1), []).append(cells)
    return rows


def build():
    rows = table_rows(PRD.read_text(encoding="utf-8"))
    if set(SLUGS) - rows.keys():
        raise ValueError(f"PRD missing SPEC rows: {set(SLUGS) - rows.keys()}")
    for code, slug in SLUGS.items():
        folder = SPECS / f"{code.lower()}-{slug}"
        folder.mkdir(parents=True, exist_ok=True)
        planning = next((r for r in rows[code] if len(r) >= 5 and r[1].startswith("P")), None)
        scope = next((r for r in rows[code] if len(r) >= 3 and not r[1].startswith("P")
                      and (r[0].startswith(f"SPEC-{code} ") or r[0] == f"SPEC-{code}")), None)
        # 010A-D acceptance is in its own owner table, not the common scope table.
        owner = next((name for name, owned in OWNERS.items() if code in owned), "四人共同负责")
        title = scope[0] if scope and code not in {"010A", "010B", "010C", "010D"} else f"SPEC-{code} {SCREENS[code]}"
        scope_text = scope[1] if scope else "按 PRD 第 4 节对应子规格和第 5 节统计口径实施。"
        acceptance = scope[2] if scope and len(scope) > 2 else "以 PRD 的本规格验收索引、追加规则和具体算例为准。"
        if code in {"010A", "010B", "010C", "010D"}:
            special = next((r for r in rows[code] if len(r) >= 4 and owner in r[0]), None)
            if special:
                scope_text, acceptance = special[1], special[2]
        anchor = f"accept-spec-{code.lower()}"
        common = (f"[PRD 统一验收](../../docs/PRD.md#{anchor}) · "
                  "[接口契约](../../docs/APIC.md) · [数据库设计](../../docs/DBD.md) · "
                  "[架构决策](../../docs/ADR.md)\n")
        priority = planning[1] if planning else "见 PRD"
        deps = planning[2] if planning else "见 PRD"
        milestone = planning[3] if planning else "见 PRD"
        risk = planning[4] if planning else "见 PRD"
        plan = (f"# {title} · plan\n\n{common}\n负责人：{owner}。优先级：{priority}。\n\n"
                f"前置：{deps}。\n\n计划验收：{milestone}。\n\n延期影响：{risk}。\n\n"
                "实施顺序：先核对 PRD/APIC/DBD 契约，再完成真实数据与权限边界，"
                "随后执行本规格验收和跨模块回归，最后登记检查点证据。计划节点不等于已通过验收。\n")
        spec = (f"# {title} · spec\n\n{common}\n负责人：{owner}。\n\n"
                f"范围：{scope_text}\n\n验收摘要：{acceptance}\n\n"
                "本文件是便于按老师目录阅读的模块摘要；规范性字段、状态码、数据约束、"
                "全部 AC 和 R01—R48 仍以链接的主文档为准。变更必须同步主文档，"
                "不得单独改此摘要形成第二套接口。\n")
        if code == "017":
            spec += "\n必做：真实端子接线、断线、输入/运行、保存重开、过程重放和功能判定；详见 [PRD 第 6 节](../../docs/PRD.md#6-spec-017-实验箱连线详细规格)。\n"
        if code == "018":
            spec += "\n必做：.circ 校验、入队、固定引擎真实执行、判分报告与重评；详见 [PRD 第 7 节](../../docs/PRD.md#7-spec-018-电路文件在线评测详细规格)。真实引擎冒烟未通过前不得作为发布完成。\n"
        criteria = re.findall(r"AC-\d+[^；]*", acceptance)
        if code == "017":
            criteria = [
                "按已发布面板版本核对端子、方向、电压位宽与必要输入",
                "接线/断线/开关/时钟/RESET/ENABLE 动作保存并重开重放",
                "结构校验与 EXP-01/02/03 功能用例逐步比对，提交保留快照与错误类型",
                "窗口、冻结名单、退课、重复提交和重做记录按 PRD/APIC 验收",
            ]
        if code == "018":
            criteria = [
                "上传 .circ 后校验格式、大小、组件白名单及对应已发布测试集",
                "固定 Logisim/JAR、真实公开 ALU/REG/CPU 电路及错误电路实测",
                "排队、租约过期、超时、资源限制、引擎故障与教师重评逐项留证",
                "学生报告脱敏，隐藏测试与原文件授权、分数快照和统计一致",
            ]
        if not criteria:
            criteria = ["按 PRD 验收索引逐条核对本规格全部 AC/R 条件与真实样例"]
        checks = "\n".join(f"- [ ] {item.strip()}" for item in criteria)
        tasks = (f"# {title} · tasks\n\n{common}\n负责人：{owner}。下列是验收任务清单，"
                 "未勾选不表示功能不存在，完成必须附测试/运行证据及提交 SHA。\n\n"
                 "- [ ] 核对依赖、权限、接口和表约束，更新同一 PR 的主文档。\n"
                 f"{checks}\n"
                 "- [ ] 验证空值、失败、越权、跨课程和并发/幂等边界。\n"
                 "- [ ] 执行对应后端/前端/浏览器检查，记录检查点、残余风险与回退方式。\n")
        wire = (f"# {title} · wireframes（界面设计）\n\n{common}\n"
                f"核心界面：{SCREENS[code]}。这是交互草图与状态要求，不是浏览器验收证据。\n\n"
                f"主流程：{FLOWS[code]}\n\n"
                "```text\n"
                "┌─ 课程与角色导航 ──────────────────────────────┐\n"
                f"│ {SCREENS[code]} │\n"
                "├─ 筛选/当前状态 ───────────────────────────────┤\n"
                f"│ {FLOWS[code]} │\n"
                "└────────────────────────────────────────────────┘\n"
                "```\n\n"
                "教师只见本课管理与统计；学生只见本人获授权的已发布内容。"
                "动作提交前显示窗口、权限和版本状态；提交后显示服务器返回的结果与 ID。"
                "空样本、未开始/已截止、无权限、校验失败和服务不可用需有独立提示，"
                "不得用零分或空白页代替。移动端保持可读和键盘可操作。\n")
        if code == "017":
            wire += "\n工作区分为器件/端子、连线画布、输入与时钟控制、动作历史、结构/功能反馈五区；保存后重进应恢复同一版本与过程。\n"
        if code == "018":
            wire += "\n上传区显示文件限制与版本；提交后只展示真实队列/运行/终态，报告区区分学生错误和系统故障，教师重评保留旧记录。\n"
        if code == "019":
            wire += "\n此规格使用 GitHub PR/Actions 与 Gitea 的工程页面，不额外开发站内管理页；界面设计关注提交 SHA、检查状态、发布记录与回滚入口。\n"
        for name, content in (("plan.md", plan), ("spec.md", spec),
                              ("tasks.md", tasks), ("wireframes.md", wire)):
            (folder / name).write_text(content, encoding="utf-8")
    index = "# 规格目录\n\n按老师展示的 `specs/001-.../{plan,spec,tasks,wireframes}` 整理。规范正文仍以 [PRD](../docs/PRD.md)、[APIC](../docs/APIC.md)、[DBD](../docs/DBD.md) 为准。\n\n"
    for code, slug in SLUGS.items():
        index += (f"- SPEC-{code}：[计划]({code.lower()}-{slug}/plan.md) · "
                  f"[规格]({code.lower()}-{slug}/spec.md) · "
                  f"[任务]({code.lower()}-{slug}/tasks.md) · "
                  f"[界面设计]({code.lower()}-{slug}/wireframes.md)\n")
    (SPECS / "README.md").write_text(index, encoding="utf-8")


if __name__ == "__main__":
    build()
