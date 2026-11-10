"""SPEC-009 电路实验台：芯片级电路模拟、控制与「后台数据缺失」判定。

页面（frontend/js/circuit-lab-view.js）按这里的定义渲染 SVG 电路图：
开关、指示灯、芯片、正交导线与接地符号全部由 spec 描述，前端不猜坐标。

四个端点（与既有 ``/alu74181/*`` 演示接口一样，纯计算的 spec / compute / table 公开）：

* ``/circuit-lab/spec``      实验定义（芯片/引脚/连线/验证用例）+ data_ready 就绪状态
* ``/circuit-lab/bootstrap`` 逐项列出后台缺失的数据与记录数，**需登录**（避免匿名枚举业务表）
* ``/circuit-lab/compute``   芯片功能表权威求值，用于复核前端模拟与回归测试
* ``/circuit-lab/table``     完整真值表，用于回归测试与前端索引

data_ready 只依赖既有业务表（course / experiment / experiment_version /
test_case / judge_profile / grading_run），不新增迁移；因此「空库」与
「已初始化」两种场景会给出可对照的、可复现的结论。
"""

import re
import sqlite3

from flask import Blueprint, request

from backend.apis.alu import MASK
from backend.apis.alu import evaluate as evaluate_74181
from backend.shared.api import ApiError, result
from backend.shared.auth import require_user
from backend.shared.db import get_db

bp = Blueprint("circuit_lab", __name__)

# ---------------------------------------------------------------------------
# 芯片功能表（服务端权威实现）
# ---------------------------------------------------------------------------


