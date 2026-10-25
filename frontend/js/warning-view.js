// SPEC-014 学习预警：规则证据 + 班级相对聚类（样本不足时降级），只提示不改成绩。
import { h, onMounted, ref } from 'vue'
import { WarningClient } from './warning-client.js'

const REASONS = {
  LOW_OBJECTIVE_RATE: { title: '客观题正确率偏低', level: 'high' },
  RECENT_ATTENDANCE: { title: '考勤连续异常', level: 'mid' },
  RELATIVE_WEAK_CLUSTER: { title: '班级相对偏弱（KMeans 聚类）', level: 'low' },
}
const ATTENDANCE_TEXT = { late: '迟到', absent: '缺勤', present: '出勤', leave: '请假' }
const LEVEL_TEXT = { high: '高', mid: '中', low: '参考' }
const MODEL_TEXT = {
  clustered: { text: '已聚类', tone: 'ok' },
  insufficient_data: { text: '样本不足，仅规则提示', tone: 'warn' },
  no_run: { text: '尚未生成批次', tone: 'idle' },
}

const percent = value => `${(Number(value) * 100).toFixed(1)}%`

function reasonText(reason) {
  switch (reason.code) {
  case 'LOW_OBJECTIVE_RATE':
    return `正确率 ${percent(reason.value)}（样本 ${reason.sample_size ?? 0} 道客观题，阈值 60%）`
  case 'RECENT_ATTENDANCE':
    return `最近两次考勤：${(reason.statuses ?? []).map(status => ATTENDANCE_TEXT[status] ?? status).join('、')}`
  case 'RELATIVE_WEAK_CLUSTER': {
    const center = Array.isArray(reason.center) ? reason.center : []
    const features = center.length === 3
      ? `；弱簇中心 正确率 ${percent(center[0])} / 实验完成 ${percent(center[1])} / 到勤 ${percent(center[2])}`
      : ''
    return `聚类 #${reason.cluster}，样本 ${reason.sample_size ?? 0} 人${features}`
  }
  default:
    return JSON.stringify(reason)
  }
}

