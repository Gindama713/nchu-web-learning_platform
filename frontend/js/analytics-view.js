import { h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { AnalyticsClient } from './analytics-client.js'

const labels = { expected_count: '应交人卷次', submitted_count: '已交人卷次', missing_count: '缺交人卷次',
  graded_count: '已批人卷次', partial_count: '待批人卷次', mean_score: '同卷平均分', mean_percentage: '平均百分比',
  answered_count: '实际客观作答次数', correct_count: '正确次数', mastery: '掌握度', completed_knowledge_count: '本人完成知识点',
  published_knowledge_count: '当前发布知识点', progress: '本人完成进度' }
const ratio = value => value === null || value === undefined ? '无数据' : `${(value * 100).toFixed(2)}%`
const shown = (key, value) => ['mastery', 'progress'].includes(key) ? ratio(value) : value === null || value === undefined
  ? '无数据' : ['mean_score', 'mean_percentage'].includes(key) ? `${Number(value).toFixed(2)}${key === 'mean_percentage' ? '%' : ' 分'}` : String(value)

export const AnalyticsView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    let api = new AnalyticsClient(props.user), epoch = 0
    const courses = ref([]), course = ref(''), data = ref(null), runId = ref(''), busy = ref(false), error = ref('')
    const filters = reactive({ dimension: 'knowledge', kind: 'homework', from: '', to: '', student_id: '', paper_id: '' })
    const storageKey = () => `010b-snapshot:${props.user.id}:${props.user.role}`
    function forget() { epoch++; data.value = null; busy.value = false; error.value = '' }
    function saved() {
      try { return JSON.parse(globalThis.localStorage?.getItem(storageKey()) ?? 'null') } catch { return null }
    }
    function remember(value) {
      try { globalThis.localStorage?.setItem(storageKey(), JSON.stringify({ course: course.value, run: value.analysis_run_id })) } catch { /* Storage is optional. */ }
    }
    function show(value, ticket) {
      if (ticket !== epoch) return
      if (!['knowledge', 'scores'].includes(value.dimension)) throw new Error('请恢复知识或分类成绩快照。')
      filters.dimension = value.dimension
      if (value.dimension === 'scores') filters.kind = value.metrics.kind
      data.value = value; runId.value = String(value.analysis_run_id); remember(value)
    }
    async function run(action) {
      if (busy.value) return
      const ticket = epoch
      busy.value = true; error.value = ''; data.value = null
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
      const selected = { ...filters }
      for (const key of ['from', 'to']) if (selected[key]) selected[key] = new Date(selected[key]).toISOString()
      if (props.user.role !== 'teacher') selected.student_id = ''
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
      course.value = available.some(c => String(c.id) === String(previous?.course)) ? String(previous.course) : available.length ? String(available[0].id) : ''
      if (previous && course.value === String(previous.course)) { runId.value = String(previous.run); await restore(ticket) }
      else if (course.value) await query(ticket)
    }
    async function download() {
      if (!data.value || busy.value) return
      const current = data.value, selectedCourse = course.value, ticket = epoch
      busy.value = true; error.value = ''
      try {
        const blob = await api.csv(selectedCourse, current.analysis_run_id)
        if (ticket !== epoch) return
        const url = globalThis.URL.createObjectURL(blob), anchor = document.createElement('a')
        anchor.href = url; anchor.download = `${current.dimension}-${current.analysis_run_id}.csv`
        document.body.append(anchor); anchor.click(); anchor.remove()
        globalThis.setTimeout(() => globalThis.URL.revokeObjectURL(url), 1000)
      } catch (failure) {
        if (ticket === epoch) { data.value = null; error.value = `${failure.message} 请恢复原快照或重新查询。` }
      } finally { if (ticket === epoch) busy.value = false }
    }
    watch(() => `${props.user.id}:${props.user.role}`, () => {
      forget(); courses.value = []; course.value = ''; runId.value = ''
      api = new AnalyticsClient(props.user)
      if (props.user.role !== 'admin') run(boot)
    }, { flush: 'sync' })
    onMounted(() => { if (props.user.role !== 'admin') run(boot) })
    onUnmounted(forget)
    const button = (label, action, disabled = false) => h('button', { type: 'button', onClick: action, disabled: busy.value || disabled }, label)
    const input = (label, value, update, type = 'text') => h('label', [label, h('input', { 'aria-label': label, type, value,
      onInput: event => { forget(); update(event.target.value) } })])
    const select = (label, value, update, options) => h('label', [label, h('select', { 'aria-label': label, value,
      onChange: event => { forget(); update(event.target.value) } }, options.map(([id, text]) => h('option', { value: id }, text)))])
    const table = (caption, headings, rows) => h('div', { class: 'analytics-scroll', tabindex: 0, role: 'region', 'aria-label': caption }, [h('table', [h('caption', caption),
      h('thead', [h('tr', headings.map(label => h('th', { scope: 'col' }, label)))]),
      h('tbody', rows.map(row => h('tr', row.map(text => h('td', String(text))))))])])
    function report() {
      const value = data.value, m = value.metrics
      const keys = Object.keys(labels).filter(key => Object.hasOwn(m, key))
      return h('article', { class: 'analytics-report' }, [h('h3', `原快照 #${value.analysis_run_id} · ${value.dimension === 'knowledge' ? '知识分析' : `分类成绩 / ${m.kind}`}`),
        h('p', `数据截止 ${value.source_until} · 生成 ${value.generated_at} · 算法 ${value.algorithm_version}`),
        h('p', value.filters ? `原筛选 ${value.filters.from} 至 ${value.filters.to} · ${value.filters.student_id ? `学生 #${value.filters.student_id}` : '全班'}${value.filters.paper_id ? ` · 试卷 #${value.filters.paper_id}` : ''}` : '历史快照未记录可展示的筛选摘要；以下为原保存结果。'),
        h('p', `有效样本 ${value.sample_size} · ${value.dimension === 'knowledge' ? '按实际客观作答去重；进度取原查询时的发布集合' : '按试卷开始时间选任务；应交取冻结名单，均分只计已批卷'}`),
        ...value.warnings.map(w => h('p', w)),
        m.selected_paper_ids && h('p', `实际试卷：${m.selected_paper_ids.join('、') || '无'}`),
        value.sample_size === 0 && h('p', { role: 'status' }, '无有效样本，均分或掌握度显示无数据。'),
        h('dl', { class: 'analytics-metrics' }, keys.flatMap(key => [h('dt', labels[key]), h('dd', shown(key, m[key]))])),
        value.dimension === 'scores' && m.mean_score === null && m.selected_paper_ids.length > 1 && h('p', '跨卷原始平均分不适用，请查看平均百分比。'),
        value.dimension === 'knowledge' ? table('知识点掌握度与错题分布（多标签分别计入，总体按实际作答去重）',
          ['知识点', '作答', '正确', '错题', '掌握度'], m.items.map(item => [`#${item.knowledge_id} ${item.title}`, item.answered_count, item.correct_count, item.wrong_count, ratio(item.mastery)]))
          : h('div', [h('h4', '已批成绩百分比分布'), ...m.score_bins.map(bin => h('div', { class: 'analytics-bin' }, [
            h('span', bin.label), h('meter', { min: 0, max: Math.max(1, m.graded_count), value: bin.count, 'aria-label': `${bin.label} ${bin.count} 人卷次` }), h('span', `${bin.count} 人卷次`)]))]),
        table('按上海周一划分的周趋势', ['区间（左闭右开）', ...keys.map(key => labels[key])], value.series.map(p => [
          `${p.period_start} — ${p.period_end}`, ...keys.map(key => shown(key, p.metrics[key]))])),
        props.user.role === 'teacher' && button('导出当前快照 CSV', download),
      ])
    }
    return () => props.user.role === 'admin' ? null : h('section', { class: 'card analytics-bank', 'aria-busy': busy.value }, [
      h('h2', '知识与分类成绩分析'), h('p', '查询保存本次结果。刷新页面恢复上次快照；重新查询才会更新统计。日期按本机时区输入，最多366天；留空为最近28天。'),
      h('div', { class: 'analytics-filters' }, [
        select('统计课程', course.value, v => { course.value = v; runId.value = '' }, courses.value.map(c => [String(c.id), c.title])),
        select('统计维度', filters.dimension, v => { filters.dimension = v }, [['knowledge', '知识掌握度、错题与进度'], ['scores', '分类成绩']]),
        input('统计起始时间', filters.from, v => { filters.from = v }, 'datetime-local'),
        input('统计结束时间', filters.to, v => { filters.to = v }, 'datetime-local'),
        props.user.role === 'teacher' && input('学生编号（留空全班）', filters.student_id, v => { filters.student_id = v }, 'number'),
        filters.dimension === 'scores' && select('成绩类别', filters.kind, v => { filters.kind = v; filters.paper_id = '' }, [['homework', '作业'], ['exam', '考试'], ['quiz', '随堂测']]),
        filters.dimension === 'scores' && input('试卷编号（留空本类别全部）', filters.paper_id, v => { filters.paper_id = v }, 'number'),
      ]), button('查询统计', () => run(query), !course.value),
      h('div', { class: 'analytics-restore' }, [input('原快照编号', runId.value, v => { runId.value = v }, 'number'), button('恢复原快照', () => run(restore), !course.value || !runId.value)]),
      busy.value && h('p', { role: 'status' }, '正在读取统计…'), error.value && h('p', { role: 'alert' }, error.value),
      !data.value && !busy.value && !error.value && h('p', '请选择筛选后查询，或填写原快照编号恢复。'), data.value && report(),
    ])
  },
}
