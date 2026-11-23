// SPEC-007 课堂演示视图：连续运行的逐拍推进与历史记录就地查看。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { DemoView, sceneSvg } from './demo-view.js'

function element(type, text = '') { return { type, text, children: [], props: {}, parent: null } }
function remove(item) {
  if (item.parent) item.parent.children.splice(item.parent.children.indexOf(item), 1)
  item.parent = null
}
const renderer = createRenderer({
  createElement: element, createText: text => element('text', text), createComment: () => element('comment'),
  setText: (item, text) => { item.text = text },
  setElementText: (item, text) => { item.text = text; item.children = [] },
  patchProp: (item, name, previous, value) => { item.props[name] = value },
  insert: (item, parent, anchor) => {
    remove(item)
    parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, item)
    item.parent = parent
  },
  remove, parentNode: item => item.parent,
  nextSibling: item => item.parent?.children[item.parent.children.indexOf(item) + 1] ?? null,
})
const content = item => item.text + item.children.map(content).join('')
const flush = async () => { await setImmediate(); await nextTick(); await setImmediate() }
const find = (item, predicate, found = []) => {
  if (predicate(item)) found.push(item)
  for (const child of item.children) find(child, predicate, found)
  return found
}
const click = async (root, label) => {
  const [button] = find(root, item => item.type === 'button' && content(item) === label)
  assert.ok(button, `button ${label} not found`)
  await button.props.onClick()
  await flush()
}

const cpuState = step => ({
  step, cycle: step > 20 ? 'halt' : 'execute', message: `连续运行第 ${step} 步`,
  registers: { A: '00', X: '00', PC: '000A', IR: '4C' },
  control: { execute: 1 }, buses: { addr: '000A', data: '00' }, ram: [],
})

async function mount(t) {
  const fixture = { advances: [], intervals: [], step: 0, revision: 3 }
  const previous = {
    fetch: globalThis.fetch, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval,
  }
  const session = {
    id: 50, course_id: 1, preset: 'cpu', revision: 3, active: true,
    state: cpuState(0), created_at: '2026-11-12T08:00:00Z', updated_at: '2026-11-12T08:30:00Z',
  }
  const ok = (data, total) => ({ ok: true, status: 200,
    json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
  globalThis.fetch = async (path, options = {}) => {
    if (path.endsWith('/auth/session')) {
      return ok({ user: { id: 7, name: '测试教师', role: 'teacher' }, csrf_token: 'token' })
    }
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 1, title: '课程 1' }], 1)
    if (path.startsWith('/api/v1/courses/1/demo-sessions?')) return ok([session], 1)
    if (path.startsWith('/api/v1/demo-sessions/50/state') && options.method === 'PUT') {
      fixture.advances.push(JSON.parse(options.body))
      fixture.step += 1
      fixture.revision += 1
      return ok({ ...session, revision: fixture.revision, state: cpuState(fixture.step) })
    }
    if (path.startsWith('/api/v1/demo-sessions/50')) {
      return ok({ ...session, revision: fixture.revision, state: cpuState(fixture.step) })
    }
    throw new Error(`Unexpected path ${path}`)
  }
  // 不真起定时器：捕获回调，测试里手动逐拍推进。
  globalThis.setInterval = (fn, ms) => { fixture.intervals.push({ fn, ms }); return 999 }
  globalThis.clearInterval = () => {}
  const root = element('root')
  const app = renderer.createApp(DemoView, { user: { id: 7, name: '测试教师', role: 'teacher' } })
  app.mount(root)
  t.after(() => {
    app.unmount()
    globalThis.fetch = previous.fetch
    globalThis.setInterval = previous.setInterval
    globalThis.clearInterval = previous.clearInterval
  })
  await flush()
  return { root, fixture }
}

test('连续运行按固定间隔逐拍推进，画面随每拍更新', async t => {
  const { root, fixture } = await mount(t)
  assert.match(content(root), /连续运行/)
  await click(root, '连续运行')
  assert.equal(fixture.advances.length, 1)
  assert.deepEqual(fixture.advances[0], { revision: 3, action: 'step' })
  assert.match(content(root), /连续运行第 1 步/)
  const runTimer = fixture.intervals.find(entry => entry.ms === 1200)
  assert.ok(runTimer, 'continuous run timer was registered')
  await runTimer.fn()
  await flush()
  await runTimer.fn()
  await flush()
  assert.equal(fixture.advances.length, 3)
  assert.equal(fixture.advances[2].revision, 5)
  assert.match(content(root), /连续运行第 3 步/)
  await click(root, '停止连续')
  await runTimer.fn()
  await flush()
  assert.equal(fixture.advances.length, 3)
})

test('点「查看」在记录行内展开历史会话详情', async t => {
  const { root } = await mount(t)
  assert.doesNotMatch(content(root), /演示 #50/)
  await click(root, '查看')
  assert.match(content(root), /演示 #50 · 指令执行/)
  assert.match(content(root), /连续运行第 0 步/)
  assert.match(content(root), /收起/)
  assert.ok(find(root, item => item.type === 'svg').length >= 2, 'detail renders its own state diagram')
  await click(root, '收起')
  assert.doesNotMatch(content(root), /演示 #50/)
})

// 组合逻辑图：MUX 与 ALU 各自都要接到 A/B 两路数据，SEL 走虚线控制线。
function vnodes(vnode, out = []) {
  if (!vnode || typeof vnode !== 'object') return out
  out.push(vnode)
  if (Array.isArray(vnode.children)) vnode.children.forEach(child => vnodes(child, out))
  return out
}

test('组合逻辑场景把 A/B 同时接到 MUX 与 ALU，并用虚线画 SEL 控制线', () => {
  const vnode = sceneSvg({ step: 2, a: 5, b: 3, sel: 1, mux_out: 3, alu_out: 2 }, 'comb')
  const nodes = vnodes(vnode)
  const texts = nodes.filter(item => item.type === 'text')
    .map(item => (typeof item.children === 'string' ? item.children : ''))
  assert.ok(texts.includes('MUX'))
  assert.ok(texts.includes('ALU'))
  assert.ok(texts.some(value => value.includes('SEL=1') && value.includes('选 B')))
  assert.ok(texts.some(value => value.includes('OP=1') && value.includes('减')))

  // 6 个端子：MUX 的 A/B/SEL、ALU 的 A/B/OP。
  const ports = nodes.filter(item => item.type === 'circle' && item.props.fill === '#ffffff')
  assert.equal(ports.length, 6)
  // 3 个分叉节点：A、B 数据线与 SEL 控制干线。
  const junctions = nodes.filter(item => item.type === 'circle' && item.props.fill !== '#ffffff')
  assert.equal(junctions.length, 3)
  // 控制干线 + 两条分支都用虚线，和数据线区分开。
  const dashed = nodes.filter(item => item.type === 'polyline' && item.props['stroke-dasharray'])
  assert.equal(dashed.length, 3)
  // 折线引线（A/B 下台阶与 SEL 的中缝分叉）都要带箭头，保证箭头指到端口而不是停在空白处。
  const arrows = nodes.filter(item => item.type === 'polyline' && item.props['marker-end'])
  assert.equal(arrows.length, 4)
})
