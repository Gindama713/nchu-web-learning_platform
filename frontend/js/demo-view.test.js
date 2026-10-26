// Component/HTTP doubles only; real browser acceptance remains unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { DemoView } from './demo-view.js'

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
const flush = async () => { await setImmediate(); await nextTick() }
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

const ROM = [0xA9, 0x05, 0x69, 0x03, 0x8D, 0x00, 0x02, 0xA9, 0x00, 0x4C, 0x00, 0x00]
const ram = Array.from({ length: 256 }, (_, index) => (index < ROM.length ? ROM[index] : 0))
const cpu = {
  id: 5, course_id: 1, preset: 'cpu', experiment_version_id: null, revision: 3, active: true,
  created_at: '2026-10-26T08:00:00Z', updated_at: '2026-10-26T08:30:00Z',
  state: {
    step: 3, cycle: 'execute', pc: 4, ir: 0xA9, a: 5, x: 0,
    flags: { zero: 0, carry: 0 }, ram,
    registers: { A: '05', X: '00', PC: '0004', IR: 'A9' },
    buses: { addr: '0004', data: '03' },
    control: { fetch: 0, decode: 0, execute: 1, mem_wr: 0, halt: 0 },
    message: '执行：LDA #05，A=05',
  },
}
const stepState = {
  ...cpu, revision: 4,
  state: {
    ...cpu.state, step: 4, cycle: 'fetch', pc: 5, ir: 0x69,
    registers: { A: '05', X: '00', PC: '0005', IR: '69' },
    buses: { addr: '0005', data: '69' },
    control: { fetch: 1, decode: 0, execute: 0, mem_wr: 0, halt: 0 },
    message: '取指：PC=0005 IR=69',
  },
}

async function mount(t, role = 'teacher', overrides = {}) {
  const fixture = {
    userId: 7, sessions: [cpu], writes: [], created: null,
    error: null, ...overrides,
  }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const ok = (data, total) => ({
      ok: true, status: 200,
      json: async () => (Array.isArray(data) ? { data, total } : { data }),
    })
    if (fixture.error) {
      return { ok: false, status: fixture.error.status, json: async () => ({ error: { message: fixture.error.message } }) }
    }
    if (path.endsWith('/auth/session')) {
      return ok({ user: { id: fixture.userId, name: '测试用户', role }, csrf_token: 'token' })
    }
    if (path === '/api/v1/courses?page=1&page_size=100') return ok([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path === '/api/v1/courses/1/demo-sessions?page=1&page_size=50') {
      return ok(fixture.sessions, fixture.sessions.length)
    }
    if (options?.method === 'POST' && path === '/api/v1/courses/1/demo-sessions') {
      fixture.writes.push(JSON.parse(options.body))
      fixture.created = { ...cpu, id: 9, preset: JSON.parse(options.body).preset, revision: 0, state: { step: 0, message: '初始' } }
      fixture.sessions = [fixture.created, ...fixture.sessions]
      return { ok: true, status: 201, json: async () => ({ data: fixture.created }) }
    }
    if (path === '/api/v1/demo-sessions/5') return ok(cpu)
    if (options?.method === 'PUT' && path === '/api/v1/demo-sessions/5/state') {
      fixture.writes.push(JSON.parse(options.body))
      return ok(stepState)
    }
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(DemoView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

test('teacher sees preset form and session list; student sees list only', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /发起演示/)
  assert.match(content(teacher.root), /门电路/)
  assert.match(content(teacher.root), /演示列表（1）/)
  assert.match(content(teacher.root), /#5/)
  assert.match(content(teacher.root), /进行中/)
  const student = await mount(t, 'student')
  assert.match(content(student.root), /演示列表（1）/)
  assert.match(content(student.root), /打开/)
  assert.doesNotMatch(content(student.root), /发起演示/)
})

test('opened cpu demo shows registers, buses and control signals; student is read-only', async t => {
  const teacher = await mount(t, 'teacher')
  await click(teacher.root, '打开')
  assert.match(content(teacher.root), /执行：LDA #05，A=05/)
  assert.match(content(teacher.root), /第 3 步 · 版本 3/)
  assert.match(content(teacher.root), /A9/)
  assert.match(content(teacher.root), /0004/)
  assert.match(content(teacher.root), /执行/)
  assert.match(content(teacher.root), /单步/)
  assert.match(content(teacher.root), /复位/)
  assert.match(content(teacher.root), /连续/)
  assert.match(content(teacher.root), /关闭演示/)
  const student = await mount(t, 'student')
  await click(student.root, '打开')
  assert.match(content(student.root), /0004/)
  assert.match(content(student.root), /只读同步中/)
  assert.doesNotMatch(content(student.root), /单步/)
  assert.doesNotMatch(content(student.root), /复位/)
  assert.doesNotMatch(content(student.root), /关闭演示/)
})

test('teacher step sends guarded revision and view follows the new revision', async t => {
  const teacher = await mount(t, 'teacher')
  await click(teacher.root, '打开')
  await click(teacher.root, '单步')
  assert.deepEqual(teacher.fixture.writes, [{ revision: 3, action: 'step' }])
  assert.match(content(teacher.root), /版本 4/)
  assert.match(content(teacher.root), /取指：PC=0005 IR=69/)
})

test('teacher creates a session from the preset form', async t => {
  const teacher = await mount(t, 'teacher')
  const form = find(teacher.root, item => item.type === 'form')
  assert.ok(form, 'create form not found')
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.deepEqual(teacher.fixture.writes, [{ preset: 'gate' }])
  assert.match(content(teacher.root), /#9/)
  assert.match(content(teacher.root), /演示列表（2）/)
})

test('server error is displayed; student sees an empty-state hint', async t => {
  const failed = await mount(t, 'student', { error: { status: 503, message: '服务未就绪' } })
  assert.match(content(failed.root), /服务未就绪/)
  const empty = await mount(t, 'student', { sessions: [] })
  assert.match(content(empty.root), /老师还没有发起课堂演示。/)
})
