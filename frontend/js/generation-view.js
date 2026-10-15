import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { GenerationClient, generationFailure } from './generation-client.js'
import { paperKinds } from './paper-client.js'

export const GenerationView = {
  props: { user: { type: Object, required: true }, courseId: { type: String, required: true },
    quizOnly: Boolean, replayId: { type: Number, default: null } },
  emits: ['open'],
  setup(props, { emit }) {
    const api = new GenerationClient(props.user.id)
    const busy = ref(false), error = ref(''), result = ref(null), knowledge = ref([]), blocked = ref(false)
    const failureTitle = ref('')
    const replay = ref(Boolean(props.replayId))
    let active = true
    const form = reactive({ title: '', kind: props.quizOnly ? 'quiz' : 'homework', count: '3', total_points: '10.01',
      easy: '3', medium: '0', hard: '0', knowledge_ids: [], seed: '', confidential: false,
      history_until: '', replay_of: props.replayId ? String(props.replayId) : '' })
    onUnmounted(() => { active = false })
    async function run(action) {
      if (busy.value || blocked.value) return
      busy.value = true; error.value = ''; result.value = null
      try {
        await api.verifySession()
        if (active) await action()
      } catch (failure) {
        if (!active) return
        error.value = generationFailure(failure)
        failureTitle.value = failure.status ? '本次未生成草稿' : '尚未确认保存结果'
        if (!failure.status) error.value += ' 如请求已经发出，请先重新加载试卷检查，避免重复生成。'
        if ([401, 403, 404].includes(failure.status)) { knowledge.value = []; blocked.value = true }
      } finally { if (active) busy.value = false }
    }
    async function loadKnowledge() {
      const rows = await api.knowledge(props.courseId)
      if (active) knowledge.value = rows
    }
    onMounted(() => { if (!replay.value) run(loadKnowledge) })
    async function generate() {
      const data = await api.generate(props.courseId, form, replay.value)
      if (active) result.value = data
    }
    function mode(value) {
      replay.value = value; result.value = null; error.value = ''
      if (!value && !knowledge.value.length) run(loadKnowledge)
    }
    const input = (key, options = {}) => h('input', { value: form[key], disabled: busy.value || blocked.value,
      onInput: event => { form[key] = event.target.value }, ...options })
    const field = (label, control) => h('label', [h('span', label), control])
    const button = (label, action, disabled = false) => h('button', { type: 'button',
      disabled: busy.value || blocked.value || disabled, onClick: action }, label)
    return () => h('section', { class: 'generation-panel', 'aria-busy': busy.value }, [
      h('h3', '智能组卷'), h('p', '按题量、难度和知识覆盖生成草稿。选题与配分保存后可从快照重放。'),
      h('div', { class: 'actions' }, [button('首次生成', () => mode(false), !replay.value),
        button('重放已有快照', () => mode(true), replay.value)]),
      h('form', { class: 'generation-form', onSubmit: event => { event.preventDefault(); run(generate) } }, [
        field('新试卷标题', input('title', { required: true, maxlength: 100, 'aria-label': '新试卷标题' })),
        replay.value ? h('div', [field('原快照编号', input('replay_of', { required: true, inputmode: 'numeric', 'aria-label': '原快照编号' })),
          h('p', '使用原快照的选题、配分、约束和随机种子，仅修改新标题。原卷保持不变。')]) : h('div', { class: 'generation-fields' }, [
          !props.quizOnly && field('生成试卷类型', h('select', { value: form.kind, disabled: busy.value || blocked.value,
            'aria-label': '生成试卷类型', onChange: event => { form.kind = event.target.value; form.confidential = form.kind === 'exam' } },
          Object.entries(paperKinds).map(([value, label]) => h('option', { value }, label)))),
          ...[['count', '选题数量', 1, 100], ['total_points', '试卷总分', 1, 1000],
            ['easy', '简单题配额', 0, 100], ['medium', '中等题配额', 0, 100], ['hard', '困难题配额', 0, 100]].map(([key, label, min, max]) =>
            field(label, input(key, { type: 'number', min, max, step: key === 'total_points' ? '.01' : '1', required: true, 'aria-label': label }))),
          field('随机种子（可留空）', input('seed', { inputmode: 'text', 'aria-label': '随机种子（可留空）' })),
          field('历史截止（可留空）', input('history_until', { type: 'datetime-local', 'aria-label': '历史截止（可留空）' })),
          h('label', { class: 'paper-check' }, [h('input', { type: 'checkbox', checked: form.confidential,
            disabled: busy.value || blocked.value, onChange: event => { form.confidential = event.target.checked } }), '要求保密']),
          h('fieldset', { class: 'generation-knowledge', disabled: busy.value || blocked.value }, [h('legend', '必选知识点（每点至少覆盖一次，可不选）'),
            ...knowledge.value.map(item => h('label', { class: 'paper-check', key: item.id }, [h('input', {
              type: 'checkbox', checked: form.knowledge_ids.includes(item.id), onChange: event => {
                form.knowledge_ids = event.target.checked ? [...form.knowledge_ids, item.id] : form.knowledge_ids.filter(id => id !== item.id)
              } }), item.title])), !knowledge.value.length && h('p', '暂无知识点；可重新加载试卷，或先在课程中创建知识点。')]),
        ]),
        h('button', { type: 'submit', disabled: busy.value || blocked.value }, replay.value ? '重放并保存新草稿' : '生成并保存草稿'),
      ]),
      busy.value && h('p', { role: 'status' }, '正在读取或生成草稿…'),
      error.value && h('div', { role: 'alert' }, [h('h4', failureTitle.value), h('p', error.value),
        blocked.value && h('p', '请重新加载试卷以确认当前身份和课程权限。')]),
      result.value && h('div', { class: 'generation-result', role: 'status' }, [
        h('h4', '草稿已保存'), h('p', `试卷 #${result.value.paper_id} · 快照 #${result.value.generation_snapshot_id}`),
        h('p', `随机种子 ${result.value.seed_text} · ${result.value.algorithm_version}`),
        h('p', `覆盖知识点：${result.value.coverage.join('、') || '无指定覆盖'}`),
        h('ol', result.value.selected_version_ids.map((id, index) => h('li', { key: id },
          `固定版本 #${id} · ${(result.value.points_hundredths[index] / 100).toFixed(2)} 分`))),
        h('p', '草稿尚未发布。请查看题目，再设置窗口并确认发布。'),
        button('查看草稿与发布设置', () => emit('open', result.value.paper_id)),
      ]),
    ])
  },
}
