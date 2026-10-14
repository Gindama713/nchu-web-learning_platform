// Component HTTP doubles; separate browser report covers actual SQLite/HTTP/UI.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { AttemptView } from './attempt-view.js'

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

async function mount(t, role = 'student', history = false) {
  const user = reactive({ id: 7, role })
  const paper = { id: 3, title: 'CPU卷', window_state: 'open', items: [
    { question_version_id: 1, position: 1, type: 'boolean', stem: 'PC？', options: [], points: 1 },
    { question_version_id: 2, position: 2, type: 'short', stem: '解释PC', options: [], points: 2 },
  ] }
  const fixture = { userId: 7, rows: [], writes: [], reads: [], failSubmit: false, conflict: false, waitDetail: null, latest: null, total: null }
  const attempt = { id: 9, paper_id: 3, student_id: 7, revision: 0, status: 'partial', score: null, partial_score: 1,
    total_points: 3, submitted_at: '2026-10-14T04:00:00Z', answers: [
      { question_version_id: 1, value: false, answered: true, grading_status: 'graded', score: 1, max_score: 1, comment: '', correct: true },
      { question_version_id: 2, value: '原文', answered: true, grading_status: 'pending', score: null, max_score: 2, comment: '', correct: null },
    ] }
  fixture.latest = attempt
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    fixture.reads.push(path)
    const result = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role: user.role }, csrf_token: 'fresh' })
    if (options.method) {
      fixture.writes.push({ path, options, payload: JSON.parse(options.body) })
      if (path.endsWith('/manual-scores')) {
        if (fixture.conflict) return { ok: false, status: 409, json: async () => ({ error: { code: 'REVISION_CONFLICT', message: '请重新加载' } }) }
        fixture.latest = { ...attempt, revision: 1, status: 'graded', score: 2, partial_score: 2,
          answers: [attempt.answers[0], { ...attempt.answers[1], grading_status: 'graded', score: 1, comment: '评语' }] }
        return result(fixture.latest)
      }
      if (fixture.failSubmit) { fixture.failSubmit = false; throw new Error('网络异常') }
      fixture.rows = [attempt]
      return result(attempt)
    }
    if (path.startsWith('/api/v1/courses?')) return result([{ id: 1, title: 'CPU' }], 1)
    if (path.includes('/papers?')) return result([paper], 1)
    if (path.includes('/attempts?')) return result(fixture.rows, fixture.total ?? fixture.rows.length)
    if (path.endsWith('/papers/3')) return result(paper)
    if (path.endsWith('/attempts/9')) { if (fixture.waitDetail) await fixture.waitDetail; return result(fixture.latest) }
    throw new Error(`Unexpected ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(AttemptView, { user, ...(history ? {} : { paper, courseId: '1' }) })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture, user, attempt }
}

test('student false answer and short text submit once and then display latest pending result', async t => {
  const { root, fixture } = await mount(t)
  change(root, '第 1 题作答 错误', false, true)
  change(root, '第 2 题作答', '学生文本')
  change(root, '确认交卷，接受漏答0分且提交后不可修改', true, true)
  submit(root, 'attempt-answer-form'); await flush()
  assert.deepEqual(fixture.writes[0].payload.answers.map(a => a.value), [false, '学生文本'])
  assert.match(content(root), /待全部批阅/)
  assert.equal(button(root, '提交整份答卷'), undefined)
  assert.equal(button(root, '保存本次批阅'), undefined)
  assert.doesNotMatch(content(root), /参考答案/)
})

test('lost submission response exposes retry with same payload and key', async t => {
  const { root, fixture } = await mount(t)
  fixture.failSubmit = true
  change(root, '第 2 题作答', '原文')
  change(root, '确认交卷，接受漏答0分且提交后不可修改', true, true)
  submit(root, 'attempt-answer-form'); await flush()
  assert.ok(button(root, '重试原交卷'))
  assert.equal(control(root, '第 2 题作答').props.disabled, true)
  submit(root, 'attempt-answer-form'); await flush()
  assert.equal(fixture.writes.length, 2)
  assert.equal(fixture.writes[0].options.headers['Idempotency-Key'], fixture.writes[1].options.headers['Idempotency-Key'])
  assert.deepEqual(fixture.writes[0].payload, fixture.writes[1].payload)
})

test('teacher grades by selected original revision and conflict locks until reload', async t => {
  const { root, fixture, attempt } = await mount(t, 'teacher')
  fixture.rows = [attempt]
  await button(root, '重新加载答卷').props.onClick(); await flush()
  await button(root, '答卷 #9 · 待人工评分 · 学生 #7').props.onClick(); await flush()
  change(root, '批阅第 2 题', true, true)
  change(root, '第 2 题评分', '1'); change(root, '第 2 题评语', '评语')
  fixture.conflict = true
  submit(root, 'attempt-grade-form'); await flush()
  assert.equal(fixture.writes[0].payload.revision, 0)
  assert.equal(button(root, '保存本次批阅').props.disabled, true)
  assert.match(content(root), /评分已被其他会话修改/)
  fixture.conflict = false; fixture.latest = { ...attempt, revision: 4 }
  await button(root, '重新加载此答卷').props.onClick(); await flush()
  change(root, '批阅第 2 题', true, true); change(root, '第 2 题评分', '1')
  submit(root, 'attempt-grade-form'); await flush()
  assert.equal(fixture.writes[1].payload.revision, 4)
  assert.match(content(root), /批阅已保存/)
})

test('history pagination and filters request current course and score state', async t => {
  const { root, fixture, attempt } = await mount(t, 'teacher', true)
  fixture.rows = [attempt]; fixture.total = 21
  await button(root, '重新加载答卷').props.onClick(); await flush()
  assert.equal(button(root, '答卷下一页').props.disabled, false)
  await button(root, '答卷下一页').props.onClick(); await flush()
  assert.match(content(root), /第 2 页/)
  assert.ok(fixture.reads.some(path => path.includes('/courses/1/attempts?page=2')))
  control(root, '筛选评分状态').props.onChange({ target: { value: 'partial' } })
  submit(root, 'inline-form attempt-filters'); await flush()
  assert.match(content(root), /第 1 页/)
  assert.match(fixture.reads.at(-1), /page=1.*status=partial/)
})

test('identity change drops late results and prevents old teacher writes', async t => {
  const { root, fixture, user, attempt } = await mount(t, 'teacher')
  fixture.rows = [attempt]
  await button(root, '重新加载答卷').props.onClick(); await flush()
  let release
  fixture.waitDetail = new Promise(resolve => { release = resolve })
  button(root, '答卷 #9 · 待人工评分 · 学生 #7').props.onClick(); await flush()
  user.id = 8; user.role = 'student'; fixture.userId = 8; fixture.rows = []
  await flush(); release(); await flush()
  assert.equal(button(root, '保存本次批阅'), undefined)
  assert.doesNotMatch(content(root), /原作答：原文/)
  assert.equal(fixture.writes.length, 0)
})
