// SPEC-007 classroom demo view: teacher projection control and student read-only sync.
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { DemoClient } from './demo-client.js'

const PRESETS = { gate: '门电路', comb: '组合', sequential: '时序', alu: 'ALU', memory: '存储', cpu: 'CPU' }
const SIGNALS = [['fetch', '取指'], ['decode', '译码'], ['execute', '执行'], ['mem_wr', '写存'], ['halt', '停机']]
const hex2 = value => String(value ?? 0).padStart(2, '0').toUpperCase()
const when = value => (value ? value.slice(0, 16).replace('T', ' ') : '—')
const short = (text, size = 40) => (text && text.length > size ? `${text.slice(0, size)}…` : text ?? '')

export const DemoView = {
  setup() {
    const api = new DemoClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const items = ref([])
    const total = ref(0)
    const current = ref(null)
    const form = reactive({ preset: 'gate' })
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    let timer = null

    const teacher = () => session.value?.user.role === 'teacher'

    function stopPoll() {
      if (timer) { globalThis.clearInterval(timer); timer = null }
    }

    function closeDetail() {
      current.value = null
      stopPoll()
    }

    function clearCourse() {
      items.value = []
      total.value = 0
      closeDetail()
    }

    function resetAuth() {
      session.value = null
      api.userId = null
      courses.value = []
      courseId.value = ''
      clearCourse()
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
        if (failure.status === 401) resetAuth()
      } finally {
        busy.value = false
      }
    }

    async function loadList() {
      if (!courseId.value) return
      const result = await api.list(courseId.value)
      items.value = result.data
      total.value = result.total
    }

    async function loadCourse() {
      clearCourse()
      if (!courseId.value) return
      await loadList()
    }

    async function boot() {
      resetAuth()
      const fresh = await api.session()
      api.userId = fresh.user.id
      session.value = fresh
      courses.value = await api.courses()
      if (!courses.value.some(course => String(course.id) === String(courseId.value))) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
    }

    async function create() {
      await api.create(courseId.value, form.preset)
      await loadList()
    }

    async function open(item) {
      const fresh = await api.get(item.id)
      current.value = fresh
      startPoll()
    }

    function startPoll() {
      stopPoll()
      timer = globalThis.setInterval(async () => {
        if (!current.value) return stopPoll()
        try {
          const fresh = await api.get(current.value.id)
          if (current.value && fresh.id === current.value.id) current.value = fresh
        } catch (failure) {
          error.value = failure.message
          stopPoll()
          if (failure.status === 401) resetAuth()
        }
      }, 1000)
    }

    async function advance(action) {
      if (!current.value) return
      current.value = await api.advance(current.value.id, current.value.revision, action)
    }

    async function closeSession() {
      if (!current.value) return
      current.value = await api.close(current.value.id, current.value.revision)
      await loadList()
    }

    onMounted(() => run(boot))
    onUnmounted(stopPoll)

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)

    const pairs = rows => h('table', { class: 'demo-state' }, h('tbody', rows.map(([label, value]) =>
      h('tr', { key: label }, [h('th', { scope: 'row' }, label), h('td', String(value ?? '—'))]))))

    function signals(control) {
      return h('p', { class: 'demo-signals' }, SIGNALS.map(([key, label]) =>
        h('span', { key, class: control?.[key] ? 'demo-signal on' : 'demo-signal' }, label)))
    }

    function grid(bytes, highlight = -1) {
      return h('div', { class: 'demo-grid' }, (bytes ?? []).map((byte, index) =>
        h('span', { key: index, class: index === highlight ? 'demo-byte on' : 'demo-byte' }, hex2(byte))))
    }

    function stage(demo) {
      const state = demo.state ?? {}
      const head = [
        h('p', { class: 'demo-message' }, short(state.message, 60)),
        h('p', { class: 'demo-step' }, `第 ${state.step ?? 0} 步 · 版本 ${demo.revision}`),
      ]
      let body
      if (demo.preset === 'gate') {
        const input = state.inputs ?? {}
        const output = state.outputs ?? {}
        body = [
          pairs([['输入 A', input.a], ['输入 B', input.b], ['输入 C', input.c], ['输入 D', input.d]]),
          pairs([['与门', output.and], ['或门', output.or], ['非门', output.not], ['异或', output.xor]]),
        ]
      } else if (demo.preset === 'comb') {
        body = pairs([['输入 A', state.a], ['输入 B', state.b], ['选择', state.sel],
          ['多路', state.mux_out], ['运算', state.alu_out]])
      } else if (demo.preset === 'sequential') {
        body = pairs([['时钟', state.clock], ['使能', state.enable], ['输入', state.d_in], ['输出', state.q]])
      } else if (demo.preset === 'alu') {
        body = pairs([['输入 A', state.a], ['输入 B', state.b], ['操作', state.op_name ?? state.op],
          ['结果', state.result], ['零标', state.flags?.zero], ['进位', state.flags?.carry]])
      } else if (demo.preset === 'memory') {
        body = [pairs([['地址', hex2(state.address)], ['数据', hex2(state.data_out)]]), grid(state.rom, state.address)]
      } else if (demo.preset === 'cpu') {
        body = [
          pairs([['累加器', state.registers?.A], ['变址', state.registers?.X],
            ['程序计', state.registers?.PC], ['指令', state.registers?.IR]]),
          pairs([['地址线', state.buses?.addr], ['数据线', state.buses?.data]]),
          signals(state.control),
          grid(state.ram, state.pc),
        ]
      } else {
        body = pairs([])
      }
      return h('div', { class: 'demo-stage' }, [...head, body])
    }

    function detail() {
      const demo = current.value
      return h('section', { class: 'demo-detail' }, [
        h('h3', `演示 #${demo.id} · ${PRESETS[demo.preset] ?? demo.preset} · ${demo.active ? '进行中' : '已关闭'}`),
        stage(demo),
        teacher() && demo.active && h('div', { class: 'actions' }, [
          button('单步', () => run(() => advance('step'), '已单步')),
          button('复位', () => run(() => advance('reset'), '已复位')),
          button('暂停', () => run(() => advance('pause'), '已暂停')),
          button('连续', () => run(() => advance('run'), '已连续运行')),
          button('关闭演示', () => run(closeSession, '演示已关闭，学生视图停止同步'), { class: 'secondary' }),
        ]),
        teacher() && !demo.active && h('p', '演示已关闭，可回到列表新建。'),
        !teacher() && h('p', { class: 'demo-readonly' }, '只读同步中（每秒自动刷新）'),
      ])
    }

    function listRows() {
      return h('ul', { class: 'rows' }, items.value.map(item => h('li', { key: item.id }, [
        h('div', [
          h('strong', `#${item.id} ${PRESETS[item.preset] ?? item.preset}`),
          h('span', ` · 版本 ${item.revision} · ${when(item.updated_at)}`),
        ]),
        h('span', { class: 'tag' }, item.active ? '进行中' : '已关闭'),
        button('打开', () => run(() => open(item))),
      ])))
    }

    return () => h('section', { class: 'card demo-module', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [h('h2', '课堂演示'), button('重新加载', () => run(boot))]),
      error.value && h('p', { class: 'demo-error', role: 'alert' }, error.value),
      notice.value && h('p', { class: 'demo-notice' }, notice.value),
      !session.value && h('p', '正在加载…'),
      session.value && h('label', { class: 'demo-course' }, ['课程 ',
        h('select', {
          value: courseId.value, disabled: busy.value,
          onChange: event => { courseId.value = event.target.value; run(loadCourse) },
        }, courses.value.map(course => h('option', {
          value: String(course.id), key: course.id,
        }, course.title)))]),
      session.value && teacher() && h('form', {
        class: 'inline-form demo-create',
        onSubmit: event => { event.preventDefault(); run(create, '演示已创建，投屏可打开详情') },
      }, [
        h('label', ['预设 ', h('select', {
          value: form.preset, disabled: busy.value,
          onChange: event => { form.preset = event.target.value },
        }, Object.entries(PRESETS).map(([value, label]) => h('option', { value, key: value }, label)))]),
        h('button', { type: 'submit', disabled: busy.value }, '发起演示'),
      ]),
      session.value && h('h3', `演示列表（${total.value}）`),
      session.value && (items.value.length
        ? listRows()
        : h('p', teacher() ? '还没有课堂演示，先发起一个。' : '老师还没有发起课堂演示。')),
      current.value && detail(),
    ])
  },
}
