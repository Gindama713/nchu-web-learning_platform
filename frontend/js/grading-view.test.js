// SPEC-018 视图测试：学生提交入口（AC-02）、模块边界（AC-04）、
// 结果轮询与隐藏用例隔离（AC-06）、系统故障提示（AC-05）与教师配置工作流。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { GradingView } from './grading-view.js'

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
const all = item => [item, ...item.children.flatMap(all)]
const content = item => item.text + item.children.map(content).join('')
const find = (root, type, label) => all(root).find(item => item.type === type && content(item) === label)
const flush = async () => { await setImmediate(); await nextTick() }

const queuedRun = { id: 21, status: 'queued', score: null, passed_count: 0, total_count: 8,
  hidden_summary: null, public_cases: null, error_code: null }
const finishedRun = { id: 21, status: 'wrong_answer', score: 75, passed_count: 6, total_count: 8,
  hidden_summary: { total: 4, passed: 2, failures: ['WRONG_ANSWER'] },
  public_cases: [{ label: 'add-1', input: [{ A: 5 }], expected: [{ Y: 8 }],
    actual: [{ Y: 8 }], passed: true },
  { label: 'and-1', input: [{ A: 5 }], expected: [{ Y: 8 }], actual: [{ Y: 9 }], passed: false }],
  error_code: null }

async function mount(t, role = 'student', overrides = {}) {
  const fixture = Object.assign({
    userId: 7, role, run: queuedRun, submission: { submission_id: 9, run_id: 21, status: 'queued' },
    writes: [], uploads: [],
  }, overrides)
  const events = []
  const listeners = {}
  const timers = []
  const previous = { fetch: globalThis.fetch, document: globalThis.document,
    CustomEvent: globalThis.CustomEvent, setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout }
  globalThis.CustomEvent = class {
    constructor(type, options = {}) { this.type = type; this.detail = options.detail }
  }
  globalThis.setTimeout = (fn, delay) => { timers.push({ fn, delay }); return timers.length }
  globalThis.clearTimeout = () => {}
  globalThis.document = {
    dispatchEvent: event => events.push(event),
    addEventListener: (type, handler) => { listeners[type] = handler },
    removeEventListener: () => {},
  }
  t.after(() => {
    globalThis.fetch = previous.fetch; globalThis.document = previous.document
    globalThis.CustomEvent = previous.CustomEvent
    globalThis.setTimeout = previous.setTimeout; globalThis.clearTimeout = previous.clearTimeout
  })
  globalThis.fetch = async (path, options = {}) => {
    const result = (data, total) => ({ ok: true, status: 200,
      json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role }, csrf_token: 'token' })
    if (options.method === 'POST' || options.method === 'PUT') {
      fixture.writes.push({ path, options })
      if (path.endsWith('/submissions')) {
        fixture.uploads.push({ path, options })
        return result(fixture.submission)
      }
      return result({ ok: true })
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path.includes('/experiment-versions?')) {
      return result([{ id: 11, version: 1, title: 'ALU v1', status: 'published',
        submission_modes: ['circuit'] }], 1)
    }
    if (path.startsWith('/api/v1/courses/1/submissions')) return result([], 0)
    if (path.startsWith('/api/v1/grading-runs/')) return result(fixture.run)
    if (path.startsWith('/api/v1/submissions/')) {
      return result({ id: 9, latest_run: fixture.run, effective_run: fixture.run })
    }
    if (path.startsWith('/api/v1/experiment-versions/11/test-suites')) {
      return result([], 0)
    }
    if (path.startsWith('/api/v1/experiment-versions/11/reference-files')) {
      return result([], 0)
    }
    throw new Error(`Unexpected path ${path}`)
  }
  const app = renderer.createApp(GradingView, { user: { id: fixture.userId, role } })
  const root = element('root')
  app.mount(root)
  await flush()
  return { root, fixture, events, listeners, timers }
}

test('student entry opens only for circuit mode from SPEC-009 dispatch (AC-02/AC-04)', async t => {
  const { root, listeners } = await mount(t)
  assert.ok(find(root, 'h2', '在线评测（SPEC-018）'))
  assert.ok(content(root).includes('请在实验中心（SPEC-009）选择'))
  listeners['cpu-experiment-open']({ detail: { mode: 'wiring', version_id: 11, experiment_id: 1 } })
  await flush()
  assert.ok(!content(root).includes('.circ 在线评测（版本 #11）'))
  listeners['cpu-experiment-open']({ detail: { mode: 'circuit', version_id: 11, experiment_id: 1 } })
  await flush()
  assert.ok(content(root).includes('.circ 在线评测（版本 #11）'))
  assert.ok(content(root).includes('请选择文件提交'))
})

