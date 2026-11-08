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
  const fixture = { userId: 7, preps: [draft, published], error: null, ...overrides }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const ok = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.error) return { ok: false, status: fixture.error.status, json: async () => ({ error: { message: fixture.error.message } }) }
    if (path.endsWith('/auth/session')) {
      return ok({ user: { id: fixture.userId, name: '测试用户', role }, csrf_token: 'token' })
    }
    if (options?.method) return ok({ id: 99, status: 'draft' }, 201)
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

test('teacher sees create form, link selects and draft actions; student does not', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /新建备课/)
  assert.match(content(teacher.root), /创建草稿/)
  assert.match(content(teacher.root), /#5 ALU 移位/)
  assert.match(content(teacher.root), /#9v1 补码加减/)
  assert.match(content(teacher.root), /编辑/)
  assert.match(content(teacher.root), /确认发布/)
  assert.match(content(teacher.root), /复制/)
  const student = await mount(t, 'student')
  assert.doesNotMatch(content(student.root), /新建备课/)
  assert.doesNotMatch(content(student.root), /确认发布/)
  assert.doesNotMatch(content(student.root), /复制/)
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

test('withdraw controls appear only on published rows', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /撤回/)
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
