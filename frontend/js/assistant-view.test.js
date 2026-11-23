// 只测界面状态机：发问、渲染数据卡片、动作按钮、未选课提示。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, h, nextTick } from 'vue'

import { AssistantView } from './assistant-view.js'

const element = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
function remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null }
const renderer = createRenderer({
  createElement: element, createText: text => element('text', text), createComment: () => element('comment'),
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, name, old, value) => { node.props[name] = value },
  insert: (node, parent, anchor) => {
    remove(node)
    parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, node)
    node.parent = parent
  },
  remove, parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
})
const all = node => [node, ...node.children.flatMap(all)]
const content = node => node.text + node.children.map(content).join('')
const button = (root, label) => all(root).find(node => node.type === 'button' && content(node) === label)
const flush = async () => { await setImmediate(); await nextTick() }

function mount({ role = 'teacher', courseId = 3, answer = reply, answers = null } = {}) {
  const events = []
  const requests = []
  const root = element('root')
  const queue = answers ?? [answer]
  let index = 0
  const oldFetch = globalThis.fetch
  globalThis.fetch = async (path, options = {}) => {
    const ok = data => ({ ok: true, status: 200, json: async () => ({ data }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 1, role }, csrf_token: 'tk' })
    if (path.includes('/assistant/ask')) {
      requests.push(JSON.parse(options.body ?? '{}'))
      return ok(queue[Math.min(index++, queue.length - 1)])
    }
    throw new Error('unexpected ' + path)
  }
  const app = renderer.createApp({
    render: () => h(AssistantView, {
      user: { id: 1, role }, courseId, onAction: action => events.push(action),
    }),
  })
  app.mount(root)
  return { root, events, requests, restore: () => { globalThis.fetch = oldFetch } }
}

const reply = {
  intent: 'attendance', title: '到勤率 50%', answer: '最近 28 天应到 2 人次，到勤率 50%。',
  facts: [{ label: '到勤率（出勤+迟到）', value: 50, unit: '%', source: '010A' }],
  caveats: [], matches: [], suggestions: ['这周学情怎么样？'],
  actions: [{ kind: 'navigate', label: '打开考勤与学情', payload: { tab: 'stats' } }],
  window: { from: '2026-10-23T00:00:00Z', to: '2026-11-20T00:00:00Z', days: 28 },
}

test('初始渲染欢迎语和快捷问题', () => {
  const view = mount()
  try {
    const text = content(view.root)
    assert.match(text, /教学助手/)
    assert.match(text, /这周学情怎么样/)
    assert.match(text, /教师视角/)
  } finally { view.restore() }
})

test('点击快捷问题后显示回答、数字与出处', async () => {
  const view = mount()
  try {
    button(view.root, '这周学情怎么样？').props.onClick()
    await flush()
    const text = content(view.root)
    assert.match(text, /到勤率 50%/)
    assert.match(text, /50 %/)          // fact 数值
    assert.match(text, /010A/)          // 数据出处
    assert.match(text, /最近 28 天/)     // 窗口
  } finally { view.restore() }
})

test('回答里的动作按钮交给父组件执行', async () => {
  const view = mount()
  try {
    button(view.root, '这周学情怎么样？').props.onClick()
    await flush()
    button(view.root, '打开考勤与学情').props.onClick()
    assert.deepEqual(view.events, [{ kind: 'navigate', label: '打开考勤与学情', payload: { tab: 'stats' } }])
  } finally { view.restore() }
})

test('未选课程时提问给出明确提示，不发请求', async () => {
  const view = mount({ courseId: 0 })
  try {
    button(view.root, '这周学情怎么样？').props.onClick()
    await flush()
    assert.match(content(view.root), /先在「课程与通知」里选一门课/)
  } finally { view.restore() }
})

test('学生视角使用自己的快捷问题', () => {
  const view = mount({ role: 'student' })
  try {
    const text = content(view.root)
    assert.match(text, /学生视角/)
    assert.match(text, /我哪里薄弱/)
  } finally { view.restore() }
})

// 走输入框 + 表单提交，和教师现场打字一致
function askText(root, text) {
  const input = all(root).find(node => node.type === 'input' && node.props['aria-label'] === '向教学助手提问')
  input.props.onInput({ target: { value: text } })
  const form = all(root).find(node => node.type === 'form')
  form.props.onSubmit({ preventDefault() {} })
}

test('澄清回答里的候选问题点击后直接发问', async () => {
  const clarify = {
    intent: 'clarify', title: '你想问哪一类？', answer: '没确定你问的是哪类数据。', facts: [], caveats: [],
    matches: [], suggestions: [],
    actions: [{ kind: 'ask', label: '这周学情怎么样？', payload: { question: '这周学情怎么样？' } }],
    window: null,
  }
  const view = mount({ answers: [clarify, reply] })
  try {
    askText(view.root, '帮我看看')
    await flush()
    button(view.root, '这周学情怎么样？').props.onClick()
    await flush()
    assert.equal(view.requests.length, 2)
    assert.equal(view.requests[1].question, '这周学情怎么样？')
    assert.equal(view.events.length, 0)   // 澄清候选是直接发问，不交给父组件跳转
  } finally { view.restore() }
})

test('多轮指代把上一位学生带给后端并显示上下文', async () => {
  const studentReply = {
    ...reply, intent: 'student_attendance', title: '莫涛（24201501） 到勤率 57.1%',
    student: { id: 1, name: '莫涛', student_no: '24201501' },
  }
  const view = mount({ answers: [studentReply, reply] })
  try {
    askText(view.root, '莫涛到了吗')
    await flush()
    assert.equal(view.requests[0].student_id, undefined)
    assert.match(content(view.root), /正在问：莫涛/)
    askText(view.root, '他考得怎么样')
    await flush()
    assert.equal(view.requests[1].student_id, 1)
    assert.equal(view.requests[1].question, '他考得怎么样')
  } finally { view.restore() }
})

