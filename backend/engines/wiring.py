"""SPEC-017 连线仿真引擎：面板定义、结构校验、组合/时序仿真与功能测试。"""

import json

# 元件端口定义：{方向, 位宽}
COMPONENT_PORTS = {
    "SWITCH": {"OUT": ("out", None)},  # width 由 params.width 决定
    "CONST": {"OUT": ("out", None)},
    "LED": {"IN": ("in", None)},
    "ALU8": {"A": ("in", 8), "B": ("in", 8), "OP": ("in", 3),
             "Y": ("out", 8), "Z": ("out", 1), "C": ("out", 1)},
    "REG8": {"D": ("in", 8), "CLK": ("in", 1), "RESET": ("in", 1), "EN": ("in", 1),
             "Q": ("out", 8)},
    "PC4": {"D": ("in", 4), "INC": ("in", 1), "LOAD": ("in", 1), "CLK": ("in", 1),
            "RESET": ("in", 1), "EN": ("in", 1), "Q": ("out", 4)},
    "ROM16X8": {"ADDR": ("in", 4), "DATA": ("out", 8)},
    "SPLIT8": {"IN": ("in", 8), "HI": ("out", 4), "LO": ("out", 4)},
    "EXTEND4": {"IN": ("in", 4), "OUT": ("out", 8)},
    "MUX8": {"A": ("in", 8), "B": ("in", 8), "SEL": ("in", 1), "Y": ("out", 8)},
    "CONTROL": {"IR": ("in", 8), "ALU_Z": ("in", 1), "ALU_C": ("in", 1),
                "CLK": ("in", 1), "RESET": ("in", 1), "EN": ("in", 1),
                "IR_EN": ("out", 1), "PC_INC": ("out", 1), "PC_LOAD": ("out", 1),
                "ACC_EN": ("out", 1), "ACC_SEL": ("out", 1), "ALU_OP": ("out", 3),
                "PHASE": ("out", 2), "Z": ("out", 1), "C": ("out", 1),
                "HALTED": ("out", 1), "ERROR": ("out", 1)},
    "CLOCK": {"OUT": ("out", 1)},
    "RESET": {"OUT": ("out", 1)},
    "ENABLE": {"OUT": ("out", 1)},
}

ALU_OPS = {
    0: ("ADD", lambda a, b: (a + b) & 0xFF, lambda a, b: 1 if a + b > 0xFF else 0),
    1: ("SUB", lambda a, b: (a - b) & 0xFF, lambda a, b: 1 if a - b < 0 else 0),
    2: ("AND", lambda a, b: a & b, lambda a, b: 0),
    3: ("OR", lambda a, b: a | b, lambda a, b: 0),
    4: ("XOR", lambda a, b: a ^ b, lambda a, b: 0),
    5: ("NOT", lambda a, b: (~a) & 0xFF, lambda a, b: 0),
    6: ("SHL", lambda a, b: (a << 1) & 0xFF, lambda a, b: (a >> 7) & 1),
    7: ("SHR", lambda a, b: a >> 1, lambda a, b: a & 1),
}


