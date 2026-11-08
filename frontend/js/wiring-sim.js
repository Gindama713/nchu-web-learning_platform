// SPEC-017 wiring simulation port (mirrors backend/engines/wiring.py) for display and state sync.
const KNOWN = value => typeof value === 'number' && Number.isInteger(value)

function combine(values, width) {
  const known = values.filter(value => KNOWN(value))
  if (!known.length) return values.length ? 'X' : 'Z'
  const first = known[0]
  return known.every(value => value === first) ? first & ((1 << width) - 1) : 'X'
}

function buildNets(wires) {
  const parent = new Map()
  const find = x => {
    while (parent.get(x, x) !== x) {
      parent.set(x, parent.get(parent.get(x, x), parent.get(x, x)))
      x = parent.get(x, x)
    }
    return x
  }
  const union = (a, b) => {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent.set(ra, rb)
  }
  const touch = x => { if (!parent.has(x)) parent.set(x, x) }
  for (const wire of wires) {
    touch(wire.from_terminal)
    touch(wire.to_terminal)
    union(wire.from_terminal, wire.to_terminal)
  }
  const nets = new Map()
  const termToNet = new Map()
  for (const wire of wires) {
    for (const tid of [wire.from_terminal, wire.to_terminal]) {
      const root = find(tid)
      if (!nets.has(root)) nets.set(root, [])
      nets.get(root).push(tid)
      termToNet.set(tid, root)
    }
  }
  return { termToNet, nets }
}

const ALU_OPS = [
  ['ADD', (a, b) => (a + b) & 0xFF, (a, b) => (a + b > 0xFF ? 1 : 0)],
  ['SUB', (a, b) => (a - b) & 0xFF, (a, b) => (a - b < 0 ? 0 : 1)],
  ['AND', (a, b) => a & b, () => 0],
  ['OR', (a, b) => a | b, () => 0],
  ['XOR', (a, b) => a ^ b, () => 0],
  ['NOT', a => (~a) & 0xFF, () => 0],
  ['SHL', a => (a << 1) & 0xFF, a => (a >> 7) & 1],
  ['SHR', a => a >> 1, a => a & 1],
]

const SOURCES = ['SWITCH', 'CONST', 'CLOCK', 'RESET', 'ENABLE']

function componentOutputs(comp, inputs, state) {
  const type = comp.type
  if (type === 'SWITCH') return { OUT: inputs.OUT }
  if (type === 'CONST') return { OUT: comp.params?.value ?? 0 }
  if (type === 'CLOCK') return { OUT: state.clk ?? 0 }
  if (type === 'RESET') return { OUT: state.reset ?? 0 }
  if (type === 'ENABLE') return { OUT: state.enable ?? 1 }
  if (type === 'LED') return {}
  if (type === 'ALU8') {
    const { A, B, OP } = inputs
    if (KNOWN(A) && KNOWN(B) && KNOWN(OP)) {
      const [, fn, carry] = ALU_OPS[OP & 7]
      const result = fn(A & 0xFF, B & 0xFF)
      return { Y: result, Z: result === 0 ? 1 : 0, C: carry(A & 0xFF, B & 0xFF) }
    }
    return { Y: 'X', Z: 'X', C: 'X' }
  }
  if (type === 'REG8' || type === 'PC4') return { Q: state[`${comp.id}_q`] ?? 0 }
  if (type === 'ROM16X8') {
    const addr = inputs.ADDR
    if (KNOWN(addr)) return { DATA: (comp.params?.words ?? [])[addr & 0xF] ?? 0 }
    return { DATA: 'X' }
  }
  if (type === 'SPLIT8') {
    const value = inputs.IN
    if (KNOWN(value)) return { HI: (value >> 4) & 0xF, LO: value & 0xF }
    return { HI: 'X', LO: 'X' }
  }
  if (type === 'EXTEND4') {
    const value = inputs.IN
    return { OUT: KNOWN(value) ? value & 0xF : 'X' }
  }
  if (type === 'MUX8') {
    const sel = inputs.SEL
    return { Y: KNOWN(sel) ? (sel === 0 ? inputs.A : inputs.B) : 'X' }
  }
  if (type === 'CONTROL') {
    const ir = inputs.IR
    const aluZ = inputs.ALU_Z
    const aluC = inputs.ALU_C
    const rst = inputs.RESET
    const en = inputs.EN
    const halted = state.halted ?? 0
    const error = state.error ?? 0
    const phase = state.phase ?? 0
    let z = state.z ?? 0
    let c = state.c ?? 0
    let irEn = 0
    let pcInc = 0
    let pcLoad = 0
    let accEn = 0
    let accSel = 0
    let aluOp = 0
    if (!(rst === 1 || en === 0 || halted === 1 || error === 1)) {
      if (phase === 0) {
        irEn = 1
        pcInc = 1
      } else if (phase === 2 && KNOWN(ir)) {
        const op = (ir >> 4) & 0xF
        if (op === 0x1) {
          accEn = 1
          accSel = 0
          z = (ir & 0xF) === 0 ? 1 : 0
          c = 0
        } else if (op >= 0x2 && op <= 0x5) {
          accEn = 1
          accSel = 1
          aluOp = op - 2
          z = KNOWN(aluZ) ? aluZ : 0
          c = KNOWN(aluC) ? aluC : 0
        } else if (op === 0x6) {
          pcLoad = 1
        }
      }
    }
    return { IR_EN: irEn, PC_INC: pcInc, PC_LOAD: pcLoad, ACC_EN: accEn, ACC_SEL: accSel,
      ALU_OP: aluOp, PHASE: phase, Z: z, C: c, HALTED: halted, ERROR: error }
  }
  return {}
}

