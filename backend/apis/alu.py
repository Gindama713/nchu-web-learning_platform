"""SPEC-019 专业组在线实验：74181 + 7400 四位加法/减法运算器。

只实现任务书要求的两种运算（A+B、A−B），口径严格按 74181 功能表：
    加法：S3S2S1S0=1001，M=0（算术模式），Cn̄=H（无进位输入）→ F = A plus B
    减法：S3S2S1S0=0110，M=0（算术模式），Cn̄=L（进位输入有效）→ F = A minus B
减法在芯片内部是 A + B̄ + 1，这里按同一口径实现，不额外假设未使用的功能行。

接口均为公开 GET（纯计算、无副作用），不写库、不需登录，方便课堂互测直接核对。
"""

from flask import Blueprint, request

from backend.shared.api import ApiError, result

bp = Blueprint("alu", __name__)

BITS = 4
MASK = (1 << BITS) - 1

ROWS = {
    "add": {
        "op": "add",
        "label": "加法 A + B",
        "s": 0b1001,
        "m": 0,
        "cn_bar": 1,
        "invert_b": False,
        "formula": "F = A plus B",
        "note": "Cn̄ 保持高电平，不注入进位，得到 A 与 B 的直加。",
    },
    "sub": {
        "op": "sub",
        "label": "减法 A − B",
        "s": 0b0110,
        "m": 0,
        "cn_bar": 0,
        "invert_b": True,
        "formula": "F = A minus B",
        "note": "Cn̄ 拉低注入进位，芯片内部按 A + B̄ + 1 完成补码减法。",
    },
}

CHIP_74181 = {
    "model": "74181",
    "title": "四位算术逻辑单元 ALU",
    "terminals": {
        "data_in": ["A0", "A1", "A2", "A3", "B0", "B1", "B2", "B3"],
        "control": ["S0", "S1", "S2", "S3", "M", "Cn̄"],
        "data_out": ["F0", "F1", "F2", "F3"],
        "status": ["Cn+4", "P̄", "Ḡ", "A=B"],
    },
    "notes": [
        "M=0 为算术模式，M=1 为逻辑模式；本实验只用算术模式。",
        "Cn̄ 为低有效进位输入：拉低等于注入 1。",
        "Cn+4 为低有效进位输出：加法溢出降低电平；减法时该脚变高表示需要借位。",
        "A=B 为开集电极输出，两数相等时有效，可直接当零标志使用。",
    ],
}

CHIP_7400 = {
    "model": "7400",
    "title": "四 2 输入与非门",
    "role": "控制译码",
    "notes": [
        "把 ADD/SUB 一个选择信号译成 74181 的 S3–S0 与 Cn̄ 两组控制位。",
        "一片 7400 含 4 个独立与非门，译码这两组控制位够用。",
        "7400 不参与数据通路：A、B 与结果 F 直接连 74181，避免多级门延迟。",
    ],
}


def chip_4(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MASK:
        raise ApiError(400, "VALIDATION_ERROR", f"操作数必须是 0—{MASK} 的整数")
    return value


def query_bit4(name):
    raw = request.args.get(name)
    if raw is None or not raw.strip().isdigit():
        raise ApiError(400, "VALIDATION_ERROR", f"{name} 必须是 0—{MASK} 的整数")
    return chip_4(int(raw.strip()))


def query_op():
    op = request.args.get("op", "add")
    if op not in ROWS:
        raise ApiError(400, "VALIDATION_ERROR", "op 只能是 add 或 sub")
    return op


def evaluate(a, b, op):
    """按 74181 功能表算一次，返回可直接展示的全部中间量。"""
    row = ROWS[op]
    carry_in = 1 - row["cn_bar"]
    operand_b = (~b) & MASK if row["invert_b"] else b
    total = a + operand_b + carry_in
    f = total & MASK
    carry = 1 if total > MASK else 0
    return {
        "op": op,
        "label": row["label"],
        "a": a,
        "b": b,
        "a_bits": format(a, f"0{BITS}b"),
        "b_bits": format(b, f"0{BITS}b"),
        "s": row["s"],
        "s3s2s1s0": format(row["s"], f"0{BITS}b"),
        "m": row["m"],
        "cn_bar": row["cn_bar"],
        "carry_in": carry_in,
        "operand_b": operand_b,
        "operand_b_bits": format(operand_b, f"0{BITS}b"),
        "internal_sum": total,
        "f": f,
        "f_bits": format(f, f"0{BITS}b"),
        "f_hex": f"0x{f:X}",
        "cn4": 0 if carry else 1,
        "carry": carry,
        "borrow": (1 - carry) if op == "sub" else None,
        "zero": 1 if f == 0 else 0,
        "equal": 1 if a == b else 0,
        "decimal_result": a + b if op == "add" else a - b,
        "expression": f"{a} {'+' if op == 'add' else '−'} {b}",
    }


@bp.get("/alu74181/spec")
def spec():
    """公开：芯片资料与两种运算的控制位配置。"""
    operations = {}
    for op, row in ROWS.items():
        operations[op] = {
            "label": row["label"],
            "s3s2s1s0": format(row["s"], f"0{BITS}b"),
            "m": row["m"],
            "cn_bar": row["cn_bar"],
            "formula": row["formula"],
            "note": row["note"],
        }
    return result({
        "experiment": "74181 + 7400 四位加法/减法运算器",
        "chips": [CHIP_74181, CHIP_7400],
        "operations": operations,
        "domains": {"a": [0, MASK], "b": [0, MASK], "bits": BITS},
    })


@bp.get("/alu74181/table")
def table():
    """公开：16×16 全组合结果，前端一次拉取即可本地索引，不必每按一键都请求。"""
    rows = [evaluate(a, b, op) for op in ROWS for a in range(MASK + 1) for b in range(MASK + 1)]
    return result({
        "operations": {op: {"label": row["label"], "s3s2s1s0": format(row["s"], f"0{BITS}b"),
                            "m": row["m"], "cn_bar": row["cn_bar"], "formula": row["formula"]}
                       for op, row in ROWS.items()},
        "count": len(rows),
        "rows": rows,
    })


@bp.get("/alu74181/compute")
def compute():
    """公开：单次运算，供页面复核与互测脚本直接核对。"""
    return result(evaluate(query_bit4("a"), query_bit4("b"), query_op()))
