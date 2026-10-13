// Vue component/HTTP doubles: no claim of real SPEC-005 integration.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { PaperView } from './paper-view.js'

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
  }, remove, parentNode: item => item.parent,
  nextSibling: item => item.parent?.children[item.parent.children.indexOf(item) + 1] ?? null,
})
const all = item => [item, ...item.children.flatMap(all)]
const content = item => item.text + item.children.map(content).join('')
const find = (root, type, label) => all(root).find(item => item.type === type && content(item) === label)
const field = (root, label, type) => find(root, 'span', label).parent.children.find(item => item.type === type)
const flush = async () => { await setImmediate(); await nextTick() }
const submit = (root, css) => all(root).find(item => item.type === 'form' && item.props.class === css)
  .props.onSubmit({ preventDefault() {} })

async function mount(t, role = 'teacher') {
  const fixture = { userId: 7, writes: [], rows: [], detail: null, unavailable: false, waitQuestions: null }
  const user = reactive({ id: 7, role })
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const result = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.unavailable) return { ok: false, status: 503, json: async () => ({ error: { message: '服务未就绪' } }) }
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role: user.role }, csrf_token: 'token' })
    if (options.method) {
      const values = JSON.parse(options.body)
      fixture.writes.push({ path, values })
      const item = path.endsWith('/publish') ? { ...fixture.detail, ...values, status: 'published', window_state: 'upcoming', participant_count: 2 }
        : { ...values, id: 3, status: 'draft', total_points: 20, participant_count: 0,
          items: values.items.map((item, index) => ({ ...item, position: index + 1, version: 1,
            stem: 'fixture', options: [], answer: true, explanation: '' })) }
      fixture.detail = item; fixture.rows = [item]
      return result(item)
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path.includes('/questions?')) {
      if (fixture.waitQuestions) await fixture.waitQuestions
      return result([{ id: 1, version_id: 8, version: 2, stem: 'PC' }, { id: 2, version_id: 9, version: 1, stem: 'ALU' }], 2)
    }
    if (path.includes('/papers?')) return result(fixture.rows, fixture.rows.length)
    if (path.endsWith('/papers/3')) return result(fixture.detail)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(PaperView, { user })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture, user }
}

test('teacher selects fixed versions, changes order and publishes with confirmation', async t => {
  const { root, fixture } = await mount(t)
  await find(root, 'button', '编排新试卷').props.onClick()
  await flush()
  field(root, '试卷标题', 'input').props.onInput({ target: { value: 'CPU卷' } })
  field(root, '试卷类型', 'select').props.onChange({ target: { value: 'exam' } })
  for (const id of ['1', '2']) {
    field(root, '选择题目版本', 'select').props.onChange({ target: { value: id } })
    await flush()
    find(root, 'button', '加入试卷').props.onClick()
    await flush()
  }
  all(root).filter(item => item.type === 'button' && content(item) === '上移')[1].props.onClick()
  await flush()
  submit(root, 'paper-editor')
  await flush()
  assert.deepEqual(fixture.writes[0].values.items.map(item => item.question_version_id), [9, 8])
  assert.equal(fixture.writes[0].values.confidential, true)
  for (const [label, value] of [['试卷开始', '2026-10-13T21:00'], ['试卷截止', '2026-10-13T22:00'], ['试卷讲评', '2026-10-13T23:00']]) {
    field(root, label, 'input').props.onInput({ target: { value } })
  }
  field(root, '保密确认说明', 'textarea').props.onInput({ target: { value: '确认未公开且非简单复制' } })
  submit(root, 'paper-publication')
  await flush()
  assert.match(fixture.writes[1].path, /papers\/3\/publish$/)
  assert.equal(fixture.writes[1].values.confidentiality_note, '确认未公开且非简单复制')
  assert.equal(find(root, 'button', '发布试卷并冻结名单'), undefined)
  assert.match(content(root), /发布冻结人数：2/)
})

test('student can open prestart metadata without teacher controls or premature answers', async t => {
  const { root, fixture } = await mount(t, 'student')
  fixture.rows = [{ id: 3, title: 'CPU卷', kind: 'exam', status: 'published', window_state: 'upcoming', total_points: 20 }]
  fixture.detail = fixture.rows[0]
  await find(root, 'button', '重新加载试卷').props.onClick()
  await find(root, 'button', '#3 · CPU卷 · 未开始').props.onClick()
  await flush()
  assert.match(content(root), /试卷尚未开始/)
  assert.equal(find(root, 'button', '编排新试卷'), undefined)
  fixture.detail = { ...fixture.detail, window_state: 'open', items: [{ question_version_id: 8, version: 2,
    position: 1, points: 20, stem: 'PC', options: [], answer: 'SECRET', explanation: 'HIDDEN' }] }
  await find(root, 'button', '#3 · CPU卷 · 未开始').props.onClick()
  await flush()
  assert.match(content(root), /PC/)
  assert.doesNotMatch(content(root), /SECRET|HIDDEN/)
  fixture.unavailable = true
  await find(root, 'button', '重新加载试卷').props.onClick()
  await flush()
  assert.doesNotMatch(content(root), /PC/)
  assert.ok(find(root, 'button', '重试试卷'))
})

test('session changes block writes and discard the old editor', async t => {
  const { root, fixture } = await mount(t)
  await find(root, 'button', '编排新试卷').props.onClick()
  await flush()
  fixture.userId = 8
  submit(root, 'paper-editor')
  await flush()
  assert.equal(fixture.writes.length, 0)
  assert.match(content(root), /登录状态已变化/)
  assert.equal(find(root, 'button', '保存试卷草稿'), undefined)
})

test('changing identity discards a late candidate response and teacher form', async t => {
  const { root, fixture, user } = await mount(t)
  let release
  fixture.waitQuestions = new Promise(resolve => { release = resolve })
  find(root, 'button', '编排新试卷').props.onClick()
  await flush()
  user.id = 8; user.role = 'student'; fixture.userId = 8
  await flush()
  release()
  await flush()
  assert.equal(find(root, 'button', '保存试卷草稿'), undefined)
  assert.doesNotMatch(content(root), /PC|ALU/)
})
