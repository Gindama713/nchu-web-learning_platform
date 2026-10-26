// Component/HTTP doubles only; real browser acceptance remains unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer } from 'vue'
import { GraphView } from './graph-view.js'

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
const flush = async () => { await setImmediate() }
const find = (item, match) => {
  if (match(item)) return item
  for (const child of item.children ?? []) {
    const found = find(child, match)
    if (found) return found
  }
  return null
}
const click = async (root, label) => {
  const node = find(root, item => item.type === 'button' && content(item) === label)
  assert.ok(node, `button ${label} not found`)
  node.props.onClick({ preventDefault() {} })
  await flush()
}

const NODES = [
  { id: 1, title: 'ALU', is_foundational: true, mastery: 1 },
  { id: 2, title: '寄存器', is_foundational: false, mastery: 0 },
  { id: 3, title: '加法器', is_foundational: false, mastery: 0 },
  { id: 4, title: '指令', is_foundational: false, mastery: 0 },
]
const EDGES = [
  { source: 4, target: 1, type: 'prerequisite' },
  { source: 1, target: 2, type: 'contains' },
  { source: 1, target: 3, type: 'contains' },
]
const PATHS = [{ from: 4, to: 1 }]

function graphData() {
  return { nodes: NODES.map(node => ({ ...node })), edges: EDGES.map(edge => ({ ...edge })),
    prerequisite_paths: PATHS.map(path => ({ ...path })) }
}

async function mount(t, role = 'student', overrides = {}) {
  const fixture = {
    userId: 7, graph: graphData(), writes: [], error: null, cycle: false, ...overrides,
  }
  const okData = data => ({ ok: true, status: 200, json: async () =>
    ({ data, total: Array.isArray(data) ? data.length : 1 }) })
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    if (fixture.error) {
      return { ok: false, status: fixture.error.status, json: async () =>
        ({ error: { code: fixture.error.code, message: fixture.error.message } }) }
    }
    if (path.endsWith('/auth/session')) {
      return okData({ user: { id: fixture.userId, name: '测试用户', role }, csrf_token: 'token' })
    }
    if (path === '/api/v1/courses?page=1&page_size=100') return okData([{ id: 1, title: 'Fixture 课程' }])
    if (path === '/api/v1/courses/1/knowledge-graph') return okData(fixture.graph)
    if (path === '/api/v1/courses/1/knowledge-graph?root_id=1') {
      return okData({
        nodes: [NODES[0], NODES[1], NODES[2], NODES[3]].map(node => ({ ...node })),
        edges: EDGES.map(edge => ({ ...edge })),
        prerequisite_paths: PATHS.map(path => ({ ...path })), root_id: 1,
      })
    }
    if (options?.method === 'POST' && path === '/api/v1/courses/1/knowledge-edges') {
      const payload = JSON.parse(options.body)
      fixture.writes.push(payload)
      if (fixture.cycle) {
        return { ok: false, status: 422, json: async () =>
          ({ error: { code: 'PREREQUISITE_CYCLE', message: '先修关系存在环' } }) }
      }
      const edge = { source: payload.source_id, target: payload.target_id, type: payload.type }
      fixture.graph.edges.push(edge)
      if (payload.type === 'prerequisite') {
        fixture.graph.prerequisite_paths.push({ from: payload.source_id, to: payload.target_id })
      }
      return { ok: true, status: 201, json: async () => ({ data: { id: fixture.graph.edges.length, ...edge } }) }
    }
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(GraphView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

test('graph renders nodes with real mastery state and edge list', async t => {
  const view = await mount(t, 'student')
  assert.match(content(view.root), /#1/)
  assert.match(content(view.root), /ALU/)
  assert.match(content(view.root), /已掌握/)
  assert.match(content(view.root), /未掌握/)
  assert.match(content(view.root), /寄存器/)
  assert.match(content(view.root), /先修指令ALU/)
  assert.match(content(view.root), /包含ALU寄存器/)
  assert.doesNotMatch(content(view.root), /添加关系/)
})

test('clicking ALU shows related registers/adders and recomputable path (AC-01/AC-04)', async t => {
  const view = await mount(t, 'student')
  await click(view.root, '查看')
  const panel = find(view.root, item => item.type === 'section' && item.props?.class === 'graph-focus-panel')
  assert.ok(panel, 'focus panel not found')
  const text = content(panel)
  assert.match(text, /节点 #1 ALU/)
  assert.match(text, /包含 寄存器/)
  assert.match(text, /包含 加法器/)
  assert.match(text, /先学 ← 指令/)
  assert.match(text, /指令 → ALU/)
})

test('root focus refetches with root_id and shows the subgraph hint', async t => {
  const view = await mount(t, 'student')
  const select = find(view.root, item => item.type === 'select' && item.props?.value === ''
    && content(item).includes('全图'))
  assert.ok(select, 'root select not found')
  select.props.onChange({ target: { value: '1' } })
  await flush()
  assert.match(content(view.root), /已聚焦 #1 ALU 的关联子图。/)
})

test('teacher adds a prerequisite edge and the path list follows (AC-04)', async t => {
  const view = await mount(t, 'teacher')
  assert.match(content(view.root), /添加关系/)
  const form = find(view.root, item => item.type === 'form' && item.props?.class === 'graph-edge-form')
  const selects = []
  const walk = item => {
    if (item.type === 'select') selects.push(item)
    for (const child of item.children ?? []) walk(child)
  }
  walk(form)
  selects[0].props.onChange({ target: { value: '2' } })
  selects[1].props.onChange({ target: { value: '4' } })
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.deepEqual(view.fixture.writes, [{ source_id: 2, target_id: 4, type: 'prerequisite' }])
  assert.match(content(view.root), /先修寄存器指令/)
  assert.match(content(view.root), /关系已保存/)
})

test('cycle edge is rejected with the server message (AC-02)', async t => {
  const view = await mount(t, 'teacher', { cycle: true })
  const form = find(view.root, item => item.type === 'form' && item.props?.class === 'graph-edge-form')
  const selects = []
  const walk = item => {
    if (item.type === 'select') selects.push(item)
    for (const child of item.children ?? []) walk(child)
  }
  walk(form)
  selects[0].props.onChange({ target: { value: '1' } })
  selects[1].props.onChange({ target: { value: '4' } })
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(view.fixture.writes.length, 1)
  assert.match(content(view.root), /先修关系存在环/)
})

test('empty graph and server failure show explicit states', async t => {
  const empty = await mount(t, 'student', { graph: { nodes: [], edges: [], prerequisite_paths: [] } })
  assert.match(content(empty.root), /课程暂无知识点，请先在知识库中创建。/)
  const failed = await mount(t, 'student', { error: { status: 503, code: 'MAINTENANCE', message: '服务维护中' } })
  assert.match(content(failed.root), /服务维护中/)
})