test('没有指代词时不带学生，班级问题不被上下文劫持', async () => {
  const studentReply = {
    ...reply, intent: 'student_attendance',
    student: { id: 1, name: '莫涛', student_no: '24201501' },
  }
  const view = mount({ answers: [studentReply, reply] })
  try {
    askText(view.root, '莫涛到了吗')
    await flush()
    askText(view.root, '这周学情怎么样')
    await flush()
    assert.equal(view.requests[1].student_id, undefined)
    for (const question of ['其他学生出勤怎么样', '他们考勤怎么样', '她们考勤怎么样', '他人成绩如何']) {
      askText(view.root, question)
      await flush()
      assert.equal(view.requests.at(-1).student_id, undefined)
    }
  } finally { view.restore() }
})

test('这名学生、那名学生、那位同学都继续查询上一个学生', async () => {
  const studentReply = { ...reply, student: { id: 9, name: '同学甲', student_no: '24200009' } }
  const view = mount({ answers: [studentReply, reply] })
  try {
    askText(view.root, '同学甲考勤')
    await flush()
    for (const pronoun of ['这名学生', '那名学生', '那位同学']) {
      askText(view.root, `${pronoun}考勤怎么样`)
      await flush()
      assert.equal(view.requests.at(-1).student_id, 9)
    }
  } finally { view.restore() }
})

test('选人澄清清除旧目标，点击候选后查询并显示新目标', async () => {
  const first = { ...reply, student: { id: 9, name: '同学甲', student_no: '24200009' } }
  const clarify = { ...reply, intent: 'clarify', student: null, facts: [],
    title: '请先确认要查询的学生', suggestions: [],
    actions: [{ kind: 'ask', label: '同名学生（24200010）', payload: { question: '24200010 考勤情况' } }],
  }
  const selected = { ...reply, student: { id: 10, name: '同名学生', student_no: '24200010' } }
  const view = mount({ answers: [first, clarify, selected] })
  try {
    askText(view.root, '同学甲考勤')
    await flush()
    askText(view.root, '同名学生考勤')
    await flush()
    assert.equal(all(view.root).filter(node => node.props.class === 'assistant-context').length, 0)
    button(view.root, '同名学生（24200010）').props.onClick()
    await flush()
    assert.deepEqual(view.requests[2], { question: '24200010 考勤情况' })
    assert.match(content(view.root), /正在问：同名学生（24200010）/)
  } finally { view.restore() }
})

test('图表空值不冒充零分或零到勤率，真实零值仍可显示', async () => {
  const view = mount({ answer: {
    ...reply,
    charts: [
      { kind: 'bar', title: '空掌握度', items: [{ label: '未知', value: null }] },
      { kind: 'line', title: '不足两周', points: [{ label: '第一周', value: null }, { label: '第二周', value: 0.5 }] },
      { kind: 'bar', title: '真实零分', items: [{ label: '已评分', value: 0 }] },
      { kind: 'donut', title: '构成', slices: [{ label: '未知项', value: null }, { label: '出勤', value: 1 }] },
    ],
  } })
  try {
    askText(view.root, '考勤')
    await flush()
    assert.deepEqual(all(view.root).filter(node => node.type === 'svg').map(node => node.props['aria-label']),
      ['真实零分', '构成'])
    assert.doesNotMatch(content(view.root), /未知项|空掌握度|不足两周/)
    assert.match(content(view.root), /0/)
  } finally { view.restore() }
})

// 图表：后端只给数字和 colorKey，前端负责画。
const charted = {
  ...reply,
  charts: [{
    kind: 'donut', title: '到勤构成', unit: '人次', total: 4,
    slices: [{ label: '出勤', value: 2, colorKey: 'present' }, { label: '缺勤', value: 2, colorKey: 'absent' }],
  }],
}

test('回答带图表时渲染 SVG、标题与图例百分比', async () => {
  const view = mount({ answer: charted })
  try {
    askText(view.root, '考勤')
    await flush()
    const svgs = all(view.root).filter(node => node.type === 'svg')
    assert.equal(svgs.length, 1)
    assert.equal(svgs[0].props['aria-label'], '到勤构成')
    const text = content(view.root)
    assert.match(text, /到勤构成/)
    assert.match(text, /出勤 · 50\.0%/)
  } finally { view.restore() }
})

test('后端没给 charts 时不画空图占位', async () => {
  const view = mount()
  try {
    askText(view.root, '考勤')
    await flush()
    assert.equal(all(view.root).filter(node => node.type === 'svg').length, 0)
  } finally { view.restore() }
})

test('横向条形按 colorKey 取色，未知图表类型直接忽略', async () => {
  const bars = {
    ...reply,
    charts: [
      { kind: 'bar', title: '知识点掌握度', unit: 'percent', max: 100,
        items: [{ label: 'ALU 的运算选择', value: 60, colorKey: 'danger' },
          { label: '存储器', value: 80, colorKey: 'ok' }] },
      { kind: 'heatmap', title: '不认识的图' },
    ],
  }
  const view = mount({ answer: bars })
  try {
    askText(view.root, '哪个知识点最薄弱')
    await flush()
    const s = all(view.root).filter(node => node.type === 'svg')
    assert.equal(s.length, 1)                       // heatmap 不渲染
    const fills = all(view.root).filter(node => node.props.class === 'chart-hbar').map(node => node.props.fill)
    assert.deepEqual(fills, ['#d94c4c', '#2e8b57'])
    assert.match(content(view.root), /60%/)
  } finally { view.restore() }
})