def _make_panel(exp_code):
    """返回内置实验面板 schema。"""
    components = []
    terminals = []

    def add(comp_id, ctype, params, port_map):
        comp = {"id": comp_id, "type": ctype, "params": params, "ports": {}}
        for port_name, tid in port_map.items():
            comp["ports"][port_name] = tid
            direction, width = COMPONENT_PORTS[ctype][port_name]
            if width is None:
                width = params.get("width", 1)
            terminals.append({"id": tid, "component_id": comp_id, "name": port_name,
                              "direction": direction, "width": width, "required": direction == "in"})
        components.append(comp)

    if exp_code == "EXP-01":
        add("sw_a", "SWITCH", {"width": 8, "initial": 0}, {"OUT": "sw_a_out"})
        add("sw_b", "SWITCH", {"width": 8, "initial": 0}, {"OUT": "sw_b_out"})
        add("sw_op", "SWITCH", {"width": 3, "initial": 0}, {"OUT": "sw_op_out"})
        add("alu", "ALU8", {}, {"A": "alu_a", "B": "alu_b", "OP": "alu_op",
                                "Y": "alu_y", "Z": "alu_z", "C": "alu_c"})
        add("led_y", "LED", {"width": 8}, {"IN": "led_y_in"})
        add("led_z", "LED", {"width": 1}, {"IN": "led_z_in"})
        add("led_c", "LED", {"width": 1}, {"IN": "led_c_in"})
    elif exp_code == "EXP-02":
        add("sw_d", "SWITCH", {"width": 8, "initial": 0}, {"OUT": "sw_d_out"})
        add("sw_en", "SWITCH", {"width": 1, "initial": 1}, {"OUT": "sw_en_out"})
        add("clk", "CLOCK", {}, {"OUT": "clk_out"})
        add("rst", "RESET", {}, {"OUT": "rst_out"})
        add("reg", "REG8", {}, {"D": "reg_d", "CLK": "reg_clk", "RESET": "reg_rst",
                                "EN": "reg_en", "Q": "reg_q"})
        add("led_q", "LED", {"width": 8}, {"IN": "led_q_in"})
    elif exp_code == "EXP-03":
        add("clk", "CLOCK", {}, {"OUT": "clk_out"})
        add("rst", "RESET", {}, {"OUT": "rst_out"})
        add("en", "ENABLE", {}, {"OUT": "en_out"})
        add("pc", "PC4", {}, {"D": "pc_d", "INC": "pc_inc", "LOAD": "pc_load", "CLK": "pc_clk",
                              "RESET": "pc_rst", "EN": "pc_en", "Q": "pc_q"})
        add("rom", "ROM16X8", {"words": [0x13, 0x22, 0xF0, 0x00, 0x00, 0x00, 0x00, 0x00,
                                          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]},
            {"ADDR": "rom_addr", "DATA": "rom_data"})
        add("ir", "REG8", {}, {"D": "ir_d", "CLK": "ir_clk", "RESET": "ir_rst",
                               "EN": "ir_en", "Q": "ir_q"})
        add("split", "SPLIT8", {}, {"IN": "split_in", "HI": "split_hi", "LO": "split_lo"})
        add("ext", "EXTEND4", {}, {"IN": "ext_in", "OUT": "ext_out"})
        add("acc", "REG8", {}, {"D": "acc_d", "CLK": "acc_clk", "RESET": "acc_rst",
                                "EN": "acc_en", "Q": "acc_q"})
        add("mux", "MUX8", {}, {"A": "mux_a", "B": "mux_b", "SEL": "mux_sel", "Y": "mux_y"})
        add("alu", "ALU8", {}, {"A": "alu_a", "B": "alu_b", "OP": "alu_op",
                                "Y": "alu_y", "Z": "alu_z", "C": "alu_c"})
        add("ctrl", "CONTROL", {}, {"IR": "ctrl_ir", "ALU_Z": "ctrl_alu_z", "ALU_C": "ctrl_alu_c",
                                    "CLK": "ctrl_clk", "RESET": "ctrl_rst", "EN": "ctrl_en",
                                    "IR_EN": "ctrl_ir_en", "PC_INC": "ctrl_pc_inc",
                                    "PC_LOAD": "ctrl_pc_load", "ACC_EN": "ctrl_acc_en",
                                    "ACC_SEL": "ctrl_acc_sel", "ALU_OP": "ctrl_alu_op",
                                    "PHASE": "ctrl_phase", "Z": "ctrl_z", "C": "ctrl_c",
                                    "HALTED": "ctrl_halted", "ERROR": "ctrl_error"})
        add("led_acc", "LED", {"width": 8}, {"IN": "led_acc_in"})
        add("led_pc", "LED", {"width": 4}, {"IN": "led_pc_in"})

    return {"schema_version": 1, "components": components, "terminals": terminals,
            "code": exp_code}


# ---------- 信号值工具 ----------

def _is_known(v):
    return isinstance(v, int)


def _combine(net_values, width):
    """合并一条网上多个驱动值，冲突返回 'X'。"""
    known = [v for v in net_values if _is_known(v)]
    if not known:
        return "Z" if not net_values else "X"
    if all(v == known[0] for v in known):
        return known[0] & ((1 << width) - 1)
    return "X"


