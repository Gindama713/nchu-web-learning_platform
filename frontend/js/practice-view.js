import { h, onMounted, onUnmounted, ref, watch } from 'vue'
import { PracticeClient, practicePayload } from './practice-client.js'
import { questionTypes } from './question-client.js'

const show = value => Array.isArray(value) ? value.join('、') : typeof value === 'boolean' ? (value ? '正确' : '错误') : String(value)

export const PracticeView = {
  props: { user: { type: Object, required: true }, entry: { type: Object, default: null } },
  setup(props) {
    let api = new PracticeClient(props.user), epoch = 0
    const courses = ref([]), course = ref(''), mode = ref('public'), knowledge = ref(''), tags = ref([])
    const rows = ref([]), page = ref(1), total = ref(0), selected = ref(null), value = ref(null)
    const pending = ref(null), result = ref(null), busy = ref(false), error = ref(''), notice = ref('')
    function clear() { rows.value = []; total.value = 0; selected.value = null; value.value = null; pending.value = null; result.value = null }
    async function run(action, writing = false) {
      if (busy.value) return
      const ticket = epoch
      busy.value = true; error.value = ''; notice.value = ''
      try {
        await api.verifySession()
        if (ticket === epoch && props.user.role === 'student') await action(ticket)
      } catch (failure) {
        if (ticket !== epoch) return
        error.value = failure.message
        // Unknown delivery keeps a locked payload for exact retry. Known rejection
        // and permission/protection failures discard displayed explanations.
        if (!writing || !pending.value || [400, 401, 403, 404, 409].includes(failure.status)) clear()
        if ([401, 403, 404].includes(failure.status)) { courses.value = []; course.value = ''; tags.value = [] }
      } finally { if (ticket === epoch) busy.value = false }
    }
    async function load(ticket, keepResult = false) {
      rows.value = []; total.value = 0
      if (!keepResult) { selected.value = null; result.value = null; pending.value = null; value.value = null }
      if (mode.value === 'public' && !course.value) return
      const data = mode.value === 'wrong' ? await api.wrong({ page: page.value, knowledgeId: knowledge.value })
        : await api.questions(course.value, { page: page.value, knowledgeId: knowledge.value })
      if (ticket !== epoch) return
      rows.value = data.data; total.value = data.total
      tags.value = [...new Set([...tags.value, ...data.data.flatMap(item => item.knowledge_ids)])].sort((a, b) => a - b)
    }
    async function boot(ticket) {
      clear(); courses.value = []
      const available = await api.courses()
      if (ticket !== epoch) return
      courses.value = available
      if (!available.some(c => String(c.id) === course.value)) course.value = available.length ? String(available[0].id) : ''
      await load(ticket)
    }
    async function openEntry(ticket) {
      const entry = props.entry
      if (!entry) return boot(ticket)
      clear(); courses.value = []; tags.value = []
      const available = await api.courses()
      if (ticket !== epoch) return
      if (!available.some(row => String(row.id) === String(entry.courseId))) throw Object.assign(new Error('推荐课程已不可访问。'), { status: 404 })
      courses.value = available; course.value = String(entry.courseId); knowledge.value = String(entry.knowledgeId)
      mode.value = 'public'; page.value = 1
      for (;;) {
        await load(ticket)
        if (ticket !== epoch) return
        const question = rows.value.find(row => row.version_id === entry.versionId && row.practice_available && row.type !== 'short')
        if (question) { choose(question); return }
        if (!rows.value.length || page.value * 20 >= total.value) throw new Error('推荐练习已变化或不可用，请刷新推荐。')
        page.value++
      }
    }
    watch(() => props.entry, () => {
      if (pending.value) { notice.value = '请先确认或重试当前练习，再打开推荐练习。'; return }
      epoch++; busy.value = false; clear()
      if (props.user.role === 'student') run(openEntry)
    })
    function change(action) {
      epoch++; busy.value = false; clear(); page.value = 1; action(); run(ticket => load(ticket))
    }
    function choose(item) {
      if (pending.value) return
      selected.value = item; value.value = null; result.value = null; error.value = ''; notice.value = ''
    }
    async function send(ticket) {
      if (!pending.value) pending.value = { questionId: selected.value.id,
        payload: practicePayload(selected.value, value.value), key: crypto.randomUUID() }
      const data = await api.practice(pending.value.questionId, pending.value.payload, pending.value.key)
      if (ticket !== epoch) return
      result.value = data; pending.value = null
      notice.value = data.correct ? '作答正确；已有错题标记为已掌握。' : '本次得0分；实际错答会保留在错题本。'
      await load(ticket, true)
    }
    watch(() => `${props.user.id}:${props.user.role}`, () => {
      epoch++; busy.value = false; clear(); courses.value = []; course.value = ''; tags.value = []; knowledge.value = ''
      api = new PracticeClient(props.user)
      if (props.user.role === 'student') run(boot)
    })
    onMounted(() => { if (props.user.role === 'student') run(props.entry ? openEntry : boot) })
    onUnmounted(() => { epoch++ })
    const button = (text, action, disabled = false) => h('button', { type: 'button', disabled: busy.value || disabled, onClick: action }, text)
    const select = (label, val, update, options) => h('label', [label, h('select', { 'aria-label': label, value: val,
      disabled: busy.value || !!pending.value, onChange: e => update(e.target.value) }, options.map(([id, name]) => h('option', { value: id }, name)))])
    function answerInput(q) {
      const locked = busy.value || !!pending.value || !!result.value
      if (q.type === 'numeric') return h('label', ['数值作答', h('input', { 'aria-label': '练习作答', type: 'number', step: 'any',
        value: value.value ?? '', disabled: locked, onInput: e => { value.value = e.target.value } })])
      const options = q.type === 'boolean' ? [{ key: true, text: '正确' }, { key: false, text: '错误' }] : q.options
      return h('div', { class: 'attempt-options' }, options.map(option => h('label', [h('input', {
        'aria-label': `练习作答 ${option.text}`, type: q.type === 'multiple' ? 'checkbox' : 'radio', name: 'practice-answer',
        checked: q.type === 'multiple' ? (value.value ?? []).includes(option.key) : value.value === option.key,
        disabled: locked, onChange: e => {
          if (q.type !== 'multiple') value.value = option.key
          else { const keys = new Set(value.value ?? []); if (e.target.checked) keys.add(option.key); else keys.delete(option.key); value.value = [...keys] }
        },
      }), option.text])))
    }
    return () => props.user.role !== 'student' ? null : h('section', { class: 'practice-bank card', 'aria-busy': busy.value }, [
      h('h2', '公开练习与个人错题'), h('p', '重练使用所选固定版本。未开放练习的题目须等待教师开放；考试答案在允许讲评后显示。'),
      h('div', { class: 'actions' }, [button('公开客观练习', () => change(() => { mode.value = 'public'; knowledge.value = ''; tags.value = [] }), !!pending.value),
        button('我的错题', () => change(() => { mode.value = 'wrong'; knowledge.value = ''; tags.value = [] }), !!pending.value),
        button('重新加载练习与错题', () => run(boot), !!pending.value)]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存练习…'),
      error.value && h('p', { role: 'alert' }, error.value), notice.value && h('p', { role: 'status' }, notice.value),
      mode.value === 'public' && select('练习课程', course.value, val => change(() => { course.value = val; tags.value = []; knowledge.value = '' }), courses.value.map(c => [String(c.id), c.title])),
      select('筛选错题或练习知识标签', knowledge.value, val => change(() => { knowledge.value = val }), [['', '全部标签'], ...tags.value.map(id => [String(id), `知识点 #${id}`])]),
      h('p', `共 ${total.value} 道${mode.value === 'wrong' ? '错题' : '公开练习题'}`),
      h('ul', { class: 'rows' }, rows.value.map(item => h('li', { key: item.id }, [
        button(`#${item.id} · v${item.version} · ${item.stem}`, () => choose(item), !!pending.value),
        mode.value === 'wrong' && h('p', `累计错答 ${item.wrong_count} 次 · ${item.resolved ? '已掌握' : '待重练'} · 来源 ${item.last_attempt_type === 'paper' ? '试卷' : '练习'}`),
      ]))),
      !rows.value.length && !busy.value && !error.value && h('p', mode.value === 'wrong' ? '暂无符合条件的错题。' : '暂无公开客观练习题。'),
      h('div', { class: 'actions' }, [button('练习错题上一页', () => { page.value--; run(ticket => load(ticket)) }, !!pending.value || page.value <= 1),
        h('span', `第 ${page.value} 页`), button('练习错题下一页', () => { page.value++; run(ticket => load(ticket)) }, !!pending.value || page.value * 20 >= total.value)]),
      selected.value && h('article', { class: 'practice-detail' }, [h('h3', `${questionTypes[selected.value.type]} · 固定版本 v${selected.value.version}`),
        h('p', { class: 'attempt-text' }, selected.value.stem),
        selected.value.answer_visible === false && h('p', '答案与解析尚受保护，请等待允许讲评。'),
        selected.value.answer_visible && Object.hasOwn(selected.value, 'answer') && h('div', { class: 'attempt-reference' }, [
          h('p', `参考答案：${show(selected.value.answer)}`), h('p', { class: 'attempt-text' }, `解析：${selected.value.explanation || '暂无'}`)]),
        (selected.value.can_practice ?? selected.value.practice_available) ? h('form', { class: 'practice-form',
          onSubmit: e => { e.preventDefault(); if (!result.value) run(send, true) } }, [answerInput(selected.value),
          h('button', { type: 'submit', disabled: busy.value || !!result.value }, pending.value ? '重试原练习' : '提交本次练习'),
          pending.value && h('p', '提交结果尚未确认，作答已锁定。重试将使用原内容。'),
          result.value && h('div', { class: 'practice-result', role: 'status' }, [h('p', `${result.value.correct ? '正确' : '错误 / 未答'} · ${result.value.score} 分`),
            h('p', { class: 'attempt-text' }, `本次解析：${result.value.explanation || '暂无'}`),
            button('再次练习此版本', () => { result.value = null; value.value = null })]),
        ]) : h('p', '该版本当前不能公开重练。可在公开客观练习中选择其他已开放题目。'),
      ]),
    ])
  },
}
