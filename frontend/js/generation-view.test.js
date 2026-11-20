// Component doubles for the generation form; real handler evidence lives elsewhere.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick } from 'vue'
import { GenerationView } from './generation-view.js'

const element = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
function remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null }
const renderer = createRenderer({
  createElement: element, createText: text => element('text', text), createComment: () => element('comment'),
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, name, old, value) => { node.props[name] = value },
  insert: (node, parent, anchor) => { remove(node); parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, node); node.parent = parent },
  remove, parentNode: node => node.parent, nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
})
const all = node => [node, ...node.children.flatMap(all)]
const content = node => node.text + node.children.map(content).join('')
const control = (root, label) => all(root).find(n => ['input', 'select'].includes(n.type) && n.props['aria-label'] === label)
const button = (root, label) => all(root).find(n => n.type === 'button' && content(n) === label)
const form = root => all(root).find(n => n.type === 'form' && n.props.class === 'generation-form')
const flush = async () => { await setImmediate(); await nextTick(); await setImmediate(); await nextTick() }

const knowledge = [{ id: 1, title: '知识点一' }, { id: 2, title: '知识点二' }]
const generated = {
  paper_id: 9, generation_snapshot_id: 4, seed_text: '9223372036854775807',
  algorithm_version: 'generation-v1', coverage: ['知识点一'],
  selected_version_ids: [11, 12, 13], points_hundredths: [334, 334, 333],
}

async function mount(t, props = {}) {
  const events = [], paths = []
  const fixture = { generate: { ok: true, body: generated }, failure: null }
  const old = globalThis.fetch
  globalThis.fetch = async (path, options = {}) => {
    paths.push({ path, options })
    const ok = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, total }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 1, role: 'teacher' }, csrf_token: 'token' })
    if (path.includes('/knowledge-points?')) return ok(knowledge, knowledge.length)
    if (path.endsWith('/generated-papers')) {
      if (fixture.failure) return { ok: false, status: fixture.failure.status, json: async () => ({ error: fixture.failure.error }) }
      return ok(fixture.generate.body)
    }
    throw new Error(`unexpected ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(GenerationView, {
    user: { id: 1, role: 'teacher' }, courseId: '3', onOpen: id => events.push(id), ...props,
  })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = old })
  await flush()
  return { root, fixture, events, paths }
}

test('default total score is 100 and difficulty quotas match the default count', async t => {
  const { root, paths } = await mount(t)
  assert.equal(control(root, '选题数量').props.value, '3')
  assert.equal(control(root, '试卷总分').props.value, '100')
  assert.equal(control(root, '简单题配额').props.value, '3')
  assert.equal(control(root, '中等题配额').props.value, '0')
  assert.equal(control(root, '困难题配额').props.value, '0')
  assert.equal(control(root, '生成试卷类型').props.value, 'homework')
  assert.match(content(root), /知识点一.*知识点二/)
  assert.equal(paths.filter(item => item.path.includes('/knowledge-points?')).length, 1)
})

test('submit sends the 100-point form and renders versioned draft without publishing', async t => {
  const { root, events, paths } = await mount(t)
  control(root, '新试卷标题').props.onInput({ target: { value: '  生成草稿  ' } })
  form(root).props.onSubmit({ preventDefault() {} })
  await flush()
  const post = paths.find(item => item.path.endsWith('/generated-papers'))
  assert.ok(post)
  const body = JSON.parse(post.options.body)
  assert.equal(body.title, '生成草稿')
  assert.equal(body.total_points, 100)
  assert.equal(body.count, 3)
  assert.deepEqual(body.difficulty_counts, { easy: 3, medium: 0, hard: 0 })
  assert.equal(post.options.headers['X-CSRF-Token'], 'token')
  assert.equal(paths.some(item => /publish/.test(item.path)), false)
  assert.match(content(root), /试卷 #9 · 快照 #4/)
  assert.match(content(root), /#11 · 3.34 分.*#12 · 3.34 分.*#13 · 3.33 分/)
  button(root, '查看草稿与发布设置').props.onClick()
  assert.deepEqual(events, [9])
})

test('replay mode hides constraints and only sends title plus snapshot id', async t => {
  const { root, paths } = await mount(t, { replayId: 12 })
  assert.equal(control(root, '原快照编号').props.value, '12')
  assert.equal(control(root, '选题数量'), undefined)
  assert.equal(paths.filter(item => item.path.includes('/knowledge-points?')).length, 0)
  control(root, '新试卷标题').props.onInput({ target: { value: '重放草稿' } })
  form(root).props.onSubmit({ preventDefault() {} })
  await flush()
  const post = paths.find(item => item.path.endsWith('/generated-papers'))
  assert.deepEqual(JSON.parse(post.options.body), { title: '重放草稿', replay_of: 12 })
  assert.match(content(root), /试卷 #9 · 快照 #4/)
})

test('infeasible guidance stays editable, permission failure blocks the form', async t => {
  const { root, fixture } = await mount(t)
  control(root, '新试卷标题').props.onInput({ target: { value: '生成草稿' } })
  fixture.failure = { status: 422, error: { message: '无解', code: 'INFEASIBLE_CONSTRAINTS' } }
  form(root).props.onSubmit({ preventDefault() {} })
  await flush()
  assert.match(content(root), /本次未生成草稿/)
  assert.match(content(root), /调整难度配额/)
  assert.equal(button(root, '生成并保存草稿').props.disabled, false)

  fixture.failure = { status: 403, error: { message: '无权访问该课程', code: 'FORBIDDEN' } }
  form(root).props.onSubmit({ preventDefault() {} })
  await flush()
  assert.match(content(root), /请重新加载试卷以确认当前身份和课程权限/)
  assert.equal(button(root, '生成并保存草稿').props.disabled, true)
})