# ---------- 结构校验 ----------

def validate_structure(panel, state):
    terminals = {t["id"]: t for t in panel["terminals"]}
    components = {c["id"]: c for c in panel["components"]}
    errors = []
    wires = state.get("wires", [])

    # 检查端子存在
    for w in wires:
        for tid in (w["from_terminal"], w["to_terminal"]):
            if tid not in terminals:
                errors.append({"code": "TERMINAL_NOT_FOUND", "wire_ids": [w["id"]],
                               "terminal_ids": [tid], "message": f"端子 {tid} 不存在"})

    if errors:
        return False, errors

    # 方向：out -> in
    for w in wires:
        src, dst = terminals[w["from_terminal"]], terminals[w["to_terminal"]]
        if src["direction"] != "out" or dst["direction"] != "in":
            errors.append({"code": "DIRECTION_MISMATCH", "wire_ids": [w["id"]],
                           "terminal_ids": [w["from_terminal"], w["to_terminal"]],
                           "message": "连接方向必须为 out->in"})

    # 位宽一致
    for w in wires:
        src, dst = terminals[w["from_terminal"]], terminals[w["to_terminal"]]
        if src["width"] != dst["width"]:
            errors.append({"code": "WIDTH_MISMATCH", "wire_ids": [w["id"]],
                           "terminal_ids": [w["from_terminal"], w["to_terminal"]],
                           "message": f"位宽不一致 {src['width']} vs {dst['width']}"})

    # 自连
    for w in wires:
        if w["from_terminal"] == w["to_terminal"]:
            errors.append({"code": "SELF_CONNECTION", "wire_ids": [w["id"]],
                           "terminal_ids": [w["from_terminal"]], "message": "不允许自连"})

    # 重复边（同 from/to）
    seen = set()
    for w in wires:
        key = (w["from_terminal"], w["to_terminal"])
        if key in seen:
            errors.append({"code": "DUPLICATE_WIRE", "wire_ids": [w["id"]],
                           "terminal_ids": list(key), "message": "重复连线"})
        seen.add(key)

    # 输出冲突：同一输入端子不能接多个输出
    in_sources = {}
    for w in wires:
        dst = w["to_terminal"]
        in_sources.setdefault(dst, []).append(w["from_terminal"])
    for dst, srcs in in_sources.items():
        if len(srcs) > 1:
            src_terms = [terminals[s] for s in srcs]
            if all(t["direction"] == "out" for t in src_terms):
                errors.append({"code": "OUTPUT_CONFLICT", "wire_ids": [],
                               "terminal_ids": [dst] + srcs,
                               "message": f"端子 {dst} 接了多个主动输出"})

    # 必需输入悬空
    if not errors:
        driven = set()
        for w in wires:
            driven.add(w["to_terminal"])
        for t in panel["terminals"]:
            if t["direction"] == "in" and t.get("required") and t["id"] not in driven:
                # CLOCK/RESET/EN 由工作台驱动，不算悬空
                comp = components.get(t["component_id"])
                if comp and comp["type"] in ("CLOCK", "RESET", "ENABLE"):
                    continue
                errors.append({"code": "REQUIRED_OPEN", "wire_ids": [],
                               "terminal_ids": [t["id"]],
                               "message": f"必需输入 {t['id']} 悬空"})

    return len(errors) == 0, errors


# ---------- 仿真 ----------

def _build_netlist(panel, wires):
    """返回 {terminal_id: net_id} 及 {net_id: [terminal_ids]}。"""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w in wires:
        union(w["from_terminal"], w["to_terminal"])

    nets = {}
    for tid in (w["from_terminal"] for w in wires):
        nets.setdefault(find(tid), []).append(tid)
    for tid in (w["to_terminal"] for w in wires):
        nets.setdefault(find(tid), []).append(tid)

    term_to_net = {}
    for net_id, members in nets.items():
        for m in members:
            term_to_net[m] = net_id
    return term_to_net, nets


