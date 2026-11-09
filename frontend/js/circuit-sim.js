// 电路实验台的模拟内核：纯函数、无 DOM/Vue 依赖，可在 node:test 里直接跑。
// 与后端 backend/apis/circuit_lab.py 的芯片功能表一一对应，验收脚本会对全组合
// 交叉比对两边结果，避免「前端一套口径、后端另一套口径」。

export const MASK4 = 15

const bit = (value, index) => (value >> index) & 1
const bits4 = value => [bit(value, 3), bit(value, 2), bit(value, 1), bit(value, 0)]

export const OP_CODES = {
  add: { s: 0b1001, m: 0, cn_bar: 1, invert_b: false, label: '加法 A + B' },
  sub: { s: 0b0110, m: 0, cn_bar: 0, invert_b: true, label: '减法 A − B' },
}

/** 7485：A≠B 时忽略级联；A=B 时输出跟随 I(A<B)/I(A=B)/I(A>B)。 */
export function simulate7485(input = {}) {
  const a = clamp(input.A ?? 0, 0, 15)
  const b = clamp(input.B ?? 0, 0, 15)
  const i_lt = clamp(input.I_LT ?? 0, 0, 1)
  const i_eq = clamp(input.I_EQ ?? 1, 0, 1)
  const i_gt = clamp(input.I_GT ?? 0, 0, 1)
  let gt = 0, eq = 0, lt = 0
  if (a > b) gt = 1
  else if (a < b) lt = 1
  else { gt = i_gt; eq = i_eq; lt = i_lt }
  return {
    chip: '7485', a, b, i_lt, i_eq, i_gt, gt, eq, lt,
    a_bits: bits4(a).join(''), b_bits: bits4(b).join(''),
    // 级联输入全 0 时三路输出都为低（7485 单片不会这样接），不能误报 A<B。
    relation: gt ? 'A>B' : eq ? 'A=B' : lt ? 'A<B' : '无有效输出',
    bits: bits4(a),
  }
}

/** 74181 + 7400：S/M/Cn̄ 由 OP 译码，减法在芯片内部是 A + B̄ + 1。 */
export function simulate74181(input = {}) {
  const a = clamp(input.A ?? 0, 0, 15)
  const b = clamp(input.B ?? 0, 0, 15)
  const op = OP_CODES[input.OP] ? input.OP : 'sub'
  const code = OP_CODES[op]
  const carry_in = 1 - code.cn_bar
  const operand_b = code.invert_b ? (~b) & MASK4 : b
  const total = a + operand_b + carry_in
  const f = total & MASK4
  const carry = total > MASK4 ? 1 : 0
  return {
    chip: '74181', op, a, b,
    a_bits: bits4(a).join(''), b_bits: bits4(b).join(''),
    s3s2s1s0: code.s.toString(2).padStart(4, '0'),
    m: code.m, cn_bar: code.cn_bar, carry_in, operand_b,
    operand_b_bits: bits4(operand_b).join(''), internal_sum: total,
    f, f_bits: bits4(f).join(''), f_hex: `0x${f.toString(16).toUpperCase()}`,
    cn4: carry ? 0 : 1, carry, borrow: op === 'sub' ? 1 - carry : null,
    zero: f === 0 ? 1 : 0, equal: a === b ? 1 : 0,
    decimal_result: op === 'add' ? a + b : a - b,
    expression: `${a} ${op === 'add' ? '+' : '−'} ${b}`,
    label: code.label,
  }
}

export function simulate(chip, input) {
  return chip === '74181' ? simulate74181(input) : simulate7485(input)
}

