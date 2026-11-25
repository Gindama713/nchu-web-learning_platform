"""Editable PUBLIC teaching examples for the fixed PRD experiments, not secret tests."""

from backend.engines.grading import BASE_COMPONENTS
from backend.models.grading import ENGINE_VERSION, MAX_LIMITS, template_for


def case(group, steps):
    return {"label": group + " 示例", "visibility": "public", "group_code": group, "steps": steps}


def step(steps, inputs, expected, event="none"):
    steps.append({"step_no": len(steps) + 1, "inputs": inputs, "expected": expected, "clock_event": event})


def pulse(steps, inputs, previous, expected):
    step(steps, inputs, previous, "falling" if steps else "none")
    step(steps, inputs, expected, "rising")


def template(code):
    groups, _ = template_for(code)
    if code == "EXP-01":
        schema = {"inputs": {"A": 8, "B": 8, "OP": 3}, "outputs": {"Y": 8, "Z": 1, "C": 1}}
        values = [(255, 1, 0, 0, 1, 1), (5, 3, 1, 2, 0, 1), (240, 15, 2, 0, 1, 0),
                  (240, 15, 3, 255, 0, 0), (255, 15, 4, 240, 0, 0), (15, 0, 5, 240, 0, 0),
                  (129, 0, 6, 2, 0, 1), (129, 0, 7, 64, 0, 1)]
        cases = []
        for group, (a, b, op, y, z, carry) in zip(groups, values):
            steps = []
            step(steps, {"A": a, "B": b, "OP": op}, {"Y": y, "Z": z, "C": carry})
            cases.append(case(group, steps))
        top = "ALU8"
    elif code == "EXP-02":
        top = "REG8"
        schema = {"inputs": {"D": 8, "RESET": 1, "EN": 1}, "outputs": {"Q": 8}, "clock": "CLK"}
        cases = []
        for group in groups:
            steps = []
            pulse(steps, {"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, {"Q": 0})
            pulse(steps, {"RESET": 0, "EN": 1, "D": 90}, {"Q": 0}, {"Q": 90})
            if group == "reset":
                pulse(steps, {"RESET": 1, "EN": 0, "D": 165}, {"Q": 90}, {"Q": 0})
            elif group == "hold":
                pulse(steps, {"RESET": 0, "EN": 0, "D": 165}, {"Q": 90}, {"Q": 90})
            elif group == "load":
                pulse(steps, {"RESET": 0, "EN": 1, "D": 165}, {"Q": 90}, {"Q": 165})
            else:
                step(steps, {"RESET": 0, "EN": 1, "D": 165}, {"Q": 90}, "none")
                step(steps, {"RESET": 0, "EN": 1, "D": 165}, {"Q": 90}, "falling")
            cases.append(case(group, steps))
    else:
        top = "CPU8"
        schema = {"inputs": {"RESET": 1, "EN": 1, "INSTR": 8}, "clock": "CLK",
                  "outputs": {"PC": 4, "ACC": 8, "IR": 8, "PHASE": 2, "Z": 1, "C": 1, "HALTED": 1, "ERROR": 1}}
        # Literal expected states implement the documented three-phase PRD examples.
        instructions = {"nop": (0, {}), "ldi": (0x15, {"ACC": 5}), "addi": (0x23, {"ACC": 3}),
                        "subi": (0x31, {"ACC": 255}), "andi": (0x4A, {"Z": 1}), "ori": (0x5A, {"ACC": 10}),
                        "jmp": (0x63, {"PC": 3}), "hlt": (0xF0, {"HALTED": 1}),
                        "invalid": (0x70, {"HALTED": 1, "ERROR": 1})}
        cases = []
        for group in groups:
            steps = []
            zero = dict.fromkeys(schema["outputs"], 0)
            pulse(steps, {"RESET": 1, "EN": 0, "INSTR": 0}, zero, zero)
            if group == "hold":
                pulse(steps, {"RESET": 0, "EN": 0, "INSTR": 255}, zero, zero)
            else:
                instruction, changes = instructions.get(group, (0x15, {"ACC": 5}))
                fetch = {**zero, "PC": 1, "IR": instruction, "PHASE": 1}
                decode = {**fetch, "PHASE": 2}
                execute = {**decode, "PHASE": 0, **changes}
                pulse(steps, {"RESET": 0, "EN": 1, "INSTR": instruction}, zero, fetch)
                pulse(steps, {"RESET": 0, "EN": 1, "INSTR": 0}, fetch, decode)
                pulse(steps, {"RESET": 0, "EN": 1, "INSTR": 0}, decode, execute)
                if group == "reset":
                    pulse(steps, {"RESET": 1, "EN": 0, "INSTR": 0}, execute, zero)
            cases.append(case(group, steps))
    return {"profile": {"top_circuit": top, "port_schema": schema, "allowed_components": sorted(BASE_COMPONENTS),
                        "engine_version": ENGINE_VERSION, "limits": MAX_LIMITS},
            "cases": cases, "groups": list(groups), "note": "公开示例，须按教学目标补充边界用例；标准及反例真实验证通过后才能发布。"}
