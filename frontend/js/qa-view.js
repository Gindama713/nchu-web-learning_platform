import { h, onBeforeUnmount, ref, watch } from 'vue'
import { KnowledgeClient } from './knowledge-client.js'

export const QAView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new KnowledgeClient()
    const courses = ref([]), course = ref(''), question = ref(''), topK = ref(3)
    const busy = ref(false), ready = ref(false), error = ref(''), result = ref(null), source = ref(null)
    const sourceBusy = ref(false)
    let generation = 0
    function invalidate() {
      generation++
      result.value = null
      source.value = null
      error.value = ''
      busy.value = false
    }
    async function boot() {
      invalidate()
      ready.value = false
      courses.value = []
      course.value = ''
      const ticket = ++generation
      busy.value = true
      try {
        const session = await api.session()
        if (session.user.id !== props.user.id) throw new Error('登录状态已变化，请重新登录。')
        api.userId = session.user.id
        const response = await api.courses()
        if (ticket !== generation) return
        courses.value = response.items
        course.value = response.items.length ? String(response.items[0].id) : ''
        ready.value = true
      } catch (failure) {
        if (ticket === generation) error.value = failure.message
      } finally { if (ticket === generation) busy.value = false }
    }
    async function search() {
      if (busy.value || !ready.value || !course.value || !question.value.trim()) return
      invalidate()
      const ticket = ++generation, id = course.value
      busy.value = true
      try {
        const response = await api.write(`/courses/${id}/qa`, 'POST', {
          question: question.value.trim(), top_k: Number(topK.value),
        })
        if (ticket === generation) result.value = response
      } catch (failure) {
        if (ticket === generation) {
          error.value = failure.code === 'INDEX_UNAVAILABLE'
            ? '课程检索索引暂时不可用，请稍后重试查询。' : failure.message
          if ([401, 404].includes(failure.status)) ready.value = false
        }
      } finally { if (ticket === generation) busy.value = false }
    }
    async function openSource(id) {
      const ticket = ++generation
      sourceBusy.value = true
      error.value = ''
      try {
        const item = await api.detail(id)
        if (!item.published) throw new Error('该知识已下架，请重新查询。')
        // 加载完成再替换，避免旧内容先被清空造成闪白
        if (ticket === generation) source.value = item
      } catch (failure) {
        if (ticket === generation) {
          result.value = null
          error.value = failure.message
        }
      } finally { if (ticket === generation) sourceBusy.value = false }
    }
    watch(() => [props.user.id, props.user.role], boot, { immediate: true })
    onBeforeUnmount(invalidate)
    const field = (label, control) => h('label', { class: 'knowledge-field' }, [h('span', label), control])
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    return () => h('section', { class: 'knowledge-module qa-module', 'aria-label': '课程检索问答', 'aria-busy': busy.value }, [
      h('header', { class: 'knowledge-heading' }, [
        h('div', [h('p', { class: 'knowledge-kicker' }, 'CPU · 知识出处'), h('h2', '课程检索问答')]),
        button('重新加载问答课程', boot),
      ]),
      h('p', { class: 'knowledge-hint' }, '在当前课程已发布知识中查找相关片段，可打开出处继续阅读。'),
      field('问答课程', h('select', {
        value: course.value, disabled: busy.value || !ready.value, 'aria-label': '问答课程',
        onChange: event => { invalidate(); course.value = event.target.value },
      }, courses.value.map(item => h('option', { value: String(item.id) }, item.title)))),
      ready.value && !courses.value.length && h('p', '暂无可访问课程，请联系任课教师。'),
      h('form', { class: 'qa-form', onSubmit: event => { event.preventDefault(); search() } }, [
        field('你的问题', h('textarea', {
          value: question.value, maxlength: 500, required: true, rows: 3, 'aria-label': '你的问题',
          disabled: !ready.value,
          placeholder: '例如：PC 有什么作用',
          onInput: event => { invalidate(); question.value = event.target.value },
        })),
        h('div', { class: 'knowledge-actions' }, [
          field('最多显示', h('select', { value: topK.value, 'aria-label': '最多显示', disabled: !ready.value,
            onChange: event => { invalidate(); topK.value = Number(event.target.value) },
          }, [1, 2, 3, 4, 5].map(value => h('option', { value }, `${value} 条`)))),
          h('button', { class: 'primary', disabled: busy.value || !ready.value || !course.value || !question.value.trim() }, '查询课程知识'),
        ]),
      ]),
      busy.value && h('p', { role: 'status' }, '正在查询或加载出处…'),
      error.value && h('div', { class: 'knowledge-error', role: 'alert' }, [
        h('p', error.value), button(ready.value ? '重试查询' : '重新加载后重试', ready.value ? search : boot),
      ]),
      result.value && h('div', { 'aria-live': 'polite' }, [
        h('p', { role: 'status' }, result.value.reason === 'empty_corpus'
          ? '本课程暂无已发布知识，请等待教师发布后重试。'
          : result.value.reason === 'no_match' ? '未找到相关知识，请调整问题或使用课程术语。'
            : `找到 ${result.value.matches.length} 条相关知识片段。`),
        h('ol', { class: 'qa-matches' }, result.value.matches.map(item => h('li', { key: item.knowledge_id }, [
          h('div', { class: 'qa-citation' }, [
            button(`打开知识出处 #${item.knowledge_id}`, () => openSource(item.knowledge_id)),
            h('span', `相似度 ${Number(item.similarity).toFixed(6)}`),
          ]), h('p', { class: 'qa-excerpt' }, item.excerpt),
        ]))),
        h('p', { class: 'qa-meta' }, `算法 ${result.value.algorithm_version} · 语料版本 ${result.value.index_version}`),
      ]),
      sourceBusy.value && h('p', { class: 'qa-loading', role: 'status' }, '正在打开知识出处…'),
      source.value && h('article', { class: 'qa-source', 'aria-label': '知识出处正文' }, [
        h('h3', source.value.title),
        h('p', `知识出处 #${source.value.id} · 内容版本 ${source.value.content_revision}`),
        // Only the SPEC-005 sanitized, attribute-free detail is HTML; excerpts stay text.
        h('div', { class: 'knowledge-prose', innerHTML: source.value.content }),
        source.value.example && h('div', { class: 'knowledge-prose', innerHTML: source.value.example }),
      ]),
    ])
  },
}
