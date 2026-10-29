// Component/HTTP doubles only; knowledge and paper integration remain unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { QuestionBankView } from './question-view.js'

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

async function mount(t, role = 'teacher') {
  const fixture = { userId: 7, knowledgeMissing: false, unavailable: false, writes: [], items: [], version: 0 }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const result = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.unavailable) return { ok: false, status: 503, json: async () => ({ error: { message: '服务未就绪' } }) }
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role }, csrf_token: 'token' })
    if (options.method) {
      const values = JSON.parse(options.body)
      fixture.writes.push(values)
      fixture.version++
      fixture.items = [{ ...values, id: 1, version_id: fixture.version, version: fixture.version }]
      return result(fixture.items[0])
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path.includes('/knowledge-points?')) {
      if (fixture.knowledgeMissing) return { ok: false, status: 404, json: async () => ({ error: { message: 'missing' } }) }
      return result([{ id: 10, title: '程序计数器' }], 1)
    }
    if (path.includes('/questions?')) return result(fixture.items, fixture.items.length)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(QuestionBankView, { user: { id: 7, role } })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

test('teacher numeric editor saves a tagged version and editing appends another version', async t => {
  const { root, fixture } = await mount(t)
  find(root, 'button', '新增题目').props.onClick()
  await flush()
  field(root, '题型', 'select').props.onChange({ target: { value: 'numeric' } })
  await flush()
  field(root, '题干', 'textarea').props.onInput({ target: { value: '8位寄存器的位宽？' } })
  field(root, '正确数值', 'input').props.onInput({ target: { value: '8' } })
  field(root, '允许误差', 'input').props.onInput({ target: { value: '0' } })
  find(root, 'label', '程序计数器').children[0].props.onChange({ target: { checked: true } })
  await flush()
  assert.equal(find(root, 'button', '保存新版本').props.disabled, false)
  all(root).find(item => item.type === 'form' && item.props.class === 'question-editor').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.writes[0].answer, 8)
  assert.deepEqual(fixture.writes[0].options, [])
  assert.deepEqual(fixture.writes[0].knowledge_ids, [10])
  assert.match(content(root), /版本 1/)
  find(root, 'button', '编辑为新版本').props.onClick()
  await flush()
  field(root, '题干', 'textarea').props.onInput({ target: { value: '位宽是多少？' } })
  all(root).find(item => item.type === 'form' && item.props.class === 'question-editor').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.version, 2)
  assert.match(content(root), /版本 2/)
})

test('missing knowledge disables creation and retry can recover actual tag loading', async t => {
  const { root, fixture } = await mount(t)
  fixture.knowledgeMissing = true
  await find(root, 'button', '重新加载题库').props.onClick()
  await flush()
  assert.match(content(root), /知识标签暂不可用/)
  assert.equal(find(root, 'button', '新增题目').props.disabled, true)
  fixture.knowledgeMissing = false
  await find(root, 'button', '重新加载题库').props.onClick()
  await flush()
  assert.equal(find(root, 'button', '新增题目').props.disabled, false)
})

test('session changes block writes and clear the previous question editor', async t => {
  const { root, fixture } = await mount(t)
  find(root, 'button', '新增题目').props.onClick()
  await flush()
  fixture.userId = 8
  all(root).find(item => item.type === 'form' && item.props.class === 'question-editor').props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.writes.length, 0)
  assert.match(content(root), /登录状态已变化/)
  assert.equal(find(root, 'button', '保存新版本'), undefined)
})

test('student has no teacher controls or reference answers and failed refresh clears rows', async t => {
  const { root, fixture } = await mount(t, 'student')
  fixture.items = [{ id: 1, version: 1, type: 'boolean', stem: 'Fixture question', options: [], difficulty: 'easy',
    answer: 'SECRET', explanation: 'HIDDEN' }]
  await find(root, 'button', '重新加载题库').props.onClick()
  await flush()
  all(root).find(n => n.type === 'button' && content(n).startsWith('#1 · v1')).props.onClick()
  await flush()
  assert.equal(find(root, 'button', '新增题目'), undefined)
  assert.doesNotMatch(content(root), /SECRET|HIDDEN/)
  fixture.unavailable = true
  await find(root, 'button', '重新加载题库').props.onClick()
  await flush()
  assert.equal(all(root).find(n => n.type === 'button' && content(n).startsWith('#1 · v1')), undefined)
  assert.ok(find(root, 'button', '重试题库'))
})