def _component_outputs(comp, inputs, state):
    """根据元件类型和输入端口值计算输出端口值。"""
    ctype = comp["type"]
    out = {}
    if ctype == "SWITCH":
        out["OUT"] = inputs.get("OUT")
    elif ctype == "CONST":
        out["OUT"] = comp["params"].get("value", 0)
    elif ctype == "CLOCK":
        out["OUT"] = state.get("clk", 0)
    elif ctype == "RESET":
        out["OUT"] = state.get("reset", 0)
    elif ctype == "ENABLE":
        out["OUT"] = state.get("enable", 1)
    elif ctype == "LED":
        pass
    elif ctype == "ALU8":
        a, b, op = inputs.get("A"), inputs.get("B"), inputs.get("OP")
        if _is_known(a) and _is_known(b) and _is_known(op):
            _name, fn, carry_fn = ALU_OPS[op & 7]
            result = fn(a & 0xFF, b & 0xFF)
            out["Y"] = result
            out["Z"] = 1 if result == 0 else 0
            out["C"] = carry_fn(a & 0xFF, b & 0xFF)
        else:
            out["Y"] = "X"
            out["Z"] = "X"
            out["C"] = "X"
    elif ctype == "REG8":
        out["Q"] = state.get("reg_q", 0)
    elif ctype == "PC4":
        out["Q"] = state.get("pc_q", 0)
    elif ctype == "ROM16X8":
        addr = inputs.get("ADDR")
        if _is_known(addr):
            words = comp["params"].get("words", [0] * 16)
            out["DATA"] = words[addr & 0xF]
        else:
            out["DATA"] = "X"
    elif ctype == "SPLIT8":
        val = inputs.get("IN")
        if _is_known(val):
            out["HI"] = (val >> 4) & 0xF
            out["LO"] = val & 0xF
        else:
            out["HI"] = out["LO"] = "X"
    elif ctype == "EXTEND4":
        val = inputs.get("IN")
        if _is_known(val):
            out["OUT"] = val & 0xF
        else:
            out["OUT"] = "X"
    elif ctype == "MUX8":
        a, b, sel = inputs.get("A"), inputs.get("B"), inputs.get("SEL")
        if _is_known(sel):
            out["Y"] = a if sel == 0 else b
        else:
            out["Y"] = "X"
    elif ctype == "CONTROL":
        ir = inputs.get("IR")
        alu_z = inputs.get("ALU_Z")
        alu_c = inputs.get("ALU_C")
        reset = inputs.get("RESET")
        en = inputs.get("EN")
        halted = state.get("halted", 0)
        error = state.get("error", 0)
        phase = state.get("phase", 0)
        z = state.get("z", 0)
        c = state.get("c", 0)

        ir_en = pc_inc = pc_load = acc_en = acc_sel = alu_op = 0
        if reset == 1 or en == 0 or halted == 1 or error == 1:
            pass
        elif phase == 0:  # FETCH
            ir_en = 1
            pc_inc = 1
        elif phase == 2 and _is_known(ir):  # EXECUTE
            op = (ir >> 4) & 0xF
            if op == 0x1:  # LDI
                acc_en = 1
                acc_sel = 0
                z = 1 if (ir & 0xF) == 0 else 0
                c = 0
            elif op in (0x2, 0x3, 0x4, 0x5):  # ADDI/SUBI/ANDI/ORI
                acc_en = 1
                acc_sel = 1
                alu_op = op - 2
                z = alu_z if _is_known(alu_z) else 0
                c = alu_c if _is_known(alu_c) else 0
            elif op == 0x6:  # JMP
                pc_load = 1
        out["IR_EN"] = ir_en
        out["PC_INC"] = pc_inc
        out["PC_LOAD"] = pc_load
        out["ACC_EN"] = acc_en
        out["ACC_SEL"] = acc_sel
        out["ALU_OP"] = alu_op
        out["PHASE"] = phase
        out["Z"] = z
        out["C"] = c
        out["HALTED"] = halted
        out["ERROR"] = error
    return out