/** 每个引脚当前的 0/1，用于开关与指示灯着色。 */
export function pinState(chip, input, pin) {
  const out = simulate(chip, input)
  if (pin.kind === 'switch') {
    if (pin.group === 'A') return bit(out.a, pin.bit)
    if (pin.group === 'B') return bit(out.b, pin.bit)
    if (pin.group === 'cascade') return input[pin.id] ?? 0
    if (pin.group === 'control') {
      // s3s2s1s0 的字符串下标 0 对应 S3、3 对应 S0。
      if (/^S[0-3]$/.test(pin.id)) return Number(out.s3s2s1s0[3 - Number(pin.id[1])])
      if (pin.id === 'M') return out.m
      if (pin.id === 'Cn') return out.cn_bar
    }
    return 0
  }
  if (pin.output === 'gt' || pin.output === 'eq' || pin.output === 'lt') return out[pin.output] ?? 0
  if (pin.output === 'cn4') return out.cn4
  if (/^f[0-3]$/.test(pin.output)) return bit(out.f, Number(pin.output[1]))
  return 0
}

/** 开关状态 → 输入对象（点击某一位时翻转该位）。 */
export function togglePin(chip, input, pin) {
  const next = { ...input }
  if (pin.group === 'A' || pin.group === 'B') {
    const key = pin.group
    const value = clamp(next[key] ?? 0, 0, 15) ^ (1 << pin.bit)
    next[key] = value & MASK4
  } else if (pin.group === 'cascade') {
    next[pin.id] = next[pin.id] ? 0 : 1
  } else if (pin.group === 'control' && pin.id === 'Cn') {
    // Cn̄ 由 7400 依据 ADD/SUB 译码：点击它等价于切换运算。
    next.OP = next.OP === 'sub' ? 'add' : 'sub'
  }
  // S3..S0 / M 是译码结果（只读），点击不会破坏 7400 的控制位一致性。
  return next
}

/** 期望值比对：只比较用例里声明的键，返回逐项明细。 */
export function checkCase(experiment, input) {
  const found = experiment.cases.find(item => item.id === experiment.active_case) || experiment.cases[0]
  const out = simulate(experiment.id, input)
  const details = Object.entries(found.expected).map(([key, expected]) => ({
    key, expected, actual: out[key] ?? null, passed: (out[key] ?? null) === expected,
  }))
  return { case: found, output: out, details, passed: details.every(item => item.passed) }
}

/** 全组合真值表，供测试脚本与前端索引使用。 */
export function truthTable(chip) {
  const rows = []
  if (chip === '7485') {
    for (let a = 0; a < 16; a += 1) {
      for (let b = 0; b < 16; b += 1) {
        for (let i_lt = 0; i_lt < 2; i_lt += 1) {
          for (let i_eq = 0; i_eq < 2; i_eq += 1) {
            for (let i_gt = 0; i_gt < 2; i_gt += 1) {
              rows.push(simulate7485({ A: a, B: b, I_LT: i_lt, I_EQ: i_eq, I_GT: i_gt }))
            }
          }
        }
      }
    }
  } else {
    for (const op of ['add', 'sub']) {
      for (let a = 0; a < 16; a += 1) {
        for (let b = 0; b < 16; b += 1) rows.push(simulate74181({ A: a, B: b, OP: op }))
      }
    }
  }
  return rows
}

/** 把 4 位数值写入输入对象，供右侧控制面板数字框使用。 */
export function setNumeric(chip, input, key, raw) {
  const value = Number.parseInt(String(raw), 10)
  const next = { ...input }
  if (key === 'A' || key === 'B') next[key] = Number.isFinite(value) ? clamp(value, 0, 15) : 0
  else if (['I_LT', 'I_EQ', 'I_GT'].includes(key)) next[key] = value ? 1 : 0
  else if (key === 'OP') next.OP = raw === 'add' ? 'add' : 'sub'
  else next[key] = raw
  delete next._control_hint
  return next
}

export function defaultInputs(experiment) {
  const base = { ...(experiment.cases[0]?.inputs ?? {}) }
  return base
}

export function inputSummary(input) {
  const parts = []
  for (const [key, value] of Object.entries(input)) {
    if (key.startsWith('_')) continue
    parts.push(`${key}=${value}`)
  }
  return parts.join(' ')
}

function clamp(value, low, high) {
  const number = Number(value)
  if (!Number.isFinite(number)) return low
  return Math.min(high, Math.max(low, Math.trunc(number)))
}
