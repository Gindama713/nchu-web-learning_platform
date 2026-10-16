// SPEC-009 视图测试：指导内容（AC-01）、两类提交入口（AC-02）、本人历史版本（AC-03）、
// 模块边界提示（AC-04）与教师工作流。组件/HTTP 双替身，不含真实浏览器验收。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { ExperimentView } from './experiment-view.js'

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
const field = (root, label, type) => find(root, 'span', label).parent.children.find(item => item.type === type)
const flush = async () => { await setImmediate(); await nextTick() }

const detailFixture = (modes = ['wiring', 'circuit']) => ({
  id: 11, experiment_id: 1, version: 1, title: 'ALU v1',
  objectives: '理解ALU运算', knowledge_ids: [10], instructions: '1. 连接 A/B/OP；2. 观察指示灯',
  submission_modes: modes,
  panel: { schema_version: 1, components: [{ id: 'alu', type: 'ALU8' }], terminals: [], layout: {} },
  rules: { require_required_inputs: true },
  judge_profile_id: null, status: 'published',
  published_at: '2026-10-01T00:00:00Z', start_at: '2026-10-01T00:00:00Z', end_at: '2099-01-01T00:00:00Z',
  experiment: { id: 1, code: 'EXP-01', title: '8位ALU', description: '组合逻辑实验', archived: 0 },
  participant_count: 2,
})

async function mount(t, role = 'teacher', overrides = {}) {
  const fixture = Object.assign({
    userId: 7, writes: [],
    experiments: [{
      id: 1, code: 'EXP-01', title: '8位ALU', description: '组合逻辑实验', archived: 0, created_at: '',
      latest_version: { id: 11, version: 1, title: 'ALU v1', status: 'published', submission_modes: ['wiring', 'circuit'],
        start_at: '2026-10-01T00:00:00Z', end_at: '2099-01-01T00:00:00Z', published_at: '2026-10-01T00:00:00Z',
        participant_count: 2 },
    }],
    versions: [
      { id: 11, experiment_id: 1, version: 1, title: 'ALU v1', status: 'published',
        start_at: '2026-10-01T00:00:00Z', end_at: '2099-01-01T00:00:00Z' },
      { id: 12, experiment_id: 1, version: 2, title: 'ALU v2', status: 'draft', start_at: null, end_at: null },
    ],
    detail: detailFixture(),
  }, overrides)
  const events = []
  const previous = { fetch: globalThis.fetch, document: globalThis.document, CustomEvent: globalThis.CustomEvent }
  globalThis.CustomEvent = class {
    constructor(type, options = {}) { this.type = type; this.detail = options.detail }
  }
  globalThis.document = { dispatchEvent: event => events.push(event) }
  globalThis.fetch = async (path, options = {}) => {
    const result = (data, total) => ({ ok: true, status: 200,
      json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role }, csrf_token: 'token' })
    if (options.method) {
      fixture.writes.push({ path, values: JSON.parse(options.body) })
      return result(fixture.detail)
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path.includes('/knowledge-points?')) return result([{ id: 10, title: '程序计数器' }], 1)
    if (path.includes('/experiments?')) return result(fixture.experiments, fixture.experiments.length)
    if (path.includes('/experiment-versions?')) return result(fixture.versions, fixture.versions.length)
    if (path.startsWith('/api/v1/experiment-versions/')) return result(fixture.detail)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(ExperimentView, { user: { id: 7, role } })
  app.mount(root)
  t.after(() => {
    app.unmount()
    globalThis.fetch = previous.fetch
    globalThis.document = previous.document
    globalThis.CustomEvent = previous.CustomEvent
  })
  await flush()
  return { root, fixture, events }
}

const formByClass = (root, className) => all(root).find(item => item.type === 'form'
  && item.props.class === className)

test('AC-01 teacher opens guidance with objectives, devices, steps, rules and knowledge', async t => {
  const { root } = await mount(t)
  assert.match(content(root), /8位ALU/)
  assert.match(content(root), /已发布 · 进行中 · 2 人/)
  find(root, 'button', '查看指导').props.onClick()
  await flush()
  assert.match(content(root), /实验目标/)
  assert.match(content(root), /理解ALU运算/)
  assert.match(content(root), /实验器件/)
  assert.match(content(root), /alu · ALU8/)
  assert.match(content(root), /实验步骤/)
  assert.match(content(root), /1\. 连接 A\/B\/OP；2\. 观察指示灯/)
  assert.match(content(root), /验证规则（公开部分）/)
  assert.match(content(root), /关联知识点/)
  assert.match(content(root), /程序计数器/)
})