export function propagate(panel, state) {
  const terminals = new Map(panel.terminals.map(t => [t.id, t]))
  const wires = state.wires ?? []
  const { termToNet, nets } = buildNets(wires)
  const values = new Map(panel.terminals.map(t => [t.id, 'Z']))
  const inputsMap = state.inputs ?? {}
  for (const comp of panel.components) {
    if (comp.type === 'SWITCH') {
      const tid = comp.ports.OUT
      values.set(tid, tid in inputsMap ? inputsMap[tid] : (comp.params?.initial ?? 0))
    } else if (comp.type === 'CONST') {
      values.set(comp.ports.OUT, comp.params?.value ?? 0)
    } else if (comp.type === 'CLOCK') {
      values.set(comp.ports.OUT, state.clk ?? 0)
    } else if (comp.type === 'RESET') {
      values.set(comp.ports.OUT, state.reset ?? 0)
    } else if (comp.type === 'ENABLE') {
      values.set(comp.ports.OUT, state.enable ?? 1)
    }
  }
  for (let round = 0; round < 100; round++) {
    let changed = false
    for (const comp of panel.components) {
      if (SOURCES.includes(comp.type) || comp.type === 'LED') continue
      const compInputs = {}
      for (const [port, spec] of Object.entries(portSpecs(comp))) {
        if (spec.direction !== 'in') continue
        const tid = comp.ports[port]
        const netId = termToNet.get(tid)
        if (netId === undefined) {
          compInputs[port] = 'Z'
          continue
        }
        const members = nets.get(netId) ?? []
        const driverVals = members.filter(nt => nt !== tid).map(nt => values.get(nt))
        const real = driverVals.filter(value => value !== 'Z')
        compInputs[port] = real.length ? combine(real, terminals.get(tid).width) : 'Z'
      }
      const outs = componentOutputs(comp, compInputs, state)
      for (const [port, value] of Object.entries(outs)) {
        const tid = comp.ports[port]
        if (values.get(tid) !== value) {
          values.set(tid, value)
          changed = true
        }
      }
    }
    if (!changed) break
  }
  const final = new Map(values)
  for (const members of nets.values()) {
    const drivers = members
      .filter(tid => terminals.get(tid).direction === 'out' && values.get(tid) !== 'Z')
      .map(tid => values.get(tid))
    const value = drivers.length ? combine(drivers, 8) : 'Z'
    for (const tid of members) {
      if (terminals.get(tid).direction === 'in') final.set(tid, value)
    }
  }
  return final
}