def evaluate_7485(a, b, i_lt=0, i_eq=1, i_gt=0):
    """7485 四级数值比较器。

    A≠B 时级联输入被忽略；A=B 时输出直接跟随级联输入（实验台默认
    I(A<B)=0, I(A=B)=1, I(A>B)=0，即单片工作时的相等状态）。
    """
    for name, value in (("a", a), ("b", b), ("i_lt", i_lt), ("i_eq", i_eq), ("i_gt", i_gt)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= (
                MASK if name in ("a", "b") else 1):
            raise ApiError(400, "VALIDATION_ERROR", f"{name} 取值超出范围")
    if a > b:
        gt, eq, lt = 1, 0, 0
    elif a < b:
        gt, eq, lt = 0, 0, 1
    else:
        gt, eq, lt = i_gt, i_eq, i_lt
    return {
        "a": a, "b": b,
        "a_bits": format(a, "04b"), "b_bits": format(b, "04b"),
        "i_lt": i_lt, "i_eq": i_eq, "i_gt": i_gt,
        "gt": gt, "eq": eq, "lt": lt,
        # 级联输入全 0 时三路输出都为低（单片 7485 不会这样接），不能误报 A<B。
        "relation": "A>B" if gt else "A=B" if eq else "A<B" if lt else "无有效输出",
        "bits": [((a >> bit) & 1) for bit in (3, 2, 1, 0)],
    }


def query_int(name, low, high, default=None):
    raw = request.args.get(name)
    if raw is None:
        if default is None:
            raise ApiError(400, "VALIDATION_ERROR", f"{name} 为必填参数")
        return default
    text = raw.strip()
    # 只接受 ASCII 十进制：str.isdigit() 会把 "²" / "１" 判为数字，而 int() 对它们
    # 或 "--1" / "1_0" / 超长整数会抛 ValueError，旧写法会让这些请求变成 500。
    if not re.fullmatch(r"-?[0-9]+", text):
        raise ApiError(400, "VALIDATION_ERROR", f"{name} 必须是 {low}—{high} 的整数")
    try:
        value = int(text)
    except ValueError as exc:  # CPython 对超长十进制串有位数上限
        raise ApiError(400, "VALIDATION_ERROR", f"{name} 必须是 {low}—{high} 的整数") from exc
    if not low <= value <= high:
        raise ApiError(400, "VALIDATION_ERROR", f"{name} 必须是 {low}—{high} 的整数")
    return value


# ---------------------------------------------------------------------------
# 电路图定义（坐标落在 760 × 600 的 viewBox 内，导线一律正交）
# ---------------------------------------------------------------------------


def _switch(pin_id, label, x, y, group, bit, side="top", initial=0):
    return {"id": pin_id, "label": label, "kind": "switch", "x": x, "y": y,
            "group": group, "bit": bit, "side": side, "initial": initial}


def _lamp(pin_id, label, x, y, output, side="bottom"):
    return {"id": pin_id, "label": label, "kind": "lamp", "x": x, "y": y,
            "output": output, "side": side}


def _wire(pin_id, points, tone="signal"):
    return {"from": pin_id, "points": points, "tone": tone}


def _build_7485():
    top_labels = ["A3", "B3", "A2", "B2", "A1", "B1", "A0", "B0"]
    pins, wires = [], []
    for index, label in enumerate(top_labels):
        x = 180 + index * 58
        group, bit = label[0], 3 - index // 2
        pins.append(_switch(label, label, x, 120, group, bit))
        wires.append(_wire(label, [[x, 138], [x, 230]]))
    for index, (pin_id, label, out) in enumerate((
            ("I_LT", "I(A<B)", "lt"), ("I_EQ", "I(A=B)", "eq"), ("I_GT", "I(A>B)", "gt"))):
        x = 180 + index * 62
        pins.append(_switch(pin_id, label, x, 470, "cascade", 2 - index,
                            side="bottom", initial=1 if index == 1 else 0))
        wires.append(_wire(pin_id, [[x, 452], [x, 340]]))
    for index, (pin_id, label, out) in enumerate((
            ("O_GT", "A>B", "gt"), ("O_EQ", "A=B", "eq"), ("O_LT", "A<B", "lt"))):
        x = 440 + index * 88
        pins.append(_lamp(pin_id, label, x, 440, out))
        wires.append(_wire(pin_id, [[x, 340], [x, 422]]))
    wires.append(_wire("gnd", [[150, 340], [150, 520], [616, 520], [616, 340]], "ground"))
    return {
        "id": "7485",
        "title": "7485 · 4 位数值比较器",
        "subtitle": "验证 7485 大小比较",
        "chip": {"label": "7485", "sub": "4 位数值比较器", "x": 150, "y": 230, "w": 460, "h": 110},
        "ground": {"x": 150, "y": 520},
        "pins": pins,
        "wires": wires,
        "doc": [
            {"title": "验证 7485 大小比较",
             "body": "把 A3..A0 与 B3..B0 拨到指定值，观察 A>B / A=B / A<B 三只指示灯。"
                     "只有一路为高电平；两数相等时输出由级联输入决定。",
             "hint": "输入已变化，请重新运行并检查比较结果。"},
            {"title": "级联输入的作用",
             "body": "保持 A=B，依次改变 I(A<B)、I(A=B)、I(A>B)，观察相等状态如何向低位传递。",
             "hint": "A=B 时级联输入直接决定输出。"},
            {"title": "全组合自检",
             "body": "任选一组 A、B 与级联输入，与右侧真值表逐行核对，确认三种关系互斥且完备。",
             "hint": "任意输入下 gt / eq / lt 恰好一个为 1。"},
        ],
        "cases": [
            {"id": "c1", "name": "A=9, B=3", "inputs": {"A": 9, "B": 3, "I_LT": 0, "I_EQ": 1, "I_GT": 0},
             "expected": {"gt": 1, "eq": 0, "lt": 0}, "note": "A 大于 B，A>B 灯亮"},
            {"id": "c2", "name": "A=6, B=6", "inputs": {"A": 6, "B": 6, "I_LT": 0, "I_EQ": 1, "I_GT": 0},
             "expected": {"gt": 0, "eq": 1, "lt": 0}, "note": "相等且级联 A=B=1，A=B 灯亮"},
            {"id": "c3", "name": "A=2, B=11", "inputs": {"A": 2, "B": 11, "I_LT": 0, "I_EQ": 1, "I_GT": 0},
             "expected": {"gt": 0, "eq": 0, "lt": 1}, "note": "A 小于 B，级联输入应被忽略"},
        ],
        "control_rows": [
            {"label": "A[3:0]", "key": "A", "type": "numeric", "hint": "0—15"},
            {"label": "B[3:0]", "key": "B", "type": "numeric", "hint": "0—15"},
            {"label": "I(A<B)", "key": "I_LT", "type": "toggle"},
            {"label": "I(A=B)", "key": "I_EQ", "type": "toggle"},
            {"label": "I(A>B)", "key": "I_GT", "type": "toggle"},
        ],
        "outputs": [
            {"key": "gt", "label": "A>B"}, {"key": "eq", "label": "A=B"}, {"key": "lt", "label": "A<B"},
        ],
    }


def _build_74181():
    top_labels = ["A3", "A2", "A1", "A0", "B3", "B2", "B1", "B0"]
    pins, wires = [], []
    for index, label in enumerate(top_labels):
        x = 180 + index * 46
        group, bit = label[0], 3 - index % 4
        pins.append(_switch(label, label, x, 120, group, bit))
        wires.append(_wire(label, [[x, 138], [x, 230]], "address" if index < 4 else "signal"))
    for index, label in enumerate(("S3", "S2", "S1", "S0", "M", "Cn")):
        x = 180 + index * 66
        pins.append(_switch(label, "Cn̄" if label == "Cn" else label, x, 480, "control", 5 - index,
                            side="bottom", initial=0))
        wires.append(_wire(label, [[x, 462], [x, 340]], "control"))
    for index, label in enumerate(("F3", "F2", "F1", "F0")):
        x = 250 + index * 56
        pins.append(_lamp(label, label, x, 400, "f" + str(3 - index)))
        wires.append(_wire(label, [[x, 340], [x, 382]], "result"))
    pins.append(_lamp("CN4", "Cn+4", 570, 400, "cn4"))
    wires.append(_wire("CN4", [[570, 340], [570, 382]], "result"))
    # 7400 控制译码回路：与参考图一致的绿色回环
    wires.append(_wire("dec_loop", [[180, 138], [140, 138], [140, 90], [660, 90],
                                    [660, 560], [140, 560], [140, 340]], "loop"))
    wires.append(_wire("gnd", [[140, 340], [140, 540], [150, 540]], "ground"))
    return {
        "id": "74181",
        "title": "74181 + 7400 · 4 位加减运算",
        "subtitle": "验证 74181 减法",
        "chip": {"label": "74181", "sub": "四位算术逻辑单元", "x": 150, "y": 230, "w": 300, "h": 110},
        "chip2": {"label": "7400", "sub": "控制译码", "x": 510, "y": 250, "w": 140, "h": 80},
        "ground": {"x": 140, "y": 540},
        "pins": pins,
        "wires": wires,
        "doc": [
            {"title": "验证 74181 减法",
             "body": "拨动 A3..A0、B3..B0 与 S3..S0 / M / Cn̄，在 F3..F0 上观察结果。"
                     "减法时 S=0110、M=0、Cn̄=0，芯片内部按 A + B̄ + 1 运算。",
             "hint": "控制位变化后请重新验算，确认 F 与 Cn+4。"},
            {"title": "加法与进位",
             "body": "切换为加法（S=1001、M=0、Cn̄=1），让 A+B 超过 15，观察 Cn+4 变低。",
             "hint": "15 + 1 会产生最高位进位。"},
        ],
        "cases": [
            {"id": "d1", "name": "9 − 4", "inputs": {"A": 9, "B": 4, "OP": "sub"},
             "expected": {"f": 5, "cn4": 0}, "note": "无借位，F=0101，Cn+4 为低有效进位输出"},
            {"id": "d2", "name": "1 − 15 借位", "inputs": {"A": 1, "B": 15, "OP": "sub"},
             "expected": {"f": 2, "cn4": 1}, "note": "补码结果 0x2；Cn+4 变高表示需要借位"},
        ],
        "control_rows": [
            {"label": "A[3:0]", "key": "A", "type": "numeric", "hint": "0—15"},
            {"label": "B[3:0]", "key": "B", "type": "numeric", "hint": "0—15"},
            {"label": "S3S2S1S0", "key": "S", "type": "text"},
            {"label": "M（模式）", "key": "M", "type": "toggle"},
            {"label": "Cn̄（进位输入）", "key": "Cn", "type": "toggle"},
            {"label": "运算", "key": "OP", "type": "choice", "options": ["add", "sub"]},
        ],
        "outputs": [
            {"key": "f", "label": "F[3:0]"}, {"key": "cn4", "label": "Cn+4"},
            {"key": "zero", "label": "结果为零"}, {"key": "equal", "label": "A=B"},
        ],
    }


EXPERIMENTS = [_build_7485(), _build_74181()]

# ---------------------------------------------------------------------------
# 后台数据就绪判定
# ---------------------------------------------------------------------------

DATA_ITEMS = (
    ("course", "课程", "SELECT COUNT(*) FROM course",
     "python scripts/seed_teacher_course.py"),
    ("course_member", "课程参与名单", "SELECT COUNT(*) FROM course_member WHERE active=1",
     "python scripts/seed_demo_roster.py"),
    ("experiment", "实验", "SELECT COUNT(*) FROM experiment", "教师端「实验中心」新建实验"),
    ("experiment_version", "已发布实验版本",
     "SELECT COUNT(*) FROM experiment_version WHERE status='published'", "教师端发布实验版本"),
    ("judge_profile", "判分配置", "SELECT COUNT(*) FROM judge_profile", "教师端配置 judge profile"),
    ("test_case", "测试用例", "SELECT COUNT(*) FROM test_case", "教师端创建测试集"),
    ("grading_run", "评测记录", "SELECT COUNT(*) FROM grading_run", "学生提交 .circ 后产生"),
    ("resource", "教学资源", "SELECT COUNT(*) FROM resource", "教师端上传资源"),
)


def readiness():
    """逐表统计，返回缺失项与补全建议；SQL 出错时降级为「未知」而不是 500。"""
    db = get_db()
    items, missing = [], []
    for key, label, sql, hint in DATA_ITEMS:
        try:
            count = db.execute(sql).fetchone()[0]
        except sqlite3.Error:  # 迁移未跑完时表可能不存在
            # 不要把 sqlite 的原始错误文本回给客户端：里面可能含表名 / 列名。
            items.append({"key": key, "label": label, "count": None,
                          "ready": False, "hint": hint})
            missing.append(label)
            continue
        ready = count > 0
        items.append({"key": key, "label": label, "count": count,
                      "ready": ready, "hint": hint})
        if not ready:
            missing.append(label)
    return {"data_ready": not missing, "missing": missing, "items": items,
            "total_items": len(items),
            "ready_items": sum(1 for item in items if item["ready"])}


@bp.get("/circuit-lab/spec")
def spec():
    """实验定义 + 后台就绪状态。定义是静态的，就绪状态随数据库变化。"""
    state = readiness()
    return result({
        "experiments": EXPERIMENTS,
        "data_ready": state["data_ready"],
        "missing": state["missing"],
        "chips": ["7485", "74181", "7400"],
    })


@bp.get("/circuit-lab/bootstrap")
def bootstrap():
    """给页面与验收脚本用的归因依据：登录后「不可用」是不是数据缺失造成。"""
    require_user()  # 逐表记录数属于内部运营数据，不对未登录请求开放
    return result(readiness())


@bp.get("/circuit-lab/compute")
def compute():
    """按芯片功能表权威求值；前端模拟可与之逐组合比对。"""
    chip = request.args.get("chip", "7485")
    if chip == "7485":
        return result(evaluate_7485(
            query_int("a", 0, MASK), query_int("b", 0, MASK),
            query_int("i_lt", 0, 1, 0), query_int("i_eq", 0, 1, 1), query_int("i_gt", 0, 1, 0)))
    if chip == "74181":
        op = request.args.get("op", "sub")
        if op not in ("add", "sub"):
            raise ApiError(400, "VALIDATION_ERROR", "op 只能是 add 或 sub")
        return result(evaluate_74181(query_int("a", 0, MASK), query_int("b", 0, MASK), op))
    raise ApiError(400, "VALIDATION_ERROR", "chip 只能是 7485 或 74181")


@bp.get("/circuit-lab/table")
def table():
    """完整真值表，用于回归测试与前端索引（7485 含 3 个级联位，共 2048 行）。"""
    chip = request.args.get("chip", "7485")
    if chip == "7485":
        rows = [evaluate_7485(a, b, i_lt, i_eq, i_gt)
                for a in range(16) for b in range(16)
                for i_lt in (0, 1) for i_eq in (0, 1) for i_gt in (0, 1)]
    elif chip == "74181":
        rows = [evaluate_74181(a, b, op) for op in ("add", "sub")
                for a in range(16) for b in range(16)]
    else:
        raise ApiError(400, "VALIDATION_ERROR", "chip 只能是 7485 或 74181")
    return result({"chip": chip, "count": len(rows), "rows": rows})
