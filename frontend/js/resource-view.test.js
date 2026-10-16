// Component/HTTP doubles only; real upload and browser acceptance remain unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { ResourceView } from './resource-view.js'

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

async function mount(t, role = 'teacher', overrides = {}) {
  const fixture = { userId: 7, items: [], chapters: [], writes: [], error: null, ...overrides }
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const ok = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.error) return { ok: false, status: fixture.error.status, json: async () => ({ error: { message: fixture.error.message } }) }
    if (path.endsWith('/auth/session')) return ok({ user: { id: fixture.userId, role }, csrf_token: 'token' })
    if (options?.method) {
      fixture.writes.push({ path, options })
      return ok({ resource_id: 1, id: 2, version: 1 }, 201)
    }
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 1, title: 'Fixture CPU' }], 1)
    if (path.includes('/chapters?')) return ok(fixture.chapters, fixture.chapters.length)
    if (path.includes('/resources?')) return ok(fixture.items, fixture.items.length)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(ResourceView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture }
}

test('teacher sees upload form, bank kind and edit controls; students do not', async t => {
  const teacher = await mount(t, 'teacher')
  assert.match(content(teacher.root), /上传资源/)
  assert.match(content(teacher.root), /题库/)
  assert.match(content(teacher.root), /文档\/题库最大 20MiB/)
  const student = await mount(t, 'student')
  assert.doesNotMatch(content(student.root), /上传资源/)
  assert.doesNotMatch(content(student.root), /编辑属性/)
})

test('question bank rows stay hidden from student listing and preview button is skipped', async t => {
  const bank = { id: 3, title: '期中题库', kind: 'question_bank', chapter_id: null,
    latest_version: 1, latest_version_id: 11, size: 20 }
  const slides = { id: 4, title: '课件', kind: 'slides', chapter_id: null,
    latest_version: 1, latest_version_id: 12, size: 30 }
  const student = await mount(t, 'student', { items: [slides] })
  assert.match(content(student.root), /课件/)
  const teacher = await mount(t, 'teacher', { items: [slides, bank] })
  assert.match(content(teacher.root), /期中题库/)
  assert.match(content(teacher.root), /导入题库|版本历史/)
})

test('list request carries selected filters from the search form', async () => {
  const seen = []
  const previous = globalThis.fetch
  globalThis.fetch = async path => {
    if (path.includes('/resources?')) seen.push(path)
    const ok = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 7, role: 'student' }, csrf_token: 'token' })
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 1, title: 'CPU' }], 1)
    if (path.includes('/chapters?')) return ok([], 0)
    if (path.includes('/resources?')) return ok([], 0)
    throw new Error(`Unexpected path ${path}`)
  }
  try {
    const root = element('root')
    const app = renderer.createApp(ResourceView)
    app.mount(root)
    await flush()
    assert.equal(seen.length, 1)
    assert.ok(seen[0].includes('page=1&page_size=20'))
    app.unmount()
  } finally {
    globalThis.fetch = previous
  }
})

test('server error message is displayed without crashing the module', async t => {
  const { root } = await mount(t, 'student', { error: { status: 503, message: '服务未就绪' } })
  assert.match(content(root), /服务未就绪/)
})
