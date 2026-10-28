import { h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { AnalyticsClient } from './analytics-client.js'
import { barChart, chartColors, donutChart } from './charts.js'

const labels = { expected_count: '应交人卷次', submitted_count: '已交人卷次', missing_count: '缺交人卷次',
  graded_count: '已批人卷次', partial_count: '待批人卷次', mean_score: '同卷平均分', mean_percentage: '平均百分比',
  answered_count: '实际客观作答次数', correct_count: '正确次数', mastery: '掌握度', completed_knowledge_count: '本人完成知识点',
  published_knowledge_count: '当前发布知识点', progress: '本人完成进度',
  student_count: '有效成绩学生', submission_count: '提交数', effective_count: '有效成绩数', accepted_count: '通过（accepted）',
  pass_rate: '教学通过率', run_count: 'run 总数', system_error_count: '系统错误 run', timeout_count: '超时 run',
  resource_limit_count: '超限额 run' }
// SPEC-010A：考勤与学习表现自己的指标集，避免与分类成绩的"人卷次"口径混淆。
const attendanceLabels = {
  expected_count: '应到人次（冻结名单）',
  present_count: '出勤',
  late_count: '迟到',
  leave_count: '请假',
  absent_count: '缺勤',
  attendance_rate: '到勤率（出勤+迟到）',
  performance_mean_percentage: '平均成绩百分比',
  performance_correlation: '考勤-成绩相关系数',
  candidate_count: '纳入统计学生',
  paired_count: '有效配对人数',
  missing_performance_count: '缺成绩人数',
}
const correlationNotes = {
  ok: '',
  insufficient_pairs: '有效配对不足 3 人，按 C02 返回无相关系数。',
  zero_variance: '到勤率或成绩没有变化（方差为零），按 C03 相关系数无定义。',
  personal_scope: '当前是学生个人范围，按 AC-05 不计算班级相关性。',
}
const ratio = value => value === null || value === undefined ? '无数据' : `${(value * 100).toFixed(2)}%`
const shown = (key, value) => ['mastery', 'progress', 'pass_rate', 'attendance_rate'].includes(key) ? ratio(value) : value === null || value === undefined
  ? '无数据' : ['mean_score', 'mean_percentage', 'performance_mean_percentage'].includes(key) ? `${Number(value).toFixed(2)}%` : String(value)
const shanghaiFormat = new globalThis.Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
const shanghaiTime = value => {
  const date = new Date(value)
  return value && Number.isFinite(date.getTime()) ? shanghaiFormat.format(date) : '无时间记录'
}

const chartNode = node => {
  if (node.kind === 'line') return h('line', { x1: node.x1, y1: node.y1, x2: node.x2, y2: node.y2, stroke: node.stroke })
  if (node.kind === 'path') return h('path', {
    d: node.d, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width ?? 1,
    'stroke-linejoin': node['stroke-linejoin'],
    class: node.draw ? 'chart-line' : undefined,
    pathLength: node.draw ? 1 : undefined,
  })
  if (node.kind === 'bar') return h('rect', {
    x: node.x, y: node.y, width: node.width, height: node.height, fill: node.fill, rx: 3,
    class: 'chart-bar', style: `animation-delay:${(node.delay ?? 0) * 70}ms`,
  })
  if (node.kind === 'dot') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width,
    class: 'chart-dot', style: `animation-delay:${560 + (node.delay ?? 0) * 70}ms`,
  })
  if (node.kind === 'arc') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: 'none', stroke: node.color,
    'stroke-width': node.thickness, 'stroke-dasharray': node.dash, 'stroke-dashoffset': node.offset,
    transform: `rotate(-90 ${node.cx} ${node.cy})`, class: 'chart-arc',
  }, [h('title', {}, node.title)])
  if (node.kind === 'rect') return h('rect', {
    x: node.x, y: node.y, width: node.width, height: node.height, fill: node.fill,
  })
  if (node.kind === 'circle') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width,
  })
  return h('text', {
    x: node.x, y: node.y, 'font-size': node.size, fill: node.fill,
    'text-anchor': node.anchor, 'font-weight': node.bold ? 700 : 400,
  }, node.text)
}

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
      if (!['knowledge', 'scores', 'grading', 'attendance'].includes(value.dimension)) throw new Error('请恢复知识、分类成绩、考勤或电路评测快照。')
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
    const input = (label, value, update, type = 'text') => h('label', [label, h('input', { 'aria-label': label, type, value, disabled: !courses.value.length,
      onInput: event => { forget(); update(event.target.value) } })])
    const select = (label, value, update, options) => h('label', [label, h('select', { 'aria-label': label, value, disabled: !courses.value.length,
      onChange: event => { forget(); update(event.target.value) } }, options.map(([id, text]) => h('option', { value: id }, text)))])
    const table = (caption, headings, rows) => h('div', { class: 'analytics-scroll', tabindex: 0, role: 'region', 'aria-label': caption }, [h('table', [h('caption', caption),
      h('thead', [h('tr', headings.map(label => h('th', { scope: 'col' }, label)))]),
      h('tbody', rows.map(row => h('tr', row.map(text => h('td', String(text))))))])])
    const bins = (m, unit, total) => h('div', [h('h4', '有效成绩分数分布'), ...m.score_bins.map(bin => h('div', { class: 'analytics-bin' }, [
      h('span', bin.label), h('meter', { min: 0, max: Math.max(1, total), value: bin.count, 'aria-label': `${bin.label} ${bin.count} ${unit}` }),
      h('span', `${bin.count} ${unit}`)]))])
    function gradingReport(m) {
      return h('div', [
        bins(m, '个有效成绩', m.effective_count),
        h('p', `实际实验版本：${m.selected_version_ids.join('、') || '无'}`),
        m.suites.length ? table('按测试集分组的教学分布与运行可靠性（故障 run 不进教学分母）',
          ['测试集', '学生', '提交', '有效成绩', '通过', '通过率', '均分', 'run 总数', '系统错误', '超时', '限额'],
          m.suites.map(s => [`#${s.suite_id}`, s.student_count, s.submission_count, s.effective_count, s.accepted_count,
            ratio(s.pass_rate), shown('mean_score', s.mean_score), s.run_count, s.system_error_count, s.timeout_count,
            s.resource_limit_count]))
          : h('p', { role: 'status' }, '本区间没有可归组的测试集运行记录。'),
      ])
    }
    function attendanceReport(m, value) {
      const reason = correlationNotes[m.correlation_reason] ?? ''
      const donut = donutChart([
        { label: '出勤', value: m.present_count, color: chartColors.present },
        { label: '迟到', value: m.late_count, color: chartColors.late },
        { label: '请假', value: m.leave_count, color: chartColors.leave },
        { label: '缺勤', value: m.absent_count, color: chartColors.absent },
      ], { size: 176, thickness: 22 })
      const chart = barChart((value.series ?? []).map(period => ({
        label: shanghaiTime(period.period_start).slice(5, 10),
        expected: period.metrics?.expected_count ?? 0,
        present: (period.metrics?.present_count ?? 0) + (period.metrics?.late_count ?? 0),
      })))
      // APIC：个人范围 candidate_count/paired_count/missing_performance_count 均为 null，只输出本人指标。
      const personal = m.candidate_count === null || m.candidate_count === undefined
      const pairing = personal
        ? '配对口径：当前是个人范围，只输出本人到勤与成绩，不计算班级配对与相关性。'
        : `配对口径：班级 ${m.candidate_count} 名学生中，${m.paired_count ?? 0} 人有已评分成绩参与相关分析，`
          + `${m.missing_performance_count ?? 0} 人因缺成绩被排除（C04：个人被排除，但班级到勤分母不丢）。`
      return h('div', [
        h('p', pairing),
        h('p', m.performance_correlation === null || m.performance_correlation === undefined
          ? '考勤-成绩相关系数：无数据'
          : `考勤-成绩相关系数 r = ${Number(m.performance_correlation).toFixed(6)}（仅描述关联，不代表因果，不自动扣分）`),
        reason && h('p', { class: 'analytics-note' }, reason),
        h('div', { class: 'chart-box chart-donut-wrap' }, donut.empty
          ? h('p', { class: 'chart-empty' }, '本区间没有考勤记录，无法统计状态构成。')
          : [
            h('figure', {}, [
              h('svg', {
                viewBox: `0 0 ${donut.size} ${donut.size}`,
                width: donut.size, height: donut.size,
                role: 'img', 'aria-label': '考勤状态构成环形图',
              }, [h('g', { class: 'chart-donut' }, donut.nodes.map(chartNode))]),
              h('div', { class: 'chart-center' }, [
                h('strong', {}, String(donut.total)),
                h('span', {}, '人次'),
              ]),
            ]),
            h('ul', { class: 'chart-legend' }, donut.rows.map(row => h('li', {}, [
              h('i', { style: `background:${row.color}` }),
              h('b', {}, String(row.value)),
              h('small', {}, `${row.label} · ${row.percent}%`),
            ]))),
          ]),
        h('div', { class: 'chart-box' }, chart.empty
          ? h('p', { class: 'chart-empty' }, '本区间内没有已关闭的考勤任务，趋势图暂无数据。')
          : h('figure', { class: 'chart-figure' }, [
            h('figcaption', {}, '按周应到 / 到勤人次（深色为到勤，含迟到）'),
            h('svg', {
              viewBox: `0 0 ${chart.width} ${chart.height}`,
              width: '100%',
              style: `max-width:${chart.width}px;height:auto;display:block`,
              role: 'img',
              'aria-label': '按周到勤率折线图',
            }, chart.nodes.map(chartNode)),
            h('p', { class: 'chart-legend' }, [
              h('span', {}, [h('i', { style: 'background:#dbe6f5' }), '应到人次']),
              h('span', {}, [h('i', { style: 'background:#173b6c' }), '到勤人次']),
            ]),
          ])),
      ])
    }
    function report() {
      const value = data.value, m = value.metrics
      const attendance = value.dimension === 'attendance'
      const labelSet = attendance ? attendanceLabels : labels
      const keys = Object.keys(labelSet).filter(key => Object.hasOwn(m, key))
      // 考勤周趋势只带 6 个核心列，否则 11 列要横向拖。
      const seriesKeys = attendance
        ? ['expected_count', 'present_count', 'late_count', 'leave_count', 'absent_count', 'attendance_rate']
        : keys
      const title = attendance ? '考勤与学习表现（010A）'
        : value.dimension === 'knowledge' ? '知识分析'
          : value.dimension === 'grading' ? '电路评测分析' : `分类成绩 / ${m.kind}`
      const basis = attendance ? '按已关闭考勤任务的冻结参与人统计，出勤含迟到；成绩只取已评分试卷'
        : value.dimension === 'knowledge' ? '按实际客观作答去重；进度取原查询时的发布集合'
          : value.dimension === 'grading' ? '按实验版本开始时间选任务；每名学生每个版本取最新一次有效成绩，运行可靠性另计'
            : '按试卷开始时间选任务；应交取冻结名单，均分只计已批卷'
      return h('article', { class: 'analytics-report' }, [h('h3', `原快照 #${value.analysis_run_id} · ${title}`),
        h('p', `数据截止 ${shanghaiTime(value.source_until)} · 生成 ${shanghaiTime(value.generated_at)}（Asia/Shanghai） · 算法 ${value.algorithm_version}`),
        h('p', value.filters ? `原筛选 ${shanghaiTime(value.filters.from)} 至 ${shanghaiTime(value.filters.to)}（Asia/Shanghai） · ${value.filters.student_id ? `学生 #${value.filters.student_id}` : '全班'}${value.filters.paper_id ? ` · 试卷 #${value.filters.paper_id}` : ''}` : '历史快照未记录可展示的筛选摘要；以下为原保存结果。'),
        h('p', `有效样本 ${value.sample_size} · ${basis}`),
        ...value.warnings.map(w => h('p', w)),
        m.selected_paper_ids && h('p', `实际试卷：${m.selected_paper_ids.join('、') || '无'}`),
        value.sample_size === 0 && h('p', { role: 'status' }, attendance
          ? '本区间没有已关闭的考勤任务或没有冻结参与人，全部指标显示无数据。'
          : '无有效样本，均分或掌握度显示无数据。'),
        h('div', { class: 'analytics-metrics' }, keys.map(key => h('div', { class: 'metric-tile' }, [
          h('span', { class: 'metric-label' }, labelSet[key]),
          h('strong', { class: ['metric-value', shown(key, m[key]) === '无数据' ? 'empty' : ''] }, shown(key, m[key])),
        ]))),
        value.dimension === 'scores' && m.mean_score === null && m.selected_paper_ids.length > 1 && h('p', '跨卷原始平均分不适用，请查看平均百分比。'),
        value.dimension === 'knowledge' ? table('知识点掌握度与错题分布（多标签分别计入，总体按实际作答去重）',
          ['知识点', '作答', '正确', '错题', '掌握度'], m.items.map(item => [`#${item.knowledge_id} ${item.title}`, item.answered_count, item.correct_count, item.wrong_count, ratio(item.mastery)]))
          : value.dimension === 'grading' ? gradingReport(m)
            : attendance ? attendanceReport(m, value) : bins(m, '人卷次', m.graded_count),
        table('按上海周一划分的周趋势', ['区间（左闭右开，Asia/Shanghai）', ...seriesKeys.map(key => labelSet[key])], value.series.map(p => [
          `${shanghaiTime(p.period_start)} — ${shanghaiTime(p.period_end)}`, ...seriesKeys.map(key => shown(key, p.metrics[key]))])),
        props.user.role === 'teacher' && button('导出当前快照 CSV', download),
      ])
    }
    return () => props.user.role === 'admin' ? null : h('section', { class: 'card analytics-bank', 'aria-busy': busy.value }, [
      h('h2', '知识与成绩分析'), h('p', '查询保存本次结果。刷新页面恢复上次快照；重新查询才会更新统计。日期按本机时区输入，最多366天；留空为最近28天。'),
      h('div', { class: 'analytics-filters' }, [
        select('统计课程', course.value, v => { course.value = v; runId.value = '' }, courses.value.map(c => [String(c.id), c.title])),
        select('统计维度', filters.dimension, v => { filters.dimension = v }, [['knowledge', '知识掌握度、错题与进度'], ['attendance', '考勤与学习表现（010A）'], ['scores', '分类成绩'], ['grading', '电路评测通过率与运行可靠性']]),
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
