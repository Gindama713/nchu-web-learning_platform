// Isolated Vue interaction tests with HTTP doubles. Not real login/browser acceptance.
// Custom host API: https://vuejs.org/api/custom-renderer.html
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { KnowledgeView } from './knowledge-view.js'

const node = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
const detach = element => {
  if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: type => node(type),
  createText: text => node('text', text),
  createComment: () => node('comment'),
  setText: (element, text) => { element.text = text },
  setElementText: (element, text) => { element.text = text; element.children = [] },
  patchProp: (element, key, previous, value) => { element.props[key] = value },
  insert: (element, parent, anchor) => {
    detach(element)
    const index = anchor ? parent.children.indexOf(anchor) : parent.children.length
    parent.children.splice(index, 0, element)
    element.parent = parent
  },
  remove: detach,
  parentNode: element => element.parent,
  nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1] ?? null,
})
const nodes = root => [root, ...root.children.flatMap(nodes)]
const visibleText = root => root.text + root.children.map(visibleText).join('')
const find = (root, type, label) => nodes(root).find(element => element.type === type && visibleText(element) === label)
const flush = async () => { await setImmediate(); await nextTick() }

async function mounted(t, role) {
  const fixture = {
    userId: role === 'teacher' ? 1 : 2,
    unavailable: false,
    item: { id: 10, chapter_id: 1, title: '程序计数器', content: '<p>PC</p>', example: '',
      published: true, is_foundational: true, content_revision: 1,
      is_bookmarked: false, progress: { completed: false, completed_at: null } },
    mutations: [],
  }
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    const result = (data, extra = {}) => ({ ok: true, status: 200, json: async () => ({ data, ...extra }) })
    if (fixture.unavailable) return { ok: false, status: 503, json: async () => ({ error: { message: '服务不可用' } }) }
    if (url === '/api/v1/auth/session') return result({ user: { id: fixture.userId, role, name: 'Fixture user' }, csrf_token: 'test-token' })
    if (options.method) {
      const body = JSON.parse(options.body)
      fixture.mutations.push({ url, method: options.method, body })
      if (url.endsWith('/bookmark')) fixture.item.is_bookmarked = body.bookmarked
      else if (url.endsWith('/progress')) fixture.item.progress.completed = body.completed
      else Object.assign(fixture.item, body)
      return result({ ...fixture.item })
    }
    if (url.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'Fixture CPU' }], { total: 1 })
    if (url.startsWith('/api/v1/courses/1/chapters?')) return result([{ id: 1, title: 'CPU', position: 0 }], { total: 1, chapters_revision: 1 })
    if (url.startsWith('/api/v1/courses/1/knowledge-points?')) return result([{ ...fixture.item }], { total: 1 })
    if (url === '/api/v1/knowledge-points/10') return result({ ...fixture.item, progress: { ...fixture.item.progress } })
    throw new Error(`Unexpected fixture URL: ${url}`)
  }
  const root = node('root')
  const app = renderer.createApp(KnowledgeView)
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = originalFetch })
  await flush()
  assert.ok(find(root, 'button', '程序计数器'))
  return { root, fixture }
}

test('student detail bookmarks/progress reflect server response and expose no teacher controls', async t => {
  const { root, fixture } = await mounted(t, 'student')
  await find(root, 'button', '程序计数器').props.onClick()
  await flush()
  assert.equal(find(root, 'button', '编辑知识'), undefined)
  assert.equal(find(root, 'button', '新增知识'), undefined)
  await find(root, 'button', '收藏知识点').props.onClick()
  await flush()
  assert.ok(find(root, 'button', '取消收藏'))
  await find(root, 'button', '标记完成').props.onClick()
  await flush()
  assert.ok(find(root, 'button', '取消完成'))
  assert.deepEqual(fixture.mutations.map(item => item.body), [{ bookmarked: true }, { completed: true }])
})

test('changed session clears previously displayed student data and never sends a write', async t => {
  const { root, fixture } = await mounted(t, 'student')
  await find(root, 'button', '程序计数器').props.onClick()
  await flush()
  fixture.userId = 3
  await find(root, 'button', '标记完成').props.onClick()
  await flush()
  assert.equal(fixture.mutations.length, 0)
  assert.equal(find(root, 'button', '程序计数器'), undefined)
  assert.equal(find(root, 'button', '标记完成'), undefined)
  assert.match(visibleText(root), /登录状态已变化/)
})

test('teacher can edit and unpublish while personal-state controls stay absent', async t => {
  const { root, fixture } = await mounted(t, 'teacher')
  await find(root, 'button', '程序计数器').props.onClick()
  await flush()
  assert.equal(find(root, 'button', '收藏知识点'), undefined)
  await find(root, 'button', '编辑知识').props.onClick()
  await flush()
  const label = find(root, 'span', '标题').parent
  label.children.find(element => element.type === 'input').props.onInput({ target: { value: '程序计数器 PC' } })
  const editor = nodes(root).find(element => element.type === 'form' && element.props.class === 'knowledge-editor')
  editor.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.equal(fixture.item.title, '程序计数器 PC')
  assert.match(visibleText(root), /知识已保存/)
  await find(root, 'button', '下架知识').props.onClick()
  await flush()
  assert.equal(fixture.item.published, false)
  assert.ok(find(root, 'button', '发布知识'))
})

test('failed refresh shows retry without retaining previous search results', async t => {
  const { root, fixture } = await mounted(t, 'student')
  fixture.unavailable = true
  const search = nodes(root).find(element => element.type === 'form' && element.props.class === 'knowledge-search')
  search.props.onSubmit({ preventDefault() {} })
  await flush()
  assert.match(visibleText(root), /服务不可用/)
  assert.equal(find(root, 'button', '程序计数器'), undefined)
  assert.ok(find(root, 'button', '重试加载'))
})