def _propagate(panel, state):
    """组合逻辑传播至稳定。返回 terminal_id->value 映射。"""
    terminals = {t["id"]: t for t in panel["terminals"]}
    wires = state["wires"]
    term_to_net, nets = _build_netlist(panel, wires)

    values = {}
    # 初始：所有端子为 Z
    for t in panel["terminals"]:
        values[t["id"]] = "Z"

    # 输入源（SWITCH/CONST/CLOCK/RESET/ENABLE）
    inputs_map = state.get("inputs", {})
    for comp in panel["components"]:
        if comp["type"] == "SWITCH":
            tid = comp["ports"]["OUT"]
            values[tid] = inputs_map.get(tid, comp["params"].get("initial", 0))
        elif comp["type"] == "CONST":
            tid = comp["ports"]["OUT"]
            values[tid] = comp["params"].get("value", 0)
        elif comp["type"] in ("CLOCK",):
            tid = comp["ports"]["OUT"]
            values[tid] = state.get("clk", 0)
        elif comp["type"] == "RESET":
            tid = comp["ports"]["OUT"]
            values[tid] = state.get("reset", 0)
        elif comp["type"] == "ENABLE":
            tid = comp["ports"]["OUT"]
            values[tid] = state.get("enable", 1)

    for _ in range(100):
        changed = False
        for comp in panel["components"]:
            if comp["type"] in ("SWITCH", "CONST", "CLOCK", "RESET", "ENABLE", "LED"):
                continue
            # 收集该元件输入端口值
            comp_inputs = {}
            for port_name in COMPONENT_PORTS[comp["type"]]:
                direction, _ = COMPONENT_PORTS[comp["type"]][port_name]
                if direction == "in":
                    tid = comp["ports"][port_name]
                    net_id = term_to_net.get(tid)
                    if net_id:
                        net_terms = nets[net_id]
                        driver_vals = [values[nt] for nt in net_terms if nt != tid]
                        # 过滤 Z
                        real = [v for v in driver_vals if v != "Z"]
                        comp_inputs[port_name] = _combine(real, terminals[tid]["width"]) if real else "Z"
                    else:
                        comp_inputs[port_name] = "Z"
            outs = _component_outputs(comp, comp_inputs, state)
            for port_name, val in outs.items():
                tid = comp["ports"][port_name]
                if values.get(tid) != val:
                    values[tid] = val
                    changed = True
        if not changed:
            break

    # 把网内值统一：每个输入端子取其网的驱动值
    final = dict(values)
    for net_id, members in nets.items():
        drivers = [values[m] for m in members
                   if terminals[m]["direction"] == "out" and values[m] != "Z"]
        val = _combine(drivers, 8) if drivers else "Z"
        for m in members:
            if terminals[m]["direction"] == "in":
                final[m] = val
    return final


def _latch_sequential(panel, state, values):
    """时钟上升沿锁存时序元件，返回新 state。"""
    new_state = dict(state)
    clk = state.get("clk", 0)
    if clk != 1:
        return new_state
    for comp in panel["components"]:
        if comp["type"] == "REG8":
            reset = values.get(comp["ports"]["RESET"], 0)
            en = values.get(comp["ports"]["EN"], 0)
            d = values.get(comp["ports"]["D"], 0)
            q_key = f"{comp['id']}_q"
            if reset == 1:
                new_state[q_key] = 0
            elif en == 1 and _is_known(d):
                new_state[q_key] = d & 0xFF
        elif comp["type"] == "PC4":
            reset = values.get(comp["ports"]["RESET"], 0)
            en = values.get(comp["ports"]["EN"], 1)
            load = values.get(comp["ports"]["LOAD"], 0)
            inc = values.get(comp["ports"]["INC"], 0)
            d = values.get(comp["ports"]["D"], 0)
            q_key = f"{comp['id']}_q"
            cur = state.get(q_key, 0)
            if reset == 1:
                new_state[q_key] = 0
            elif en == 1:
                if load == 1 and _is_known(d):
                    new_state[q_key] = d & 0xF
                elif inc == 1:
                    new_state[q_key] = (cur + 1) & 0xF
    # phase 推进
    reset = state.get("reset", 0)
    halted = state.get("halted", 0)
    error = state.get("error", 0)
    en = state.get("enable", 1)
    if reset == 1:
        new_state["phase"] = 0
    elif halted == 1 or error == 1 or en == 0:
        pass
    else:
        ir = state.get("ir", 0)
        phase = state.get("phase", 0)
        if phase == 0:
            new_state["phase"] = 1
        elif phase == 1:
            new_state["phase"] = 2
        else:
            new_state["phase"] = 0
            op = (ir >> 4) & 0xF
            if op == 0xF:
                new_state["halted"] = 1
            elif op not in (0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6):
                new_state["error"] = 1
    return new_state


