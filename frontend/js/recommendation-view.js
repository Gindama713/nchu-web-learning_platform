import { h, onMounted, onUnmounted, ref, watch } from 'vue'
import { RecommendationClient, recommendationReasons, recommendationStates } from './recommendation-client.js'

// Recommendation presentation only; source_until remains the original UTC cutoff.
const sourceClock = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
function sourceTime(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return '时间异常'
  const date = new Date(value)
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  if (!Number.isFinite(date.getTime()) || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) return '时间异常'
  const parts = Object.fromEntries(sourceClock.formatToParts(date).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} (Asia/Shanghai)`
}

export const RecommendationView = {
  props: { user: { type: Object, required: true } },
  emits: ['practice'],
  setup(props, { emit }) {
    let api = new RecommendationClient(props.user), epoch = 0, entrySequence = 0
    const courses = ref([]), course = ref(''), limit = ref(5), data = ref(null), detail = ref(null)
    const busy = ref(false), error = ref('')
    function clear() { data.value = null; detail.value = null }
    async function run(action, reset = true) {
      const ticket = ++epoch
      busy.value = true; error.value = ''; detail.value = null
      if (reset) clear()
      try {
        await api.verifySession()
        if (ticket !== epoch || props.user.role !== 'student') return
        await action(ticket)
      } catch (failure) {
        if (ticket !== epoch) return
        clear(); error.value = `${failure.message} 可重试推荐，仍可在练习区正常作答。`
        if ([401, 403, 404].includes(failure.status)) { courses.value = []; course.value = '' }
      } finally { if (ticket === epoch) busy.value = false }
    }
    async function load(ticket) {
      if (!course.value) return
      const result = await api.recommendations(course.value, limit.value)
      await api.verifySession()
      if (ticket === epoch) data.value = result
    }
    async function boot(ticket) {
      courses.value = []
      const available = await api.courses()
      if (ticket !== epoch) return
      courses.value = available
      if (!available.some(row => String(row.id) === course.value)) course.value = available.length ? String(available[0].id) : ''
      await load(ticket)
    }
    function open(item) {
      run(async ticket => {
        // Refresh eligibility before resolving the existing 005 source.
        const current = await api.recommendations(course.value, limit.value)
        if (ticket !== epoch) return
        data.value = current
        if (!current.items.some(row => row.knowledge_id === item.knowledge_id)) throw new Error('该知识已不在当前推荐中，请选择当前结果。')
        const point = await api.knowledgeDetail(item.knowledge_id)
        await api.verifySession()
        if (ticket === epoch) detail.value = point
      }, false)
    }
    function practice(item) {
      run(async ticket => {
        const current = await api.recommendations(course.value, limit.value)
        await api.verifySession()
        if (ticket !== epoch) return
        data.value = current
        const row = current.items.find(row => row.knowledge_id === item.knowledge_id)
        if (!row?.question_version_id || row.question_version_id !== item.question_version_id) throw new Error('练习入口已变化，请刷新后选择当前入口。')
        emit('practice', { courseId: course.value, knowledgeId: row.knowledge_id, versionId: row.question_version_id, nonce: ++entrySequence })
        // The independent practice component owns submission and exact retry.
      }, false)
    }
    watch(() => `${props.user.id}:${props.user.role}`, () => {
      epoch++; clear(); courses.value = []; course.value = ''; error.value = ''; busy.value = false
      api = new RecommendationClient(props.user)
      if (props.user.role === 'student') run(boot)
    })
    onMounted(() => { if (props.user.role === 'student') run(boot) })
    onUnmounted(() => { epoch++ })
    const button = (text, action, disabled = false) => h('button', { type: 'button', disabled: busy.value || disabled, onClick: action }, text)
    return () => props.user.role !== 'student' ? null : h('section', { class: 'recommendation-bank card', 'aria-busy': busy.value }, [
      h('h2', '个人学习推荐'), h('p', '依据最近28天本人实际客观作答与当前完成状态。自报完成不代表掌握；多标签分别计入知识点样本。'),
      h('div', { class: 'actions' }, [
        h('label', ['推荐课程', h('select', { 'aria-label': '推荐课程', value: course.value,
          onChange: e => { course.value = e.target.value; run(load) } }, courses.value.map(row => h('option', { value: String(row.id) }, row.title)))]),
        h('label', ['推荐数量', h('input', { 'aria-label': '推荐数量', type: 'number', min: 1, max: 20, step: 1, value: limit.value,
          onInput: e => { limit.value = e.target.value; epoch++; clear(); busy.value = false } })]),
        button('刷新推荐', () => run(boot)),
      ]),
      busy.value && h('p', { role: 'status' }, '正在读取当前学习记录…'),
      error.value && h('p', { role: 'alert' }, error.value),
      !courses.value.length && !busy.value && !error.value && h('p', '暂无可访问的课程，请联系教师确认课程成员。'),
      data.value && h('div', { class: 'recommendation-result' }, [
        h('p', { role: 'status' }, recommendationStates[data.value.reason]),
        h('p', { class: 'recommendation-meta' }, `依据截止 ${sourceTime(data.value.source_until)} · 算法 ${data.value.algorithm_version}`),
        h('p', '推荐分数仅用于排序，范围0—1；掌握度来自有效客观作答。'),
        h('ol', { class: 'rows' }, data.value.items.map(item => h('li', { key: item.knowledge_id }, [
          h('h3', `知识点 #${item.knowledge_id}`), h('p', recommendationReasons[item.reason]),
          h('p', `排序分数 ${Number(item.score).toFixed(6)} · 样本 ${item.sample_size} 次 · 掌握度 ${item.mastery === null ? '暂无样本' : (item.mastery * 100).toFixed(2) + '%'}`),
          h('p', `出处：${courses.value.find(row => String(row.id) === course.value)?.title ?? ''} / 知识点 #${item.knowledge_id}`),
          button(`阅读知识 #${item.knowledge_id}`, () => open(item)),
          item.question_version_id ? button(`去练习 · 版本 #${item.question_version_id}`, () => practice(item)) : h('p', '暂无合格的开放客观练习，可先阅读知识。'),
        ]))),
      ]),
      detail.value && h('article', { class: 'recommendation-source' }, [
        h('h3', detail.value.title), h('p', `知识 #${detail.value.id} · 章节 #${detail.value.chapter_id} · 内容修订 ${detail.value.content_revision}`),
        h('div', { class: 'knowledge-prose', innerHTML: detail.value.content }),
        detail.value.example && h('div', [h('h4', '例题'), h('div', { class: 'knowledge-prose', innerHTML: detail.value.example })]),
      ]),
    ])
  },
}
