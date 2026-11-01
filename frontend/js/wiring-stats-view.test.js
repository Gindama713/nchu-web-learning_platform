// Component/HTTP doubles only; real browser acceptance remains unverified.
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer } from 'vue'
import { WiringStatsView } from './wiring-stats-view.js'

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
const flush = async () => { await setImmediate() }

const RUN = {
  analysis_run_id: 5, dimension: 'wiring', unit: 'student',
  population_basis: '已发布连线实验的参与学生', source_until: '2026-10-26T08:00:00Z',
  generated_at: '2026-10-26T08:30:00Z', algorithm_version: 'wiring-analysis-v1',
  sample_size: 3,
  metrics: { assigned_count: 3, completed_student_count: 2, completion_rate: 0.6667, attempt_count: 4,
    error_counts: { WIDTH_MISMATCH: 2, FLOATING_INPUT: 1 } },
  series: [
    { period_start: '2026-10-05T00:00:00Z', period_end: '2026-10-12T00:00:00Z',
      metrics: { assigned_count: 2, completed_student_count: 1, completion_rate: 0.5, attempt_count: 2 } },
    { period_start: '2026-10-12T00:00:00Z', period_end: '2026-10-19T00:00:00Z',
      metrics: { assigned_count: 1, completed_student_count: 1, completion_rate: 1, attempt_count: 2 } },
  ],
  warnings: ['完成率仅统计功能全过的提交，草稿不计入'],
}
const EMPTY = {
  ...RUN, analysis_run_id: 6, sample_size: 0,
  metrics: { assigned_count: 0, completed_student_count: 0, completion_rate: null, attempt_count: 0,
    error_counts: {} },
  series: [], warnings: [],
}

async function mount(t, role = 'teacher', overrides = {}) {
  const fixture = {
    userId: 7, analytics: RUN, restored: null, error: null, queries: [], ...overrides,
  }
  const okData = data => ({ ok: true, status: 200, json: async () =>
    ({ data, total: Array.isArray(data) ? data.length : 1 }) })
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage }
  globalThis.fetch = async path => {
    if (fixture.error) {
      return { ok: false, status: fixture.error.status, json: async () =>
        ({ error: { code: fixture.error.code, message: fixture.error.message } }) }
    }
    if (path.endsWith('/auth/session')) {
      return okData({ user: { id: fixture.userId, name: '测试用户', role }, csrf_token: 'token' })
    }
    if (path === '/api/v1/courses?page=1&page_size=100') return okData([{ id: 1, title: 'Fixture 课程' }])
    if (path === '/api/v1/courses/1/analytics?dimension=wiring') {
      fixture.queries.push(path)
      return okData(fixture.analytics)
    }
    if (path === '/api/v1/courses/1/analytics?analysis_run_id=7') {
      fixture.restored = path
      return okData({ ...fixture.analytics, analysis_run_id: 7 })
    }
    throw new Error(`Unexpected path ${path}`)
  }
  const root = element('root')
  const app = renderer.createApp(WiringStatsView, { user: { id: fixture.userId, name: '测试用户', role } })
  app.mount(root)
  t.after(() => {
    app.unmount()
    globalThis.fetch = previous.fetch
    globalThis.localStorage = previous.localStorage
  })
  await flush()
  return { root, fixture }
}

test('teacher boot queries wiring dimension and renders metrics, errors and series', async t => {
  const view = await mount(t, 'teacher')
  assert.deepEqual(view.fixture.queries, ['/api/v1/courses/1/analytics?dimension=wiring'])
  const text = content(view.root)
  assert.match(text, /原快照 #5 · 连线统计/)
  assert.match(text, /应做人数3/)
  assert.match(text, /完成人数2/)
  assert.match(text, /66\.67%/)
  assert.match(text, /提交次数4/)
  assert.match(text, /有效样本 3/)
  assert.match(text, /WIDTH_MISMATCH2/)
  assert.match(text, /FLOATING_INPUT1/)
  assert.match(text, /完成率仅统计功能全过的提交，草稿不计入/)
  assert.match(text, /wiring-analysis-v1/)
  assert.match(text, /周区间（左闭右开，Asia\/Shanghai）应做人数完成人数完成率提交次数/)
  assert.match(text, /导出当前快照 CSV/)
})

test('empty sample shows explicit zero-state instead of a blank page', async t => {
  const view = await mount(t, 'teacher', { analytics: EMPTY })
  const text = content(view.root)
  assert.match(text, /有效样本 0/)
  assert.match(text, /无有效样本，完成率显示无数据。/)
  assert.match(text, /完成率无数据/)
  assert.match(text, /本区间没有校验错误记录。/)
  assert.match(text, /原快照 #6 · 连线统计/)
})

test('saved pointer restores the previous wiring snapshot on boot', async t => {
  globalThis.localStorage = {
    getItem: key => (key === '010c-snapshot:7:teacher'
      ? JSON.stringify({ course: '1', run: 7 }) : null),
    setItem() {}, removeItem() {},
  }
  const view = await mount(t, 'teacher')
  assert.equal(view.fixture.restored, '/api/v1/courses/1/analytics?analysis_run_id=7')
  assert.match(content(view.root), /原快照 #7 · 连线统计/)
  assert.deepEqual(view.fixture.queries, [])
})

test('student only sees a restricted notice', async t => {
  const view = await mount(t, 'student')
  assert.match(content(view.root), /连线统计仅对教师开放。/)
  assert.doesNotMatch(content(view.root), /查询统计/)
  assert.doesNotMatch(content(view.root), /恢复原快照/)
})

test('server error is displayed and old data is not silently replaced', async t => {
  const view = await mount(t, 'teacher', { error: { status: 503, code: 'UNAVAILABLE', message: '服务未就绪' } })
  assert.match(content(view.root), /服务未就绪/)
  assert.match(content(view.root), /不会自动替换为最新数据/)
  assert.doesNotMatch(content(view.root), /原快照 #5/)
})