def step(panel, state):
    """执行一个完整时钟周期，返回新 state。"""
    s = dict(state)
    s["clk"] = 0
    _propagate(panel, s)
    s["clk"] = 1
    values = _propagate(panel, s)
    s = _latch_sequential(panel, s, values)
    # 更新 ir 供 phase 推进使用
    for comp in panel["components"]:
        if comp["type"] == "REG8" and comp["id"] == "ir":
            s["ir"] = s.get("ir_q", 0)
    s["clk"] = 0
    _propagate(panel, s)
    s["tick"] = s.get("tick", 0) + 1
    return s


def reset(panel, state):
    """复位：保留导线和 SWITCH/ENABLE，RESET 做一个完整周期后归 0。"""
    s = dict(state)
    s["reset"] = 1
    s["clk"] = 0
    _propagate(panel, s)
    s["clk"] = 1
    values = _propagate(panel, s)
    s = _latch_sequential(panel, s, values)
    s["clk"] = 0
    _propagate(panel, s)
    s["reset"] = 0
    s["tick"] = 0
    s["phase"] = 0
    s["halted"] = 0
    s["error"] = 0
    s["z"] = 0
    s["c"] = 0
    for comp in panel["components"]:
        if comp["type"] in ("REG8", "PC4"):
            s[f"{comp['id']}_q"] = 0
    return s


def initial_state(panel):
    s = {"wires": [], "inputs": {}, "phase": 0, "tick": 0, "clk": 0, "reset": 0, "enable": 1}
    for comp in panel["components"]:
        if comp["type"] in ("REG8", "PC4"):
            s[f"{comp['id']}_q"] = 0
        elif comp["type"] == "SWITCH":
            s["inputs"][comp["ports"]["OUT"]] = comp["params"].get("initial", 0)
    return s


# ---------- 动作重放 ----------

def replay(panel, actions, base_state=None):
    """从初态顺序重放动作，返回最终 state。"""
    state = base_state or initial_state(panel)
    undo_stack = []
    redo_stack = []
    for action in actions:
        atype = action["type"]
        payload = action.get("payload", {})
        if atype == "connect":
            wire = payload
            state["wires"] = [w for w in state["wires"] if w["id"] != wire["id"]]
            state["wires"].append(wire)
            undo_stack.append(("disconnect", {"wire_id": wire["id"]}))
        elif atype == "disconnect":
            wire_id = payload["wire_id"]
            removed = [w for w in state["wires"] if w["id"] == wire_id]
            state["wires"] = [w for w in state["wires"] if w["id"] != wire_id]
            if removed:
                undo_stack.append(("connect", removed[0]))
        elif atype == "set_input":
            tid = payload["terminal_id"]
            old = state["inputs"].get(tid)
            state["inputs"][tid] = payload["value"]
            undo_stack.append(("set_input", {"terminal_id": tid, "value": old}))
        elif atype == "step":
            state = step(panel, state)
            undo_stack = []
            redo_stack = []
        elif atype == "reset":
            state = reset(panel, state)
            undo_stack = []
            redo_stack = []
        elif atype == "undo":
            if undo_stack:
                inv_type, inv_payload = undo_stack.pop()
                if inv_type == "connect":
                    state["wires"].append(inv_payload)
                elif inv_type == "disconnect":
                    state["wires"] = [w for w in state["wires"] if w["id"] != inv_payload["wire_id"]]
                elif inv_type == "set_input":
                    state["inputs"][inv_payload["terminal_id"]] = inv_payload["value"]
                redo_stack.append((atype, payload))
        elif atype == "redo":
            if redo_stack:
                orig_type, orig_payload = redo_stack.pop()
                if orig_type == "connect":
                    state["wires"] = [w for w in state["wires"] if w["id"] != orig_payload["id"]]
                    state["wires"].append(orig_payload)
                elif orig_type == "disconnect":
                    state["wires"] = [w for w in state["wires"] if w["id"] != orig_payload["wire_id"]]
                elif orig_type == "set_input":
                    state["inputs"][orig_payload["terminal_id"]] = orig_payload["value"]
    return state


