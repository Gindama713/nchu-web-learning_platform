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

async function mount(t, role = 'teacher', quizOnly = false) {
  const fixture = { userId: 7, writes: [], rows: [], detail: null, unavailable: false, waitQuestions: null,
    waitStatistics: null, statistics: null }
  const user = reactive({ id: 7, role })
  const previous = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const result = (data, total) => ({ ok: true, status: 200, json: async () => ({ data, ...(total === undefined ? {} : { total }) }) })
    if (fixture.unavailable) return { ok: false, status: 503, json: async () => ({ error: { message: '服务未就绪' } }) }
    if (path.endsWith('/auth/session')) return result({ user: { id: fixture.userId, role: user.role }, csrf_token: 'token' })
    if (options.method) {
      const values = JSON.parse(options.body)
      fixture.writes.push({ path, values })
      if (path.endsWith('/review')) {
        fixture.detail = { ...fixture.detail, review_at: '2026-10-13T14:00:00Z' }
        return result({ review_published_at: fixture.detail.review_at })
      }
      const item = path.endsWith('/publish') || path.endsWith('/quizzes') ? { ...fixture.detail, ...values,
        status: 'published', window_state: 'upcoming', participant_count: 2, ...(quizOnly ? { review_at: null } : {}) }
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
    if (path.includes('/papers?') || path.includes('/quizzes?')) return result(fixture.rows, fixture.rows.length)
    if (path.includes('/attempts?')) return result([], 0)
    if (path.endsWith('/statistics')) {
      const snapshot = fixture.statistics
      if (fixture.waitStatistics) await fixture.waitStatistics
      return result(snapshot)
    }
    if (path.endsWith('/papers/3')) return result(fixture.detail)
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(PaperView, { user, quizOnly })
  app.mount(root)
  t.after(() => { app.unmount(); globalThis.fetch = previous })
  await flush()
  return { root, fixture, user }
}

test('dedicated quiz screen creates quiz drafts and publishes without automatic review', async t => {
  const { root, fixture } = await mount(t, 'teacher', true)
  assert.ok(find(root, 'h2', '随堂测'))
  assert.equal(find(root, 'span', '筛选试卷类型'), undefined)
  await find(root, 'button', '编排新试卷').props.onClick(); await flush()
  assert.equal(find(root, 'span', '试卷类型'), undefined)
  field(root, '试卷标题', 'input').props.onInput({ target: { value: 'CPU随堂测' } })
  field(root, '选择题目版本', 'select').props.onChange({ target: { value: '1' } }); await flush()
  find(root, 'button', '加入试卷').props.onClick(); await flush()
  submit(root, 'paper-editor'); await flush()
  assert.equal(fixture.writes[0].values.kind, 'quiz')
  assert.equal(find(root, 'span', '试卷讲评'), undefined)
  field(root, '试卷开始', 'input').props.onInput({ target: { value: '2026-10-13T21:00' } })
  field(root, '试卷截止', 'input').props.onInput({ target: { value: '2026-10-13T22:00' } })
  submit(root, 'paper-publication'); await flush()
  assert.equal(fixture.writes[1].path, '/api/v1/courses/1/quizzes')
  assert.equal(fixture.writes[1].values.paper_id, 3)
  assert.equal(Object.hasOwn(fixture.writes[1].values, 'review_at'), false)
  assert.match(content(root), /待教师讲评/)
  assert.equal(find(root, 'button', '发布随堂测并冻结名单'), undefined)
})

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

const publishedQuiz = { id: 3, title: 'CPU随堂测', kind: 'quiz', status: 'published', window_state: 'closed',
  total_points: 10, participant_count: 2, review_at: null, items: [] }
const quizStatistics = { quiz_id: 3, source_until: '2026-10-13T14:00:00Z', expected_count: 2,
  submitted_count: 1, missing_count: 1, objective_correct_rate: null, questions: [
    { question_version_id: 8, type: 'short', max_score: 10, submitted_count: 1, answered_count: 1,
      unanswered_count: 0, graded_count: 0, pending_count: 1, correct_count: null, correct_rate: null,
      mean_score: null, options: [] },
  ] }

async function openQuiz(root, fixture, state = 'closed') {
  fixture.detail = { ...publishedQuiz, window_state: state }
  fixture.rows = [fixture.detail]; fixture.statistics = quizStatistics
  await find(root, 'button', '重新加载试卷').props.onClick()
  await find(root, 'button', `#3 · CPU随堂测 · ${state === 'closed' ? '已截止' : '进行中'}`).props.onClick()
  await flush()
}

test('teacher statistics shows nulls and pending; explicit review refreshes original paper', async t => {
  const { root, fixture } = await mount(t, 'teacher', true)
  await openQuiz(root, fixture)
  await find(root, 'button', '刷新逐题统计').props.onClick(); await flush()
  assert.match(content(root), /应交 2 · 已交 1 · 缺交 1 · 客观正确率 —/)
  assert.match(content(root), /已定分 0 · 待批 1 · 正确数 — · 正确率 — · 均分 —/)
  await find(root, 'button', '发布讲评并开放答案').props.onClick(); await flush()
  assert.equal(fixture.writes[0].path, '/api/v1/quizzes/3/review')
  assert.deepEqual(fixture.writes[0].values, {})
  assert.match(content(root), /讲评已发布/)
  assert.equal(find(root, 'button', '发布讲评并开放答案'), undefined)
  fixture.unavailable = true
  await find(root, 'button', '刷新逐题统计').props.onClick(); await flush()
  assert.doesNotMatch(content(root), /应交 2|CPU随堂测/)
  assert.ok(find(root, 'button', '重试试卷'))
})

test('review controls follow server window and session verification prevents writes', async t => {
  const { root, fixture } = await mount(t, 'teacher', true)
  await openQuiz(root, fixture, 'open')
  assert.equal(find(root, 'button', '发布讲评并开放答案').props.disabled, true)
  await openQuiz(root, fixture)
  fixture.userId = 8
  await find(root, 'button', '发布讲评并开放答案').props.onClick(); await flush()
  assert.equal(fixture.writes.length, 0)
  assert.match(content(root), /登录状态已变化/)
  assert.equal(find(root, 'button', '发布讲评并开放答案'), undefined)
})

test('student has no statistics/review controls and late teacher statistics is discarded on identity change', async t => {
  const { root, fixture, user } = await mount(t, 'teacher', true)
  await openQuiz(root, fixture)
  let release
  fixture.waitStatistics = new Promise(resolve => { release = resolve })
  find(root, 'button', '刷新逐题统计').props.onClick(); await flush()
  user.id = 8; user.role = 'student'; fixture.userId = 8
  await flush(); release(); await flush()
  assert.doesNotMatch(content(root), /应交 2/)
  await find(root, 'button', '#3 · CPU随堂测 · 已截止').props.onClick(); await flush()
  assert.equal(find(root, 'button', '刷新逐题统计'), undefined)
  assert.equal(find(root, 'button', '发布讲评并开放答案'), undefined)
})
