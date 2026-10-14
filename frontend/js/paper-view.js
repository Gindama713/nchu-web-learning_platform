import { cloneVNode, h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { PaperClient, paperKinds, paperPayload, publicationPayload, windowStates } from './paper-client.js'
import { AttemptView } from './attempt-view.js'
import { QuizClient } from './quiz-client.js'

export const PaperView = {
  props: { user: { type: Object, required: true }, quizOnly: { type: Boolean, default: false } },
  setup(props) {
    const client = () => new (props.quizOnly ? QuizClient : PaperClient)(props.user.id)
    let api = client(), epoch = 0
    const teacher = () => props.user.role === 'teacher'
    const courses = ref([]), courseId = ref(''), rows = ref([]), selected = ref(null), candidates = ref([])
    const items = ref([]), editing = ref(false), candidatePage = ref(1), questionId = ref('')
    const page = ref(1), total = ref(0), busy = ref(false), error = ref(''), notice = ref('')
    const filters = reactive({ kind: '', status: '' })
    const form = reactive({ title: '', kind: props.quizOnly ? 'quiz' : 'homework', confidential: false })
    const times = reactive({ start_at: '', end_at: '', review_at: '', confidentiality_note: '' })
    const statistics = ref(null)

    function clear() {
      statistics.value = null
      rows.value = []; total.value = 0; selected.value = null; candidates.value = []; items.value = []
      editing.value = false; questionId.value = ''; candidatePage.value = 1
      Object.assign(form, { title: '', kind: props.quizOnly ? 'quiz' : 'homework', confidential: false })
      Object.assign(times, { start_at: '', end_at: '', review_at: '', confidentiality_note: '' })
    }
    async function run(action, success = '') {
      if (busy.value) return
      const ticket = epoch
      busy.value = true; error.value = ''; notice.value = ''
      try {
        await api.verifySession()
        if (ticket !== epoch) return
        await action(ticket)
        if (ticket === epoch) notice.value = success
      } catch (failure) {
        if (ticket !== epoch) return
        error.value = failure.message
        // Remove stale question/answer data whenever a load or permission check fails.
        clear()
        if (failure.status === 401) { courses.value = []; courseId.value = '' }
      } finally { if (ticket === epoch) busy.value = false }
    }
    async function load(ticket) {
      statistics.value = null
      rows.value = []; selected.value = null; total.value = 0
      if (!courseId.value) return
      const result = await api.list(courseId.value, { page: page.value, ...filters })
      if (ticket !== epoch) return
      rows.value = result.data; total.value = result.total
    }
    async function boot(ticket) {
      clear(); courses.value = []
      const result = await api.courses()
      if (ticket !== epoch) return
      courses.value = result
      if (!result.some(item => String(item.id) === courseId.value)) courseId.value = result.length ? String(result[0].id) : ''
      await load(ticket)
    }
    async function edit(ticket) {
      clear()
      if (!teacher() || !courseId.value) return
      const result = await api.questions(courseId.value)
      if (ticket !== epoch) return
      candidates.value = result; editing.value = true
    }
    function add() {
      const row = candidates.value.find(item => String(item.id) === questionId.value)
      if (!row || items.value.some(item => item.question_id === row.id)) return
      items.value.push({ question_id: row.id, question_version_id: row.version_id,
        version: row.version, stem: row.stem, points: '10' })
      questionId.value = ''
    }
    async function save(ticket) {
      const item = await api.create(courseId.value, paperPayload(form, items.value))
      if (ticket !== epoch) return
      editing.value = false; items.value = []; candidates.value = []
      await load(ticket)
      if (ticket === epoch) selected.value = item
    }
    async function open(id, ticket) {
      statistics.value = null
      selected.value = null; editing.value = false; items.value = []; candidates.value = []
      const item = await api.detail(id)
      if (ticket !== epoch) return
      selected.value = item
      Object.assign(times, { start_at: '', end_at: '', review_at: '', confidentiality_note: '' })
    }
    async function publish(ticket) {
      const item = selected.value
      const payload = publicationPayload(times, item.confidential, props.quizOnly)
      const updated = await api.publish(item.id, payload, courseId.value)
      if (ticket !== epoch) return
      await load(ticket)
      if (ticket === epoch) selected.value = updated
    }
    async function loadStatistics(ticket) {
      statistics.value = null
      const result = await new QuizClient(props.user.id).statistics(selected.value.id)
      if (ticket === epoch) statistics.value = result
    }
    async function review(ticket) {
      const id = selected.value.id
      await new QuizClient(props.user.id).review(id)
      if (ticket !== epoch) return
      await open(id, ticket)
      if (ticket === epoch) await loadStatistics(ticket)
    }
    watch(() => `${props.user.id}:${props.user.role}`, () => {
      epoch++; busy.value = false; clear(); courses.value = []; courseId.value = ''
      api = client()
      run(boot)
    })
    onUnmounted(() => { epoch++ })
    onMounted(() => run(boot))

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const field = (label, input) => h('label', [h('span', label), cloneVNode(input, { 'aria-label': label })])
    const input = (value, update, options = {}) => h('input', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const select = (value, update, values, placeholder = '') => h('select', {
      value, disabled: busy.value, onChange: event => update(event.target.value),
    }, [...(placeholder ? [h('option', { value: '' }, placeholder)] : []),
      ...Object.entries(values).map(([id, label]) => h('option', { value: id }, label))])
    const submit = label => h('button', { type: 'submit', disabled: busy.value }, label)
    const rate = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`
    const score = value => value == null ? '—' : String(Number(value.toFixed(2)))

    function quizStatistics(item) {
      const stats = statistics.value
      return h('section', { class: 'quiz-statistics' }, [
        h('h4', '逐题统计与讲评'),
        h('div', { class: 'actions' }, [button('刷新逐题统计', () => run(loadStatistics)),
          !item.review_at && button('发布讲评并开放答案', () => run(review, '讲评已发布。学生重新加载后可查看答案与解析。'),
            { disabled: busy.value || item.window_state !== 'closed' })]),
        !item.review_at && h('p', '截止后才可发布讲评。发布将向参与学生开放标准答案与解析。'),
        stats && h('div', [
          h('p', `统计截至：${stats.source_until}`),
          h('p', `应交 ${stats.expected_count} · 已交 ${stats.submitted_count} · 缺交 ${stats.missing_count} · 客观正确率 ${rate(stats.objective_correct_rate)}`),
          h('p', '漏答计入客观正确率分母；均分只计已定分；“—”表示无样本或不适用。多选各选项比例之和可以超过100%。'),
          h('ol', { class: 'paper-items' }, stats.questions.map((q, index) => h('li', { key: q.question_version_id }, [
            h('p', `第 ${index + 1} 题 · 版本 #${q.question_version_id} · 满分 ${q.max_score}`),
            h('p', `已交 ${q.submitted_count} · 已答 ${q.answered_count} · 漏答 ${q.unanswered_count}`),
            h('p', `已定分 ${q.graded_count} · 待批 ${q.pending_count} · 正确数 ${q.correct_count ?? '—'} · 正确率 ${rate(q.correct_rate)} · 均分 ${score(q.mean_score)}`),
            h('ul', q.options.map(option => h('li', { key: option.key },
              `${option.key} · ${option.text}：${option.selected_count} 人 · ${rate(option.selection_rate)}`))),
          ]))),
        ]),
      ])
    }

    function editor() {
      const choices = candidates.value.filter(row => !items.value.some(item => item.question_id === row.id))
      const subset = choices.slice((candidatePage.value - 1) * 20, candidatePage.value * 20)
      return h('form', { class: 'paper-editor', onSubmit: event => { event.preventDefault(); run(save, '草稿已保存，题目版本与配分已固定。') } }, [
        h('h3', '编排试卷草稿'),
        field('试卷标题', input(form.title, value => { form.title = value }, { required: true, maxlength: 100 })),
        !props.quizOnly && field('试卷类型', select(form.kind, value => { form.kind = value; form.confidential = value === 'exam' }, paperKinds)),
        h('label', { class: 'paper-check' }, [h('input', { type: 'checkbox', checked: form.confidential,
          disabled: busy.value, onChange: event => { form.confidential = event.target.checked } }), '要求保密（曾公开的题目不能发布）']),
        field('选择题目版本', select(questionId.value, value => { questionId.value = value },
          Object.fromEntries(subset.map(row => [String(row.id), `#${row.id} · v${row.version} · ${row.stem.slice(0, 60)}`])), '请选择题目')),
        button('加入试卷', add, { disabled: busy.value || !questionId.value }),
        h('div', { class: 'actions' }, [
          button('候选上一页', () => { candidatePage.value--; questionId.value = '' }, { disabled: busy.value || candidatePage.value <= 1 }),
          h('span', `候选第 ${candidatePage.value} 页`),
          button('候选下一页', () => { candidatePage.value++; questionId.value = '' }, { disabled: busy.value || candidatePage.value * 20 >= choices.length }),
        ]),
        !candidates.value.length && h('p', '暂无可用题目。请先在课程题库创建带知识标签的题目。'),
        h('ol', { class: 'paper-items' }, items.value.map((item, index) => h('li', { key: item.question_id }, [
          h('p', `#${item.question_id} · v${item.version} · ${item.stem}`),
          field(`第 ${index + 1} 题配分`, input(item.points, value => { item.points = value }, { type: 'number', min: '0.01', step: '0.01', required: true })),
          h('div', { class: 'actions' }, [
            button('上移', () => { [items.value[index - 1], items.value[index]] = [item, items.value[index - 1]] }, { disabled: busy.value || index === 0 }),
            button('下移', () => { [items.value[index + 1], items.value[index]] = [item, items.value[index + 1]] }, { disabled: busy.value || index === items.value.length - 1 }),
            button('移除', () => { items.value.splice(index, 1); candidatePage.value = 1 }),
          ]),
        ]))),
        h('p', '保存将引用所选固定版本，题库之后新增版本不会改变这份卷。'),
        h('div', { class: 'actions' }, [h('button', { type: 'submit', disabled: busy.value || !items.value.length }, '保存试卷草稿'),
          button('取消编卷', () => { editing.value = false; items.value = []; candidates.value = [] })]),
      ])
    }
    function detail(item) {
      return h('article', { class: 'paper-detail' }, [
        h('h3', item.title), h('p', `${paperKinds[item.kind]} · ${item.status === 'draft' ? '草稿' : windowStates[item.window_state]} · 总分 ${item.total_points}`),
        item.status === 'published' && h('p', `开始：${item.start_at} · 截止：${item.end_at} · 讲评：${item.review_at ?? '待教师讲评'}`),
        teacher() && h('p', `发布冻结人数：${item.participant_count}`),
        !teacher() && !item.items && h('p', '试卷尚未开始，开始后可查看题目。'),
        (teacher() || item.window_state === 'closed') && h('ol', { class: 'paper-items' }, (item.items ?? []).map(q => h('li', { key: q.question_version_id }, [
          h('p', `第 ${q.position} 题 · ${q.points} 分 · v${q.version}`), h('p', { class: 'paper-text' }, q.stem),
          h('ul', q.options.map(option => h('li', `${option.key} · ${option.text}`))),
          (teacher() || (item.review_at && item.window_state === 'closed')) && Object.hasOwn(q, 'answer') && h('div', [
            h('p', `参考答案：${JSON.stringify(q.answer)}`), h('p', { class: 'paper-text' }, `解析：${q.explanation || '暂无'}`),
          ]),
        ]))),
        teacher() && item.status === 'draft' && h('form', { class: 'paper-publication', onSubmit: event => {
          event.preventDefault(); run(publish, '发布成功，试卷内容、时间和参与名单已冻结。')
        } }, [h('h4', '设置窗口并发布'),
          h('p', props.quizOnly ? '随堂测截止后由教师发布讲评，讲评前不开放答案。时间按本机时区输入，服务器复核后生效。发布后不可修改。'
            : '普通发布采用定时讲评。时间按本机时区输入；服务器复核后生效。发布后不可修改。'),
          ...(props.quizOnly ? [['start_at', '试卷开始'], ['end_at', '试卷截止']]
            : [['start_at', '试卷开始'], ['end_at', '试卷截止'], ['review_at', '试卷讲评']]).map(([key, label]) =>
            field(label, input(times[key], value => { times[key] = value }, { type: 'datetime-local', required: true }))),
          item.confidential && field('保密确认说明', h('textarea', { value: times.confidentiality_note, required: true, maxlength: 1000,
            disabled: busy.value, onInput: event => { times.confidentiality_note = event.target.value } })),
          item.confidential && h('p', '请确认所有题目未公开且并非对公开题的简单复制。系统会复核可追踪的公开历史。'),
          submit(props.quizOnly ? '发布随堂测并冻结名单' : '发布试卷并冻结名单'),
        ]),
        teacher() && item.kind === 'quiz' && item.status === 'published' && quizStatistics(item),
        item.status === 'published' && h(AttemptView, { key: `${epoch}:${item.id}:${item.review_at}`, user: props.user, paper: item, courseId: courseId.value }),
      ])
    }
    return () => h('section', { class: 'card paper-bank', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [h('h2', props.quizOnly ? '随堂测' : '课程试卷'), button('重新加载试卷', () => run(boot))]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存试卷…'),
      error.value && h('div', { role: 'alert' }, [h('p', error.value), button('重试试卷', () => run(boot))]),
      notice.value && h('p', { role: 'status' }, notice.value),
      !courses.value.length && !busy.value && !error.value && h('p', '暂无可访问课程。'),
      courses.value.length > 0 && field('试卷课程', select(courseId.value, value => {
        courseId.value = value; epoch++; busy.value = false; page.value = 1; clear(); run(load)
      }, Object.fromEntries(courses.value.map(item => [String(item.id), item.title])))),
      courseId.value && h('div', [
        h('form', { class: 'inline-form paper-filters', onSubmit: event => { event.preventDefault(); page.value = 1; run(load) } }, [
          !props.quizOnly && field('筛选试卷类型', select(filters.kind, value => { filters.kind = value }, paperKinds, '全部类型')),
          field('筛选试卷状态', select(filters.status, value => { filters.status = value }, { draft: '草稿', published: '已发布' }, '全部状态')),
          submit('筛选试卷'), teacher() && button('编排新试卷', () => run(edit)),
        ]),
        h('p', `共 ${total.value} 份试卷`),
        h('ul', { class: 'rows' }, rows.value.map(item => h('li', { key: item.id }, [
          button(`#${item.id} · ${item.title} · ${item.status === 'draft' ? '草稿' : windowStates[item.window_state]}`, () => run(ticket => open(item.id, ticket))),
        ]))),
        !rows.value.length && !busy.value && !error.value && h('p', '暂无符合条件的试卷。'),
        h('div', { class: 'actions' }, [
          button('试卷上一页', () => { page.value--; run(load) }, { disabled: busy.value || page.value <= 1 }),
          h('span', `第 ${page.value} 页`),
          button('试卷下一页', () => { page.value++; run(load) }, { disabled: busy.value || page.value * 20 >= total.value }),
        ]),
        editing.value ? editor() : selected.value && detail(selected.value),
      ]),
    ])
  },
}