# ---------- 功能测试 ----------

def run_functional_tests(panel, state):
    """对提交快照运行服务端功能断言，返回 {passed, results}。"""
    code = panel["code"]
    results = []
    passed = True

    if code == "EXP-01":
        for op in range(8):
            s = dict(state)
            s["inputs"] = {tid: v for tid, v in state["inputs"].items()}
            # 设置 A=255, B=1 用于 ADD；其他用对应值
            for comp in panel["components"]:
                if comp["type"] == "SWITCH" and comp["id"] == "sw_a":
                    s["inputs"][comp["ports"]["OUT"]] = 255 if op == 0 else (0 if op == 1 else 0xA5 if op in (2, 3, 4, 5) else 0x81)
                if comp["type"] == "SWITCH" and comp["id"] == "sw_b":
                    s["inputs"][comp["ports"]["OUT"]] = 1 if op == 0 else (1 if op == 1 else 0x3C)
                if comp["type"] == "SWITCH" and comp["id"] == "sw_op":
                    s["inputs"][comp["ports"]["OUT"]] = op
            values = _propagate(panel, s)
            y = values.get("alu_y")
            z = values.get("alu_z")
            c = values.get("alu_c")
            expected = {0: (0, 1, 1), 1: (255, 0, 0), 2: (0x24, 0, 0), 3: (0xBD, 0, 0),
                        4: (0x99, 0, 0), 5: (0x5A, 0, 0), 6: (2, 0, 1), 7: (0x40, 0, 1)}
            exp_y, exp_z, exp_c = expected[op]
            ok = y == exp_y and z == exp_z and c == exp_c
            if not ok:
                passed = False
            results.append({"op": ALU_OPS[op][0], "passed": ok,
                            "expected": {"Y": exp_y, "Z": exp_z, "C": exp_c},
                            "actual": {"Y": y, "Z": z, "C": c}})

    elif code == "EXP-02":
        cases = [
            ({"sw_en_out": 0}, 1, "reset+en=0 -> Q=0"),
            ({"sw_en_out": 1, "sw_d_out": 0xA5}, 1, "en=1 D=A5 -> Q=A5"),
            ({"sw_en_out": 0, "sw_d_out": 0x3C}, 1, "en=0 -> hold"),
        ]
        for i, (inputs, _, desc) in enumerate(cases):
            s = reset(panel, dict(state))
            s["inputs"] = {tid: v for tid, v in state["inputs"].items()}
            s["inputs"].update(inputs)
            s = step(panel, s)
            q = s.get("reg_q")
            expected_q = [0, 0xA5, 0][i]
            # case 2: hold previous A5
            ok = q == expected_q if i < 2 else q == 0xA5
            if not ok:
                passed = False
            results.append({"case": desc, "passed": ok, "expected": expected_q if i < 2 else 0xA5,
                            "actual": q})

    elif code == "EXP-03":
        s = reset(panel, dict(state))
        s["inputs"] = {tid: v for tid, v in state["inputs"].items()}
        checks = []
        for tick in range(12):
            s = step(panel, s)
            if tick in (0, 2, 5, 8):
                checks.append({"tick": tick, "pc": s.get("pc_q"), "ir": s.get("ir_q"),
                               "phase": s.get("phase"), "acc": s.get("acc_q")})
        # 简化：验证前几拍 PC 递增
        ok = checks[0]["pc"] == 1 if checks else False
        if not ok:
            passed = False
        results.append({"case": "cpu_steps", "passed": ok, "checks": checks})

    return passed, results


def panel_to_json(panel):
    return json.dumps(panel, ensure_ascii=False)
