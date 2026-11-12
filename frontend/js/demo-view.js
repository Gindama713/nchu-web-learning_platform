// SPEC-007 课堂演示：六个内置场景的可视化与状态同步。
// 状态由后端 demo.py 的场景引擎推进，这里只渲染服务端返回的 state，不在前端推算电路结果。
import { h, onMounted, onUnmounted, ref } from 'vue'
import { DemoClient, cpuCycles, demoActions, demoPresets } from './demo-client.js'

const INK = '#182436'
const MUTED = '#60718a'
const LINE = '#9cabc0'
const ACCENT = '#173b6c'
const SIGNAL = '#f0a500'
const IDLE = '#c9d4e2'
const pretty = value => (value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—')

const hex = (value, width = 2) => Number(value ?? 0).toString(16).toUpperCase().padStart(width, '0')
const on = value => Number(value) === 1

// ---------- SVG 原子 ----------

function text(x, y, content, opts = {}) {
  return h('text', {
    x, y,
    'font-size': opts.size ?? 12,
    fill: opts.fill ?? INK,
    'font-weight': opts.bold ? 600 : 400,
    'text-anchor': opts.anchor ?? 'start',
    'font-family': opts.mono ? 'ui-monospace, monospace' : 'inherit',
  }, content)
}

function box(x, y, width, height, opts = {}) {
  return h('rect', {
    x, y, width, height, rx: opts.rx ?? 6,
    fill: opts.fill ?? '#ffffff',
    stroke: opts.stroke ?? LINE,
    'stroke-width': opts.strokeWidth ?? 1.2,
    'stroke-dasharray': opts.dashed ? '5 4' : undefined,
  })
}

// 带标题与取值的方框（寄存器、门、部件都用它）
function unit(x, y, width, height, title, value, opts = {}) {
  return h('g', {}, [
    box(x, y, width, height, opts),
    text(x + 8, y + 15, title, { size: 11, fill: MUTED }),
    text(x + width / 2, y + height - 8, value, { size: 14, bold: true, anchor: 'middle', mono: true }),
  ])
}

function lamp(x, y, lit, caption) {
  return h('g', {}, [
    h('circle', { cx: x, cy: y, r: 8, fill: lit ? SIGNAL : IDLE, stroke: lit ? '#a86f00' : LINE }),
    text(x, y + 26, caption, { size: 11, fill: MUTED, anchor: 'middle' }),
    text(x, y + 4, lit ? '1' : '0', { size: 10, fill: lit ? '#3a2600' : MUTED, anchor: 'middle', bold: true }),
  ])
}

function wire(x1, y1, x2, y2, opts = {}) {
  return h('line', {
    x1, y1, x2, y2,
    stroke: opts.stroke ?? LINE,
    'stroke-width': opts.width ?? 1.4,
    'marker-end': opts.arrow ? 'url(#demo-arrow)' : undefined,
  })
}

function polyline(points, opts = {}) {
  return h('polyline', {
    points: points.map(([px, py]) => `${px},${py}`).join(' '),
    fill: 'none',
    stroke: opts.stroke ?? LINE,
    'stroke-width': opts.width ?? 1.4,
    'stroke-dasharray': opts.dashed ? '5 4' : undefined,
    'marker-end': opts.arrow ? 'url(#demo-arrow)' : undefined,
  })
}

// 分叉处的实心节点：表示两条引线在这一点相连。
function junction(x, y, color = '#5b6b82') {
  return h('circle', { cx: x, cy: y, r: 3, fill: color })
}

// 部件边框上的接线端子，让箭头明确“指到端口”而不是落在空白处。
function port(x, y) {
  return h('circle', { cx: x, cy: y, r: 2.6, fill: '#ffffff', stroke: ACCENT, 'stroke-width': 1.2 })
}

// ---------- 六个场景 ----------

function sceneGate(state) {
  const rows = [
    ['AND', 'A·B', true, state.outputs?.and],
    ['OR', 'A+B', true, state.outputs?.or],
    ['NOT', "A'", false, state.outputs?.not],
    ['XOR', 'A⊕B', true, state.outputs?.xor],
  ]
  const nodes = []
  rows.forEach(([name, formula, useB, out], index) => {
    const y = 18 + index * 48
    nodes.push(unit(16, y, 74, 36, 'A', state.inputs?.a ?? 0, { fill: '#f7faff' }))
    if (useB) nodes.push(unit(104, y, 74, 36, 'B', state.inputs?.b ?? 0, { fill: '#f7faff' }))
    nodes.push(wire(useB ? 178 : 90, y + 18, 250, y + 18, { arrow: true }))
    nodes.push(h('g', {}, [
      box(250, y, 128, 36, { fill: '#eef4fd', stroke: ACCENT }),
      text(314, y + 16, `${name}  ${formula}`, { size: 12, bold: true, anchor: 'middle', fill: ACCENT }),
      text(314, y + 30, useB ? `A=${state.inputs?.a ?? 0} B=${state.inputs?.b ?? 0}` : `A=${state.inputs?.a ?? 0}`,
        { size: 10, fill: MUTED, anchor: 'middle' }),
    ]))
    nodes.push(wire(378, y + 18, 424, y + 18, { arrow: true, stroke: on(out) ? SIGNAL : LINE }))
    nodes.push(lamp(440, y + 14, on(out), name))
  })
  return { width: 500, height: 212, nodes }
}

function sceneComb(state) {
  const DATA = '#5b6b82'
  const CTRL = '#6b4fb0'
  const sel = Number(state.sel ?? 0)
  const muxPick = sel === 0 ? 'A' : 'B'
  const aluOp = ['加', '减', '与', '或'][sel] ?? '—'
  const litMux = Number(state.mux_out ?? 0) !== 0
  const litAlu = Number(state.alu_out ?? 0) !== 0

  const nodes = [
    // ---- 左侧输入 ----
    unit(16, 22, 96, 44, 'A (4bit)', hex(state.a, 1)),
    unit(16, 78, 96, 44, 'B (4bit)', hex(state.b, 1)),
    unit(16, 178, 96, 44, 'SEL', sel),

    // ---- 两个部件尺寸相同、关于水平中线 y=136 严格镜像 ----
    h('g', {}, [
      box(252, 20, 152, 100, { fill: '#eef4fd', stroke: ACCENT, strokeWidth: 1.6 }),
      text(330, 62, 'MUX', { size: 14, bold: true, anchor: 'middle', fill: ACCENT }),
      text(330, 82, `SEL=${sel} → 选 ${muxPick}`, { size: 10, fill: MUTED, anchor: 'middle' }),
      text(262, 48, 'A', { size: 10, fill: MUTED, mono: true }),
      text(262, 104, 'B', { size: 10, fill: MUTED, mono: true }),
      text(306, 114, 'SEL', { size: 9, fill: MUTED, mono: true }),
    ]),
    h('g', {}, [
      box(252, 152, 152, 100, { fill: '#eef4fd', stroke: ACCENT, strokeWidth: 1.6 }),
      text(330, 196, 'ALU', { size: 14, bold: true, anchor: 'middle', fill: ACCENT }),
      text(330, 216, `OP=${sel} ${aluOp}`, { size: 10, fill: MUTED, anchor: 'middle' }),
      text(262, 176, 'A', { size: 10, fill: MUTED, mono: true }),
      text(262, 232, 'B', { size: 10, fill: MUTED, mono: true }),
      text(306, 168, 'OP', { size: 9, fill: MUTED, mono: true }),
    ]),

    // ---- 输出：两个框同样关于中线镜像 ----
    wire(404, 70, 448, 70, { arrow: true, stroke: litMux ? SIGNAL : LINE }),
    wire(404, 202, 448, 202, { arrow: true, stroke: litAlu ? SIGNAL : LINE }),
    unit(448, 42, 96, 56, 'MUX 输出', hex(state.mux_out, 1),
      { stroke: litMux ? SIGNAL : LINE }),
    unit(448, 174, 96, 56, 'ALU 输出', hex(state.alu_out, 1),
      { stroke: litAlu ? SIGNAL : LINE }),

    // ---- A、B 各走一条水平直线进 MUX，再各自下一个等长台阶到 ALU ----
    wire(112, 44, 252, 44, { arrow: true, stroke: DATA }),
    junction(218, 44, DATA),
    polyline([[218, 44], [218, 172], [252, 172]], { arrow: true, stroke: DATA }),

    wire(112, 100, 252, 100, { arrow: true, stroke: DATA }),
    junction(196, 100, DATA),
    polyline([[196, 100], [196, 228], [252, 228]], { arrow: true, stroke: DATA }),

    // ---- SEL：控制干线沿两部件的中缝走，再上下对称地插入 MUX 底部与 ALU 顶部 ----
    polyline([[112, 200], [240, 200], [240, 136], [320, 136]], { stroke: CTRL, dashed: true }),
    junction(320, 136, CTRL),
    polyline([[320, 136], [320, 120]], { stroke: CTRL, dashed: true, arrow: true }),
    polyline([[320, 136], [320, 152]], { stroke: CTRL, dashed: true, arrow: true }),

    // ---- 接线端子 ----
    port(252, 44), port(252, 100), port(320, 120),
    port(252, 172), port(252, 228), port(320, 152),

    text(280, 282,
      `第 ${state.step} 步：A=${hex(state.a, 1)} B=${hex(state.b, 1)} SEL=${sel}`
      + ` → MUX 选 ${muxPick}，输出 ${hex(state.mux_out, 1)}；ALU ${aluOp}，输出 ${hex(state.alu_out, 1)}`,
      { size: 12, fill: MUTED, anchor: 'middle' }),
  ]
  return { width: 560, height: 294, nodes }
}

function sceneSequential(state) {
  const clockHigh = on(state.clock)
  const writing = clockHigh && on(state.enable)
  // 三条数据/控制线各走各的 y，箭头正好落在 REG8 左边框的端口上，不再压在任何方框上。
  const ports = [['D', 42], ['CLK', 108], ['EN', 166]]
  return {
    width: 560,
    height: 228,
    nodes: [
      unit(16, 20, 96, 44, 'D (8bit)', hex(state.d_in)),
      unit(16, 88, 96, 40, 'CLK', clockHigh ? '1' : '0',
        { stroke: clockHigh ? SIGNAL : LINE, strokeWidth: clockHigh ? 2 : 1.2 }),
      unit(16, 146, 96, 40, 'EN', state.enable),
      wire(112, 42, 250, 42, { arrow: true }),
      wire(112, 108, 250, 108, { arrow: true, stroke: clockHigh ? SIGNAL : LINE }),
      wire(112, 166, 250, 166, { arrow: true }),
      h('g', {}, [
        box(250, 18, 132, 166, { fill: '#eef4fd', stroke: ACCENT, strokeWidth: 1.6 }),
        ...ports.map(([name, y]) => text(258, y + 4, name, { size: 10, fill: MUTED, mono: true })),
        text(316, 90, 'REG8', { size: 14, bold: true, anchor: 'middle', fill: ACCENT }),
        text(316, 112, writing ? '上升沿写入' : '保持', { size: 10, fill: MUTED, anchor: 'middle' }),
      ]),
      wire(382, 101, 432, 101, { arrow: true, stroke: on(state.q) ? SIGNAL : LINE }),
      unit(432, 74, 100, 54, 'Q (8bit)', hex(state.q), { stroke: on(state.q) ? SIGNAL : LINE }),
      text(16, 212, `第 ${state.step} 步：CLK=${state.clock} EN=${state.enable} D=${hex(state.d_in)} → Q=${hex(state.q)}`,
        { size: 12, fill: MUTED }),
    ],
  }
}

function sceneAlu(state) {
  // A / B / OP 三个输入以 ALU8 的垂直中心（y=100）上下对称，输出也从中心引出。
  return {
    width: 620,
    height: 206,
    nodes: [
      unit(16, 24, 96, 44, 'A (8bit)', hex(state.a)),
      unit(16, 78, 96, 44, 'B (8bit)', hex(state.b)),
      unit(16, 132, 96, 44, 'OP', state.op_name ?? state.op),
      wire(112, 46, 190, 46, { arrow: true }),
      wire(112, 100, 190, 100, { arrow: true }),
      wire(112, 154, 190, 154, { arrow: true }),
      h('g', {}, [
        box(190, 30, 144, 140, { fill: '#eef4fd', stroke: ACCENT, strokeWidth: 1.6 }),
        text(262, 92, 'ALU8', { size: 15, bold: true, anchor: 'middle', fill: ACCENT }),
        text(262, 114, state.op_name ?? '', { size: 12, anchor: 'middle', fill: MUTED }),
      ]),
      wire(334, 100, 392, 100, { arrow: true, stroke: on(state.result) ? SIGNAL : LINE }),
      unit(392, 72, 120, 56, 'RESULT (8bit)', hex(state.result),
        { stroke: on(state.result) ? SIGNAL : LINE }),
      lamp(432, 158, on(state.flags?.zero), 'Z'),
      lamp(492, 158, on(state.flags?.carry), 'C'),
    ],
  }
}

function sceneMemory(state) {
  const rom = Array.isArray(state.rom) ? state.rom : []
  const cells = []
  const columns = 8
  const cellW = 58
  const cellH = 40
  rom.forEach((byte, index) => {
    const col = index % columns
    const row = Math.floor(index / columns)
    const x = 16 + col * cellW
    const y = 18 + row * cellH
    const active = index === state.address
    cells.push(h('g', {}, [
      box(x, y, cellW - 6, cellH - 8, { fill: active ? '#fff4d6' : '#fbfdff', stroke: active ? '#d18700' : LINE,
        strokeWidth: active ? 2 : 1 }),
      text(x + 6, y + 13, hex(index, 1), { size: 10, fill: MUTED, mono: true }),
      text(x + (cellW - 6) / 2, y + 27, hex(byte), { size: 13, bold: true, anchor: 'middle', mono: true }),
    ]))
  })
  return {
    width: 480,
    height: 118,
    nodes: [
      ...cells,
      text(16, 108, `ADDR=${hex(state.address, 1)}  DATA=${hex(state.data_out)}  第 ${state.step} 步`, { size: 12, fill: MUTED }),
    ],
  }
}

function sceneCpu(state) {
  const registers = state.registers ?? {}
  const control = state.control ?? {}
  const buses = state.buses ?? {}
  const ram = Array.isArray(state.ram) ? state.ram : []
  const rawPc = Number(state.pc ?? 0)
  const pc = rawPc < 256 ? rawPc : -1

  const nodes = [
    // 寄存器堆
    unit(16, 20, 100, 42, 'A', registers.A ?? '00'),
    unit(124, 20, 100, 42, 'X', registers.X ?? '00'),
    unit(16, 70, 100, 42, 'PC', registers.PC ?? '0000'),
    unit(124, 70, 100, 42, 'IR', registers.IR ?? '00'),
    // 下一周期的控制信号
    h('g', {}, [
      box(16, 122, 208, 106, { fill: '#fbfdff', dashed: true }),
      text(24, 140, '下一周期控制', { size: 11, fill: MUTED }),
      ...[['fetch', '取指'], ['decode', '译码'], ['execute', '执行'], ['mem_wr', '写存'], ['halt', '停机']]
        .map(([key, name], index) => {
          const x = 52 + (index % 3) * 66
          const y = 168 + Math.floor(index / 3) * 40
          return lamp(x, y, on(control[key]), name)
        }),
    ]),
    // 总线
    h('g', {}, [
      box(246, 30, 100, 80, { fill: '#eef4fd', stroke: ACCENT }),
      text(296, 50, '总线', { size: 12, bold: true, anchor: 'middle', fill: ACCENT }),
      text(296, 70, `ADDR ${buses.addr ?? '----'}`, { size: 10, anchor: 'middle', mono: true, fill: MUTED }),
      text(296, 88, `DATA ${buses.data ?? '--'}`, { size: 10, anchor: 'middle', mono: true, fill: MUTED }),
    ]),
    wire(216, 41, 246, 41, { arrow: true }),
    wire(216, 91, 246, 91, { arrow: true }),
    wire(346, 70, 372, 70, { arrow: true, stroke: SIGNAL }),
  ]

  // RAM 16×16，格子放大到 10px 才看得清
  const size = 10
  const originX = 372
  const originY = 20
  for (let index = 0; index < 256; index += 1) {
    const col = index % 16
    const row = Math.floor(index / 16)
    const value = Number(ram[index] ?? 0)
    const isPc = index === pc
    nodes.push(h('rect', {
      x: originX + col * size,
      y: originY + row * size,
      width: size - 1.2,
      height: size - 1.2,
      fill: isPc ? SIGNAL : value ? '#9fb8dc' : '#eef3fa',
      stroke: isPc ? '#a86f00' : '#dce4ee',
      'stroke-width': 0.4,
    }))
  }
  nodes.push(text(originX, originY + 16 * size + 16, 'RAM 256B（黄=PC，蓝=非零）', { size: 11, fill: MUTED }))
  nodes.push(text(246, 140, `下一周期：${cpuCycles[state.cycle] ?? state.cycle}`, { size: 12, bold: true, fill: ACCENT }))
  nodes.push(text(246, 160, `第 ${state.step} 步`, { size: 11, fill: MUTED }))
  nodes.push(text(246, 180, `PC=${registers.PC ?? '----'}`, { size: 11, fill: MUTED, mono: true }))

  return { width: 540, height: 240, nodes }
}

const SCENES = {
  gate: sceneGate,
  comb: sceneComb,
  sequential: sceneSequential,
  alu: sceneAlu,
  memory: sceneMemory,
  cpu: sceneCpu,
}

export function sceneSvg(state, preset) {
  const render = SCENES[preset]
  if (!render || !state) return null
  const scene = render(state)
  return h('svg', {
    viewBox: `0 0 ${scene.width} ${scene.height}`,
    width: '100%',
    style: `max-width:${scene.width}px;height:auto;display:block`,
    role: 'img',
    'aria-label': `${demoPresets[preset]} 状态图`,
  }, [
    h('defs', {}, [
      h('marker', {
        id: 'demo-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5',
        markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse',
      }, [h('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: LINE })]),
    ]),
    ...scene.nodes,
  ])
}

// ---------- 组件 ----------

export const DemoView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new DemoClient(props.user.id)
    const isTeacher = () => props.user.role === 'teacher'

    const courses = ref([])
    const courseId = ref('')
    const sessions = ref([])
    const total = ref(0)
    const page = ref(1)
    const preset = ref('gate')
    const current = ref(null)
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const following = ref(true)
    const running = ref(false)
    const viewing = ref(null)
    const viewError = ref('')
    let timer = null
    let runTimer = null
    let inFlight = false

    function applySession(session) {
      current.value = session
    }

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.code === 'REVISION_CONFLICT') {
          error.value = `演示已被推进（当前第 ${failure.detail?.current ?? '?'} 步），正在同步最新状态`
          await refreshCurrent(true)
        }
      } finally { busy.value = false }
    }

    async function loadSessions() {
      if (!courseId.value) { sessions.value = []; total.value = 0; return }
      const result = await api.sessions(courseId.value, { page: page.value })
      sessions.value = result.data
      total.value = result.total
    }

    async function loadCourse() {
      current.value = null
      page.value = 1
      if (!courseId.value) { sessions.value = []; total.value = 0; return }
      await loadSessions()
      if (following.value) await followActive()
    }

    // 学生（和教师）都跟随最近一个进行中的演示
    async function followActive() {
      if (!courseId.value) return
      const result = await api.sessions(courseId.value, { active: true, pageSize: 1 })
      const latest = result.data[0]
      if (latest && (!current.value || current.value.id !== latest.id)) applySession(latest)
      if (!latest && current.value && !current.value.active) { /* 保留查看最近的已关闭会话 */ }
    }

    async function refreshCurrent(force = false) {
      if (!current.value) return
      const next = await api.session(current.value.id)
      if (force || next.revision !== current.value.revision) applySession(next)
    }

    function startTimer() {
      stopTimer()
      timer = globalThis.setInterval(async () => {
        if (!following.value || !current.value?.active) return
        try { await refreshCurrent() } catch { /* 轮询失败不打断演示 */ }
      }, 2000)
    }

    function stopTimer() {
      if (timer) { globalThis.clearInterval(timer); timer = null }
    }

    async function boot() {
      courses.value = []
      sessions.value = []; current.value = null
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
      startTimer()
    }

    async function createDemo() {
      const created = await api.createSession(courseId.value, { preset: preset.value })
      applySession(created)
      await loadSessions()
      following.value = true
      return created
    }

    function stopRun() {
      if (runTimer) { globalThis.clearInterval(runTimer); runTimer = null }
      running.value = false
    }

    // 后端 action=run 是一次性算完 64 拍再返回终态，画面只会「跳一下」。
    // 真正的连续运行改由前端定时逐拍推进，每一步都从服务端拿新 state 并重绘。
    async function autoStep() {
      if (!running.value || inFlight || busy.value || !current.value?.active) return
      inFlight = true
      try {
        const next = await api.advance(current.value.id, current.value.revision, 'step')
        applySession(next)
        notice.value = `连续运行中 · 第 ${next.state?.step ?? 0} 步`
        await loadSessions()
        if (next.state?.cycle === 'halt' || next.state?.control?.halt) {
          stopRun()
          notice.value = '检测到停机信号，连续运行已结束'
        }
      } catch (failure) {
        stopRun()
        error.value = failure.message
        if (failure.code === 'REVISION_CONFLICT') {
          error.value = '演示状态已被其它操作推进，正在同步最新状态'
          await refreshCurrent(true).catch(() => {})
        }
      } finally { inFlight = false }
    }

    async function toggleRun() {
      if (running.value) {
        stopRun()
        notice.value = '已暂停连续运行'
        return
      }
      if (!current.value?.active) return
      error.value = ''
      running.value = true
      await autoStep()
      if (running.value) runTimer = globalThis.setInterval(autoStep, 1200)
    }

    async function act(action) {
      if (!current.value) return
      stopRun()
      await run(async () => {
        const next = await api.advance(current.value.id, current.value.revision, action)
        applySession(next)
        await loadSessions()
      }, `${demoActions[action]}完成`)
    }

    async function closeDemo() {
      stopRun()
      if (!current.value) return
      await run(async () => {
        const closed = await api.close(current.value.id, current.value.revision)
        applySession(closed)
        await loadSessions()
      }, '演示已关闭')
    }

    // 历史记录就地展开详情：原来只改上方舞台，列表里点「查看」看不出任何变化。
    async function viewSession(item) {
      viewError.value = ''
      try {
        const detail = await api.session(item.id)
        viewing.value = detail
      } catch (failure) {
        viewing.value = null
        viewError.value = `无法读取演示 #${item.id}：${failure.message}`
      }
    }

    function closeView() { viewing.value = null; viewError.value = '' }

    async function toggleFollow() {
      following.value = !following.value
      if (following.value) await run(followActive, '已恢复跟随最新演示')
    }

    onMounted(() => { boot().catch(failure => { error.value = failure.message }) })
    onUnmounted(() => { stopTimer(); stopRun() })

    const state = () => current.value?.state ?? null

    return () => {
      const teacher = isTeacher()
      const active = Boolean(current.value?.active)
      return h('section', { class: 'card demo-card' }, [
        h('h2', {}, '课堂演示'),
        h('p', {}, '门电路、组合逻辑、时序逻辑、运算器、存储器与指令执行流程。教师推进状态，学生端自动同步观看。'),

        h('div', { class: 'inline-form' }, [
          h('label', {}, ['课程', h('select', {
            value: courseId.value,
            onChange: event => { courseId.value = event.target.value; loadCourse().catch(f => { error.value = f.message }) },
          }, courses.value.map(course => h('option', { value: String(course.id) }, course.title ?? `课程 ${course.id}`)))]),
        ]),

        teacher && h('div', { class: 'inline-form' }, [
          h('label', {}, ['演示场景', h('select', {
            value: preset.value,
            onChange: event => { preset.value = event.target.value },
          }, Object.entries(demoPresets).map(([key, name]) => h('option', { value: key }, name)))]),
          h('button', { type: 'button', disabled: busy.value || !courseId.value, onClick: () => run(createDemo, '已新建演示') },
            busy.value ? '处理中…' : '开始新演示'),
        ]),

        error.value && h('p', { class: 'demo-alert', role: 'alert' }, error.value),
        notice.value && h('p', { class: 'demo-notice', role: 'status' }, notice.value),

        current.value ? h('div', { class: 'demo-stage' }, [
          h('header', { class: 'demo-stage-head' }, [
            h('div', {}, [
              h('strong', {}, demoPresets[current.value.preset] ?? current.value.preset),
              h('span', { class: 'demo-meta' },
                `第 ${state()?.step ?? 0} 步 · revision ${current.value.revision} · ${active ? '进行中' : '已关闭'}`),
            ]),
            h('div', { class: 'demo-actions' }, [
              !teacher && h('button', {
                type: 'button', class: 'secondary', onClick: () => run(toggleFollow),
              }, following.value ? '正在跟随' : '恢复跟随'),
              teacher && active && h('button', { type: 'button', disabled: busy.value, onClick: () => act('step') }, '单步'),
              teacher && active && h('button', {
                type: 'button', class: running.value ? 'secondary' : '',
                disabled: busy.value, onClick: toggleRun,
              }, running.value ? '停止连续' : '连续运行'),
              teacher && active && h('button', { type: 'button', disabled: busy.value, onClick: () => act('pause') }, '暂停'),
              teacher && active && h('button', { type: 'button', class: 'secondary', disabled: busy.value, onClick: () => act('reset') }, '复位'),
              teacher && active && h('button', { type: 'button', class: 'secondary', disabled: busy.value, onClick: () => run(closeDemo) }, '结束演示'),
            ]),
          ]),
          h('div', { class: 'demo-canvas' }, [sceneSvg(state(), current.value.preset)]),
          h('p', { class: 'demo-message' }, state()?.message ?? ''),
          running.value && h('p', { class: 'demo-hint', role: 'status' },
            '连续运行中：每 1.2 秒推进一拍，画面实时刷新；点「停止连续」或「暂停」结束。'),
          !teacher && h('p', { class: 'demo-hint' }, '学生端只读，每 2 秒自动同步教师推进的状态。'),
        ]) : h('p', { class: 'demo-placeholder' },
          teacher ? '选择场景后点击「开始新演示」。' : '当前课程还没有进行中的课堂演示。'),

        sessions.value.length > 0 && h('div', {}, [
          h('h3', {}, `本课程演示记录（共 ${total.value} 条）`),
          viewError.value && h('p', { class: 'demo-alert', role: 'alert' }, viewError.value),
          h('ul', { class: 'rows' }, sessions.value.map(item => h('li', { key: item.id, class: 'demo-session-item' }, [
            h('div', { class: 'demo-session-row' }, [
              h('span', {}, `#${item.id} ${demoPresets[item.preset] ?? item.preset}`),
              h('span', { class: 'demo-meta' }, `revision ${item.revision} · ${item.active ? '进行中' : '已关闭'}`),
              h('button', {
                type: 'button', class: 'secondary',
                onClick: () => (viewing.value?.id === item.id ? closeView() : run(() => viewSession(item))),
              }, viewing.value?.id === item.id ? '收起' : '查看'),
            ]),
            viewing.value?.id === item.id && h('div', { class: 'demo-session-detail' }, [
              h('div', { class: 'demo-session-detail-head' }, [
                h('strong', {}, `演示 #${viewing.value.id} · ${demoPresets[viewing.value.preset] ?? viewing.value.preset}`),
                h('span', { class: 'demo-meta' },
                  `第 ${viewing.value.state?.step ?? 0} 步 · revision ${viewing.value.revision} · ${viewing.value.active ? '进行中' : '已关闭'}`),
              ]),
              h('div', { class: 'demo-canvas' }, [sceneSvg(viewing.value.state, viewing.value.preset)]),
              h('p', { class: 'demo-message' }, viewing.value.state?.message ?? ''),
              h('p', { class: 'demo-meta' },
                `创建 ${pretty(viewing.value.created_at)} · 更新 ${pretty(viewing.value.updated_at)}`),
            ]),
          ]))),
          total.value > sessions.value.length && h('button', {
            type: 'button', class: 'secondary',
            onClick: () => run(async () => { page.value += 1; await loadSessions() }),
          }, '加载更早的记录'),
        ]),
      ])
    }
  },
}
