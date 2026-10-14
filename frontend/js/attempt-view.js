import { h, onMounted, onUnmounted, ref, watch } from 'vue'
import { AttemptClient, answerPayload, scorePayload } from './attempt-client.js'
import { questionTypes } from './question-client.js'

const statusNames = { partial: '待人工评分', graded: '已评分' }
const gradeNames = { unanswered: '未作答 · 0分', pending: '待人工评分', graded: '已评分' }
const showValue = value => value === null ? '未作答' : typeof value === 'boolean' ? (value ? '正确' : '错误')
  : Array.isArray(value) ? value.join('、') : String(value)

export const AttemptView = {
  props: { user: { type: Object, required: true }, paper: { type: Object, default: null },
    courseId: { type: String, default: '' } },
  setup(props) {
    let api = new AttemptClient(props.user), epoch = 0
    const teacher = () => props.user.role === 'teacher'
    const courses = ref([]), course = ref(props.courseId), papers = ref([]), paperFilter = ref(''), status = ref('')
    const rows = ref([]), page = ref(1), total = ref(0), selected = ref(null), selectedPaper = ref(props.paper)
    const values = ref({}), drafts = ref([]), pending = ref(null), confirmed = ref(false), conflict = ref(false)
    const busy = ref(false), error = ref(''), notice = ref('')
    const loaded = ref(false)
    const clock = ref(Date.now())
    let timer

    function reset() {
      rows.value = []; total.value = 0; selected.value = null; selectedPaper.value = props.paper
      values.value = {}; drafts.value = []; pending.value = null; confirmed.value = false; conflict.value = false
      loaded.value = false
    }
    async function run(action, writing = false) {
      if (busy.value) return
      const ticket = epoch
      busy.value = true; error.value = ''; notice.value = ''
      try {
        await api.verifySession()
        if (ticket === epoch) await action(ticket)
      } catch (failure) {
        if (ticket !== epoch) return
        error.value = failure.message
        if (!writing) reset()
        if ([401, 403, 404].includes(failure.status)) {
          reset(); selectedPaper.value = null; courses.value = []; papers.value = []; course.value = ''
        }
        if (failure.code === 'REVISION_CONFLICT') conflict.value = true
        if (failure.code === 'ALREADY_SUBMITTED') {
          pending.value = null; confirmed.value = false
          error.value = '这份卷已提交，请重新加载答卷查看结果。'
        }
      } finally { if (ticket === epoch) busy.value = false }
    }
    function setAttempt(item, paper) {
      selected.value = item; selectedPaper.value = paper; conflict.value = false
      const byVersion = new Map((paper.items ?? []).map(q => [q.question_version_id, q]))
      drafts.value = item.answers.filter(a => a.answered && byVersion.get(a.question_version_id)?.type === 'short')
        .map(a => ({ question_version_id: a.question_version_id, max_score: a.max_score,
          score: a.score === null ? '' : String(a.score), comment: a.comment, include: false }))
    }
    async function open(id, ticket) {
      selected.value = null; drafts.value = []; conflict.value = false
      const item = await api.detail(id)
      if (ticket !== epoch) return
      const paper = props.paper ?? await api.paper(item.paper_id)
      if (ticket === epoch) setAttempt(item, paper)
    }
    async function load(ticket) {
      if (!course.value) return
      rows.value = []; total.value = 0; selected.value = null; drafts.value = []; conflict.value = false
      loaded.value = false
      const result = await api.list(course.value, { page: page.value, paperId: props.paper?.id ?? paperFilter.value, status: status.value })
      if (ticket !== epoch) return
      rows.value = result.data; total.value = result.total
      loaded.value = true
      if (props.paper && !teacher() && result.data.length) await open(result.data[0].id, ticket)
    }
    async function boot(ticket) {
      reset(); papers.value = []
      if (!props.paper) {
        const available = await api.courses()
        if (ticket !== epoch) return
        courses.value = available
        if (!available.some(c => String(c.id) === course.value)) course.value = available.length ? String(available[0].id) : ''
        if (course.value) {
          const result = await api.papers(course.value)
          if (ticket !== epoch) return
          papers.value = result
        }
      }
      await load(ticket)
    }
    async function send(ticket) {
      if (!confirmed.value) throw new Error('请先确认提交；漏答得0分，每人每卷只能提交一次。')
      if (!pending.value) pending.value = { payload: answerPayload(props.paper.items, values.value), key: crypto.randomUUID() }
      const submitted = await api.submit(props.paper.id, pending.value.payload, pending.value.key, props.paper.kind === 'quiz')
      if (ticket !== epoch) return
      pending.value = null; confirmed.value = false
      setAttempt(submitted, props.paper)
      // Acceptance may replay an old snapshot; latest results always use GET.
      const latest = await api.detail(submitted.id)
      if (ticket !== epoch) return
      setAttempt(latest, props.paper); total.value = 1; rows.value = [latest]
      notice.value = '交卷成功。可从答卷历史重新查看最新评分。'
    }
    async function grade(ticket) {
      const payload = scorePayload(selected.value.revision, drafts.value)
      const item = await api.grade(selected.value.id, payload)
      if (ticket !== epoch) return
      setAttempt(item, selectedPaper.value)
      rows.value = rows.value.map(row => row.id === item.id ? item : row)
      notice.value = '批阅已保存。学生可查看最新评分。'
    }
    watch(() => `${props.user.id}:${props.user.role}:${props.courseId}:${props.paper?.id ?? ''}`, () => {
      epoch++; busy.value = false; reset(); courses.value = []; papers.value = []; course.value = props.courseId
      api = new AttemptClient(props.user); run(boot)
    })
    onMounted(() => {
      run(boot)
      if (props.paper?.kind === 'quiz') timer = globalThis.setInterval(() => { clock.value = Date.now() }, 1000)
    })
    onUnmounted(() => { epoch++; globalThis.clearInterval(timer) })

    const button = (text, action, disabled = false) => h('button', { type: 'button', disabled: busy.value || disabled, onClick: action }, text)
    const field = (text, node) => h('label', [h('span', text), node])
    const input = (label, value, update, extra = {}) => h('input', { 'aria-label': label, value,
      disabled: busy.value, onInput: e => update(e.target.value), ...extra })
    const check = (label, checked, update, disabled = false) => h('label', { class: 'attempt-check' }, [
      h('input', { type: 'checkbox', 'aria-label': label, checked, disabled: busy.value || disabled,
        onChange: e => update(e.target.checked) }), label])
    const select = (label, value, update, options) => field(label, h('select', { 'aria-label': label, value,
      disabled: busy.value, onChange: e => update(e.target.value) }, options.map(([id, text]) => h('option', { value: id }, text))))
    const submit = (text, disabled = false) => h('button', { type: 'submit', disabled: busy.value || disabled }, text)

    function answerInput(q) {
      const id = q.question_version_id, label = `第 ${q.position} 题作答`
      const disabled = busy.value || !!pending.value
      if (q.type === 'single' || q.type === 'boolean') {
        const options = q.type === 'boolean' ? [{ key: true, text: '正确' }, { key: false, text: '错误' }] : q.options
        return h('div', { class: 'attempt-options' }, options.map(option => h('label', [h('input', {
          type: 'radio', name: `answer-${id}`, 'aria-label': `${label} ${option.text}`,
          checked: values.value[id] === option.key, disabled, onChange: () => { values.value[id] = option.key },
        }), option.text])), button('清空本题', () => { values.value[id] = null }, !!pending.value))
      }
      if (q.type === 'multiple') return h('div', { class: 'attempt-options' }, q.options.map(option => check(
        `${label} ${option.text}`, (values.value[id] ?? []).includes(option.key), checked => {
          const keys = new Set(values.value[id] ?? [])
          if (checked) keys.add(option.key); else keys.delete(option.key)
          values.value[id] = [...keys]
        }, !!pending.value)))
      if (q.type === 'short') return h('textarea', { 'aria-label': label, value: values.value[id] ?? '', rows: 4,
        maxlength: 5000, disabled, onInput: e => { values.value[id] = e.target.value } })
      return input(label, values.value[id] ?? '', value => { values.value[id] = value }, { type: 'number', step: 'any', disabled })
    }
    function answerForm() {
      const remaining = Math.max(0, Math.ceil((Date.parse(props.paper.end_at) - clock.value) / 1000))
      return h('form', { class: 'attempt-answer-form', onSubmit: e => { e.preventDefault(); run(send, true) } }, [
        h('h4', '填写答卷'), h('p', '漏答得0分；已作答简答等待教师评分。提交后不能修改。'),
        props.paper.kind === 'quiz' && h('p', { class: 'quiz-time' },
          `截止：${props.paper.end_at} · 本机估计剩余 ${Math.floor(remaining / 60)} 分 ${remaining % 60} 秒。收卷以服务器时间为准。`),
        h('ol', { class: 'attempt-questions' }, props.paper.items.map(q => h('li', { key: q.question_version_id }, [
          h('p', `第 ${q.position} 题 · ${questionTypes[q.type]} · ${q.points} 分`),
          h('p', { class: 'attempt-text' }, q.stem), answerInput(q),
        ]))),
        pending.value && h('p', { role: 'status' }, '提交结果尚未确认，重试会发送同一份答卷。也可重新加载答卷查看是否已提交。'),
        check('确认交卷，接受漏答0分且提交后不可修改', confirmed.value, value => { confirmed.value = value }, !!pending.value),
        submit(pending.value ? '重试原交卷' : '提交整份答卷', !confirmed.value),
      ])
    }
    function resultView() {
      const item = selected.value
      const questions = new Map((selectedPaper.value.items ?? []).map(q => [q.question_version_id, q]))
      return h('article', { class: 'attempt-result' }, [
        h('h4', `${selectedPaper.value.title} · 答卷 #${item.id}`),
        h('div', { class: 'attempt-summary', role: 'status' }, [h('strong', statusNames[item.status]),
          h('span', `总分：${item.score === null ? '待全部批阅' : item.score} / ${item.total_points}`),
          h('span', `已定分：${item.partial_score}`)]),
        h('p', `提交时间：${item.submitted_at}${teacher() ? ` · 学生 #${item.student_id}` : ''}`),
        button('重新加载此答卷', () => run(ticket => open(item.id, ticket))),
        conflict.value && h('p', { role: 'alert' }, '评分已被其他会话修改。请重新加载此答卷，再填写批阅。'),
        h('ol', { class: 'attempt-questions' }, item.answers.map(a => {
          const q = questions.get(a.question_version_id)
          return h('li', { key: a.question_version_id }, [
            h('p', `第 ${q?.position ?? '?'} 题 · ${questionTypes[q?.type] ?? '题目'} · ${gradeNames[a.grading_status]}`),
            h('p', { class: 'attempt-text' }, q?.stem ?? ''),
            q?.options?.length > 0 && h('ul', q.options.map(option => h('li', { key: option.key }, `${option.key} · ${option.text}`))),
            h('p', { class: 'attempt-text' }, `原作答：${showValue(a.value)}`),
            h('p', `得分：${a.score === null ? '待评分' : a.score} / ${a.max_score}`),
            a.comment && h('p', { class: 'attempt-text' }, `评语：${a.comment}`),
            Object.hasOwn(a, 'answer') && h('div', { class: 'attempt-reference' }, [
              h('p', { class: 'attempt-text' }, `参考答案：${showValue(a.answer)}`),
              h('p', { class: 'attempt-text' }, `解析：${a.explanation || '暂无'}`),
            ]),
          ])
        })),
        teacher() && drafts.value.length > 0 && h('form', { class: 'attempt-grade-form', onSubmit: e => { e.preventDefault(); if (!conflict.value) run(grade, true) } }, [
          h('h4', '简答批阅 / 更正'), h('p', '勾选本次要保存的题目；可以分批批阅，也可更正已批分数。'),
          ...drafts.value.map(draft => {
            const position = questions.get(draft.question_version_id)?.position
            return h('fieldset', { disabled: busy.value || conflict.value, key: draft.question_version_id }, [
              h('legend', `第 ${position} 题 · 配分 ${draft.max_score}`),
              check(`批阅第 ${position} 题`, draft.include, value => { draft.include = value }, conflict.value),
              field(`第 ${position} 题评分`, input(`第 ${position} 题评分`, draft.score, value => { draft.score = value },
                { type: 'number', min: 0, max: draft.max_score, step: '0.01', required: draft.include, disabled: busy.value || conflict.value })),
              field(`第 ${position} 题评语`, h('textarea', { 'aria-label': `第 ${position} 题评语`, value: draft.comment,
                maxlength: 1000, rows: 3, disabled: busy.value || conflict.value, onInput: e => { draft.comment = e.target.value } })),
            ])
          }), submit('保存本次批阅', conflict.value),
        ]),
      ])
    }
    return () => h('section', { class: `attempt-bank${props.paper ? ' attempt-inline' : ' card'}`, 'aria-busy': busy.value }, [
      h(props.paper ? 'h4' : 'h2', teacher() ? '答卷批阅' : '答卷历史与结果'),
      button('重新加载答卷', () => run(boot)),
      busy.value && h('p', { role: 'status' }, '正在加载或保存答卷…'),
      error.value && h('p', { role: 'alert' }, error.value), notice.value && h('p', { role: 'status' }, notice.value),
      !props.paper && select('答卷课程', course.value, value => {
        epoch++; busy.value = false; course.value = value; paperFilter.value = ''; page.value = 1; reset(); run(boot)
      }, courses.value.map(c => [String(c.id), c.title])),
      !props.paper && course.value && h('form', { class: 'inline-form attempt-filters', onSubmit: e => { e.preventDefault(); page.value = 1; run(load) } }, [
        select('筛选答卷试卷', paperFilter.value, value => { paperFilter.value = value }, [['', '全部试卷'], ...papers.value.map(p => [String(p.id), p.title])]),
        select('筛选评分状态', status.value, value => { status.value = value }, [['', '全部状态'], ...Object.entries(statusNames)]), submit('筛选答卷'),
      ]),
      h('p', `共 ${total.value} 份答卷`),
      h('ul', { class: 'rows' }, rows.value.map(item => h('li', { key: item.id }, button(
        `答卷 #${item.id} · ${statusNames[item.status]}${teacher() ? ` · 学生 #${item.student_id}` : ''}`,
        () => run(ticket => open(item.id, ticket)))))),
      !rows.value.length && !busy.value && !error.value && h('p', teacher() ? '暂无符合条件的答卷。学生交卷后可在这里批阅。' : '暂无答卷。可在课程试卷中选择进行中的卷作答。'),
      !props.paper || teacher() ? h('div', { class: 'actions' }, [
        button('答卷上一页', () => { page.value--; run(load) }, page.value <= 1), h('span', `第 ${page.value} 页`),
        button('答卷下一页', () => { page.value++; run(load) }, page.value * 20 >= total.value),
      ]) : null,
      selected.value && selectedPaper.value && resultView(),
      props.paper && !teacher() && course.value && loaded.value && !busy.value && !selected.value && !total.value &&
        props.paper.window_state === 'open' && props.paper.items && answerForm(),
    ])
  },
}