export const WarningView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new WarningClient(props.user.id)
    const courses = ref([])
    const courseId = ref('')
    const items = ref([])
    const total = ref(0)
    const runId = ref(null)
    const modelStatus = ref('no_run')
    const people = ref(new Map())
    const filter = ref('')
    const editing = ref(null)
    const note = ref('')
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')

    const nameOf = id => people.value.get(id)?.name ?? `学生 #${id}`
    const noOf = id => people.value.get(id)?.student_no ?? ''

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.status === 401) courses.value = []
      } finally { busy.value = false }
    }

    async function loadPeople() {
      people.value = new Map()
      if (!courseId.value) return
      const list = await api.members(courseId.value)
      people.value = new Map(list.map(person => [person.user_id, person]))
    }

    async function loadWarnings() {
      items.value = []; total.value = 0
      if (!courseId.value) { runId.value = null; modelStatus.value = 'no_run'; return }
      const content = await api.warnings(courseId.value, { status: filter.value })
      items.value = content.data
      total.value = content.total
      runId.value = content.analysis_run_id ?? null
      modelStatus.value = content.model_status ?? 'no_run'
    }

    async function bindCourse() {
      editing.value = null; note.value = ''
      await loadPeople()
      await loadWarnings()
    }

    async function generate() {
      const created = await api.createRun(courseId.value)
      await loadWarnings()
      return created
    }

    function begin(id) {
      editing.value = editing.value === id ? null : id
      note.value = ''
    }

    async function confirmHandle(id) {
      const text = note.value.trim()
      if (!text) throw new Error('请填写处理记录，会写入预警历史。')
      await api.handle(id, text)
      editing.value = null
      await loadWarnings()
    }

    async function boot() {
      courses.value = []
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await bindCourse()
    }

    onMounted(() => { boot().catch(failure => { error.value = failure.message }) })

    function distribution() {
      const counts = new Map()
      items.value.forEach(item => (item.reasons ?? []).forEach(reason => {
        counts.set(reason.code, (counts.get(reason.code) ?? 0) + 1)
      }))
      const rows = [...counts.entries()]
        .map(([code, count]) => ({ code, count, title: REASONS[code]?.title ?? code, level: REASONS[code]?.level ?? 'low' }))
        .sort((left, right) => right.count - left.count)
      return { rows, max: Math.max(1, ...rows.map(row => row.count)) }
    }

    function card(item) {
      const open = item.status === 'open'
      const student = nameOf(item.student_id)
      const isEditing = editing.value === item.id
      return h('li', { key: item.id, class: ['warn-item', open ? 'open' : 'handled'] }, [
        h('div', { class: 'warn-head' }, [
          h('span', { class: 'warn-avatar' }, (noOf(item.student_id) || String(item.student_id)).slice(-2)),
          h('div', { class: 'warn-who' }, [
            h('strong', {}, student),
            h('small', {}, noOf(item.student_id) || '—'),
          ]),
          h('span', { class: ['warn-badge', open ? 'open' : 'handled'] }, open ? '未处理' : '已处理'),
          h('span', { class: 'warn-sample' }, `最大样本 ${item.sample_size ?? 0}`),
        ]),
        h('ul', { class: 'warn-reasons' }, item.reasons.map(reason => {
          const meta = REASONS[reason.code] ?? { title: reason.code, level: 'low' }
          return h('li', { class: `warn-reason ${meta.level}` }, [
            h('span', { class: 'warn-level' }, LEVEL_TEXT[meta.level]),
            h('span', {}, meta.title),
            h('em', {}, reasonText(reason)),
          ])
        })),
        isEditing
          ? h('div', { class: 'warn-editor' }, [
            h('label', {}, ['处理记录', h('input', {
              value: note.value, 'aria-label': '处理记录', maxlength: 500,
              placeholder: '例如：已单独联系，安排补练（1—500 字）',
              onInput: event => { note.value = event.target.value },
            })]),
            h('button', { type: 'button', disabled: busy.value, onClick: () => run(() => confirmHandle(item.id), '已记录处理') }, '确认'),
            h('button', { type: 'button', class: 'secondary', onClick: () => { editing.value = null } }, '取消'),
          ])
          : open && h('div', { class: 'warn-actions' }, [
            h('button', { type: 'button', class: 'secondary', onClick: () => begin(item.id) }, '标记处理'),
          ]),
      ])
    }

    return () => {
      const model = MODEL_TEXT[modelStatus.value] ?? MODEL_TEXT.no_run
      const pending = items.value.filter(item => item.status === 'open').length
      const handled = items.value.length - pending
      return h('section', { class: 'card warn-card' }, [
        h('h2', {}, '学习预警'),
        h('p', {}, '证据来自真实客观作答、最近两次考勤与班级相对聚类。预警只用于提示教师，不写处分、不改成绩。'
        + '聚类需至少 10 名三项分母齐全且客观作答 ≥5 的学生、至少 2 种不同特征行，否则降级为 insufficient_data，只输出有证据的规则提示。'),

        h('div', { class: 'inline-form' }, [
          h('label', {}, ['课程', h('select', {
            value: courseId.value,
            onChange: event => { courseId.value = event.target.value; run(bindCourse) },
          }, courses.value.map(course => h('option', { value: String(course.id) }, course.title ?? `课程 ${course.id}`)))]),
          h('label', {}, ['只看', h('select', {
            value: filter.value,
            onChange: event => { filter.value = event.target.value; run(loadWarnings) },
          }, [['', '全部'], ['open', '未处理'], ['handled', '已处理']].map(([value, label]) => h('option', { value }, label)))]),
          h('button', { type: 'button', disabled: busy.value || !courseId.value, onClick: () => run(generate) },
            busy.value ? '生成中…' : '生成预警批次'),
        ]),

        error.value && h('p', { class: 'warn-alert', role: 'alert' }, error.value),
        notice.value && h('p', { class: 'warn-notice', role: 'status' }, notice.value),

        h('div', { class: 'warn-strip' }, [
          h('span', { class: `warn-model ${model.tone}` }, model.text),
          runId.value && h('span', {}, `批次 #${runId.value}`),
          h('span', {}, `共 ${total.value} 条`),
          h('span', { class: 'warn-pending' }, `未处理 ${pending}`),
          h('span', {}, `已处理 ${handled}`),
        ]),

        modelStatus.value === 'no_run'
          ? h('p', { class: 'warn-empty' }, '还没有预警批次。先点「生成预警批次」，系统会按最近的考勤与作答事实算一次。')
          : items.value.length
            ? h('div', {}, [
              // 原因分布：一眼看出这批预警主要是哪类问题
              h('div', { class: 'warn-chart' }, [
                h('p', { class: 'warn-chart-title' }, `预警原因分布（${items.value.length} 条预警）`),
                ...distribution().rows.map(row => h('div', { class: 'warn-bar-row' }, [
                  h('span', { class: 'warn-bar-label' }, row.title),
                  h('div', { class: 'warn-bar-track' }, [
                    h('i', {
                      class: `warn-bar-fill ${row.level}`,
                      style: `width:${Math.round((row.count / distribution().max) * 100)}%`,
                    }),
                  ]),
                  h('span', { class: 'warn-bar-value' }, String(row.count)),
                ])),
              ]),
              h('ul', { class: 'warn-list' }, items.value.map(card)),
            ])
            : h('p', { class: 'warn-empty' }, '当前筛选下没有预警记录。'),
      ])
    }
  },
}
