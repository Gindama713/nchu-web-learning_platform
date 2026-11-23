import { h, onMounted, reactive, ref } from 'vue'
import { KnowledgeClient } from './knowledge-client.js'

const blank = () => ({ title: '', content: '', example: '', published: false, is_foundational: false, images: [] })

export const KnowledgeView = {
  setup() {
    const api = new KnowledgeClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const chapters = ref([])
    const revision = ref(0)
    const chapterId = ref('')
    const query = ref('')
    const items = ref([])
    const page = ref(1)
    const total = ref(0)
    const selected = ref(null)
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const newChapter = ref('')
    const rename = reactive({})
    const editing = ref(false)
    const editId = ref(null)
    const targetChapter = ref('')
    const form = reactive(blank())
    const imageCandidates = ref([])
    const imageSources = reactive({})
    const teacher = () => session.value?.user.role === 'teacher'
    const student = () => session.value?.user.role === 'student'

    function clearCourse() {
      chapters.value = []
      items.value = []
      selected.value = null
      chapterId.value = ''
      total.value = 0
      page.value = 1
      query.value = ''
      editing.value = false
      newChapter.value = ''
      imageCandidates.value = []
      for (const key of Object.keys(imageSources)) delete imageSources[key]
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
        error.value = failure.status === 404 && !session.value
          ? '暂时无法读取登录状态。请在登录服务可用后重试。'
          : failure.message
        if (failure.status === 401) {
          session.value = null
          api.userId = null
          courses.value = []
          courseId.value = ''
          clearCourse()
        } else if (failure.status === 404) {
          selected.value = null
          editing.value = false
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
        page: page.value, q: query.value, chapterId: chapterId.value,
      })
      items.value = result.data
      total.value = result.total
    }

    async function loadChapters() {
      const result = await api.chapters(courseId.value)
      chapters.value = result.items
      revision.value = result.revision
      for (const chapter of chapters.value) rename[chapter.id] = chapter.title
    }

    async function loadImageCandidates() {
      imageCandidates.value = courseId.value ? await api.imageCandidates(courseId.value) : []
    }

    async function loadCourse() {
      clearCourse()
      if (!courseId.value) return
      await loadChapters()
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
      courses.value = (await api.courses()).items
      if (!courses.value.some(course => String(course.id) === String(courseId.value))) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
    }

    function startEdit(item = null) {
      editId.value = item?.id ?? null
      targetChapter.value = String(item?.chapter_id ?? (chapterId.value || chapters.value[0]?.id || ''))
      const images = Array.isArray(item?.images) ? item.images.map(image => ({
        resource_version_id: image.resource_version_id,
        placement: image.placement,
        alt: image.alt ?? '',
        caption: image.caption ?? '',
        version: image.version,
        resource_title: image.resource_title,
        available: image.available,
      })) : []
      Object.assign(form, item
        ? { ...Object.fromEntries(Object.keys(blank()).map(key => [key, item[key]])), images }
        : blank())
      editing.value = true
      notice.value = ''
      if (teacher()) run(loadImageCandidates)
    }

    async function save() {
      const values = {
        ...form,
        images: form.images.map(image => ({
          resource_version_id: image.resource_version_id,
          placement: image.placement,
          alt: image.alt,
          caption: image.caption,
        })),
      }
      const result = editId.value
        ? await api.update(editId.value, values)
        : await api.create(targetChapter.value, values)
      editing.value = false
      await loadChapters()
      await loadList()
      selected.value = await api.detail(result.id)
    }

    async function move(index, direction) {
      const ids = chapters.value.map(chapter => chapter.id)
      const next = index + direction
      ;[ids[index], ids[next]] = [ids[next], ids[index]]
      await api.reorder(courseId.value, revision.value, ids)
      await loadChapters()
      await loadList()
    }

    async function setPersonal(kind) {
      const id = selected.value.id
      if (kind === 'bookmark') await api.bookmark(id, !selected.value.is_bookmarked)
      else await api.progress(id, !selected.value.progress.completed)
      selected.value = await api.detail(id)
    }

    onMounted(() => run(boot))
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const textInput = (value, update, options = {}) => h('input', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const field = (label, control) => h('label', { class: 'knowledge-field' }, [h('span', label), control])
    const chooseChapter = (value, update, options = {}) => h('select', {
      value, disabled: busy.value, onChange: event => update(event.target.value), ...options,
    }, chapters.value.map(chapter => h('option', { value: String(chapter.id) }, chapter.title)))

    const placementLabel = value => value === 'example' ? '例题后' : '正文后'

    function imageOptions(image) {
      const options = imageCandidates.value.map(candidate => ({
        value: String(candidate.resource_version_id),
        label: `${candidate.resource_title} · v${candidate.version} · ${candidate.width}×${candidate.height}`,
      }))
      if (image && !options.some(option => option.value === String(image.resource_version_id))) {
        options.unshift({
          value: String(image.resource_version_id),
          label: `${image.resource_title ?? '当前图片'} · v${image.version ?? '?'}（不可用）`,
        })
      }
      return options
    }

    function chooseImageVersion(image, value) {
      image.resource_version_id = Number(value)
      const candidate = imageCandidates.value.find(item => String(item.resource_version_id) === String(value))
      if (candidate) {
        image.version = candidate.version
        image.resource_title = candidate.resource_title
        image.available = true
      }
    }

    function addImage() {
      const candidate = imageCandidates.value[0]
      if (!candidate) {
        notice.value = '暂无可选图片，请先到“教学资源”上传 guide 类型的 PNG/JPEG'
        return
      }
      form.images.push({
        resource_version_id: candidate.resource_version_id,
        placement: 'content',
        alt: '',
        caption: '',
        version: candidate.version,
        resource_title: candidate.resource_title,
        available: true,
      })
    }

    function moveImage(index, direction) {
      const next = index + direction
      if (next < 0 || next >= form.images.length) return
      ;[form.images[index], form.images[next]] = [form.images[next], form.images[index]]
    }

    function imageEditor() {
      return h('section', { class: 'knowledge-image-editor' }, [
        h('h4', '知识点图片'),
        h('p', { class: 'knowledge-hint' },
          '图片来自本课程 guide 资源的固定版本；先在教学资源上传 PNG/JPEG，再在这里选择。'),
        ...form.images.map((image, index) => h('div', {
          class: 'knowledge-image-row', key: `${index}-${image.resource_version_id}`,
        }, [
          h('label', { class: 'knowledge-field' }, [h('span', '图片来源'), h('select', {
            value: String(image.resource_version_id), disabled: busy.value,
            onChange: event => chooseImageVersion(image, event.target.value),
          }, imageOptions(image).map(option => h('option', { value: option.value }, option.label)))]),
          h('label', { class: 'knowledge-field' }, [h('span', '位置'), h('select', {
            value: image.placement, disabled: busy.value,
            onChange: event => { image.placement = event.target.value },
          }, ['content', 'example'].map(value => h('option', { value }, placementLabel(value))))]),
          h('label', { class: 'knowledge-field' }, [h('span', '替代文本'), textInput(
            image.alt, value => { image.alt = value }, { maxlength: 200, placeholder: '给无法显示图片的读者' })]),
          h('label', { class: 'knowledge-field' }, [h('span', '图注'), textInput(
            image.caption, value => { image.caption = value }, { maxlength: 200, placeholder: '可选' })]),
          h('div', { class: 'knowledge-actions' }, [
            button('上移', () => moveImage(index, -1), { disabled: busy.value || index === 0 }),
            button('下移', () => moveImage(index, 1),
              { disabled: busy.value || index === form.images.length - 1 }),
            button('移除', () => form.images.splice(index, 1), { disabled: busy.value }),
          ]),
        ])),
        h('div', { class: 'knowledge-actions' }, [
          button('添加图片', addImage, { disabled: busy.value || !imageCandidates.value.length }),
        ]),
        !imageCandidates.value.length && h('p', { class: 'knowledge-hint' },
          '暂无可选图片。请先到“教学资源”上传 guide 类型的 PNG/JPEG。'),
      ])
    }

    function imageSource(image) {
      const key = `${selected.value?.id}:${image.id}`
      if (!imageSources[key]) imageSources[key] = api.imageUrl(selected.value.id, image.id)
      return imageSources[key]
    }

    function imageFigures(placement) {
      return (selected.value?.images ?? [])
        .filter(image => image.placement === placement)
        .map(image => h('figure', { class: 'knowledge-figure', key: image.id }, image.available === false
          ? [h('div', { class: 'knowledge-image-unavailable' }, '图片当前不可用')]
          : [
              h('img', { src: imageSource(image), alt: image.alt || '', loading: 'lazy' }),
              image.caption && h('figcaption', image.caption),
            ]))
    }

    function editor() {
      return h('form', {
        class: 'knowledge-editor', onSubmit: event => {
          event.preventDefault()
          run(save, '知识已保存')
        },
      }, [
        h('h3', editId.value ? '编辑知识点' : '新增知识点'),
        !editId.value && field('所属章节', chooseChapter(targetChapter.value, value => { targetChapter.value = value }, { required: true })),
        field('标题', textInput(form.title, value => { form.title = value }, { required: true, maxlength: 100 })),
        field('正文', h('textarea', {
          value: form.content, required: true, maxlength: 5000, rows: 9, disabled: busy.value,
          onInput: event => { form.content = event.target.value },
        })),
        h('small', '支持文字及基础 HTML 排版；公式可用 sub/sup。正文和例题里的图片/链接标签仍会被移除，图片请用下方图片区。'),
        field('例题', h('textarea', {
          value: form.example, maxlength: 5000, rows: 4, disabled: busy.value,
          onInput: event => { form.example = event.target.value },
        })),
        imageEditor(),
        ...[['published', '发布后学生可见'], ['is_foundational', '标记为基础知识']].map(([key, label]) =>
          h('label', { class: 'knowledge-check' }, [h('input', {
            type: 'checkbox', checked: form[key], disabled: busy.value,
            onChange: event => { form[key] = event.target.checked },
          }), label])),
        h('div', { class: 'knowledge-actions' }, [
          h('button', { type: 'submit', disabled: busy.value || !targetChapter.value, class: 'primary' }, '保存知识'),
          button('取消编辑', () => { editing.value = false }),
        ]),
      ])
    }

    function detail() {
      const item = selected.value
      if (!item) return h('div', { class: 'knowledge-placeholder' }, [
        h('h3', '选择一个知识点'), h('p', '从列表打开知识正文、例题和学习状态。'),
      ])
      return h('article', { class: 'knowledge-detail' }, [
        h('div', { class: 'knowledge-detail-meta' }, [
          h('span', { class: 'knowledge-status' }, item.published ? '已发布' : '草稿 / 已下架'),
          item.is_foundational && h('span', { class: 'knowledge-status foundational' }, '基础知识'),
        ]),
        h('h3', item.title),
        // Only SPEC-005 server-sanitized, attribute-free markup is rendered as HTML.
        h('div', { class: 'knowledge-prose', innerHTML: item.content }),
        ...imageFigures('content'),
        (item.example || (item.images ?? []).some(image => image.placement === 'example'))
          && h('section', { class: 'knowledge-example' }, [
            h('h4', '例题'),
            item.example && h('div', { class: 'knowledge-prose', innerHTML: item.example }),
            ...imageFigures('example'),
          ]),
        student() && h('div', { class: 'knowledge-actions' }, [
          button(item.is_bookmarked ? '取消收藏' : '收藏知识点', () => run(() => setPersonal('bookmark'), '收藏状态已保存'),
            { 'aria-pressed': item.is_bookmarked }),
          button(item.progress.completed ? '取消完成' : '标记完成', () => run(() => setPersonal('progress'), '完成状态已保存'),
            { 'aria-pressed': item.progress.completed, class: 'primary' }),
        ]),
        student() && h('p', { class: 'knowledge-hint' }, item.progress.completed
          ? '已标记完成。该状态代表你的学习进度。' : '阅读后可标记完成，便于继续学习。'),
        teacher() && h('div', { class: 'knowledge-actions' }, [
          button('编辑知识', () => startEdit(item)),
          button(item.published ? '下架知识' : '发布知识', () => run(async () => {
            await api.update(item.id, { published: !item.published })
            selected.value = await api.detail(item.id)
            await loadChapters()
            await loadList()
          }, item.published ? '知识已下架，历史进度保留' : '知识已发布')),
        ]),
      ])
    }

    return () => h('section', { class: 'knowledge-module', 'aria-labelledby': 'knowledge-title', 'aria-busy': busy.value }, [
      h('header', { class: 'knowledge-heading' }, [
        h('div', [h('p', { class: 'knowledge-kicker' }, 'CPU · 课程知识'), h('h2', { id: 'knowledge-title' }, '章节与知识')]),
        button('重新加载', () => run(boot)),
      ]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { class: 'knowledge-error', role: 'alert' }, [
        h('strong', '暂时无法完成操作'), h('p', error.value),
        button('重试加载', () => run(boot)),
      ]),
      notice.value && h('p', { class: 'knowledge-notice', role: 'status' }, notice.value),
      !session.value && !busy.value && !error.value && h('p', '登录后即可查看课程知识。'),
      session.value && h('div', { class: 'knowledge-course' }, [
        field('当前课程', h('select', {
          value: courseId.value, disabled: busy.value || !courses.value.length,
          onChange: event => { courseId.value = event.target.value; run(loadCourse) },
        }, courses.value.length ? courses.value.map(course => h('option', { value: String(course.id) }, course.title))
          : [h('option', { value: '' }, '暂无可访问课程')])),
        h('span', `${session.value.user.name} · ${teacher() ? '教师' : student() ? '学生' : '管理员只读'}`),
      ]),
      session.value && !courses.value.length && !busy.value && h('p', '还没有可访问的课程，请联系任课教师确认课程成员。'),
      courseId.value && session.value && h('div', { class: 'knowledge-layout' }, [
        h('aside', { class: 'knowledge-chapters', 'aria-label': '课程章节' }, [
          h('h3', '章节目录'),
          button('全部章节', () => { chapterId.value = ''; page.value = 1; selected.value = null; editing.value = false; run(loadList) },
            { class: !chapterId.value ? 'chapter-selected' : '' }),
          h('ol', chapters.value.map((chapter, index) => h('li', { key: chapter.id }, [
            button(chapter.title, () => {
              chapterId.value = String(chapter.id); page.value = 1; selected.value = null; editing.value = false; run(loadList)
            }, { class: String(chapter.id) === chapterId.value ? 'chapter-selected' : '' }),
            teacher() && h('details', [h('summary', '管理章节'),
              field('章节名称', textInput(rename[chapter.id], value => { rename[chapter.id] = value }, { maxlength: 100 })),
              button('保存名称', () => run(async () => {
                await api.renameChapter(chapter.id, rename[chapter.id]); await loadChapters()
              }, '章节名称已保存')),
              h('div', { class: 'knowledge-actions' }, [
                button('上移', () => run(() => move(index, -1), '章节顺序已保存'), { disabled: busy.value || index === 0 }),
                button('下移', () => run(() => move(index, 1), '章节顺序已保存'), { disabled: busy.value || index === chapters.value.length - 1 }),
              ]),
            ]),
          ]))),
          !chapters.value.length && h('p', teacher() ? '先新增章节，再编写知识点。' : '暂无包含已发布知识的章节。'),
          teacher() && h('form', { class: 'knowledge-new-chapter', onSubmit: event => {
            event.preventDefault()
            run(async () => { await api.addChapter(courseId.value, newChapter.value); newChapter.value = ''; await loadChapters() }, '章节已新增')
          } }, [
            field('新章节名称', textInput(newChapter.value, value => { newChapter.value = value }, { required: true, maxlength: 100 })),
            h('button', { type: 'submit', disabled: busy.value }, '新增章节'),
          ]),
        ]),
        h('div', { class: 'knowledge-content' }, [
          h('form', { class: 'knowledge-search', onSubmit: event => {
            event.preventDefault(); page.value = 1; selected.value = null; editing.value = false; run(loadList)
          } }, [
            field('检索知识', textInput(query.value, value => { query.value = value }, { maxlength: 100, placeholder: '输入标题、正文或例题关键词' })),
            h('button', { type: 'submit', class: 'primary', disabled: busy.value }, '检索'),
            teacher() && button('新增知识', () => startEdit(), { disabled: busy.value || !chapters.value.length }),
          ]),
          h('p', { class: 'knowledge-hint' }, `共 ${total.value} 个知识点${chapterId.value ? ' · 当前章节' : ''}`),
          h('div', { class: 'knowledge-reading' }, [
            h('div', { class: 'knowledge-results' }, [
              ...items.value.map(item => button(item.title, () => run(async () => {
                selected.value = null; editing.value = false; selected.value = await api.detail(item.id)
              }), { key: item.id, class: selected.value?.id === item.id ? 'result-selected' : '' })),
              !items.value.length && !busy.value && h('p', query.value ? '没有匹配知识，请调整关键词。' : '暂无知识点。'),
              h('div', { class: 'knowledge-pagination' }, [
                button('上一页', () => { page.value--; run(loadList) }, { disabled: busy.value || page.value === 1 }),
                h('span', `第 ${page.value} 页`),
                button('下一页', () => { page.value++; run(loadList) }, { disabled: busy.value || page.value * 20 >= total.value }),
              ]),
            ]),
            h('div', { class: 'knowledge-reader' }, editing.value ? editor() : detail()),
          ]),
        ]),
      ]),
    ])
  },
}
