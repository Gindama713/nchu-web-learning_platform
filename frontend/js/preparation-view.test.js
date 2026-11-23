// Component/HTTP doubles only; real browser acceptance remains unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { PreparationView } from './preparation-view.js'

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
const find = (item, predicate, found = []) => {
  if (predicate(item)) found.push(item)
  for (const child of item.children) find(child, predicate, found)
  return found
}
const click = async (root, label) => {
  const [button] = find(root, item => item.type === 'button' && content(item) === label)
  assert.ok(button, `button ${label} not found`)
  button.props.onClick()
  await flush()
}
const select = (root, ariaLabel, value) => {
  const [field] = find(root, item => item.type === 'select' && item.props['aria-label'] === ariaLabel)
  assert.ok(field, `select ${ariaLabel} not found`)
  field.props.onChange({ target: { value } })
}
const type = (root, ariaLabel, value) => {
  const [field] = find(root, item => item.type === 'input' && item.props['aria-label'] === ariaLabel)
  assert.ok(field, `input ${ariaLabel} not found`)
  field.props.onInput({ target: { value } })
}

const draft = {
  id: 21, title: '第 3 讲 预习', status: 'draft', scheduled_at: '2026-11-02T08:00:00Z',
  knowledge_ids: [5], resource_version_ids: [], question_version_ids: [11, 12], quiz_ids: [7],
}
const published = {
  id: 18, title: '第 2 讲 预习', status: 'published', scheduled_at: '2026-10-26T08:00:00Z',
  published_at: '2026-10-25T10:00:00Z', knowledge_ids: [4], resource_version_ids: [31],
  question_version_ids: [], quiz_ids: [7],
}

async function mount(t, role = 'teacher', overrides = {}) {
  const fixture = { userId: 7, preps: [draft, published], error: null, writes: [], ...overrides }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const ok = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.error) return { ok: false, status: fixture.error.status, json: async () => ({ error: { message: fixture.error.message } }) }
    if (path.endsWith('/auth/session')) {
      return ok({ user: { id: fixture.userId, name: '测试用户', role }, csrf_token: 'token' })
    }
    if (options?.method) {
      fixture.writes.push({ path, body: JSON.parse(options.body ?? '{}') })
      return ok({ id: 99, status: 'draft' }, 201)
    }
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 1, title: 'Fixture CPU' }], 1)
    // 列表可见性由服务端控制：学生仅返回已发布
    const visible = role === 'student' ? fixture.preps.filter(item => item.status === 'published') : fixture.preps
    if (path.includes('/preparations?')) return ok(visible, visible.length)
    if (path.includes('/knowledge-points?')) return ok([{ id: 5, title: 'ALU 移位' }], 1)
    if (path.includes('/resources?')) return ok([{ id: 2, title: '指导书', latest_version_id: 31 }], 1)
    if (path.includes('/questions?')) return ok([{ id: 9, version_id: 11, version: 1, stem: '补码加减' }], 1)
    if (path.includes('/quizzes?')) return ok([{ id: 7, title: '进位随堂测', window_state: 'open' }], 1)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(PreparationView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

test('teacher sees create form, dropdowns and draft actions; student does not', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /新建备课/)
  assert.match(content(teacher.root), /创建草稿/)
  assert.match(content(teacher.root), /#5 ALU 移位/)
  assert.match(content(teacher.root), /#9v1 补码加减/)
  assert.match(content(teacher.root), /排期日期/)
  assert.match(content(teacher.root), /选择知识…/)
  assert.match(content(teacher.root), /编辑/)
  assert.match(content(teacher.root), /发布/)
  assert.match(content(teacher.root), /复制/)
  await click(teacher.root, '发布')
  assert.match(content(teacher.root), /确认发布/)
  await click(teacher.root, '编辑')
  assert.match(content(teacher.root), /保存草稿/)
  assert.equal(find(teacher.root, item => item.props.role === 'dialog').length, 1, '编辑在独立弹窗里打开')
  const student = await mount(t, 'student')
  assert.doesNotMatch(content(student.root), /新建备课/)
  assert.doesNotMatch(content(student.root), /确认发布/)
  assert.doesNotMatch(content(student.root), /复制/)
})

test('schedule and link dropdowns write the expected payload', async t => {
  const view = await mount(t, 'teacher')
  const [title] = find(view.root, item => item.type === 'input')
  title.props.onInput({ target: { value: '第 4 讲 预习' } })
  await flush()
  type(view.root, '排期日期', '2026-11-20')
  await flush()
  type(view.root, '开始时间', '10:00')
  await flush()
  type(view.root, '结束时间', '11:30')
  await flush()
  select(view.root, '知识选择', '5')
  await flush()
  select(view.root, '测验选择', '7')
  await flush()
  const [form] = find(view.root, item => item.type === 'form'
    && String(item.props.class ?? '').includes('preparation-create'))
  assert.ok(form, 'create form not found')
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  await flush()
  const create = view.fixture.writes.find(entry => entry.path === '/api/v1/courses/1/preparations')
  assert.ok(create, 'create request was sent')
  assert.equal(create.body.title, '第 4 讲 预习')
  assert.deepEqual(create.body.knowledge_ids, [5])
  assert.deepEqual(create.body.quiz_ids, [7])
  assert.equal(create.body.scheduled_at, '2026-11-20T02:00:00.000Z')
  assert.equal(create.body.scheduled_end_at, '2026-11-20T03:30:00.000Z')
})

test('结束时间早于开始时间时拒绝提交', async t => {
  const view = await mount(t, 'teacher')
  const [title] = find(view.root, item => item.type === 'input')
  title.props.onInput({ target: { value: '第 5 讲 预习' } })
  await flush()
  type(view.root, '排期日期', '2026-11-20')
  await flush()
  type(view.root, '开始时间', '10:00')
  await flush()
  type(view.root, '结束时间', '09:00')
  await flush()
  const [form] = find(view.root, item => item.type === 'form'
    && String(item.props.class ?? '').includes('preparation-create'))
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.match(content(view.root), /结束时间必须晚于开始时间/)
  assert.equal(view.fixture.writes.length, 0)
})

test('student sees only published preparations with quiz windows', async t => {
  const open = { ...published, quizzes: [{ id: 7, title: '进位随堂测', window_state: 'open' }] }
  const student = await mount(t, 'student', { preps: [open, draft] })
  assert.match(content(student.root), /第 2 讲 预习/)
  assert.match(content(student.root), /进行中/)
  assert.doesNotMatch(content(student.root), /第 3 讲 预习/)
  const empty = await mount(t, 'student', { preps: [draft] })
  assert.match(content(empty.root), /老师还没有发布预习内容/)
})

test('withdraw controls appear only on published rows after opening the panel', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /撤回/)
  assert.doesNotMatch(content(teacher.root), /确认撤回/)
  await click(teacher.root, '撤回')
  assert.match(content(teacher.root), /确认撤回/)
})

