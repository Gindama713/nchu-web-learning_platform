import { h, onMounted, reactive, ref } from 'vue'
import { difficulties, emptyQuestion, QuestionClient, questionPayload, questionTypes } from './question-client.js'

export const QuestionBankView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new QuestionClient(props.user.id)
    const teacher = () => props.user.role === 'teacher'
    const courses = ref([]), courseId = ref(''), knowledge = ref([]), rows = ref([])
    const page = ref(1), total = ref(0), busy = ref(false), error = ref(''), notice = ref('')
    const knowledgeError = ref(''), editing = ref(false), editId = ref(null), selected = ref(null)
    const filters = reactive({ type: '', difficulty: '', knowledgeId: '' })
    const form = reactive(emptyQuestion())

    function clear() {
      rows.value = []; total.value = 0; selected.value = null; editing.value = false
    }
    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.status === 401 || failure.status === 404) {
          clear(); knowledge.value = []
          if (failure.status === 401) { courses.value = []; courseId.value = '' }
        }
      } finally { busy.value = false }
    }
    async function load() {
      rows.value = []; total.value = 0; selected.value = null; editing.value = false
      if (!courseId.value) return
      const result = await api.list(courseId.value, { page: page.value, ...filters })
      rows.value = result.data; total.value = result.total
    }
    async function loadCourse() {
      clear(); knowledge.value = []; knowledgeError.value = ''; page.value = 1
      filters.knowledgeId = ''
      if (!courseId.value) return
      await load()
      if (teacher()) {
        try { knowledge.value = await api.knowledge(courseId.value) } catch (failure) {
          if (failure.status === 401) throw failure
          knowledgeError.value = failure.status === 404 || failure.status === 503
            ? '知识标签暂不可用，请等待知识模块接入后重新加载。' : failure.message
        }
      }
    }
    async function boot() {
      clear(); courses.value = []; knowledge.value = []; knowledgeError.value = ''
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
    }
    function edit(item = null) {
      editId.value = item?.id ?? null
      const fresh = item ? Object.fromEntries(Object.keys(emptyQuestion()).map(key => [key, item[key]])) : emptyQuestion()
      Object.assign(form, JSON.parse(JSON.stringify(fresh)))
      editing.value = true; selected.value = null; notice.value = ''
    }
    async function save() {
      const result = editId.value ? await api.update(editId.value, questionPayload(form))
        : await api.create(courseId.value, questionPayload(form))
      await load()
      selected.value = result
    }
    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const field = (label, input) => h('label', [h('span', label), input])
    const text = (value, update, options = {}) => h('input', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const area = (value, update, options = {}) => h('textarea', {
      value, disabled: busy.value, maxlength: 5000, rows: 4, onInput: event => update(event.target.value), ...options,
    })
    const select = (value, update, values, placeholder = '') => h('select', {
      value, disabled: busy.value, onChange: event => update(event.target.value),
    }, [...(placeholder ? [h('option', { value: '' }, placeholder)] : []),
      ...Object.entries(values).map(([key, label]) => h('option', { value: key }, label))])
    const toggle = (label, checked, update) => h('label', { class: 'question-check' }, [h('input', {
      type: 'checkbox', checked, disabled: busy.value, onChange: event => update(event.target.checked),
    }), label])

    function editor() {
      const choice = form.type === 'single' || form.type === 'multiple'
      return h('form', { class: 'question-editor', onSubmit: event => {
        event.preventDefault(); run(save, '新版本已保存，旧版本保留。')
      } }, [
        h('h3', editId.value ? `编辑题目 #${editId.value}` : '新增题目'),
        field('题型', select(form.type, value => {
          const fresh = emptyQuestion(value)
          Object.assign(form, { type: value, options: fresh.options, answer: fresh.answer, tolerance: 0, practice_available: false })
        }, questionTypes)),
        field('题干', area(form.stem, value => { form.stem = value }, { required: true })),
        field('难度', select(form.difficulty, value => { form.difficulty = value }, difficulties)),
        choice && h('fieldset', [h('legend', '选项（2至8项，key须唯一）'),
          ...form.options.map((option, index) => h('div', { class: 'question-option', key: index }, [
            field(`选项 ${index + 1} key`, text(option.key, value => { option.key = value }, { required: true, maxlength: 20 })),
            field(`选项 ${index + 1} 内容`, text(option.text, value => { option.text = value }, { required: true, maxlength: 5000 })),
            button('移除选项', () => { form.options.splice(index, 1) }, { disabled: busy.value || form.options.length <= 2 }),
          ])),
          button('添加选项', () => { form.options.push({ key: '', text: '' }) }, { disabled: busy.value || form.options.length >= 8 }),
        ]),
        form.type === 'single' && field('正确答案', select(form.answer, value => { form.answer = value },
          Object.fromEntries(form.options.filter(item => item.key).map(item => [item.key, item.key])), '请选择选项key')),
        form.type === 'multiple' && h('fieldset', [h('legend', '正确答案（至少一项）'),
          ...form.options.map((option, index) => toggle(option.key || `选项 ${index + 1}`, form.answer.includes(option.key), value => {
            form.answer = value ? [...form.answer, option.key] : form.answer.filter(key => key !== option.key)
          })),
        ]),
        form.type === 'boolean' && field('正确答案', select(String(form.answer), value => { form.answer = value === 'true' }, { true: '正确', false: '错误' })),
        form.type === 'numeric' && field('正确数值', text(form.answer, value => { form.answer = value }, { type: 'number', step: 'any', required: true })),
        form.type === 'numeric' && field('允许误差', text(form.tolerance, value => { form.tolerance = value }, { type: 'number', min: 0, step: 'any', required: true })),
        form.type === 'short' && field('参考答案', area(form.answer, value => { form.answer = value }, { required: true })),
        field('解析', area(form.explanation, value => { form.explanation = value })),
        h('fieldset', [h('legend', '知识标签（至少一项）'),
          ...knowledge.value.map(item => toggle(item.title, form.knowledge_ids.includes(item.id), value => {
            form.knowledge_ids = value ? [...form.knowledge_ids, item.id] : form.knowledge_ids.filter(id => id !== item.id)
          })),
        ]),
        form.type !== 'short' && toggle('开放为公开练习（曾公开后不再具备保密资格）', form.practice_available,
          value => { form.practice_available = value }),
        h('p', '保存会生成新版本，已引用的旧版本不会改动。'),
        h('div', { class: 'actions' }, [h('button', {
          type: 'submit', disabled: busy.value || !knowledge.value.length || !form.knowledge_ids.length,
        }, '保存新版本'), button('取消编辑', () => { editing.value = false })]),
      ])
    }
    function detail(item) {
      return h('article', { class: 'question-detail' }, [h('h3', `题目 #${item.id} · 版本 ${item.version}`),
        h('p', `${questionTypes[item.type]} · ${difficulties[item.difficulty]}`),
        h('p', { class: 'question-text' }, item.stem),
        h('ul', item.options.map(option => h('li', `${option.key} · ${option.text}`))),
        teacher() && h('p', `参考答案：${JSON.stringify(item.answer)}`),
        teacher() && h('p', { class: 'question-text' }, `解析：${item.explanation || '暂无'}`),
        teacher() && button('编辑为新版本', () => edit(item), { disabled: busy.value || !knowledge.value.length }),
      ])
    }
    // 题库分布：题型与难度各一行条形图，只统计当前筛选结果
    function bars(title, labels, counts) {
      const max = Math.max(1, ...Object.keys(labels).map(code => counts.get(code) ?? 0))
      return h('div', { class: 'qb-chart' }, [
        h('p', { class: 'qb-chart-title' }, title),
        ...Object.entries(labels).map(([code, label]) => h('div', { class: 'qb-bar-row' }, [
          h('span', { class: 'qb-bar-label' }, label),
          h('div', { class: 'qb-bar-track' }, [
            h('i', { class: 'qb-bar-fill', style: `width:${Math.round(((counts.get(code) ?? 0) / max) * 100)}%` }),
          ]),
          h('span', { class: 'qb-bar-value' }, String(counts.get(code) ?? 0)),
        ])),
      ])
    }
    function distribution() {
      const typeCount = new Map(), diffCount = new Map()
      rows.value.forEach(item => {
        typeCount.set(item.type, (typeCount.get(item.type) ?? 0) + 1)
        diffCount.set(item.difficulty, (diffCount.get(item.difficulty) ?? 0) + 1)
      })
      return h('div', { class: 'qb-stats' }, [
        bars('题型分布', questionTypes, typeCount),
        bars('难度分布', difficulties, diffCount),
      ])
    }
    onMounted(() => run(boot))
    return () => h('section', { class: 'card question-bank', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [h('h2', '课程题库'), button('重新加载题库', () => run(boot))]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { role: 'alert' }, [h('p', error.value), button('重试题库', () => run(boot))]),
      notice.value && h('p', { role: 'status' }, notice.value),
      knowledgeError.value && h('p', { role: 'alert' }, knowledgeError.value),
      !courses.value.length && !busy.value && !error.value && h('p', '暂无可访问课程。'),
      courses.value.length > 0 && field('题库课程', select(courseId.value, value => {
        courseId.value = value; run(loadCourse)
      }, Object.fromEntries(courses.value.map(item => [String(item.id), item.title])))),
      courseId.value && h('div', [
        h('form', { class: 'inline-form question-filters', onSubmit: event => {
          event.preventDefault(); page.value = 1; run(load)
        } }, [field('筛选题型', select(filters.type, value => { filters.type = value }, questionTypes, '全部题型')),
          field('筛选难度', select(filters.difficulty, value => { filters.difficulty = value }, difficulties, '全部难度')),
          teacher() && knowledge.value.length > 0 && field('筛选知识点', select(filters.knowledgeId, value => {
            filters.knowledgeId = value
          }, Object.fromEntries(knowledge.value.map(item => [String(item.id), item.title])), '全部知识点')),
          h('button', { type: 'submit', disabled: busy.value }, '筛选题目'),
          teacher() && button('新增题目', () => edit(), { disabled: busy.value || !knowledge.value.length }),
        ]),
        teacher() && !knowledge.value.length && !busy.value && !knowledgeError.value && h('p', '请先在课程中创建知识点，再添加题目。'),
        h('p', { class: 'qb-total' }, `共 ${total.value} 道题目`),
        rows.value.length > 0 && distribution(),
        h('ul', { class: 'rows' }, rows.value.map(item => h('li', { key: item.id }, [
          h('button', {
            type: 'button',
            class: 'qb-item',
            onClick: () => { selected.value = item; editing.value = false },
          }, [
            h('span', { class: 'qb-item-id' }, `#${item.id} · v${item.version}`),
            h('span', { class: 'qb-item-stem' }, item.stem.slice(0, 60)),
            h('span', { class: `qb-item-tag ${item.difficulty}` }, difficulties[item.difficulty] ?? item.difficulty),
          ]),
        ]))),
        !rows.value.length && !busy.value && !error.value && h('p', '暂无符合条件的题目。'),
        h('div', { class: 'actions' }, [
          button('题库上一页', () => { page.value--; run(load) }, { disabled: busy.value || page.value <= 1 }),
          h('span', `第 ${page.value} 页`),
          button('题库下一页', () => { page.value++; run(load) }, { disabled: busy.value || page.value * 20 >= total.value }),
        ]),
        editing.value ? editor() : selected.value && detail(selected.value),
      ]),
    ])
  },
}
