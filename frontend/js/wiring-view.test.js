// Component/HTTP doubles only; real browser acceptance remains unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer } from 'vue'
import { WiringView } from './wiring-view.js'

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
const findAll = (item, match, acc = []) => {
  if (match(item)) acc.push(item)
  for (const child of item.children ?? []) findAll(child, match, acc)
  return acc
}
const click = async (root, label) => {
  const node = find(root, item => item.type === 'button' && content(item) === label)
  assert.ok(node, `button ${label} not found`)
  node.props.onClick({ preventDefault() {} })
  await flush()
}
const submitForm = async (root, cls) => {
  const node = find(root, item => item.type === 'form' && item.props?.class === cls)
  assert.ok(node, `form ${cls} not found`)
  node.props.onSubmit({ preventDefault() {} })
  await flush()
}

const PANEL = {
  schema_version: 1, code: 'EXP-01',
  components: [
    { id: 'sw_a', type: 'SWITCH', params: { width: 8, initial: 0 }, ports: { OUT: 'sw_a_out' } },
    { id: 'sw_b', type: 'SWITCH', params: { width: 8, initial: 0 }, ports: { OUT: 'sw_b_out' } },
    { id: 'sw_op', type: 'SWITCH', params: { width: 3, initial: 0 }, ports: { OUT: 'sw_op_out' } },
    { id: 'alu', type: 'ALU8', params: {}, ports: { A: 'alu_a', B: 'alu_b', OP: 'alu_op', Y: 'alu_y', Z: 'alu_z', C: 'alu_c' } },
    { id: 'led_y', type: 'LED', params: { width: 8 }, ports: { IN: 'led_y_in' } },
    { id: 'led_z', type: 'LED', params: { width: 1 }, ports: { IN: 'led_z_in' } },
    { id: 'led_c', type: 'LED', params: { width: 1 }, ports: { IN: 'led_c_in' } },
  ],
  terminals: [
    { id: 'sw_a_out', component_id: 'sw_a', name: 'OUT', direction: 'out', width: 8, required: false },
    { id: 'sw_b_out', component_id: 'sw_b', name: 'OUT', direction: 'out', width: 8, required: false },
    { id: 'sw_op_out', component_id: 'sw_op', name: 'OUT', direction: 'out', width: 3, required: false },
    { id: 'alu_a', component_id: 'alu', name: 'A', direction: 'in', width: 8, required: true },
    { id: 'alu_b', component_id: 'alu', name: 'B', direction: 'in', width: 8, required: true },
    { id: 'alu_op', component_id: 'alu', name: 'OP', direction: 'in', width: 3, required: true },
    { id: 'alu_y', component_id: 'alu', name: 'Y', direction: 'out', width: 8, required: false },
    { id: 'alu_z', component_id: 'alu', name: 'Z', direction: 'out', width: 1, required: false },
    { id: 'alu_c', component_id: 'alu', name: 'C', direction: 'out', width: 1, required: false },
    { id: 'led_y_in', component_id: 'led_y', name: 'IN', direction: 'in', width: 8, required: false },
    { id: 'led_z_in', component_id: 'led_z', name: 'IN', direction: 'in', width: 1, required: false },
    { id: 'led_c_in', component_id: 'led_c', name: 'IN', direction: 'in', width: 1, required: false },
  ],
}
const WIRES = [
  { id: 'w-1', from_terminal: 'sw_a_out', to_terminal: 'alu_a' },
  { id: 'w-2', from_terminal: 'sw_b_out', to_terminal: 'alu_b' },
  { id: 'w-3', from_terminal: 'sw_op_out', to_terminal: 'alu_op' },
  { id: 'w-4', from_terminal: 'alu_y', to_terminal: 'led_y_in' },
  { id: 'w-5', from_terminal: 'alu_z', to_terminal: 'led_z_in' },
  { id: 'w-6', from_terminal: 'alu_c', to_terminal: 'led_c_in' },
]
const HISTORY = [
  ...WIRES.map((wire, index) => ({
    seq: index + 1, type: 'connect', payload: { ...wire }, client_at: '2026-10-26T07:00:00Z',
  })),
  { seq: 7, type: 'set_input', payload: { terminal_id: 'sw_a_out', value: 255 }, client_at: '2026-10-26T07:30:00Z' },
  { seq: 8, type: 'set_input', payload: { terminal_id: 'sw_b_out', value: 1 }, client_at: '2026-10-26T07:40:00Z' },
  { seq: 9, type: 'set_input', payload: { terminal_id: 'sw_op_out', value: 0 }, client_at: '2026-10-26T07:50:00Z' },
]

function freshAttempt() {
  return {
    id: 12, experiment_version_id: 3, student_id: 7, revision: 2, status: 'draft',
    state: { wires: WIRES.map(wire => ({ ...wire })), inputs: { sw_a_out: 255, sw_b_out: 1, sw_op_out: 0 },
      phase: 0, tick: 0, clk: 0, reset: 0, enable: 1 },
    latest_seq: 9, snapshot_hash: null, submitted_at: null, completed: false,
    functional_results: null, saved_at: '2026-10-26T08:00:00Z',
    created_at: '2026-10-26T07:00:00Z', updated_at: '2026-10-26T08:00:00Z', action_count: 9,
  }
}

