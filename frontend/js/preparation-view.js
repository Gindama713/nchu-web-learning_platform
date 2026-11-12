// SPEC-004 preparation view: draft units, course links, copy, publish and withdraw.
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { PreparationClient } from './preparation-client.js'

const STATUS = { draft: '草稿', published: '已发布', withdrawn: '已撤回' }
const WINDOW = { upcoming: '未开始', open: '进行中', closed: '已结束' }
// 与连线统计（SPEC-010C）一致：后端存 UTC，展示/编辑统一按 Asia/Shanghai（+08:00）。
const shanghaiFormat = new globalThis.Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const toShanghaiInput = value => {
  const date = new Date(value ?? '')
  return value && Number.isFinite(date.getTime()) ? shanghaiFormat.format(date).replace(' ', 'T') : ''
}
const fromShanghaiInput = value => (value ? new Date(`${value}+08:00`).toISOString() : null)
const short = (text, size = 24) => (text && text.length > size ? `${text.slice(0, size)}…` : text ?? '')
// 排期是「日期 + 开始 + 结束」三段：日期用日历控件，时间自己填（缺省结束自动取开始后 1.5 小时）。
const splitLocal = value => {
  const text = toShanghaiInput(value)
  if (!text) return { date: '', time: '' }
  const [date, time = ''] = text.split('T')
  return { date, time: time.slice(0, 5) }
}
const joinLocal = (date, time) => (date ? `${date}T${time || '00:00'}` : '')
const addMinutes = (time, minutes) => {
  const [hour, minute] = (time || '08:00').split(':').map(Number)
  const total = (hour * 60 + minute + minutes) % 1440
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

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
    // 编辑/发布/撤回/复制都放到独立弹窗里，不再挤在列表行内。
    const modal = reactive({ id: null, kind: '' })
    // 复制弹窗里先填标题与新排期：默认不带源单元的旧排期（多半已经是过去时间）。
    const copyDraft = reactive({ title: '', scheduled_at: '', scheduled_end_at: '' })
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const form = reactive({
      title: '', scheduled_at: '', scheduled_end_at: '', knowledge_ids: [], resource_version_ids: [],
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
      closeModal()
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
        title: item.title,
        scheduled_at: toShanghaiInput(item.scheduled_at),
        scheduled_end_at: toShanghaiInput(item.scheduled_end_at),
        ...linkData(item),
      }
    }

    function collect(ids) {
      return [...ids].map(value => Number(value)).filter(Boolean)
    }

    // 排期区间校验与提交载荷：日期为空即不排期，结束时间必须晚于开始时间。
    function schedulePayload(data, start, end) {
      if (end && !start) throw new Error('请先选择排期日期和开始时间，再填结束时间')
      if (start && end && end <= start) throw new Error('结束时间必须晚于开始时间')
      data.scheduled_at = fromShanghaiInput(start)
      data.scheduled_end_at = fromShanghaiInput(end)
      return data
    }

    async function create() {
      if (!form.title.trim()) throw new Error('请填写备课标题')
      const data = schedulePayload({
        title: form.title.trim(),
        knowledge_ids: collect(form.knowledge_ids),
        resource_version_ids: collect(form.resource_version_ids),
        question_version_ids: collect(form.question_version_ids),
        quiz_ids: collect(form.quiz_ids),
      }, form.scheduled_at, form.scheduled_end_at)
      await api.create(courseId.value, data)
      Object.assign(form, {
        title: '', scheduled_at: '', scheduled_end_at: '', knowledge_ids: [], resource_version_ids: [],
        question_version_ids: [], quiz_ids: [],
      })
      await loadList()
    }

    async function saveEdit(item) {
      const draft = edit[item.id]
      if (!draft.title.trim()) throw new Error('请填写备课标题')
      const data = schedulePayload({ title: draft.title.trim(), ...linkData(draft) },
        draft.scheduled_at, draft.scheduled_end_at)
      await api.update(item.id, data)
      delete edit[item.id]
      closeModal()
      await loadList()
    }

    // 复制不再用 window.prompt：原生弹窗风格不一致、可能被浏览器拦截，也放不下排期。
    function openCopy(item) {
      copyDraft.title = item.title.length > 90 ? `${item.title.slice(0, 90)}（副本）` : `${item.title}（副本）`
      copyDraft.scheduled_at = ''
      copyDraft.scheduled_end_at = ''
      openModal(item, 'copy')
    }

    async function submitCopy(item) {
      if (!copyDraft.title.trim()) throw new Error('请填写复制后的标题')
      const data = schedulePayload({ title: copyDraft.title.trim() },
        copyDraft.scheduled_at, copyDraft.scheduled_end_at)
      await api.copy(item.id, data.title, {
        scheduled_at: data.scheduled_at, scheduled_end_at: data.scheduled_end_at,
      })
      closeModal()
      await loadList()
    }

    async function publish(item) {
      await api.publish(item.id, replaceId[item.id] || null)
      delete replaceId[item.id]
      closeModal()
      await loadList()
    }

    async function withdraw(item) {
      const reason = (withdrawReason[item.id] ?? '').trim()
      if (!reason) throw new Error('撤回理由（1—500 字）必填')
      await api.withdraw(item.id, reason)
      delete withdrawReason[item.id]
      closeModal()
      await loadList()
    }

    onMounted(() => {
      // 弹窗支持 Esc 关闭（测试渲染器里没有 addEventListener，做能力检测）。
      if (typeof globalThis.addEventListener === 'function') globalThis.addEventListener('keydown', onKeydown)
      run(boot)
    })
    onUnmounted(() => {
      if (typeof globalThis.removeEventListener === 'function') globalThis.removeEventListener('keydown', onKeydown)
    })
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    // 排期三段：日期走浏览器日历控件，开始/结束时间自己填（默认 08:00–09:30）。
    function scheduleFields(source) {
      const start = splitLocal(source.scheduled_at)
      const end = splitLocal(source.scheduled_end_at)
      const setStart = (date, time) => { source.scheduled_at = joinLocal(date, time) }
      const setEnd = (date, time) => { source.scheduled_end_at = joinLocal(date, time) }
      const field = (label, control) => h('label', { class: 'preparation-field' }, [h('span', label), control])
      return h('div', { class: 'preparation-schedule' }, [
        field('排期日期', h('input', {
          'aria-label': '排期日期', type: 'date', value: start.date, disabled: busy.value,
          onInput: event => {
            const date = event.target.value
            if (!date) { source.scheduled_at = ''; source.scheduled_end_at = ''; return }
            setStart(date, start.time || '08:00')
            if (end.date) setEnd(date, end.time)
          },
        })),
        field('开始时间', h('input', {
          'aria-label': '开始时间', type: 'time', step: 300, value: start.time,
          disabled: busy.value || !start.date,
          onInput: event => {
            const time = event.target.value
            setStart(start.date, time)
            // 结束时间缺失或已经早于新的开始时间时，自动顺延到开始后 1.5 小时
            if (!end.time || (time && end.time <= time)) setEnd(start.date, addMinutes(time, 90))
          },
        })),
        field('结束时间', h('input', {
          'aria-label': '结束时间', type: 'time', step: 300, value: end.time,
          disabled: busy.value || !start.date,
          onInput: event => setEnd(start.date, event.target.value),
        })),
      ])
    }

    // 原来用 <select multiple> 且把 option.value 取成不存在的 entry.value，
    // 选中项根本写不进 ids。改成「下拉挑一个 + 已选标签」，并按类别取真实 id。
    function linkPicker(label, ids, entries, valueOf, format) {
      const chosen = ids ?? []
      const options = entries.map(entry => ({
        value: String(valueOf(entry)), label: format(entry),
      }))
      const names = new Map(options.map(option => [option.value, option.label]))
      const available = options.filter(option => !chosen.some(id => String(id) === option.value))
      return h('div', { class: 'preparation-picker' }, [
        h('label', [label, h('select', {
          'aria-label': `${label}选择`, value: '', disabled: busy.value,
          onChange: event => {
            const value = event.target.value
            if (value && !chosen.some(id => String(id) === value)) chosen.push(Number(value))
            event.target.value = ''
          },
        }, [h('option', { value: '' }, `选择${label}…`),
          ...available.map(option => h('option', { value: option.value, key: option.value }, option.label))])]),
        h('div', { class: 'preparation-chips' }, chosen.length
          ? chosen.map(id => h('button', {
            type: 'button', class: 'preparation-chip', disabled: busy.value,
            'aria-label': `移除 ${names.get(String(id)) ?? id}`,
            onClick: () => {
              const index = chosen.findIndex(value => String(value) === String(id))
              if (index >= 0) chosen.splice(index, 1)
            },
          }, `${names.get(String(id)) ?? `#${id}`} ×`))
          : h('span', { class: 'preparation-empty' }, '未选择')),
      ])
    }

    function linkSelects(source) {
      return [
        ['知识', source.knowledge_ids ?? source.knowledge, candidates.knowledge,
          point => point.id, point => `#${point.id} ${short(point.title)}`],
        ['资源', source.resource_version_ids ?? source.resources, candidates.resources,
          item => item.latest_version_id, item => `#${item.latest_version_id} ${short(item.title)}`],
        ['题目', source.question_version_ids ?? source.questions, candidates.questions,
          item => item.version_id ?? item.id, item => `#${item.id}v${item.version} ${short(item.stem)}`],
        ['测验', source.quiz_ids ?? source.quizzes, candidates.quizzes,
          quiz => quiz.id,
          quiz => `#${quiz.id} ${short(quiz.title)} · ${WINDOW[quiz.window_state] ?? quiz.window_state ?? '未设置窗口'}`],
      ].map(([label, ids, entries, valueOf, format]) =>
        linkPicker(label, ids ?? [], entries, valueOf, format))
    }

    const statusText = item => (item.status === 'published' && item.published_at ? `已发布` : STATUS[item.status])
    const scheduleText = item => {
      const start = splitLocal(item.scheduled_at)
      if (!start.date) return '无排期'
      const end = splitLocal(item.scheduled_end_at)
      return `${start.date} ${start.time}${end.time ? `–${end.time}` : ''}`
    }

    function quizCell(item) {
      const entries = item.quizzes ?? []
      if (!entries.length) return item.quiz_ids.length ? item.quiz_ids.join(', ') : '—'
      return h('ul', { class: 'preparation-quiz' }, entries.map(quiz => h('li', { key: quiz.id },
        `#${quiz.id} ${short(quiz.title, 18)} · ${WINDOW[quiz.window_state] ?? quiz.window_state}`)))
    }

    function openModal(item, kind) {
      modal.id = item.id
      modal.kind = kind
      if (kind === 'edit') openEdit(item)
    }

    function closeModal() {
      modal.id = null
      modal.kind = ''
    }

    const modalItem = () => items.value.find(item => item.id === modal.id) ?? null
    const onKeydown = event => { if (event.key === 'Escape' && modal.id) closeModal() }

    function teacherActions(item) {
      return h('div', { class: 'preparation-actions' }, [
        item.status === 'draft' && button('编辑', () => openModal(item, 'edit'), { class: 'secondary' }),
        item.status === 'draft' && button('发布', () => openModal(item, 'publish')),
        item.status === 'published' && button('撤回', () => openModal(item, 'withdraw'), { class: 'secondary' }),
        button('复制', () => openCopy(item), { class: 'secondary' }),
      ].filter(Boolean))
    }

    // 编辑/发布/撤回统一在独立弹窗里完成，列表行只留按钮。
    function modalView() {
      const item = modalItem()
      if (!item) return null
      const titles = { edit: '编辑', publish: '发布', withdraw: '撤回', copy: '复制' }
      let body = null
      if (modal.kind === 'edit' && edit[item.id]) {
        const draft = edit[item.id]
        body = h('form', { class: 'preparation-form', onSubmit: event => {
          event.preventDefault()
          run(() => saveEdit(item), '备课草稿已保存')
        } }, [
          h('label', { class: 'preparation-field' }, ['标题', h('input', {
            value: draft.title, maxlength: 100, required: true, disabled: busy.value,
            onInput: event => { draft.title = event.target.value },
          })]),
          scheduleFields(draft),
          h('div', { class: 'preparation-links' }, linkSelects(draft)),
          h('small', '知识/资源/题目/测验从下拉里逐个添加；同名多条是不同编号的历史数据，按编号与窗口状态区分。'),
          h('div', { class: 'preparation-panel-actions' }, [
            h('button', { type: 'submit', disabled: busy.value }, '保存草稿'),
            button('取消', closeModal, { class: 'secondary' }),
          ]),
        ])
      } else if (modal.kind === 'publish') {
        body = h('div', { class: 'preparation-form' }, [
          h('label', { class: 'preparation-field' }, ['替换已发布单元', h('select', {
            value: replaceId[item.id] ?? '', disabled: busy.value,
            onChange: event => { replaceId[item.id] = event.target.value },
          }, [h('option', { value: '' }, '不替换'),
            ...items.value.filter(other => other.status === 'published' && other.id !== item.id)
              .map(other => h('option', { value: String(other.id), key: other.id }, `#${other.id} ${short(other.title)}`))])]),
          h('small', '发布后学生收到预习通知；替换会把旧发布单元撤回。'),
          h('div', { class: 'preparation-panel-actions' }, [
            button('确认发布', () => run(() => publish(item), '备课已发布并通知学生')),
            button('取消', closeModal, { class: 'secondary' }),
          ]),
        ])
      } else if (modal.kind === 'withdraw') {
        body = h('div', { class: 'preparation-form' }, [
          h('label', { class: 'preparation-field' }, ['撤回理由（1—500 字）', h('input', {
            value: withdrawReason[item.id] ?? '', maxlength: 500, required: true, disabled: busy.value,
            onInput: event => { withdrawReason[item.id] = event.target.value },
          })]),
          h('small', '撤回后学生不再看到这条备课，已发布记录仍保留在教师的列表里。'),
          h('div', { class: 'preparation-panel-actions' }, [
            button('确认撤回', () => run(() => withdraw(item), '备课已撤回，学生不再可见')),
            button('取消', closeModal, { class: 'secondary' }),
          ]),
        ])
      } else if (modal.kind === 'copy') {
        body = h('form', { class: 'preparation-form', onSubmit: event => {
          event.preventDefault()
          run(() => submitCopy(item), '已复制为新草稿，原单元不变')
        } }, [
          h('label', { class: 'preparation-field' }, ['新标题', h('input', {
            'aria-label': '复制后的标题', value: copyDraft.title, maxlength: 100, required: true,
            disabled: busy.value,
            onInput: event => { copyDraft.title = event.target.value },
          })]),
          scheduleFields(copyDraft),
          h('small', '复制默认不继承原单元的排期（原窗口可能已经过去），需要就现在设置；知识/资源/题目/测验的关联会一并带走。'),
          h('div', { class: 'preparation-panel-actions' }, [
            h('button', { type: 'submit', disabled: busy.value }, '创建副本'),
            button('取消', closeModal, { class: 'secondary' }),
          ]),
        ])
      }
      return h('div', { class: 'preparation-modal-backdrop', onClick: closeModal }, [
        h('div', {
          class: 'preparation-modal', role: 'dialog', 'aria-modal': 'true',
          'aria-label': `${titles[modal.kind] ?? ''}备课`,
          onClick: event => event.stopPropagation(),
        }, [
          h('header', { class: 'preparation-modal-head' }, [
            h('h4', `${titles[modal.kind] ?? ''}「${short(item.title, 20)}」`),
            h('button', {
              type: 'button', class: 'preparation-modal-close', 'aria-label': '关闭', disabled: busy.value,
              onClick: closeModal,
            }, '×'),
          ]),
          body,
        ]),
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
      h('div', { class: 'actions' }, [
        h('h2', { id: 'preparation-title' }, '备课单元'),
        session.value && button('重新加载', () => run(boot)),
      ]),
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
        h('label', { class: 'preparation-field' }, ['标题', h('input', {
          value: form.title, maxlength: 100, required: true, disabled: busy.value,
          onInput: event => { form.title = event.target.value },
        })]),
        scheduleFields(form),
        h('div', { class: 'preparation-links' }, linkSelects(form)),
        h('small', '知识/资源/题目/测验从下拉里逐个添加；同名多条是不同编号的历史数据，按编号与窗口状态区分。关联随堂测须先发布才能发布备课。'),
        h('button', { type: 'submit', disabled: busy.value }, '创建草稿'),
      ]),
      courseId.value && (items.value.length
        ? h('ul', { class: 'rows' }, items.value.map(item => h('li', { key: item.id }, [
          h('div', [
            h('strong', item.title),
            h('span', ` · ${statusText(item)} · ${scheduleText(item)}`),
            teacher() && h('span', ` · 关联 ${linkCount(item)}`),
          ]),
          !teacher() && quizCell(item),
          teacher() && teacherActions(item),
        ])))
        : h('p', teacher() ? '暂无备课，先创建草稿。' : '老师还没有发布预习内容。')),
      courseId.value && total.value > 20 && h('div', { class: 'actions preparation-pager' }, [
        button('上一页', () => { page.value--; run(loadList) }, { disabled: busy.value || page.value <= 1 }),
        h('span', `第 ${page.value} 页 / 共 ${Math.ceil(total.value / 20)} 页`),
        button('下一页', () => { page.value++; run(loadList) }, { disabled: busy.value || page.value >= Math.ceil(total.value / 20) }),
      ]),
      modalView(),
    ])
  },
}
