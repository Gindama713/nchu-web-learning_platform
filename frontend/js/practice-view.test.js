// Component HTTP doubles; separate browser report covers actual SQLite/HTTP/UI.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { PracticeView } from './practice-view.js'

const element = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
function remove(node) {
  if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  node.parent = null
}
const renderer = createRenderer({
  createElement: element, createText: text => element('text', text), createComment: () => element('comment'),
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, name, old, value) => { node.props[name] = value },
  insert: (node, parent, anchor) => { remove(node); parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, node); node.parent = parent },
  remove, parentNode: node => node.parent, nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
})
const all = node => [node, ...node.children.flatMap(all)]
const content = node => node.text + node.children.map(content).join('')
const button = (root, label) => all(root).find(n => n.type === 'button' && content(n) === label)
const control = (root, label) => all(root).find(n => ['input', 'textarea', 'select'].includes(n.type) && n.props['aria-label'] === label)
const form = (root, css) => all(root).find(n => n.type === 'form' && n.props.class === css)
const flush = async () => { await setImmediate(); await nextTick() }
const submit = (root, css) => form(root, css).props.onSubmit({ preventDefault() {} })
const change = (root, label, value, checked = false) => control(root, label).props[checked ? 'onChange' : 'onInput']({ target: { value, checked: value } })

async function mount(t, entry = null) {
  const user = reactive({ id: 1, role: 'student' })
  const q = { id: 5, version_id: 8, version: 1, stem: '<script>旧题干</script>', type: 'boolean', options: [], knowledge_ids: [2], practice_available: true }
  const fixture = { q, public: [q], wrong: [], writes: [], reads: [], userId: 1, fail: false, status: 0, wait: null, unavailable: false, total: null }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    fixture.reads.push(path)
    const result = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, total }) })
    if (fixture.unavailable) return { ok: false, status: 503, json: async () => ({ error: { message: '暂不可用' } }) }
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role: user.role }, csrf_token: 'fresh' })
    if (options.method === 'POST') {
      fixture.writes.push({ path, options })
      if (fixture.fail) { fixture.fail = false; throw new Error('丢失响应') }
      if (fixture.status) return { ok: false, status: fixture.status, json: async () => ({ error: { code: 'QUESTION_RESERVED', message: '仍受保护' } }) }
      fixture.wrong = [{ ...q, question_version_id: 8, wrong_count: 1, resolved: false, answer_visible: true, can_practice: true, last_attempt_type: 'practice', answer: true, explanation: '<b>历史解析</b>' }]
      return result({ attempt_id: 7, question_version_id: 8, correct: false, score: 0, explanation: '<img>本次解析' })
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 3, title: 'CPU' }], 1)
    if (path.includes('/questions?')) { if (fixture.wait) await fixture.wait; return result(fixture.public, fixture.total ?? fixture.public.length) }
    if (path.includes('/wrong-questions?')) return result(fixture.wrong, fixture.total ?? fixture.wrong.length)
    throw new Error(path)
  }
  const root = element('root'), app = renderer.createApp(PracticeView, { user, entry })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture, user }
}

const open = async root => { button(root, '#5 · v1 · <script>旧题干</script>').props.onClick(); await flush() }

test('recommendation opens exact current version via existing public API and normal submission', async t => {
  const { root, fixture } = await mount(t, { courseId: 3, knowledgeId: 2, versionId: 8 })
  assert.ok(form(root, 'practice-form'))
  assert.match(fixture.reads.find(path => path.includes('/questions?')), /knowledge_id=2/)
  submit(root, 'practice-form'); await flush()
  assert.equal(JSON.parse(fixture.writes[0].options.body).question_version_id, 8)
})

test('recommendation cannot substitute another version when selected entry disappeared', async t => {
  const { root } = await mount(t, { courseId: 3, knowledgeId: 2, versionId: 9 })
  assert.match(content(root), /已变化或不可用/)
  assert.equal(form(root, 'practice-form'), undefined)
})

test('public exercise has no reference before submit and binds fixed version even on latest update', async t => {
  const { root, fixture } = await mount(t)
  await open(root)
  assert.doesNotMatch(content(root), /本次解析|参考答案/)
  change(root, '练习作答 错误', false, true)
  fixture.public = [{ ...fixture.q, version_id: 9, version: 2 }]
  submit(root, 'practice-form'); await flush()
  assert.deepEqual(JSON.parse(fixture.writes[0].options.body), { question_version_id: 8, answer: false })
  assert.match(content(root), /本次解析：<img>本次解析/)
  assert.equal(button(root, '提交本次练习').props.disabled, true)
  assert.equal(all(root).some(n => n.type === 'script' || n.type === 'img'), false)
})

test('committed response loss locks answer and navigation until retry with exact same key/payload', async t => {
  const { root, fixture } = await mount(t)
  await open(root); fixture.fail = true
  change(root, '练习作答 错误', false, true)
  submit(root, 'practice-form'); await flush()
  assert.ok(button(root, '重试原练习'))
  assert.equal(control(root, '练习作答 错误').props.disabled, true)
  assert.equal(button(root, '我的错题').props.disabled, true)
  submit(root, 'practice-form'); await flush()
  assert.equal(fixture.writes[0].options.body, fixture.writes[1].options.body)
  assert.equal(fixture.writes[0].options.headers['Idempotency-Key'], fixture.writes[1].options.headers['Idempotency-Key'])
})

test('protected wrong question displays history without answers or form and filters/paginates', async t => {
  const { root, fixture } = await mount(t)
  fixture.wrong = [{ ...fixture.q, wrong_count: 3, resolved: false, answer_visible: false, can_practice: false, last_attempt_type: 'paper' }]
  fixture.total = 21
  button(root, '我的错题').props.onClick(); await flush(); await open(root)
  assert.match(content(root), /累计错答 3 次.*待重练/)
  assert.match(content(root), /答案与解析尚受保护/)
  assert.equal(form(root, 'practice-form'), undefined)
  assert.doesNotMatch(content(root), /参考答案/)
  control(root, '筛选错题或练习知识标签').props.onChange({ target: { value: '2' } }); await flush()
  assert.match(fixture.reads.at(-1), /knowledge_id=2/)
  button(root, '练习错题下一页').props.onClick(); await flush()
  assert.match(fixture.reads.at(-1), /page=2/)
})

test('identity change and late response cannot restore old question or write as old student', async t => {
  const { root, fixture, user } = await mount(t)
  let release
  fixture.wait = new Promise(resolve => { release = resolve })
  button(root, '重新加载练习与错题').props.onClick(); await flush()
  user.id = 2; fixture.userId = 2; fixture.public = []
  await flush(); release(); await flush()
  assert.doesNotMatch(content(root), /旧题干/)
  user.role = 'teacher'; await flush()
  assert.equal(form(root, 'practice-form'), undefined)
  assert.equal(fixture.writes.length, 0)
})

test('protection rejection clears saved references and retry payload; failed refresh removes old result', async t => {
  const { root, fixture } = await mount(t)
  await open(root); fixture.status = 409
  submit(root, 'practice-form'); await flush()
  assert.match(content(root), /仍受保护/)
  assert.equal(form(root, 'practice-form'), undefined)
  fixture.status = 0; button(root, '重新加载练习与错题').props.onClick(); await flush(); await open(root)
  submit(root, 'practice-form'); await flush()
  assert.match(content(root), /本次解析/)
  fixture.unavailable = true; button(root, '重新加载练习与错题').props.onClick(); await flush()
  assert.doesNotMatch(content(root), /本次解析|旧题干/)
  assert.match(content(root), /暂不可用/)
})