const PORT_CACHE = new Map()
function portSpecs(comp) {
  if (!PORT_CACHE.has(comp.type)) {
    const specs = {}
    if (comp.type === 'SWITCH') specs.OUT = { direction: 'out' }
    else if (comp.type === 'CONST') specs.OUT = { direction: 'out' }
    else if (comp.type === 'LED') specs.IN = { direction: 'in' }
    else if (comp.type === 'CLOCK' || comp.type === 'RESET' || comp.type === 'ENABLE') {
      specs.OUT = { direction: 'out' }
    } else if (comp.type === 'ALU8') {
      specs.A = { direction: 'in' }; specs.B = { direction: 'in' }; specs.OP = { direction: 'in' }
      specs.Y = { direction: 'out' }; specs.Z = { direction: 'out' }; specs.C = { direction: 'out' }
    } else if (comp.type === 'REG8') {
      specs.D = { direction: 'in' }; specs.CLK = { direction: 'in' }
      specs.RESET = { direction: 'in' }; specs.EN = { direction: 'in' }; specs.Q = { direction: 'out' }
    } else if (comp.type === 'PC4') {
      specs.D = { direction: 'in' }; specs.INC = { direction: 'in' }; specs.LOAD = { direction: 'in' }
      specs.CLK = { direction: 'in' }; specs.RESET = { direction: 'in' }; specs.EN = { direction: 'in' }
      specs.Q = { direction: 'out' }
    } else if (comp.type === 'ROM16X8') {
      specs.ADDR = { direction: 'in' }; specs.DATA = { direction: 'out' }
    } else if (comp.type === 'SPLIT8') {
      specs.IN = { direction: 'in' }; specs.HI = { direction: 'out' }; specs.LO = { direction: 'out' }
    } else if (comp.type === 'EXTEND4') {
      specs.IN = { direction: 'in' }; specs.OUT = { direction: 'out' }
    } else if (comp.type === 'MUX8') {
      specs.A = { direction: 'in' }; specs.B = { direction: 'in' }; specs.SEL = { direction: 'in' }
      specs.Y = { direction: 'out' }
    } else if (comp.type === 'CONTROL') {
      for (const [port, direction] of Object.entries({
        IR: 'in', ALU_Z: 'in', ALU_C: 'in', CLK: 'in', RESET: 'in', EN: 'in',
        IR_EN: 'out', PC_INC: 'out', PC_LOAD: 'out', ACC_EN: 'out', ACC_SEL: 'out',
        ALU_OP: 'out', PHASE: 'out', Z: 'out', C: 'out', HALTED: 'out', ERROR: 'out',
      })) specs[port] = { direction }
    }
    PORT_CACHE.set(comp.type, specs)
  }
  return PORT_CACHE.get(comp.type)
}

function latch(panel, state, values) {
  const next = { ...state }
  if ((state.clk ?? 0) !== 1) return next
  for (const comp of panel.components) {
    if (comp.type === 'REG8') {
      const reset = values.get(comp.ports.RESET) ?? 0
      const en = values.get(comp.ports.EN) ?? 0
      const d = values.get(comp.ports.D) ?? 0
      const key = `${comp.id}_q`
      if (reset === 1) next[key] = 0
      else if (en === 1 && KNOWN(d)) next[key] = d & 0xFF
    } else if (comp.type === 'PC4') {
      const reset = values.get(comp.ports.RESET) ?? 0
      const en = values.get(comp.ports.EN) ?? 1
      const load = values.get(comp.ports.LOAD) ?? 0
      const inc = values.get(comp.ports.INC) ?? 0
      const d = values.get(comp.ports.D) ?? 0
      const key = `${comp.id}_q`
      const cur = state[key] ?? 0
      if (reset === 1) next[key] = 0
      else if (en === 1) {
        if (load === 1 && KNOWN(d)) next[key] = d & 0xF
        else if (inc === 1) next[key] = (cur + 1) & 0xF
      }
    }
  }
  const reset = state.reset ?? 0
  const halted = state.halted ?? 0
  const error = state.error ?? 0
  const en = state.enable ?? 1
  if (reset === 1) next.phase = 0
  else if (halted === 1 || error === 1 || en === 0) { /* hold */ } else {
    const ir = state.ir ?? 0
    const phase = state.phase ?? 0
    if (phase === 0) next.phase = 1
    else if (phase === 1) next.phase = 2
    else {
      next.phase = 0
      const op = (ir >> 4) & 0xF
      if (op === 0xF) next.halted = 1
      else if (![0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6].includes(op)) next.error = 1
    }
  }
  return next
}

