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
const find = (item, predicate, found = []) => {
  if (predicate(item)) found.push(item)
  for (const child of item.children) find(child, predicate, found)
  return found
}
const flush = async () => { await setImmediate() }

const RUN = {
  analysis_run_id: 5, dimension: 'wiring', unit: 'student',
  population_basis: '已发布连线实验的参与学生', source_until: '2026-10-26T08:00:00Z',
  generated_at: '2026-10-26T08:30:00Z', algorithm_version: 'wiring-analysis-v2',
  sample_size: 3,
  metrics: { assigned_count: 3, completed_student_count: 2, completion_rate: 0.6667, attempt_count: 4,
    error_counts: { WIDTH_MISMATCH: 2, FLOATING_INPUT: 1 } },
  series: [
    { period_start: '2026-10-05T00:00:00Z', period_end: '2026-10-12T00:00:00Z',
      metrics: { assigned_count: 2, completed_student_count: 1, completion_rate: 0.5, attempt_count: 2 } },
    { period_start: '2026-10-12T00:00:00Z', period_end: '2026-10-19T00:00:00Z',
      metrics: { assigned_count: 1, completed_student_count: 1, completion_rate: 1, attempt_count: 2 } },
  ],
  warnings: ['实验时间窗与查询区间有交集即计入，进行中的实验也会统计', '完成率仅统计功能全过的提交，草稿不计入'],
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
    if (path.startsWith('/api/v1/courses/1/analytics?')) {
      const params = new globalThis.URL(path, 'http://127.0.0.1').searchParams
      if (params.get('analysis_run_id')) {
        fixture.restored = path
        return okData({ ...fixture.analytics, analysis_run_id: 7 })
      }
      fixture.queries.push(path)
      return okData(fixture.analytics)
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
  assert.match(text, /第 5 次分析快照 · 连线统计/)
  assert.match(text, /应做人数3/)
  assert.match(text, /完成人数2/)
  assert.match(text, /66\.67%/)
  assert.match(text, /提交次数4/)
  assert.match(text, /有效样本 3/)
  assert.match(text, /WIDTH_MISMATCH2/)
  assert.match(text, /FLOATING_INPUT1/)
  assert.match(text, /完成率仅统计功能全过的提交，草稿不计入/)
  assert.match(text, /实验时间窗与查询区间有交集即计入/)
  assert.match(text, /wiring-analysis-v2/)
  assert.match(text, /周区间（左闭右开，Asia\/Shanghai）应做人数完成人数完成率提交次数/)
  assert.match(text, /导出当前快照 CSV/)
  assert.match(text, /统计起始日期/)
  assert.match(text, /统计结束日期/)
  const dates = find(view.root, item => item.type === 'input' && item.props.type === 'date')
  assert.equal(dates.length, 2, '起始/结束都是日期日历控件')
  assert.equal(find(view.root, item => item.type === 'select'
    && item.props['aria-label'] === '统计起始时间').length, 0)
})

test('日期筛选换算成上海时区的整天区间', async t => {
  const view = await mount(t, 'teacher')
  const [from, to] = find(view.root, item => item.type === 'input' && item.props.type === 'date')
  view.fixture.queries.length = 0
  from.props.onInput({ target: { value: '2026-10-05' } })
  to.props.onInput({ target: { value: '2026-10-19' } })
  await flush()
  const [query] = find(view.root, item => item.type === 'button' && content(item) === '查询统计')
  await query.props.onClick()
  await flush()
  assert.equal(view.fixture.queries.length, 1)
  const url = new globalThis.URL(view.fixture.queries[0], 'http://127.0.0.1')
  assert.equal(url.searchParams.get('from'), '2026-10-04T16:00:00.000Z')
  assert.equal(url.searchParams.get('to'), '2026-10-19T16:00:00.000Z')
})

test('empty sample shows explicit zero-state instead of a blank page', async t => {
  const view = await mount(t, 'teacher', { analytics: EMPTY })
  const text = content(view.root)
  assert.match(text, /有效样本 0/)
  assert.match(text, /这段时间没有已发布的连线实验，暂时没有可统计的数据。/)
  assert.match(text, /完成率无数据/)
  assert.match(text, /本区间没有校验错误记录。/)
  assert.match(text, /第 6 次分析快照 · 连线统计/)
})

test('saved pointer restores the previous wiring snapshot on boot', async t => {
  globalThis.localStorage = {
    getItem: key => (key === '010c-snapshot:7:teacher'
      ? JSON.stringify({ course: '1', run: 7 }) : null),
    setItem() {}, removeItem() {},
  }
  const view = await mount(t, 'teacher')
  assert.equal(view.fixture.restored, '/api/v1/courses/1/analytics?analysis_run_id=7')
  assert.match(content(view.root), /第 7 次分析快照 · 连线统计/)
  assert.deepEqual(view.fixture.queries, [])
})

test('恢复快照输入框用模块限定的可访问名，不与同页成绩统计撞名', async t => {
  const view = await mount(t, 'teacher')
  const labels = find(view.root, item => ['input', 'select'].includes(item.type) && item.props['aria-label'])
    .map(item => item.props['aria-label'])
  assert.ok(labels.includes('原快照编号（连线统计）'))
  assert.ok(!labels.includes('原快照编号'), '同页还留着裸标签就会和成绩统计撞名')
  assert.equal(new Set(labels).size, labels.length, `可访问名重复：${labels.join('、')}`)
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