test('submission polls run until terminal state then stops (AC-02)', async t => {
  const { root, listeners, fixture, timers } = await mount(t)
  listeners['cpu-experiment-open']({ detail: { mode: 'circuit', version_id: 11, experiment_id: 1 } })
  await flush()
  const upload = all(root).find(item => item.type === 'input' && item.props.type === 'file')
  assert.ok(upload, 'file input rendered')
  await upload.props.onChange({ target: { files: [new globalThis.Blob(['x'])], value: '' } })
  await flush()
  assert.equal(fixture.uploads.length, 1)
  assert.match(fixture.uploads[0].path, /\/experiment-versions\/11\/submissions$/)
  // 第一次轮询：仍排队，再次排定新计时器。
  timers.splice(0).forEach(timer => timer.fn())
  await flush()
  assert.ok(content(root).includes('排队中'))
  assert.equal(timers.length, 1)
  // 终态后停止轮询。
  fixture.run = finishedRun
  timers.splice(0).forEach(timer => timer.fn())
  await flush()
  assert.equal(timers.length, 0)
  assert.ok(content(root).includes('答案错误 · 75 分'))
})

test('student result shows public cases and hidden summary only (AC-06)', async t => {
  const { root, listeners, fixture, timers } = await mount(t)
  fixture.run = finishedRun
  listeners['cpu-experiment-open']({ detail: { mode: 'circuit', version_id: 11, experiment_id: 1 } })
  await flush()
  const upload = all(root).find(item => item.type === 'input' && item.props.type === 'file')
  await upload.props.onChange({ target: { files: [new globalThis.Blob(['x'])], value: '' } })
  await flush()
  // 触发首拍轮询：直接到达终态并停止。
  timers.splice(0).forEach(timer => timer.fn())
  await flush()
  const text = content(root)
  assert.ok(text.includes('add-1') && text.includes('and-1'))
  assert.ok(text.includes('隐藏用例 2/4'))
  assert.ok(!text.includes('sub-1'))
  assert.equal(timers.length, 0)
})

test('system_error run warns without masking previous score (AC-05)', async t => {
  const { root, listeners, fixture, timers } = await mount(t)
  fixture.run = { ...finishedRun, status: 'system_error', score: null, error_code: 'ENGINE_CRASH' }
  listeners['cpu-experiment-open']({ detail: { mode: 'circuit', version_id: 11, experiment_id: 1 } })
  await flush()
  const upload = all(root).find(item => item.type === 'input' && item.props.type === 'file')
  await upload.props.onChange({ target: { files: [new globalThis.Blob(['x'])], value: '' } })
  await flush()
  timers.splice(0).forEach(timer => timer.fn())
  await flush()
  const text = content(root)
  assert.ok(text.includes('系统故障未影响既有成绩'))
  assert.ok(text.includes('ENGINE_CRASH'))
})

test('teacher saves judge profile through verified session write', async t => {
  const { root, fixture } = await mount(t, 'teacher')
  assert.ok(content(root).includes('以下为含 circuit 模式的实验版本'))
  const configure = find(root, 'button', '配置评测')
  await configure.props.onClick()
  await flush()
  const submit = all(root).find(item => item.type === 'button'
    && content(item) === '保存判分配置')
  await submit.parent.props.onSubmit({ preventDefault() {} })
  await flush()
  const profileWrite = fixture.writes.find(write =>
    write.path.endsWith('/experiment-versions/11/judge-profile'))
  assert.equal(profileWrite.options.method, 'PUT')
  assert.deepEqual(JSON.parse(profileWrite.options.body), {
    top_circuit: 'alu8', port_schema: { inputs: { A: 8, B: 8 }, outputs: { Y: 8 } },
    allowed_components: ['Adder', 'AND', 'OR'], limits: {} })
  assert.ok(content(root).includes('判分配置已保存'))
})

test('teacher class listing renders effective score column and regrade form', async t => {
  const { root } = await mount(t, 'teacher')
  assert.ok(content(root).includes('班级提交（effective_run 为计入教学的最新有效成绩）'))
  assert.ok(find(root, 'button', '筛选'))
})

