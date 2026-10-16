"""SPEC-007 课堂演示 HTTP 适配器与内置可信场景引擎。"""

import json

from flask import Blueprint, request

from backend.shared.api import (
    ApiError,
    audit,
    body,
    non_negative_int,
    page_args,
    paged,
    positive_int,
    result,
    stamp,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("demo", __name__)

PRESETS = ("gate", "comb", "sequential", "alu", "memory", "cpu")
ACTIONS = ("step", "reset", "pause", "run")
MAX_RUN_STEPS = 64


# ---------- 内置可信场景引擎 ----------

def _gate_initial():
    return {"step": 0, "inputs": {"a": 0, "b": 0, "c": 0, "d": 0},
            "outputs": {"and": 0, "or": 0, "not": 0, "xor": 0}, "message": "初始：A=B=C=D=0"}


def _gate_step(state):
    n = (state["step"] + 1) % 16
    a, b, c, d = (n >> 3) & 1, (n >> 2) & 1, (n >> 1) & 1, n & 1
    return {"step": n, "inputs": {"a": a, "b": b, "c": c, "d": d},
            "outputs": {"and": a & b, "or": a | b, "not": 1 - a, "xor": a ^ b},
            "message": f"真值表第 {n} 步：A={a} B={b} C={c} D={d}"}


def _comb_initial():
    return {"step": 0, "a": 0, "b": 0, "sel": 0,
            "mux_out": 0, "alu_out": 0, "message": "组合逻辑初始：A=B=SEL=0"}


def _comb_step(state):
    n = state["step"] + 1
    a = n & 0xF
    b = (n >> 4) & 0xF
    sel = (n >> 8) & 0x3
    mux_out = a if sel == 0 else b
    alu_op = sel
    if alu_op == 0:
        alu_out = (a + b) & 0xF
    elif alu_op == 1:
        alu_out = (a - b) & 0xF
    elif alu_op == 2:
        alu_out = a & b
    else:
        alu_out = a | b
    return {"step": n, "a": a, "b": b, "sel": sel, "mux_out": mux_out, "alu_out": alu_out,
            "message": f"组合：A={a:X} B={b:X} SEL={sel} MUX={mux_out:X} ALU={alu_out:X}"}


def _sequential_initial():
    return {"step": 0, "clock": 0, "d_in": 0, "enable": 1, "q": 0,
            "message": "REG8 初始：Q=0"}


def _sequential_step(state):
    n = state["step"] + 1
    clock = state["clock"] ^ 1
    d_in = n & 0xFF
    enable = (n >> 8) & 1
    q = state["q"]
    if clock == 1 and enable:
        q = d_in
    return {"step": n, "clock": clock, "d_in": d_in, "enable": enable, "q": q,
            "message": f"REG8：CLK={clock} EN={enable} D={d_in:02X} Q={q:02X}"}


def _alu_initial():
    return {"step": 0, "a": 0, "b": 0, "op": 0, "result": 0,
            "flags": {"zero": 0, "carry": 0},
            "message": "ALU8 初始：A=B=0 OP=ADD"}


_ALU_OPS = ("ADD", "SUB", "AND", "OR", "XOR", "NOT", "SHL", "SHR")


def _alu_step(state):
    n = state["step"] + 1
    a = n & 0xFF
    b = (n >> 8) & 0xFF
    op = n % 8
    if op == 0:
        r = a + b
        carry = 1 if r > 0xFF else 0
        result = r & 0xFF
    elif op == 1:
        r = a - b
        carry = 1 if r < 0 else 0
        result = r & 0xFF
    elif op == 2:
        result = a & b
        carry = 0
    elif op == 3:
        result = a | b
        carry = 0
    elif op == 4:
        result = a ^ b
        carry = 0
    elif op == 5:
        result = (~a) & 0xFF
        carry = 0
    elif op == 6:
        result = (a << 1) & 0xFF
        carry = (a >> 7) & 1
    else:
        result = a >> 1
        carry = a & 1
    zero = 1 if result == 0 else 0
    return {"step": n, "a": a, "b": b, "op": op, "op_name": _ALU_OPS[op],
            "result": result, "flags": {"zero": zero, "carry": carry},
            "message": f"ALU：A={a:02X} B={b:02X} {_ALU_OPS[op]} = {result:02X} Z={zero} C={carry}"}


_ROM = [0xA9, 0x05, 0x69, 0x03, 0x8D, 0x10, 0x00, 0xA9, 0x00, 0x4C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]


def _memory_initial():
    return {"step": 0, "address": 0, "data_out": _ROM[0], "rom": list(_ROM),
            "message": f"ROM 读：ADDR=00 DATA={_ROM[0]:02X}"}


def _memory_step(state):
    n = state["step"] + 1
    addr = n % 16
    return {"step": n, "address": addr, "data_out": _ROM[addr], "rom": list(_ROM),
            "message": f"ROM 读：ADDR={addr:02X} DATA={_ROM[addr]:02X}"}


# CPU-EDU-8 内置可信状态机
_CPU_ROM = [
    0xA9, 0x05,   # LDA #5
    0x69, 0x03,   # ADC #3
    0x8D, 0x00, 0x02,  # STA $0200
    0xA9, 0x00,   # LDA #0
    0x4C, 0x00, 0x00,  # JMP $0000
]
_CPU_OPS = {
    0xA9: ("LDA_IMM", 2),
    0x69: ("ADC_IMM", 2),
    0x8D: ("STA_ABS", 3),
    0xA2: ("LDX_IMM", 2),
    0x4C: ("JMP_ABS", 3),
    0xEA: ("NOP", 1),
}


def _cpu_initial():
    mem = [0] * 256
    for i, v in enumerate(_CPU_ROM):
        mem[i] = v
    return {
        "step": 0, "cycle": "fetch", "pc": 0, "ir": 0, "a": 0, "x": 0,
        "flags": {"zero": 0, "carry": 0}, "ram": mem,
        "registers": {"A": "00", "X": "00", "PC": "0000", "IR": "00"},
        "buses": {"addr": "0000", "data": "00"},
        "control": {"fetch": 1, "decode": 0, "execute": 0, "mem_wr": 0, "halt": 0},
        "message": "CPU 复位：PC=0000，等待取指",
    }


def _cpu_step(state):
    pc = state["pc"]
    cycle = state["cycle"]
    a, x = state["a"], state["x"]
    carry = state["flags"]["carry"]
    ram = list(state["ram"])
    n = state["step"] + 1

    if cycle == "fetch":
        ir = ram[pc]
        return {
            "step": n, "cycle": "decode", "pc": (pc + 1) & 0xFFFF,
            "ir": ir, "a": a, "x": x, "flags": state["flags"], "ram": ram,
            "registers": {"A": f"{a:02X}", "X": f"{x:02X}", "PC": f"{(pc + 1) & 0xFFFF:04X}", "IR": f"{ir:02X}"},
            "buses": {"addr": f"{pc:04X}", "data": f"{ir:02X}"},
            "control": {"fetch": 0, "decode": 1, "execute": 0, "mem_wr": 0, "halt": 0},
            "message": f"取指：PC={pc:04X} IR={ir:02X}",
        }

    ir = state["ir"]
    pc_after_fetch = state["pc"]
    op_info = _CPU_OPS.get(ir)

    if cycle == "decode":
        if op_info is None:
            return {
                "step": n, "cycle": "halt", "pc": pc_after_fetch, "ir": ir,
                "a": a, "x": x, "flags": state["flags"], "ram": ram,
                "registers": state["registers"], "buses": state["buses"],
                "control": {"fetch": 0, "decode": 0, "execute": 0, "mem_wr": 0, "halt": 1},
                "message": f"非法 opcode {ir:02X}，CPU 停机",
            }
        name, length = op_info
        return {
            "step": n, "cycle": "execute", "pc": pc_after_fetch, "ir": ir,
            "a": a, "x": x, "flags": state["flags"], "ram": ram,
            "registers": state["registers"],
            "buses": {"addr": f"{pc_after_fetch:04X}", "data": f"{ram[pc_after_fetch] if pc_after_fetch < 256 else 0:02X}"},
            "control": {"fetch": 0, "decode": 0, "execute": 1, "mem_wr": 0, "halt": 0},
            "message": f"译码：{name}（{length} 字节）",
        }

    # execute
    name, length = op_info
    new_pc = (pc_after_fetch + length - 1) & 0xFFFF
    msg = "执行："
    if name == "LDA_IMM":
        a = ram[pc_after_fetch]
        new_pc = (pc_after_fetch + 1) & 0xFFFF
        msg = f"执行：LDA #{a:02X}，A={a:02X}"
    elif name == "ADC_IMM":
        val = ram[pc_after_fetch]
        s = a + val + carry
        a = s & 0xFF
        carry = 1 if s > 0xFF else 0
        new_pc = (pc_after_fetch + 1) & 0xFFFF
        msg = f"执行：ADC #{val:02X}，A={a:02X} C={carry}"
    elif name == "STA_ABS":
        lo = ram[pc_after_fetch]
        hi = ram[(pc_after_fetch + 1) & 0xFFFF]
        addr = (hi << 8) | lo
        if addr < 256:
            ram[addr] = a
        new_pc = (pc_after_fetch + 2) & 0xFFFF
        msg = f"执行：STA ${addr:04X}，存 A={a:02X}"
    elif name == "LDX_IMM":
        x = ram[pc_after_fetch]
        new_pc = (pc_after_fetch + 1) & 0xFFFF
        msg = f"执行：LDX #{x:02X}"
    elif name == "JMP_ABS":
        lo = ram[pc_after_fetch]
        hi = ram[(pc_after_fetch + 1) & 0xFFFF]
        new_pc = (hi << 8) | lo
        msg = f"执行：JMP ${new_pc:04X}"
    elif name == "NOP":
        msg = "执行：NOP"

    zero = 1 if a == 0 else 0
    return {
        "step": n, "cycle": "fetch", "pc": new_pc, "ir": ir, "a": a, "x": x,
        "flags": {"zero": zero, "carry": carry}, "ram": ram,
        "registers": {"A": f"{a:02X}", "X": f"{x:02X}", "PC": f"{new_pc:04X}", "IR": f"{ir:02X}"},
        "buses": {"addr": f"{new_pc:04X}", "data": f"{ram[new_pc] if new_pc < 256 else 0:02X}"},
        "control": {"fetch": 1, "decode": 0, "execute": 0, "mem_wr": 1 if name == "STA_ABS" else 0, "halt": 0},
        "message": msg,
    }


SCENES = {
    "gate": (_gate_initial, _gate_step),
    "comb": (_comb_initial, _comb_step),
    "sequential": (_sequential_initial, _sequential_step),
    "alu": (_alu_initial, _alu_step),
    "memory": (_memory_initial, _memory_step),
    "cpu": (_cpu_initial, _cpu_step),
}


def _initial_state(preset):
    return SCENES[preset][0]()


def _apply_action(state, preset, action):
    if action == "reset":
        return _initial_state(preset)
    if action == "pause":
        return state
    if action == "step":
        return SCENES[preset][1](state)
    # run
    cur = state
    for _ in range(MAX_RUN_STEPS):
        cur = SCENES[preset][1](cur)
        if cur.get("control", {}).get("halt") or cur.get("cycle") == "halt":
            break
    return cur


# ---------- 数据访问 ----------

def _row(db, demo_id):
    return db.execute("SELECT * FROM demo_session WHERE id=?", (demo_id,)).fetchone()


def _serialize(row, state=None):
    if state is None:
        state = json.loads(row["state"])
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "preset": row["preset"],
        "experiment_version_id": row["experiment_version_id"],
        "revision": row["revision"],
        "state": state,
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _experiment_table_exists(db):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_version'").fetchone() is not None


def _validate_experiment(db, course_id, preset, experiment_version_id):
    if experiment_version_id is None:
        if preset in ("cpu", "alu", "sequential"):
            return  # 内置场景，允许不关联实验
        return
    if not _experiment_table_exists(db):
        raise ApiError(503, "EXPERIMENT_MODULE_NOT_READY",
                       "Experiment module (SPEC-009) is not available yet")
    row = db.execute(
        "SELECT ev.id FROM experiment_version ev JOIN experiment e ON e.id=ev.experiment_id "
        "WHERE ev.id=? AND e.course_id=? AND ev.status='published'",
        (experiment_version_id, course_id)).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Related experiment version not found in this course")


# ---------- HTTP 端点 ----------

@bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/courses/<int:course_id>/demo-sessions")
def create_session(course_id):
    course_access(course_id, teacher=True)
    data = body(("preset",), ("experiment_version_id",))
    preset = data["preset"]
    if preset not in PRESETS:
        raise ApiError(400, "VALIDATION_ERROR", "invalid preset")
    experiment_version_id = data.get("experiment_version_id")
    if experiment_version_id is not None:
        experiment_version_id = positive_int(experiment_version_id, "experiment_version_id")
    with write() as db:
        _validate_experiment(db, course_id, preset, experiment_version_id)
        state = _initial_state(preset)
        timestamp = stamp()
        cursor = db.execute(
            "INSERT INTO demo_session(course_id,preset,experiment_version_id,revision,state,active,created_at,updated_at) "
            "VALUES(?,?,?,0,?,1,?,?)",
            (course_id, preset, experiment_version_id, json.dumps(state, ensure_ascii=False),
             timestamp, timestamp))
        demo_id = cursor.lastrowid
        row = _row(db, demo_id)
        audit("demo.create", "demo_session", demo_id,
              after={"preset": preset, "experiment_version_id": experiment_version_id})
    return result(_serialize(row, state), 201)


@bp.put("/demo-sessions/<int:demo_id>/state")
def advance_state(demo_id):
    require_user()
    data = body(("revision", "action"), ("inputs",))
    revision = non_negative_int(data["revision"], "revision")
    action = data["action"]
    if action not in ACTIONS:
        raise ApiError(400, "VALIDATION_ERROR", "invalid action")
    with write() as db:
        row = _row(db, demo_id)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Demo session not found")
        course_access(row["course_id"], teacher=True)
        if not row["active"]:
            raise ApiError(409, "STATE_CONFLICT", "Demo session is closed")
        if row["revision"] != revision:
            raise ApiError(409, "REVISION_CONFLICT", "stale revision",
                           {"current": row["revision"], "provided": revision})
        state = json.loads(row["state"])
        new_state = _apply_action(state, row["preset"], action)
        new_revision = revision + 1
        db.execute(
            "UPDATE demo_session SET revision=?,state=?,updated_at=? WHERE id=?",
            (new_revision, json.dumps(new_state, ensure_ascii=False), stamp(), demo_id))
        audit("demo.advance", "demo_session", demo_id,
              after={"action": action, "revision": new_revision})
    return result(_serialize(row, new_state) | {"revision": new_revision})


@bp.get("/demo-sessions/<int:demo_id>")
def get_session(demo_id):
    require_user()
    after_revision = request.args.get("after_revision")
    if after_revision is not None:
        after_revision = non_negative_int(after_revision, "after_revision")
    db = get_db()
    row = _row(db, demo_id)
    if not row:
        raise ApiError(404, "NOT_FOUND", "Demo session not found")
    course_access(row["course_id"])
    item = _serialize(row)
    if after_revision is not None and item["revision"] <= after_revision:
        item["revision"] = after_revision
    return result(item)


@bp.get("/courses/<int:course_id>/demo-sessions")
def list_sessions(course_id):
    course_access(course_id)
    page, size = page_args()
    db = get_db()
    where = ["course_id=?"]
    params = [course_id]
    active = request.args.get("active")
    if active is not None:
        if active not in ("true", "false"):
            raise ApiError(400, "VALIDATION_ERROR", "active must be true or false")
        where.append("active=?")
        params.append(1 if active == "true" else 0)
    where_sql = " WHERE " + " AND ".join(where)
    total = db.execute("SELECT COUNT(*) FROM demo_session" + where_sql, params).fetchone()[0]
    rows = db.execute("SELECT * FROM demo_session" + where_sql + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    items = [_serialize(r) for r in rows]
    return paged(items, total, page, size)


@bp.post("/demo-sessions/<int:demo_id>/close")
def close_session(demo_id):
    require_user()
    data = body(("revision",))
    revision = non_negative_int(data["revision"], "revision")
    with write() as db:
        row = _row(db, demo_id)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Demo session not found")
        course_access(row["course_id"], teacher=True)
        if row["revision"] != revision:
            raise ApiError(409, "REVISION_CONFLICT", "stale revision",
                           {"current": row["revision"], "provided": revision})
        if not row["active"]:
            return result(_serialize(row))
        db.execute("UPDATE demo_session SET active=0,updated_at=? WHERE id=?",
                   (stamp(), demo_id))
        row = _row(db, demo_id)
        audit("demo.close", "demo_session", demo_id, after={"active": False})
    return result(_serialize(row))
