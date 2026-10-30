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
    const filters = reactive({ from: '', to: '' })
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
    async function query(ticket) {
      if (!course.value) throw new Error('请先选择统计课程。')
      const selected = { dimension: 'wiring', ...filters }
      for (const key of ['from', 'to']) if (selected[key]) selected[key] = new Date(selected[key]).toISOString()
      show(await api.query(course.value, selected), ticket)
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
      filters.from = ''
      filters.to = ''
      api = new AnalyticsClient(props.user)
      if (teacher()) run(boot)
    }, { flush: 'sync' })
    onMounted(() => { if (teacher()) run(boot) })
    onUnmounted(forget)

    const button = (label, action, disabled = false) => h('button', {
      type: 'button', onClick: action, disabled: busy.value || disabled,
    }, label)
    const input = (label, value, update, type = 'text') => h('label', [label, h('input', {
      'aria-label': label, type, value, disabled: !courses.value.length,
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
      return h('article', { class: 'wiring-stats-report' }, [
        h('h3', `原快照 #${value.analysis_run_id} · 连线统计`),
        h('p', `数据截止 ${shanghaiTime(value.source_until)} · 生成 ${shanghaiTime(value.generated_at)}（Asia/Shanghai） · 算法 ${value.algorithm_version}`),
        h('p', `有效样本 ${value.sample_size} · 统计口径：已发布连线实验的参与学生（按人与实验版本去重）`),
        ...(value.warnings ?? []).map(warning => h('p', warning)),
        value.sample_size === 0 && h('p', { role: 'status' }, '无有效样本，完成率显示无数据。'),
        h('dl', { class: 'wiring-stats-metrics' },
          METRICS.flatMap(([key, label]) => [h('dt', label), h('dd', shown(key, m[key]))])),
        errors.length
          ? table('连线校验错误分布（同一提交同版本同错误码只计一次）', ['错误码', '次数'],
            errors.map(([code, count]) => [code, count]))
          : h('p', { role: 'status' }, '本区间没有校验错误记录。'),
        table('按上海周一划分的连线周趋势', ['周区间（左闭右开，Asia/Shanghai）', ...METRICS.map(([, label]) => label)],
          value.series.map(period => [
            `${shanghaiTime(period.period_start)} — ${shanghaiTime(period.period_end)}`,
            ...METRICS.map(([key]) => shown(key, period.metrics[key])),
          ])),
        button('导出当前快照 CSV', download),
      ])
    }

    return () => h('section', { class: 'card wiring-stats', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [
        h('h2', '连线统计'),
        teacher() && button('重新加载', () => run(boot)),
      ]),
      !teacher() && h('p', '连线统计仅对教师开放。'),
      teacher() && h('p', '统计已发布连线实验的应做人数、完成率、提交次数与校验错误分布。查询保存本次结果；刷新页面恢复上次快照。日期留空为最近28天，最多366天。'),
      teacher() && h('div', { class: 'wiring-stats-filters' }, [
        h('label', ['统计课程 ', h('select', {
          'aria-label': '统计课程', value: course.value, disabled: !courses.value.length,
          onChange: event => { forget(); course.value = event.target.value },
        }, courses.value.map(item => h('option', { value: String(item.id), key: item.id }, item.title)))]),
        input('统计起始时间', filters.from, value => { filters.from = value }, 'datetime-local'),
        input('统计结束时间', filters.to, value => { filters.to = value }, 'datetime-local'),
      ]),
      teacher() && button('查询统计', () => run(query), !course.value),
      teacher() && h('div', { class: 'wiring-stats-restore' }, [
        input('原快照编号', runId.value, value => { runId.value = value }, 'number'),
        button('恢复原快照', () => run(restore), !course.value || !runId.value),
      ]),
      busy.value && h('p', { role: 'status' }, '正在读取统计…'),
      error.value && h('p', { role: 'alert' }, error.value),
      teacher() && !data.value && !busy.value && !error.value && h('p', '请选择筛选后查询，或填写原快照编号恢复。'),
      teacher() && data.value && report(),
    ])
  },
}