test('link counts summarise per row for teachers', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /知1 题2 测1/)
  assert.match(content(teacher.root), /知1 资1 测1/)
})

test('server error message is displayed without crashing the module', async t => {
  const { root } = await mount(t, 'student', { error: { status: 503, message: '服务未就绪' } })
  assert.match(content(root), /服务未就绪/)
})

test('复制走页内弹窗而不是原生 prompt，默认不继承旧排期', async t => {
  const view = await mount(t, 'teacher')
  assert.equal(find(view.root, item => item.props.role === 'dialog').length, 0)
  await click(view.root, '复制')
  const [dialog] = find(view.root, item => item.props.role === 'dialog')
  assert.ok(dialog, '复制应打开页内弹窗')
  assert.match(content(dialog), /复制「第 3 讲 预习」/)
  const [title] = find(view.root, item => item.props['aria-label'] === '复制后的标题')
  assert.equal(title.props.value, '第 3 讲 预习（副本）')
  // 「创建副本」是 submit 按钮，走表单提交而不是 onClick
  const forms = find(view.root, item => item.type === 'form' && item.props.onSubmit)
  forms.at(-1).props.onSubmit({ preventDefault() {} })
  await flush()
  const write = view.fixture.writes.at(-1)
  assert.equal(write.path, '/api/v1/preparations/21/copy')
  assert.deepEqual(write.body, { title: '第 3 讲 预习（副本）' })
  assert.equal(find(view.root, item => item.props.role === 'dialog').length, 0, '提交后应关闭弹窗')
})

test('复制弹窗里可以当场设置新排期', async t => {
  const view = await mount(t, 'teacher')
  await click(view.root, '复制')
  // 页面里新建表单也有「排期日期」，弹窗那只是最后一个
  const dates = find(view.root, item => item.type === 'input' && item.props['aria-label'] === '排期日期')
  dates.at(-1).props.onInput({ target: { value: '2026-11-20' } })
  await flush()
  const starts = find(view.root, item => item.type === 'input' && item.props['aria-label'] === '开始时间')
  starts.at(-1).props.onInput({ target: { value: '14:00' } })
  await flush()
  const forms = find(view.root, item => item.type === 'form' && item.props.onSubmit)
  forms.at(-1).props.onSubmit({ preventDefault() {} })
  await flush()
  const write = view.fixture.writes.at(-1)
  assert.equal(write.body.scheduled_at, '2026-11-20T06:00:00.000Z')
  assert.equal(write.body.scheduled_end_at, '2026-11-20T07:30:00.000Z')
})
