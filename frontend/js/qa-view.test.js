// Component doubles cover state/races. Real HTTP and installed-browser evidence is separate.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { QAView } from './qa-view.js'

const node = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
function remove(n) { if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1); n.parent = null }
const renderer = createRenderer({
  createElement: node, createText: text => node('text', text), createComment: () => node('comment'),
  setText: (n, text) => { n.text = text }, setElementText: (n, text) => { n.text = text; n.children = [] },
  patchProp: (n, key, old, value) => { n.props[key] = value },
  insert: (n, parent, anchor) => { remove(n); parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, n); n.parent = parent },
  remove, parentNode: n => n.parent, nextSibling: n => n.parent?.children[n.parent.children.indexOf(n) + 1] ?? null,
})
const all = n => [n, ...n.children.flatMap(all)]
const content = n => n.text + n.children.map(content).join('')
const button = (root, label) => all(root).find(n => n.type === 'button' && content(n) === label)
const control = (root, label) => all(root).find(n => n.props['aria-label'] === label)
const flush = async () => { await setImmediate(); await nextTick() }
const change = (root, label, value) => {
  const n = control(root, label)
  n.props[n.type === 'select' ? 'onChange' : 'onInput']({ target: { value } })
}
const matched = () => ({ matches: [{ knowledge_id: 7, excerpt: '<script>片段</script>', similarity: 0.1234 }],
  found: true, reason: 'matched', algorithm_version: 'qa-tfidf-v1', index_version: 'revision-a' })

async function mount(t, courseWait = null) {
  const root = node('root'), user = reactive({ id: 1, role: 'student' }), paths = []
  const fixture = { data: matched(), fail: null, wait: null, courseWait, userId: 1 }
  const oldFetch = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    paths.push({ path, options })
    const ok = data => ({ ok: true, json: async () => ({ data, total: 2 }) })
    if (path.endsWith('/session')) return ok({ user: { id: fixture.userId }, csrf_token: 'current' })
    if (path.startsWith('/api/v1/courses?')) {
      if (fixture.courseWait) await fixture.courseWait
      return ok([{ id: 2, title: 'CPU' }, { id: 3, title: '第二门课程' }])
    }
    const data = globalThis.structuredClone(fixture.data)
    if (fixture.wait) await fixture.wait
    if (fixture.fail) return { ok: false, status: fixture.fail.status,
      json: async () => ({ error: { code: fixture.fail.code, message: '受控失败' } }) }
    if (path.includes('/knowledge-points/')) return ok({ id: 7, title: '程序计数器', content: '<p>正文</p>', published: true, content_revision: 2 })
    return ok(data)
  }
  const app = renderer.createApp(QAView, { user })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = oldFetch })
  await flush()
  return { root, fixture, paths, user }
}
async function search(root, question = 'PC 有什么作用') {
  change(root, '你的问题', question)
  await flush()
  all(root).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  await flush()
}

test('loading courses disables query and query posts only question/top_k with fresh session', async t => {
  let release
  const waiting = new Promise(resolve => { release = resolve })
  const { root, paths } = await mount(t, waiting)
  assert.equal(button(root, '查询课程知识').props.disabled, true)
  release(); await flush()
  await search(root)
  const request = paths.at(-1)
  assert.equal(request.path, '/api/v1/courses/2/qa')
  assert.equal(request.options.headers['X-CSRF-Token'], 'current')
  assert.deepEqual(JSON.parse(request.options.body), { question: 'PC 有什么作用', top_k: 3 })
})

test('renders six decimal similarity, algorithm/revision, escaped excerpts and real source control', async t => {
  const { root } = await mount(t)
  await search(root)
  assert.match(content(root), /相似度 0.123400/)
  assert.match(content(root), /qa-tfidf-v1.*revision-a/)
  assert.match(content(root), /<script>片段/)
  assert.equal(all(root).some(n => n.type === 'script' || n.props.innerHTML), false)
  button(root, '打开知识出处 #7').props.onClick(); await flush()
  assert.match(content(root), /程序计数器/)
  assert.match(content(root), /内容版本 2/)
})

test('no_match and empty_corpus give distinct recovery directions and keep metadata', async t => {
  const { root, fixture } = await mount(t)
  for (const [reason, message] of [['no_match', /未找到相关知识/], ['empty_corpus', /暂无已发布知识/]]) {
    fixture.data = { ...matched(), found: false, matches: [], reason }
    await search(root)
    assert.match(content(root), message)
    assert.match(content(root), /revision-a/)
    assert.equal(button(root, '打开知识出处 #7'), undefined)
  }
})

test('failed rebuild clears previous text and explicit retry recovers', async t => {
  const { root, fixture } = await mount(t)
  await search(root)
  fixture.fail = { status: 503, code: 'INDEX_UNAVAILABLE' }
  await search(root)
  assert.match(content(root), /索引暂时不可用/)
  assert.doesNotMatch(content(root), /片段<\/script>/)
  fixture.fail = null
  button(root, '重试查询').props.onClick(); await flush()
  assert.match(content(root), /找到 1 条/)
})

test('editing question or changing course drops a late response', async t => {
  const { root, fixture } = await mount(t)
  for (const [label, value] of [['你的问题', 'ALU'], ['问答课程', '3']]) {
    let release
    fixture.wait = new Promise(resolve => { release = resolve })
    await search(root)
    change(root, label, value); await flush()
    release(); await flush()
    assert.doesNotMatch(content(root), /revision-a/)
    fixture.wait = null
  }
})

test('identity change drops old result and 401 requires fresh course load', async t => {
  const { root, fixture, user } = await mount(t)
  let release
  fixture.wait = new Promise(resolve => { release = resolve })
  await search(root)
  fixture.userId = 2; user.id = 2
  await flush(); release(); await flush(); fixture.wait = null
  assert.doesNotMatch(content(root), /revision-a/)
  fixture.fail = { status: 401, code: 'UNAUTHENTICATED' }
  await search(root)
  assert.equal(button(root, '查询课程知识').props.disabled, true)
  assert.ok(button(root, '重新加载后重试'))
})

test('source withdrawn or permission denied clears all previous excerpts', async t => {
  const { root, fixture } = await mount(t)
  await search(root)
  fixture.fail = { status: 404, code: 'NOT_FOUND' }
  button(root, '打开知识出处 #7').props.onClick(); await flush()
  assert.match(content(root), /受控失败/)
  assert.equal(button(root, '打开知识出处 #7'), undefined)
  assert.doesNotMatch(content(root), /revision-a/)
})