test('teacher creates an experiment and a version with parsed panel and rules JSON', async t => {
  const { root, fixture } = await mount(t)
  find(root, 'button', '新增实验').props.onClick()
  await flush()
  field(root, '实验代码', 'select').props.onChange({ target: { value: 'EXP-02' } })
  field(root, '标题', 'input').props.onInput({ target: { value: '寄存器与总线' } })
  field(root, '说明', 'input').props.onInput({ target: { value: '掌握写入时序' } })
  formByClass(root, 'inline-form experiment-create').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.deepEqual(fixture.writes[0].values, {
    code: 'EXP-02', title: '寄存器与总线', description: '掌握写入时序',
  })
  find(root, 'button', '新增版本').props.onClick()
  await flush()
  field(root, '所属实验', 'select').props.onChange({ target: { value: '1' } })
  field(root, '版本标题', 'input').props.onInput({ target: { value: 'ALU v3' } })
  field(root, '实验目标', 'textarea').props.onInput({ target: { value: '目标X' } })
  field(root, '实验步骤', 'textarea').props.onInput({ target: { value: '步骤Y' } })
  find(root, 'label', '程序计数器').children[0].props.onChange({ target: { checked: true } })
  find(root, 'label', '.circ 在线评测（发布需 SPEC-018 判分配置）').children[0]
    .props.onChange({ target: { checked: true } })
  field(root, '面板 panel JSON（连线必填）', 'textarea').props.onInput({
    target: { value: '{"schema_version":1,"components":[],"terminals":[],"layout":{}}' },
  })
  field(root, '规则 rules JSON（hidden 部分仅教师可见）', 'textarea').props.onInput({
    target: { value: '{"require_required_inputs":true}' },
  })
  formByClass(root, 'inline-form experiment-version-form').props.onSubmit({ preventDefault() {} })
  await flush()
  const version = fixture.writes.at(-1).values
  assert.equal(version.title, 'ALU v3')
  assert.deepEqual(version.submission_modes, ['wiring', 'circuit'])
  assert.deepEqual(version.panel, { schema_version: 1, components: [], terminals: [], layout: {} })
  assert.deepEqual(version.rules, { require_required_inputs: true })
  assert.deepEqual(version.knowledge_ids, [10])
})

test('teacher publishes a draft version with an ISO window', async t => {
  const { root, fixture } = await mount(t)
  find(root, 'button', '发布').props.onClick()
  await flush()
  field(root, '开始时间', 'input').props.onInput({ target: { value: '2026-11-01T08:00' } })
  field(root, '截止时间', 'input').props.onInput({ target: { value: '2026-11-08T08:00' } })
  formByClass(root, 'inline-form experiment-publish').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.writes[0].path, '/api/v1/experiment-versions/12/publish')
  assert.deepEqual(fixture.writes[0].values, {
    start_at: new Date('2026-11-01T08:00').toISOString(),
    end_at: new Date('2026-11-08T08:00').toISOString(),
  })
  assert.match(content(root), /版本已发布，参与名单已冻结并通知学生/)
})

test('AC-02 student sees both submission entries and dispatches the wiring target', async t => {
  const { root, events } = await mount(t, 'student')
  find(root, 'button', '查看指导').props.onClick()
  await flush()
  const wiring = find(root, 'button', '进入实验箱连线（SPEC-017）')
  const circuit = find(root, 'button', '上传 .circ 在线评测（SPEC-018）')
  assert.ok(wiring)
  assert.ok(circuit)
  wiring.props.onClick()
  assert.equal(events.length, 1)
  assert.equal(events[0].type, 'cpu-experiment-open')
  assert.deepEqual(events[0].detail, { mode: 'wiring', version_id: 11, experiment_id: 1 })
  await flush()
  assert.match(content(root), /SPEC-017 模块提供/)
  circuit.props.onClick()
  assert.equal(events[1].detail.mode, 'circuit')
  await flush()
  assert.match(content(root), /SPEC-018 模块提供/)
})

test('AC-02 wiring-only version shows only the wiring entry', async t => {
  const { root } = await mount(t, 'student', {
    experiments: [{
      id: 2, code: 'EXP-03', title: 'CPU数据通路连线', description: '', archived: 0, created_at: '',
      latest_version: { id: 21, version: 1, title: '通路 v1', status: 'published',
        submission_modes: ['wiring'], start_at: '2026-10-01T00:00:00Z', end_at: '2099-01-01T00:00:00Z',
        published_at: '2026-10-01T00:00:00Z', participant_count: 3 },
    }],
    versions: [{ id: 21, experiment_id: 2, version: 1, title: '通路 v1', status: 'published',
      start_at: '2026-10-01T00:00:00Z', end_at: '2099-01-01T00:00:00Z' }],
    detail: Object.assign(detailFixture(['wiring']), {
      id: 21, experiment_id: 2, version: 1, title: '通路 v1',
      experiment: { id: 2, code: 'EXP-03', title: 'CPU数据通路连线', description: '', archived: 0 },
    }),
  })
  find(root, 'button', '查看指导').props.onClick()
  await flush()
  assert.ok(find(root, 'button', '进入实验箱连线（SPEC-017）'))
  assert.equal(find(root, 'button', '上传 .circ 在线评测（SPEC-018）'), undefined)
})

test('AC-03 student opens the own visible history versions', async t => {
  const { root } = await mount(t, 'student')
  assert.ok(find(root, 'button', '历史版本'))
  find(root, 'button', '历史版本').props.onClick()
  await flush()
  assert.match(content(root), /本人可见历史版本/)
  assert.match(content(root), /ALU v1/)
})

test('AC-04 boundary: student has no teacher controls and no replacement workspace here', async t => {
  const { root } = await mount(t, 'student')
  assert.equal(find(root, 'button', '新增实验'), undefined)
  assert.equal(find(root, 'button', '新增版本'), undefined)
  assert.equal(find(root, 'button', '发布'), undefined)
  assert.match(content(root), /仅显示本人参与名单内的已发布实验/)
})

test('changed session user blocks writes', async t => {
  const { root, fixture } = await mount(t)
  find(root, 'button', '新增实验').props.onClick()
  await flush()
  field(root, '标题', 'input').props.onInput({ target: { value: '寄存器与总线' } })
  field(root, '说明', 'input').props.onInput({ target: { value: '掌握写入时序' } })
  fixture.userId = 8
  formByClass(root, 'inline-form experiment-create').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.writes.length, 0)
  assert.match(content(root), /登录状态已变化/)
})
