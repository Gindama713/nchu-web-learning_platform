// SPEC-003 teaching resources view: upload, versions, preview/download, import.
import { h, onMounted, reactive, ref } from 'vue'
import { ResourceClient, contentUrl } from './resource-client.js'

const KINDS = [
  ['slides', '课件'], ['video', '视频'], ['guide', '实验指导'], ['question_bank', '题库'],
]
const kindLabel = value => KINDS.find(([key]) => key === value)?.[1] ?? value
const humanSize = bytes => bytes == null ? '' :
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : `${Math.ceil(bytes / 1024)} KiB`

export const ResourceView = {
  setup() {
    const api = new ResourceClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const chapters = ref([])
    const query = ref('')
    const kind = ref('')
    const chapterId = ref('')
    const items = ref([])
    const page = ref(1)
    const total = ref(0)
    const versions = reactive({})
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const uploadForm = reactive({ title: '', kind: 'slides', chapter_id: '' })
    const uploadFile = ref(null)
    const versionFile = reactive({})
    const versionNote = reactive({})
    const editTitle = reactive({})
    const editVisibility = reactive({})
    const teacher = () => session.value?.user.role === 'teacher'
    const student = () => session.value?.user.role === 'student'

    function clearCourse() {
      chapters.value = []
      items.value = []
      total.value = 0
      page.value = 1
      query.value = ''
      kind.value = ''
      chapterId.value = ''
      for (const key of Object.keys(versions)) delete versions[key]
      for (const key of Object.keys(versionFile)) delete versionFile[key]
      for (const key of Object.keys(versionNote)) delete versionNote[key]
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
      items.value = []
      total.value = 0
      const result = await api.list(courseId.value, {
        page: page.value, q: query.value, kind: kind.value, chapterId: chapterId.value,
      })
      items.value = result.data
      total.value = result.total
    }

    async function loadCourse() {
      clearCourse()
      if (!courseId.value) return
      chapters.value = await api.chapters(courseId.value)
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

    async function upload() {
      const file = uploadFile.value?.files?.[0]
      if (!file) throw new Error('请选择要上传的文件')
      const form = new FormData()
      form.append('file', file)
      form.append('title', uploadForm.title)
      form.append('kind', uploadForm.kind)
      if (uploadForm.chapter_id) form.append('chapter_id', uploadForm.chapter_id)
      await api.upload(courseId.value, form)
      uploadForm.title = ''
      uploadFile.value.value = ''
      await loadList()
    }

    async function loadVersions(resourceId) {
      const result = await api.versions(resourceId)
      versions[resourceId] = result.data
    }

    async function addVersion(resourceId) {
      const file = versionFile[resourceId]?.files?.[0]
      if (!file) throw new Error('请选择新版本文件')
      const form = new FormData()
      form.append('file', file)
      if (versionNote[resourceId]) form.append('change_note', versionNote[resourceId])
      await api.addVersion(resourceId, form)
      versionFile[resourceId].value = ''
      versionNote[resourceId] = ''
      await loadVersions(resourceId)
      await loadList()
    }

    async function saveEdit(item) {
      const data = {}
      const title = editTitle[item.id] ?? ''
      const visibility = editVisibility[item.id] ?? item.visibility
      if (title && title !== item.title) data.title = title
      if (visibility !== item.visibility) data.visibility = visibility
      if (!Object.keys(data).length) throw new Error('没有需要保存的修改')
      await api.update(item.id, data)
      editTitle[item.id] = ''
      editVisibility[item.id] = ''
      await loadList()
    }

    async function importBank(resourceId, versionId) {
      return api.importQuestions(resourceId, versionId)
    }

    // 每次点击生成新 event_id：一次明确的预览或一次明确的下载各计一次逻辑访问。
    function openContent(versionId, intent) {
      window.open(contentUrl(versionId, intent, crypto.randomUUID()), intent === 'download' ? '_self' : '_blank')
    }

    onMounted(() => run(boot))
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)

    function versionRows(resourceId) {
      return h('details', { onToggle: event => { if (event.target.open) run(() => loadVersions(resourceId)) } }, [
        h('summary', '版本历史'),
        versions[resourceId] && h('table', { class: 'resource-table' }, [
          h('thead', h('tr', [h('th', '版本'), h('th', '大小'), h('th', '更新说明'), h('th', '操作')])),
          h('tbody', versions[resourceId].map(row => h('tr', { key: row.id }, [
            h('td', `v${row.version}`),
            h('td', humanSize(row.size)),
            h('td', row.change_note ?? ''),
            h('td', { class: 'resource-actions' }, [
              row.kind !== 'question_bank' && button('预览', () => openContent(row.id, 'view')),
              button('下载', () => openContent(row.id, 'download')),
              teacher() && row.kind === 'question_bank' && button('导入题库',
                () => run(() => importBank(resourceId, row.id), '题库已按整批导入，可在题目模块查看')),
            ]),
          ]))),
        ]),
        teacher() && h('form', { class: 'resource-version-form', onSubmit: event => {
          event.preventDefault()
          run(() => addVersion(resourceId), '新版本已保存，旧版本仍可访问')
        } }, [
          h('input', { type: 'file', ref: el => { versionFile[resourceId] = el }, disabled: busy.value }),
          h('input', {
            value: versionNote[resourceId] ?? '', maxlength: 500, placeholder: '更新说明（可选）',
            disabled: busy.value, onInput: event => { versionNote[resourceId] = event.target.value },
          }),
          h('button', { type: 'submit', disabled: busy.value }, '上传新版本'),
        ]),
      ])
    }

    return () => h('section', { class: 'resource-module card', 'aria-labelledby': 'resource-title', 'aria-busy': busy.value }, [
      h('h2', { id: 'resource-title' }, '教学资源'),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { class: 'resource-error', role: 'alert' }, [h('strong', '暂时无法完成操作'), h('p', error.value)]),
      notice.value && h('p', { class: 'resource-notice', role: 'status' }, notice.value),
      !session.value && !busy.value && !error.value && h('p', '登录后即可查看教学资源。'),
      session.value && !courses.value.length && h('p', '还没有可访问的课程。'),
      session.value && courses.value.length && h('div', { class: 'resource-course' }, [
        h('label', ['当前课程 ', h('select', {
          value: courseId.value, disabled: busy.value,
          onChange: event => { courseId.value = event.target.value; run(loadCourse) },
        }, courses.value.map(course => h('option', { value: String(course.id) }, course.title)))]),
        h('span', `${session.value.user.name} · ${teacher() ? '教师' : student() ? '学生' : '管理员只读'}`),
      ]),
      courseId.value && h('form', { class: 'resource-search', onSubmit: event => {
        event.preventDefault(); page.value = 1; run(loadList)
      } }, [
        h('label', ['检索 ', h('input', {
          value: query.value, maxlength: 100, placeholder: '按标题检索', disabled: busy.value,
          onInput: event => { query.value = event.target.value },
        })]),
        h('label', ['类型 ', h('select', {
          value: kind.value, disabled: busy.value,
          onChange: event => { kind.value = event.target.value },
        }, [h('option', { value: '' }, '全部类型'),
          ...(teacher() ? KINDS : KINDS.filter(([key]) => key !== 'question_bank'))
            .map(([key, label]) => h('option', { value: key }, label))])]),
        chapters.value.length > 0 && h('label', ['章节 ', h('select', {
          value: chapterId.value, disabled: busy.value,
          onChange: event => { chapterId.value = event.target.value },
        }, [h('option', { value: '' }, '全部章节'),
          chapters.value.map(chapter => h('option', { value: String(chapter.id) }, chapter.title))])]),
        h('button', { type: 'submit', disabled: busy.value }, '检索'),
      ]),
      courseId.value && teacher() && h('form', { class: 'resource-upload', onSubmit: event => {
        event.preventDefault()
        run(upload, '资源已上传，当前为第 1 版')
      } }, [
        h('h3', '上传资源'),
        h('label', ['标题 ', h('input', {
          value: uploadForm.title, maxlength: 100, required: true, disabled: busy.value,
          onInput: event => { uploadForm.title = event.target.value },
        })]),
        h('label', ['类型 ', h('select', {
          value: uploadForm.kind, disabled: busy.value,
          onChange: event => { uploadForm.kind = event.target.value },
        }, KINDS.map(([key, label]) => h('option', { value: key }, label)))]),
        chapters.value.length > 0 && h('label', ['章节 ', h('select', {
          value: uploadForm.chapter_id, disabled: busy.value,
          onChange: event => { uploadForm.chapter_id = event.target.value },
        }, [h('option', { value: '' }, '不关联章节'),
          chapters.value.map(chapter => h('option', { value: String(chapter.id) }, chapter.title))])]),
        h('label', ['文件 ', h('input', {
          type: 'file', required: true, disabled: busy.value,
          ref: el => { uploadFile.value = el },
        })]),
        h('small', '文档/题库最大 20MiB，视频最大 100MiB；题库源文件仅教师可见。'),
        h('button', { type: 'submit', disabled: busy.value }, '上传'),
      ]),
      courseId.value && h('table', { class: 'resource-table' }, [
        h('thead', h('tr', [h('th', '标题'), h('th', '类型'), h('th', '章节'), h('th', '最新版'), h('th', '大小'), h('th', '操作')])),
        h('tbody', items.value.length ? items.value.map(item => h('tr', { key: item.id }, [
          h('td', item.title),
          h('td', kindLabel(item.kind)),
          h('td', chapters.value.find(chapter => String(chapter.id) === String(item.chapter_id))?.title ?? '—'),
          h('td', item.latest_version ? `v${item.latest_version}` : '—'),
          h('td', humanSize(item.size)),
          h('td', { class: 'resource-actions' }, [
            item.kind !== 'question_bank' && button('预览', () => openContent(item.latest_version_id, 'view')),
            button('下载', () => openContent(item.latest_version_id, 'download')),
            teacher() && h('details', { class: 'resource-edit' }, [
              h('summary', '编辑属性'),
              h('form', { onSubmit: event => {
                event.preventDefault()
                run(() => saveEdit(item), '资源属性已更新')
              } }, [
                h('label', ['标题 ', h('input', {
                  value: editTitle[item.id] ?? '', maxlength: 100, placeholder: item.title, disabled: busy.value,
                  onInput: event => { editTitle[item.id] = event.target.value },
                })]),
                item.kind !== 'question_bank' && h('label', ['可见性 ', h('select', {
                  value: editVisibility[item.id] ?? item.visibility, disabled: busy.value,
                  onChange: event => { editVisibility[item.id] = event.target.value },
                }, [h('option', { value: 'students' }, '学生可见'),
                  h('option', { value: 'teacher_only' }, '仅教师')])]),
                h('button', { type: 'submit', disabled: busy.value }, '保存'),
              ]),
            ]),
            versionRows(item.id),
          ]),
        ])) : [h('tr', h('td', { colspan: 6 }, '暂无资源。'))]),
      ]),
      courseId.value && total.value > 20 && h('div', { class: 'resource-pager' }, [
        button('上一页', () => { page.value--; run(loadList) }, { disabled: busy.value || page.value <= 1 }),
        h('span', `第 ${page.value} 页 / 共 ${Math.ceil(total.value / 20)} 页`),
        button('下一页', () => { page.value++; run(loadList) }, { disabled: busy.value || page.value >= Math.ceil(total.value / 20) }),
      ]),
    ])
  },
}