export function stepSim(panel, state) {
  let s = { ...state }
  s.clk = 0
  propagate(panel, s)
  s.clk = 1
  const values = propagate(panel, s)
  s = latch(panel, s, values)
  for (const comp of panel.components) {
    if (comp.type === 'REG8' && comp.id === 'ir') s.ir = s.ir_q ?? 0
  }
  s.clk = 0
  propagate(panel, s)
  s.tick = (s.tick ?? 0) + 1
  return s
}

export function resetSim(panel, state) {
  let s = { ...state }
  s.reset = 1
  s.clk = 0
  propagate(panel, s)
  s.clk = 1
  const values = propagate(panel, s)
  s = latch(panel, s, values)
  s.clk = 0
  propagate(panel, s)
  s.reset = 0
  s.tick = 0
  s.phase = 0
  s.halted = 0
  s.error = 0
  s.z = 0
  s.c = 0
  for (const comp of panel.components) {
    if (comp.type === 'REG8' || comp.type === 'PC4') s[`${comp.id}_q`] = 0
  }
  return s
}

export function initialState(panel) {
  const state = { wires: [], inputs: {}, phase: 0, tick: 0, clk: 0, reset: 0, enable: 1 }
  for (const comp of panel.components) {
    if (comp.type === 'REG8' || comp.type === 'PC4') state[`${comp.id}_q`] = 0
    else if (comp.type === 'SWITCH') state.inputs[comp.ports.OUT] = comp.params?.initial ?? 0
  }
  return state
}

// Mirror of backend replay: applies one action and records undo inverses into stack.
export function replayAction(panel, state, action, stack) {
  const type = action.type
  const payload = action.payload ?? {}
  if (type === 'connect') {
    state.wires = state.wires.filter(wire => wire.id !== payload.id)
    state.wires.push({ ...payload })
    stack.push({ type: 'disconnect', payload: { wire_id: payload.id } })
    return state
  }
  if (type === 'disconnect') {
    const removed = state.wires.find(wire => wire.id === payload.wire_id)
    state.wires = state.wires.filter(wire => wire.id !== payload.wire_id)
    if (removed) stack.push({ type: 'connect', payload: { ...removed } })
    return state
  }
  if (type === 'set_input') {
    const previous = state.inputs[payload.terminal_id]
    state.inputs = { ...state.inputs, [payload.terminal_id]: payload.value }
    stack.push({ type: 'set_input', payload: { terminal_id: payload.terminal_id, value: previous } })
    return state
  }
  if (type === 'step') {
    stack.length = 0
    return stepSim(panel, state)
  }
  if (type === 'reset') {
    stack.length = 0
    return resetSim(panel, state)
  }
  if (type === 'undo' && stack.length) {
    const inverse = stack.pop()
    if (inverse.type === 'connect') state.wires = [...state.wires, { ...inverse.payload }]
    else if (inverse.type === 'disconnect') {
      state.wires = state.wires.filter(wire => wire.id !== inverse.payload.wire_id)
    } else if (inverse.type === 'set_input') {
      state.inputs = { ...state.inputs, [inverse.payload.terminal_id]: inverse.payload.value }
    }
    return state
  }
  return state
}
