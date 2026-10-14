// Component doubles test races/UI only; actual HTTP/browser evidence is separate.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { AnalyticsView } from './analytics-view.js'

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
const button = (root, label) => all(root).find(n => n.type === 'button' && content(n) === label)
const control = (root, label) => all(root).find(n => ['input', 'select'].includes(n.type) && n.props['aria-label'] === label)
const flush = async () => { await setImmediate(); await nextTick() }
const change = (root, label, value) => {
  const node = control(root, label)
  node.props[node.type === 'select' ? 'onChange' : 'onInput']({ target: { value } })
}
const knowledge = (id = 17) => ({ analysis_run_id: id, dimension: 'knowledge', source_until: '2026-10-14T00:00:00Z', generated_at: 'same',
  algorithm_version: 'knowledge-objective-v1', sample_size: 4, population_basis: 'objective', warnings: ['多标签去重'],
  metrics: { mastery: 0.75, progress: null, answered_count: 4, items: [{ knowledge_id: 1, title: '<script>教学标题</script>', answered_count: 4, correct_count: 3, wrong_count: 1, mastery: 0.75 }] }, series: [] })

async function mount(t, previous = null) {
  const user = reactive({ id: 1, role: 'teacher' }), paths = [], memory = new Map()
  if (previous) memory.set('010b-snapshot:1:teacher', JSON.stringify(previous))
  const fixture = { data: knowledge(), wait: null, fail: false, userId: 1 }
  const oldFetch = globalThis.fetch, oldStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: key => memory.get(key), setItem: (key, val) => memory.set(key, val) }
  globalThis.fetch = async path => {
    paths.push(path)
    const ok = data => ({ ok: true, json: async () => ({ data, total: 2 }) })
    if (path.endsWith('/session')) return ok({ user: { id: fixture.userId, role: user.role }, csrf_token: 'current' })
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 3, title: 'CPU' }, { id: 4, title: '其他课程' }])
    const data = globalThis.structuredClone(fixture.data)
    if (fixture.wait) await fixture.wait
    if (fixture.fail) return { ok: false, status: 404, json: async () => ({ error: { message: '快照已不可用' } }) }
    return ok(data)
  }
  const root = element('root'), app = renderer.createApp(AnalyticsView, { user })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = oldFetch; globalThis.localStorage = oldStorage })
  await flush()
  return { root, fixture, user, paths, memory }
}

test('renders real zero vs unknown, text escapes, and stores only snapshot pointer', async t => {
  const { root, memory } = await mount(t)
  assert.match(content(root), /75.00%/)
  assert.match(content(root), /本人完成进度无数据/)
  assert.match(content(root), /<script>教学标题/)
  assert.equal(all(root).some(n => n.type === 'script'), false)
  assert.deepEqual(JSON.parse(memory.get('010b-snapshot:1:teacher')), { course: '3', run: 17 })
  assert.ok(button(root, '导出当前快照 CSV'))
})

test('reload restores saved ID only and unavailable old ID never silently creates new snapshot', async t => {
  const { root, fixture, paths } = await mount(t, { course: '3', run: 17 })
  assert.equal(paths.at(-1), '/api/v1/courses/3/analytics?analysis_run_id=17')
  fixture.fail = true
  button(root, '恢复原快照').props.onClick(); await flush()
  assert.match(content(root), /快照已不可用/)
  assert.equal(button(root, '导出当前快照 CSV'), undefined)
  assert.equal(paths.filter(p => p.includes('dimension=')).length, 0)
})

test('filter or course change invalidates display and a late request cannot resurrect it', async t => {
  const { root, fixture } = await mount(t)
  let release
  fixture.wait = new Promise(resolve => { release = resolve })
  button(root, '查询统计').props.onClick(); await flush()
  change(root, '统计课程', '4'); await flush()
  release(); await flush()
  assert.doesNotMatch(content(root), /教学标题/)
  assert.equal(button(root, '导出当前快照 CSV'), undefined)
})

test('scores category and paper filters do not leak to knowledge and empty means are unknown', async t => {
  const { root, fixture, paths } = await mount(t)
  change(root, '统计维度', 'scores'); await flush()
  change(root, '成绩类别', 'quiz'); change(root, '试卷编号（留空本类别全部）', '9'); await flush()
  fixture.data = { ...knowledge(18), dimension: 'scores', sample_size: 0, metrics: { kind: 'quiz', expected_count: 3, submitted_count: 1,
    missing_count: 2, graded_count: 0, partial_count: 1, mean_score: null, mean_percentage: null, selected_paper_ids: [9], score_bins: [] } }
  button(root, '查询统计').props.onClick(); await flush()
  assert.match(paths.at(-1), /dimension=scores&kind=quiz&paper_id=9/)
  assert.match(content(root), /平均百分比无数据/)
  assert.match(content(root), /缺交人卷次2/)
  change(root, '统计维度', 'knowledge'); await flush(); fixture.data = knowledge()
  button(root, '查询统计').props.onClick(); await flush()
  assert.equal(paths.at(-1), '/api/v1/courses/3/analytics?dimension=knowledge')
})

test('identity switch invalidates late result; students never receive export controls', async t => {
  const { root, fixture, user } = await mount(t)
  let release
  fixture.wait = new Promise(resolve => { release = resolve })
  button(root, '查询统计').props.onClick(); await flush()
  user.id = 2; user.role = 'student'; fixture.userId = 2; fixture.fail = true
  await flush(); release(); await flush()
  assert.equal(button(root, '导出当前快照 CSV'), undefined)
  assert.equal(control(root, '学生编号（留空全班）'), undefined)
  assert.doesNotMatch(content(root), /教学标题/)
})

test('export authorization failure clears old report and requires explicit recovery', async t => {
  const { root, fixture } = await mount(t)
  fixture.fail = true
  button(root, '导出当前快照 CSV').props.onClick(); await flush()
  assert.match(content(root), /快照已不可用/)
  assert.doesNotMatch(content(root), /教学标题/)
  assert.equal(button(root, '导出当前快照 CSV'), undefined)
})
