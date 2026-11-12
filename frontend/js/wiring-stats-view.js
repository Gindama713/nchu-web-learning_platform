// SPEC-010C wiring analytics view: teacher-only completion and error snapshots.
import { h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { AnalyticsClient } from './analytics-client.js'

const METRICS = [
  ['assigned_count', '应做人数'],
  ['completed_student_count', '完成人数'],
  ['completion_rate', '完成率'],
  ['attempt_count', '提交次数'],
]
const rate = value => (value === null || value === undefined ? '无数据' : `${(value * 100).toFixed(2)}%`)
const shown = (key, value) => (key === 'completion_rate' ? rate(value) : String(value ?? '无数据'))
const shanghaiFormat = new globalThis.Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
const shanghaiTime = value => {
  const date = new Date(value)
  return value && Number.isFinite(date.getTime()) ? shanghaiFormat.format(date) : '无时间记录'
}
// 统计起止精确到「几月几号」：日期用日历控件，换算成上海时区的当天 0 点与次日 0 点（右开）。
const DAY_MS = 86400000
const shanghaiDay = value => new globalThis.Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' })
  .format(value).slice(0, 10)
const dayStart = value => new Date(`${value}T00:00:00+08:00`)
const MAX_SPAN = 366 * DAY_MS

export const WiringStatsView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    let api = new AnalyticsClient(props.user), epoch = 0
    const courses = ref([])
    const course = ref('')
    const data = ref(null)
    const runId = ref('')
    const busy = ref(false)
    const error = ref('')
    const filters = reactive({ fromDate: '', toDate: '' })
    const teacher = () => props.user.role === 'teacher'
    const storageKey = () => `010c-snapshot:${props.user.id}:${props.user.role}`

    function forget() {
      epoch += 1
      data.value = null
      busy.value = false
      error.value = ''
    }
    function saved() {
      try { return JSON.parse(globalThis.localStorage?.getItem(storageKey()) ?? 'null') } catch { return null }
    }
    function remember() {
      try {
        globalThis.localStorage?.setItem(storageKey(),
          JSON.stringify({ course: course.value, run: data.value?.analysis_run_id }))
      } catch { /* Storage is optional. */ }
    }
    function show(value, ticket) {
      if (ticket !== epoch) return
      if (value.dimension !== 'wiring') throw new Error('请恢复连线统计快照。')
      data.value = value
      runId.value = String(value.analysis_run_id)
      remember()
    }
    async function run(action) {
      if (busy.value) return
      const ticket = epoch
      busy.value = true
      error.value = ''
      try {
        await api.verifySession()
        if (ticket === epoch) await action(ticket)
      } catch (failure) {
        if (ticket !== epoch) return
        data.value = null
        error.value = `${failure.message} 原快照不可用时请重新查询；不会自动替换为最新数据。`
      } finally { if (ticket === epoch) busy.value = false }
    }
    // 选「到 X 日」含 X 日当天：区间右端取次日 0 点，若超过当前时刻则截到当前时刻（后端要求 to ≤ now）。
    function range() {
      const selected = { dimension: 'wiring' }
      if (filters.fromDate) selected.from = dayStart(filters.fromDate).toISOString()
      if (filters.toDate) {
        const end = new Date(dayStart(filters.toDate).getTime() + DAY_MS)
        const now = new Date()
        selected.to = (end > now ? now : end).toISOString()
      }
      if (selected.from && selected.to) {
        const span = new Date(selected.to) - new Date(selected.from)
        if (span < 0) throw new Error('起始日期不能晚于结束日期。')
        if (span > MAX_SPAN) throw new Error('统计区间不能超过 366 天，请缩小日期范围。')
      }
      return selected
    }
    async function query(ticket) {
      if (!course.value) throw new Error('请先选择统计课程。')
      show(await api.query(course.value, range()), ticket)
    }
    async function restore(ticket) {
      if (!course.value || !/^[1-9][0-9]*$/.test(runId.value)) throw new Error('请选择课程并填写有效快照编号。')
      show(await api.restore(course.value, runId.value), ticket)
    }
    async function boot(ticket) {
      const available = await api.courses()
      if (ticket !== epoch) return
      courses.value = available
      const previous = saved()
      course.value = available.some(item => String(item.id) === String(previous?.course))
        ? String(previous.course)
        : available.length ? String(available[0].id) : ''
      if (previous && course.value === String(previous.course)) { runId.value = String(previous.run); await restore(ticket) }
      else if (course.value) await query(ticket)
    }
    async function download() {
      if (!data.value || busy.value) return
      const current = data.value, selectedCourse = course.value, ticket = epoch
      busy.value = true
      error.value = ''
      try {
        const blob = await api.csv(selectedCourse, current.analysis_run_id)
        if (ticket !== epoch) return
        const url = globalThis.URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = `wiring-${current.analysis_run_id}.csv`
        document.body.append(anchor)
        anchor.click()
        anchor.remove()
        globalThis.setTimeout(() => globalThis.URL.revokeObjectURL(url), 1000)
      } catch (failure) {
        if (ticket === epoch) error.value = `${failure.message} 请恢复原快照或重新查询。`
      } finally { if (ticket === epoch) busy.value = false }
    }
    watch(() => `${props.user.id}:${props.user.role}`, () => {
      forget()
      courses.value = []
      course.value = ''
      runId.value = ''
      filters.fromDate = ''
      filters.toDate = ''
      api = new AnalyticsClient(props.user)
      if (teacher()) run(boot)
    }, { flush: 'sync' })
    onMounted(() => { if (teacher()) run(boot) })
    onUnmounted(forget)

    const button = (label, action, disabled = false) => h('button', {
      type: 'button', onClick: action, disabled: busy.value || disabled,
    }, label)
    // aria-label 带上模块名：成绩统计与本卡在同一页，两边都叫「原快照编号」时读屏和
    // 自动化会抓到对方的输入框（实测踩过，误判成「恢复快照失效」）。
    const input = (label, value, update, type = 'text', aria = label) => h('label', [label, h('input', {
      'aria-label': aria, type, value, disabled: !courses.value.length,
      onInput: event => { forget(); update(event.target.value) },
    })])
    const dateField = (label, value, update) => h('label', [label, h('input', {
      'aria-label': label, type: 'date', value, disabled: !courses.value.length,
      max: shanghaiDay(new Date()),
      onInput: event => { forget(); update(event.target.value) },
    })])
    const table = (caption, headings, rows) => h('div', {
      class: 'wiring-stats-scroll', tabindex: 0, role: 'region', 'aria-label': caption,
    }, [h('table', [h('caption', caption),
      h('thead', [h('tr', headings.map(label => h('th', { scope: 'col' }, label)))]),
      h('tbody', rows.map(row => h('tr', row.map(text => h('td', String(text))))))])])

    function report() {
      const value = data.value
      const m = value.metrics
      const errors = Object.entries(m.error_counts ?? {})
      // 算法版本、快照号、样本口径收进折叠区，结论先摆出来
      const tech = h('details', { class: 'analytics-tech' }, [
        h('summary', {}, '数据口径与快照信息'),
        h('p', {}, `第 ${value.analysis_run_id} 次分析快照 · 连线统计`),
        h('p', {}, `数据截止 ${shanghaiTime(value.source_until)} · 生成于 ${shanghaiTime(value.generated_at)}`),
        h('p', {}, `有效样本 ${value.sample_size} · 已发布连线实验的参与学生（按人与实验版本去重）`),
        h('p', {}, `算法版本 ${value.algorithm_version}`),
        ...(value.warnings ?? []).map(warning => h('p', {}, warning)),
      ])
      return h('article', { class: 'wiring-stats-report' }, [
        h('h3', '本次统计结果'),
        value.sample_size === 0 && h('p', { class: 'analytics-empty', role: 'status' },
          '这段时间没有已发布的连线实验，暂时没有可统计的数据。'),
        h('dl', { class: 'wiring-stats-metrics' },
          METRICS.flatMap(([key, label]) => [h('dt', label), h('dd', shown(key, m[key]))])),
        errors.length
          ? table('连线校验错误分布（同一提交同版本同错误码只计一次）', ['错误码', '次数'],
            errors.map(([code, count]) => [code, count]))
          : h('p', { role: 'status' }, '本区间没有校验错误记录。'),
        value.sample_size === 0
          ? h('p', { class: 'chart-empty' }, '这段时间没有可统计的数据，周趋势先不展示。')
          : table('按上海周一划分的连线周趋势', ['周区间（左闭右开，Asia/Shanghai）', ...METRICS.map(([, label]) => label)],
            value.series.map(period => [
              `${shanghaiTime(period.period_start)} — ${shanghaiTime(period.period_end)}`,
              ...METRICS.map(([key]) => shown(key, period.metrics[key])),
            ])),
        tech,
        button('导出当前快照 CSV', download),
      ])
    }

    return () => h('section', { class: 'card wiring-stats', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [
        h('h2', '连线统计'),
        teacher() && button('重新加载', () => run(boot)),
      ]),
      !teacher() && h('p', '连线统计仅对教师开放。'),
      teacher() && h('p', '统计已发布连线实验的应做人数、完成率与校验错误分布。实验时间窗与所选区间有交集即计入，正在进行的实验也会统计到。刷新页面会恢复上次结果；日期留空即统计最近 28 天，「结束日期」含当天，且不能晚于今天。'),
      teacher() && h('div', { class: 'wiring-stats-filters' }, [
        h('label', ['统计课程 ', h('select', {
          'aria-label': '统计课程（连线统计）', value: course.value, disabled: !courses.value.length,
          onChange: event => { forget(); course.value = event.target.value },
        }, courses.value.map(item => h('option', { value: String(item.id), key: item.id }, item.title)))]),
        dateField('统计起始日期', filters.fromDate, value => { filters.fromDate = value }),
        dateField('统计结束日期', filters.toDate, value => { filters.toDate = value }),
      ]),
      teacher() && button('查询统计', () => run(query), !course.value),
      teacher() && h('details', { class: 'analytics-restore' }, [
        h('summary', {}, '按快照编号恢复以前的结果'),
        h('div', { class: 'analytics-restore-row' }, [
          input('原快照编号', runId.value, value => { runId.value = value }, 'number', '原快照编号（连线统计）'),
          button('恢复原快照', () => run(restore), !course.value || !runId.value),
        ]),
      ]),
      busy.value && h('p', { role: 'status' }, '正在读取统计…'),
      error.value && h('p', { role: 'alert' }, error.value),
      teacher() && !data.value && !busy.value && !error.value && h('p', '请选择筛选后查询，或填写原快照编号恢复。'),
      teacher() && data.value && report(),
    ])
  },
}
