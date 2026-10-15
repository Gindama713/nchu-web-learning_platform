// Component doubles test races/UI only; actual HTTP/browser evidence is separate.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { RecommendationView } from './recommendation-view.js'

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

const recommendation = (reason = 'ok', items = [{ knowledge_id: 1, question_version_id: 8, score: .6, mastery: null, sample_size: 0, reason: 'insufficient_sample' }]) =>
  ({ items, reason, source_until: '2026-10-15T05:00:00.000Z', algorithm_version: 'recommend-v1' })

async function mount(t) {
  const user = reactive({ id: 1, role: 'student' }), events = [], paths = []
  const fixture = { data: recommendation(), fail: false, status: 503, userId: 1, wait: null }
  const old = globalThis.fetch
  globalThis.fetch = async path => {
    paths.push(path)
    const ok = (data, total) => ({ ok: true, json: async () => ({ data, total }) })
    if (path.endsWith('/session')) return ok({ user: { id: fixture.userId, role: user.role }, csrf_token: 'current' })
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 3, title: 'CPU' }, { id: 4, title: '其他课程' }], 2)
    const data = globalThis.structuredClone(fixture.data)
    if (fixture.wait) await fixture.wait
    if (fixture.fail) return { ok: false, status: fixture.status, json: async () => ({ error: { message: '暂不可用' } }) }
    if (path.includes('/knowledge-points/')) return ok({ id: 1, chapter_id: 2, content_revision: 1, title: '<script>文本标题</script>', content: '<p>安全正文</p>', example: '' })
    return ok(data)
  }
  const root = element('root'), app = renderer.createApp(RecommendationView, { user, onPractice: entry => events.push(entry) })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = old })
  await flush()
  return { root, fixture, user, events, paths }
}

test('reason, six decimals, unknown mastery, source metadata and safe title render', async t => {
  const { root, paths } = await mount(t)
  assert.match(content(root), /样本较少.*0.600000.*暂无样本/)
  assert.match(content(root), /recommend-v1/)
  assert.match(content(root), /出处：CPU/)
  button(root, '阅读知识 #1').props.onClick(); await flush()
  assert.match(content(root), /文本标题/)
  assert.equal(all(root).some(n => n.type === 'script'), false)
  assert.ok(paths.includes('/api/v1/knowledge-points/1'))
})

test('recommendation cutoff crosses UTC Sunday into Shanghai Monday without changing UTC data or week window', async t => {
  const { root, fixture } = await mount(t)
  for (const [value, expected] of [
    ['2026-10-18T15:59:59.000Z', '2026-10-18 23:59:59 (Asia/Shanghai)'],
    ['2026-10-18T16:00:00.000Z', '2026-10-19 00:00:00 (Asia/Shanghai)'],
    ['2026-10-19T00:00:00+08:00', '2026-10-19 00:00:00 (Asia/Shanghai)'],
  ]) {
    fixture.data = { ...recommendation(), source_until: value }
    const before = JSON.stringify(fixture.data)
    button(root, '刷新推荐').props.onClick(); await flush()
    assert.ok(content(root).includes(`依据截止 ${expected}`))
    assert.match(content(root), /recommend-v1/)
    assert.equal(JSON.stringify(fixture.data), before)
  }
})

test('recommendation missing or malformed cutoff never shows epoch, local time or Invalid Date', async t => {
  const { root, fixture } = await mount(t)
  for (const [value, expected] of [[null, '—'], [undefined, '—'], ['', '—'], ['bad', '时间异常'],
    ['2026-10-18T16:00:00', '时间异常'], ['2026-02-30T16:00:00Z', '时间异常'], [0, '时间异常']]) {
    fixture.data = { ...recommendation('all_mastered', []), source_until: value }
    button(root, '刷新推荐').props.onClick(); await flush()
    assert.ok(content(root).includes(`依据截止 ${expected}`))
    assert.doesNotMatch(content(root), /1970-|Invalid Date|NaN/)
  }
})

test('every empty reason keeps metadata, no made up item or exercise', async t => {
  const { root, fixture } = await mount(t)
  for (const [reason, text] of [['no_published_knowledge', '暂无已发布知识'], ['no_foundational_candidates', '暂无未完成的基础知识'], ['all_mastered', '均已完成']]) {
    fixture.data = recommendation(reason, [])
    button(root, '刷新推荐').props.onClick(); await flush()
    assert.match(content(root), new RegExp(text))
    assert.match(content(root), /依据截止.*recommend-v1/)
    assert.equal(button(root, '阅读知识 #1'), undefined)
  }
  fixture.data = recommendation('cold_start', [{ knowledge_id: 2, question_version_id: null, score: 1, mastery: null, sample_size: 0, reason: 'foundational' }])
  button(root, '刷新推荐').props.onClick(); await flush()
  assert.match(content(root), /教师标记的基础知识.*1.000000.*暂无合格/)
})

test('failure clears old results and source; explicit retry recovers', async t => {
  const { root, fixture } = await mount(t)
  button(root, '阅读知识 #1').props.onClick(); await flush()
  fixture.fail = true
  button(root, '刷新推荐').props.onClick(); await flush()
  assert.doesNotMatch(content(root), /文本标题|0.600000/)
  assert.match(content(root), /仍可在练习区正常作答/)
  fixture.fail = false
  button(root, '刷新推荐').props.onClick(); await flush()
  assert.match(content(root), /0.600000/)
})

test('course, limit, and identity changes discard late responses', async t => {
  const { root, fixture, user } = await mount(t)
  let release
  fixture.wait = new Promise(resolve => { release = resolve })
  button(root, '刷新推荐').props.onClick(); await flush()
  change(root, '推荐数量', '2'); await flush()
  release(); fixture.wait = null; await flush()
  assert.doesNotMatch(content(root), /0.600000/)
  change(root, '推荐课程', '4'); await flush()
  assert.match(content(root), /出处：其他课程/)
  fixture.wait = new Promise(resolve => { release = resolve })
  button(root, '刷新推荐').props.onClick(); await flush()
  user.id = 2; fixture.userId = 2; fixture.fail = true
  await flush(); release(); await flush()
  assert.doesNotMatch(content(root), /0.600000/)
  user.role = 'teacher'; await flush()
  assert.equal(button(root, '刷新推荐'), undefined)
})

test('practice entry revalidates, emits exact version, and changed qualification clears result', async t => {
  const { root, fixture, events } = await mount(t)
  button(root, '去练习 · 版本 #8').props.onClick(); await flush()
  assert.deepEqual(events[0], { courseId: '3', knowledgeId: 1, versionId: 8, nonce: 1 })
  fixture.data.items[0].question_version_id = null
  button(root, '去练习 · 版本 #8').props.onClick(); await flush()
  assert.equal(events.length, 1)
  assert.match(content(root), /入口已变化/)
  assert.equal(button(root, '去练习 · 版本 #8'), undefined)
})

test('revoked membership and invalid limit remove source and never expose other identity input', async t => {
  const { root, fixture, paths } = await mount(t)
  change(root, '推荐数量', '21')
  button(root, '刷新推荐').props.onClick(); await flush()
  assert.match(content(root), /1至20/)
  assert.equal(paths.some(p => p.includes('limit=21') || p.includes('student_id') || p.includes('user_id')), false)
  change(root, '推荐数量', '1'); fixture.fail = true; fixture.status = 404
  button(root, '刷新推荐').props.onClick(); await flush()
  assert.equal(button(root, '阅读知识 #1'), undefined)
  assert.equal(control(root, '推荐课程').children.length, 0)
})