const VERSION = {
  id: 3, experiment_id: 2, version: 1, title: 'EXP-01 组合逻辑', objectives: '', knowledge_ids: [],
  instructions: '', submission_modes: ['wiring'], panel: PANEL, rules: {}, judge_profile_id: null,
  status: 'published', published_at: '2026-10-25T00:00:00Z', start_at: null, end_at: null,
  experiment: { id: 2, code: 'EXP-01', title: '组合逻辑实验', description: '', archived: false },
}

async function mount(t, role = 'student', overrides = {}) {
  const fixture = {
    userId: 7, attempt: freshAttempt(), attempts: [freshAttempt()], history: HISTORY.map(row => ({ ...row })),
    version: VERSION, writes: [], error: null, validateResult: null, submitResult: null,
    validateRevision: null, ...overrides,
  }
  const okData = data => ({ ok: true, status: 200, json: async () =>
    (Array.isArray(data) ? { data, total: data.length } : { data }) })
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
    if (path === '/api/v1/courses/1/experiment-versions?status=published&page=1&page_size=100') {
      return okData([fixture.version])
    }
    if (path === '/api/v1/courses/1/wiring-attempts?experiment_version_id=3&page=1&page_size=50') {
      return okData(fixture.attempts)
    }
    if (path === '/api/v1/wiring-attempts/12/actions?after_seq=0&page=1&page_size=200') {
      return okData({ items: fixture.history, latest_seq: fixture.attempt.latest_seq,
        next_after_seq: fixture.attempt.latest_seq, page: 1, page_size: 200, total: fixture.history.length })
    }
    if (options?.method === 'PUT' && path === '/api/v1/wiring-attempts/12') {
      const payload = JSON.parse(options.body)
      fixture.writes.push(payload)
      fixture.attempt.revision = payload.revision + 1
      fixture.attempt.state = payload.state
      fixture.attempt.latest_seq += payload.actions.length
      fixture.attempt.action_count = fixture.attempt.latest_seq
      fixture.attempt.saved_at = '2026-10-26T09:00:00Z'
      return okData({ id: 12, revision: fixture.attempt.revision,
        latest_seq: fixture.attempt.latest_seq, saved_at: fixture.attempt.saved_at })
    }
    if (path === '/api/v1/wiring-attempts/12') return okData(fixture.attempt)
    if (options?.method === 'POST' && path === '/api/v1/wiring-attempts/12/validate') {
      fixture.validateRevision = JSON.parse(options.body).revision
      return okData(fixture.validateResult ?? { valid: true, errors: [], revision: fixture.validateRevision })
    }
    if (options?.method === 'POST' && path === '/api/v1/wiring-attempts/12/submit') {
      fixture.attempt.status = 'submitted'
      fixture.attempt.completed = true
      fixture.attempt.snapshot_hash = 'abc123def4567890'
      fixture.attempt.submitted_at = '2026-10-26T10:00:00Z'
      fixture.attempt.functional_results = [
        { op: 'ADD', passed: true, expected: { Y: 0, Z: 1, C: 1 }, actual: { Y: 0, Z: 1, C: 1 } },
      ]
      return okData({ id: 12, status: 'submitted', completed: true,
        snapshot_hash: 'abc123def4567890', submitted_at: '2026-10-26T10:00:00Z' })
    }
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(WiringView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

const pickVersion = async root => {
  const selects = findAll(root, item => item.type === 'select')
  selects[1].props.onChange({ target: { value: '3' } })
  await flush()
}

test('student opens attempt and sees five regions with live signals', async t => {
  const view = await mount(t, 'student')
  assert.match(content(view.root), /EXP-01 组合逻辑/)
  await pickVersion(view.root)
  assert.match(content(view.root), /连线记录（1）/)
  assert.match(content(view.root), /发起连线/)
  assert.match(content(view.root), /#12/)
  await click(view.root, '打开')
  assert.match(content(view.root), /连线 #12 · EXP-01 组合逻辑 · 草稿/)
  assert.match(content(view.root), /器件端子/)
  assert.match(content(view.root), /连线画布/)
  assert.match(content(view.root), /输入时钟/)
  assert.match(content(view.root), /动作历史/)
  assert.match(content(view.root), /校验提交/)
  assert.match(content(view.root), /sw_a_out → alu_a/)
  assert.match(content(view.root), /w-1sw_a.OUTalu.A/)
  assert.match(content(view.root), /当前 255/)
  assert.match(content(view.root), /led_y\(8位\)0/)
  assert.match(content(view.root), /led_z\(1位\)1/)
  assert.match(content(view.root), /revision 2 · 动作 9/)
})

test('connect and write input buffer locally then save in one guarded PUT', async t => {
  const view = await mount(t, 'student')
  await pickVersion(view.root)
  await click(view.root, '打开')
  const form = find(view.root, item => item.type === 'form' && item.props?.class === 'wiring-connect')
  const selects = findAll(form, item => item.type === 'select')
  selects[0].props.onChange({ target: { value: 'sw_a_out' } })
  selects[1].props.onChange({ target: { value: 'alu_b' } })
  await submitForm(view.root, 'wiring-connect')
  assert.match(content(view.root), /未保存 1 条动作/)
  const inputForm = find(view.root, item => item.type === 'form' && item.props?.class === 'wiring-input')
  findAll(inputForm, item => item.type === 'select')[0].props.onChange({ target: { value: 'sw_b_out' } })
  find(inputForm, item => item.type === 'input').props.onInput({ target: { value: '2' } })
  await submitForm(view.root, 'wiring-input')
  assert.match(content(view.root), /当前 2/)
  await click(view.root, '保存')
  assert.equal(view.fixture.writes.length, 1)
  assert.equal(view.fixture.writes[0].revision, 2)
  assert.deepEqual(view.fixture.writes[0].actions.map(action => action.type), ['connect', 'set_input'])
  assert.equal(view.fixture.writes[0].state.wires.length, 7)
  assert.equal(view.fixture.writes[0].state.inputs.sw_b_out, 2)
  assert.match(content(view.root), /已保存/)
  assert.match(content(view.root), /revision 3 · 动作 11/)
  assert.match(content(view.root), /无未保存修改/)
})

test('undo removes the last buffered edits before saving', async t => {
  const view = await mount(t, 'student')
  await pickVersion(view.root)
  await click(view.root, '打开')
  await click(view.root, '撤销')
  await click(view.root, '撤销')
  assert.match(content(view.root), /未保存 2 条动作/)
  assert.match(content(view.root), /当前 255/)
  await click(view.root, '撤销')
  await click(view.root, '撤销')
  assert.match(content(view.root), /未保存 4 条动作/)
  assert.doesNotMatch(content(view.root), /w-6/)
  assert.match(content(view.root), /当前 0/)
  await click(view.root, '保存')
  assert.deepEqual(view.fixture.writes[0].actions.map(action => action.type), ['undo', 'undo', 'undo', 'undo'])
  assert.equal(view.fixture.writes[0].state.wires.length, 5)
})

test('step sends guarded action and view shows client-simulated replay state', async t => {
  const view = await mount(t, 'student')
  await pickVersion(view.root)
  await click(view.root, '打开')
  await click(view.root, '单步')
  assert.equal(view.fixture.writes[0].revision, 2)
  assert.equal(view.fixture.writes[0].actions[0].type, 'step')
  assert.equal(view.fixture.writes[0].state.tick, 1)
  assert.match(content(view.root), /1 · 译码/)
  assert.match(content(view.root), /revision 3 · 动作 10/)
})

test('validation errors are rendered with codes and terminals (AC-02)', async t => {
  const view = await mount(t, 'student', {
    validateResult: { valid: false, revision: 2, errors: [
      { code: 'WIDTH_MISMATCH', message: '位宽不一致', terminal_ids: ['alu_a', 'sw_op_out'] },
    ] },
  })
  await pickVersion(view.root)
  await click(view.root, '打开')
  await click(view.root, '校验')
  assert.equal(view.fixture.validateRevision, 2)
  assert.match(content(view.root), /WIDTH_MISMATCH/)
  assert.match(content(view.root), /位宽不一致/)
  assert.match(content(view.root), /alu_a sw_op_out/)
})

test('submit locks the attempt and shows functional results (AC-07)', async t => {
  const view = await mount(t, 'student')
  await pickVersion(view.root)
  await click(view.root, '打开')
  await click(view.root, '提交')
  assert.match(content(view.root), /已提交/)
  assert.match(content(view.root), /abc123def456/)
  assert.match(content(view.root), /全部通过/)
  assert.match(content(view.root), /ADD/)
  assert.match(content(view.root), /重新连线/)
  assert.doesNotMatch(content(view.root), /单步/)
})

test('teacher browses attempts read-only with action history', async t => {
  const view = await mount(t, 'teacher')
  assert.doesNotMatch(content(view.root), /发起连线/)
  await pickVersion(view.root)
  await click(view.root, '打开')
  assert.match(content(view.root), /连线画布/)
  assert.match(content(view.root), /w-1sw_a.OUTalu.A/)
  assert.match(content(view.root), /连接/)
  assert.doesNotMatch(content(view.root), /断线/)
  assert.doesNotMatch(content(view.root), /写入/)
  assert.doesNotMatch(content(view.root), /保存校验/)
})

test('server error is displayed and student sees empty-state hint', async t => {
  const failed = await mount(t, 'student', { error: { status: 503, code: 'UNAVAILABLE', message: '服务未就绪' } })
  assert.match(content(failed.root), /服务未就绪/)
  const empty = await mount(t, 'student', { attempts: [] })
  await pickVersion(empty.root)
  assert.match(content(empty.root), /还没有连线记录，可发起新连线。/)
  assert.match(content(empty.root), /发起连线/)
})
