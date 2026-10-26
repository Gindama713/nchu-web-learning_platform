// SPEC-004 preparation view: draft units, course links, copy, publish and withdraw.
import { h, onMounted, reactive, ref } from 'vue'
import { PreparationClient } from './preparation-client.js'

const STATUS = { draft: '草稿', published: '已发布', withdrawn: '已撤回' }
const WINDOW = { upcoming: '未开始', open: '进行中', closed: '已结束' }
const localValue = value => (value ? value.slice(0, 16) : '')
const short = (text, size = 24) => (text && text.length > size ? `${text.slice(0, size)}…` : text ?? '')

export const PreparationView = {
  setup() {
    const api = new PreparationClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const items = ref([])
    const page = ref(1)
    const total = ref(0)
    const candidates = reactive({ knowledge: [], resources: [], questions: [], quizzes: [] })
    const edit = reactive({})
    const withdrawReason = reactive({})
    const replaceId = reactive({})
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const form = reactive({
      title: '', scheduled_at: '', knowledge_ids: [], resource_version_ids: [],
      question_version_ids: [], quiz_ids: [],
    })
    const teacher = () => session.value?.user.role === 'teacher'
    const student = () => session.value?.user.role === 'student'

    function clearCourse() {
      items.value = []
      total.value = 0
      page.value = 1
      for (const key of Object.keys(candidates)) candidates[key] = []
      for (const key of Object.keys(edit)) delete edit[key]
      for (const key of Object.keys(withdrawReason)) delete withdrawReason[key]
      for (const key of Object.keys(replaceId)) delete replaceId[key]
    }

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true
      error.value = ''
      notice.value = ''
      try {
        await action()
        notice.value = success
      } catch (failure) {
        error.value = failure.message
        if (failure.status === 401) {
          session.value = null
          api.userId = null
          courses.value = []
          courseId.value = ''
          clearCourse()
        }
      } finally {
        busy.value = false
      }
    }

    async function loadList() {
      if (!courseId.value) return
      const result = await api.list(courseId.value, page.value)
      items.value = result.data
      total.value = result.total
    }

    async function loadCourse() {
      clearCourse()
      if (!courseId.value) return
      if (!teacher()) return loadList()
      const [knowledge, resources, questions, quizzes] = await Promise.all([
        api.knowledge(courseId.value), api.resources(courseId.value),
        api.questions(courseId.value), api.quizzes(courseId.value),
      ])
      candidates.knowledge = knowledge
      candidates.resources = resources
      candidates.questions = questions
      candidates.quizzes = quizzes
      await loadList()
    }

    async function boot() {
      session.value = null
      api.userId = null
      courses.value = []
      clearCourse()
      const fresh = await api.session()
      api.userId = fresh.user.id
      session.value = fresh
      courses.value = await api.courses()
      if (!courses.value.some(course => String(course.id) === String(courseId.value))) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
    }

    const linkData = source => ({
      knowledge_ids: [...source.knowledge_ids],
      resource_version_ids: [...source.resource_version_ids],
      question_version_ids: [...source.question_version_ids],
      quiz_ids: [...source.quiz_ids],
    })

    function openEdit(item) {
      edit[item.id] = {
        title: item.title, scheduled_at: localValue(item.scheduled_at), ...linkData(item),
      }
    }

    function collect(ids) {
      return [...ids].map(value => Number(value)).filter(Boolean)
    }

    async function create() {
      if (!form.title.trim()) throw new Error('请填写备课标题')
      const data = {
        title: form.title.trim(),
        knowledge_ids: collect(form.knowledge_ids),
        resource_version_ids: collect(form.resource_version_ids),
        question_version_ids: collect(form.question_version_ids),
        quiz_ids: collect(form.quiz_ids),
      }
      if (form.scheduled_at) data.scheduled_at = new Date(form.scheduled_at).toISOString()
      await api.create(courseId.value, data)
      Object.assign(form, {
        title: '', scheduled_at: '', knowledge_ids: [], resource_version_ids: [],
        question_version_ids: [], quiz_ids: [],
      })
      await loadList()
    }

    async function saveEdit(item) {
      const draft = edit[item.id]
      if (!draft.title.trim()) throw new Error('请填写备课标题')
      const data = { title: draft.title.trim(), ...linkData(draft) }
      data.scheduled_at = draft.scheduled_at ? new Date(draft.scheduled_at).toISOString() : null
      await api.update(item.id, data)
      delete edit[item.id]
      await loadList()
    }

    async function copy(item) {
      const title = window.prompt('复制标题（必填，不修改原单元）')
      if (!title) return
      await api.copy(item.id, title)
      await loadList()
    }

    async function publish(item) {
      await api.publish(item.id, replaceId[item.id] || null)
      delete replaceId[item.id]
      await loadList()
    }

    async function withdraw(item) {
      const reason = (withdrawReason[item.id] ?? '').trim()
      if (!reason) throw new Error('撤回理由（1—500 字）必填')
      await api.withdraw(item.id, reason)
      delete withdrawReason[item.id]
      await loadList()
    }

    onMounted(() => run(boot))
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const multi = (ids, entries, format) => h('select', {
      multiple: true, size: Math.min(4, Math.max(2, entries.length)),
      disabled: busy.value,
      value: ids,
      onChange: event => { ids.length = 0; ids.push(...collect(event.target.selectedOptions)) },
    }, entries.map(entry => h('option', { value: entry.value, key: entry.value }, format(entry))))

    function linkSelects(source) {
      return [
        ['知识', source.knowledge_ids ?? source.knowledge, candidates.knowledge,
          point => `#${point.id} ${short(point.title)}`],
        ['资源', source.resource_version_ids ?? source.resources, candidates.resources,
          item => `#${item.latest_version_id} ${short(item.title)}`],
        ['题目', source.question_version_ids ?? source.questions, candidates.questions,
          item => `#${item.id}v${item.version} ${short(item.stem)}`],
        ['测验', source.quiz_ids ?? source.quizzes, candidates.quizzes,
          quiz => `#${quiz.id} ${short(quiz.title)}`],
      ].map(([label, ids, entries, format]) => h('label', [`${label} `, multi(ids ?? [], entries, format)]))
    }

    const statusText = item => (item.status === 'published' && item.published_at ? `已发布` : STATUS[item.status])

    function quizCell(item) {
      const entries = item.quizzes ?? []
      if (!entries.length) return item.quiz_ids.length ? item.quiz_ids.join(', ') : '—'
      return h('ul', { class: 'preparation-quiz' }, entries.map(quiz => h('li', { key: quiz.id },
        `#${quiz.id} ${short(quiz.title, 18)} · ${WINDOW[quiz.window_state] ?? quiz.window_state}`)))
    }

    function teacherActions(item) {
      return h('td', { class: 'preparation-actions' }, [
        item.status === 'draft' && h('details', { class: 'preparation-edit' }, [
          h('summary', { onClick: () => openEdit(item) }, '编辑'),
          edit[item.id] && h('form', { onSubmit: event => {
            event.preventDefault()
            run(() => saveEdit(item), '备课草稿已保存')
          } }, [
            h('label', ['标题 ', h('input', {
              value: edit[item.id].title, maxlength: 100, required: true, disabled: busy.value,
              onInput: event => { edit[item.id].title = event.target.value },
            })]),
            h('label', ['排期 ', h('input', {
              type: 'datetime-local', value: edit[item.id].scheduled_at, disabled: busy.value,
              onInput: event => { edit[item.id].scheduled_at = event.target.value },
            })]),
            linkSelects(edit[item.id]),
            h('button', { type: 'submit', disabled: busy.value }, '保存草稿'),
          ]),
        ]),
        item.status === 'draft' && h('details', { class: 'preparation-edit' }, [
          h('summary', '发布'),
          h('div', { class: 'preparation-publish' }, [
            h('label', ['替换 ', h('select', {
              value: replaceId[item.id] ?? '', disabled: busy.value,
              onChange: event => { replaceId[item.id] = event.target.value },
            }, [h('option', { value: '' }, '不替换'),
              ...items.value.filter(other => other.status === 'published' && other.id !== item.id)
                .map(other => h('option', { value: String(other.id), key: other.id }, `#${other.id} ${short(other.title)}`))])]),
            h('small', '发布后学生收到预习通知；替换会把旧发布单元撤回。'),
            button('确认发布', () => run(() => publish(item), '备课已发布并通知学生')),
          ]),
        ]),
        item.status === 'published' && h('details', { class: 'preparation-edit' }, [
          h('summary', '撤回'),
          h('div', { class: 'preparation-publish' }, [
            h('label', ['理由 ', h('input', {
              value: withdrawReason[item.id] ?? '', maxlength: 500, required: true, disabled: busy.value,
              onInput: event => { withdrawReason[item.id] = event.target.value },
            })]),
            button('确认撤回', () => run(() => withdraw(item), '备课已撤回，学生不再可见')),
          ]),
        ]),
        button('复制', () => run(() => copy(item), '已复制为新草稿，原单元不变')),
      ])
    }

    const linkCount = item => {
      const parts = [
        item.knowledge_ids.length && `知${item.knowledge_ids.length}`,
        item.resource_version_ids.length && `资${item.resource_version_ids.length}`,
        item.question_version_ids.length && `题${item.question_version_ids.length}`,
        item.quiz_ids.length && `测${item.quiz_ids.length}`,
      ].filter(Boolean)
      return parts.length ? parts.join(' ') : '—'
    }

    return () => h('section', { class: 'preparation-module card', 'aria-labelledby': 'preparation-title', 'aria-busy': busy.value }, [
      h('h2', { id: 'preparation-title' }, '备课单元'),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { class: 'preparation-error', role: 'alert' }, [h('strong', '暂时无法完成操作'), h('p', error.value)]),
      notice.value && h('p', { class: 'preparation-notice', role: 'status' }, notice.value),
      !session.value && !busy.value && !error.value && h('p', '登录后即可查看备课单元。'),
      session.value && !courses.value.length && h('p', '还没有可访问的课程。'),
      session.value && courses.value.length && h('div', { class: 'preparation-course' }, [
        h('label', ['当前课程 ', h('select', {
          value: courseId.value, disabled: busy.value,
          onChange: event => { courseId.value = event.target.value; run(loadCourse) },
        }, courses.value.map(course => h('option', { value: String(course.id) }, course.title)))]),
        h('span', `${session.value.user.name} · ${teacher() ? '教师' : student() ? '学生' : '管理员只读'}`),
      ]),
      courseId.value && teacher() && h('form', { class: 'preparation-create', onSubmit: event => {
        event.preventDefault()
        run(create, '备课草稿已创建，发布前学生不可见')
      } }, [
        h('h3', '新建备课'),
        h('label', ['标题 ', h('input', {
          value: form.title, maxlength: 100, required: true, disabled: busy.value,
          onInput: event => { form.title = event.target.value },
        })]),
        h('label', ['排期 ', h('input', {
          type: 'datetime-local', value: form.scheduled_at, disabled: busy.value,
          onInput: event => { form.scheduled_at = event.target.value },
        })]),
        linkSelects(form),
        h('small', '知识/资源/题目/测验仅限本课程；关联随堂测须先发布才能发布备课。'),
        h('button', { type: 'submit', disabled: busy.value }, '创建草稿'),
      ]),
      courseId.value && h('table', { class: 'preparation-table' }, [
        h('thead', h('tr', teacher()
          ? [h('th', '标题'), h('th', '状态'), h('th', '排期'), h('th', '关联'), h('th', '操作')]
          : [h('th', '标题'), h('th', '状态'), h('th', '排期'), h('th', '随堂测')])),
        h('tbody', items.value.length ? items.value.map(item => h('tr', { key: item.id }, [
          h('td', item.title),
          h('td', statusText(item)),
          h('td', item.scheduled_at?.slice(0, 16).replace('T', ' ') ?? '—'),
          teacher() ? h('td', linkCount(item)) : h('td', quizCell(item)),
          ...(teacher() ? [teacherActions(item)] : []),
        ])) : [h('tr', h('td', { colspan: teacher() ? 5 : 4 },
          teacher() ? '暂无备课，先创建草稿。' : '老师还没有发布预习内容。'))]),
      ]),
      courseId.value && total.value > 20 && h('div', { class: 'preparation-pager' }, [
        button('上一页', () => { page.value--; run(loadList) }, { disabled: busy.value || page.value <= 1 }),
        h('span', `第 ${page.value} 页 / 共 ${Math.ceil(total.value / 20)} 页`),
        button('下一页', () => { page.value++; run(loadList) }, { disabled: busy.value || page.value >= Math.ceil(total.value / 20) }),
      ]),
    ])
  },
}
