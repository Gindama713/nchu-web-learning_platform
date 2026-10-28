// SPEC-017 wiring lab view: terminals, wires, inputs/clock, action history and feedback.
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { WiringClient } from './wiring-client.js'
import { initialState, propagate, replayAction, resetSim, stepSim } from './wiring-sim.js'

const STATUS = { draft: '草稿', submitted: '已提交' }
const ACTIONS = {
  connect: '连接', disconnect: '断线', set_input: '输入',
  step: '单步', reset: '复位', undo: '撤销', redo: '重做',
}
const PHASES = { 0: '取指', 1: '译码', 2: '执行' }
const when = value => (value ? value.slice(0, 16).replace('T', ' ') : '—')
let wireSeq = 0

const newWireId = () => `w-${Date.now().toString(36)}-${(wireSeq += 1)}`
const summaryOf = action => {
  const payload = action.payload ?? {}
  if (action.type === 'connect') return `${payload.from_terminal} → ${payload.to_terminal}`
  if (action.type === 'disconnect') return payload.wire_id
  if (action.type === 'set_input') return `${payload.terminal_id}=${payload.value}`
  return ''
}

export const WiringView = {
  setup() {
    const api = new WiringClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const versions = ref([])
    const versionId = ref('')
    const items = ref([])
    const total = ref(0)
    const current = ref(null)
    const localState = ref(null)
    const pending = ref([])
    const undoStack = ref([])
    const connectForm = reactive({ from: '', to: '' })
    const inputForm = reactive({ terminal_id: '', value: '' })
    const feedback = ref(null)
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    let runTimer = 0

    const teacher = () => session.value?.user.role === 'teacher'
    const attempt = () => current.value?.attempt
    const readOnly = () => !current.value || attempt()?.status === 'submitted' || teacher()
    const panel = () => current.value?.panel
    const terminals = () => panel()?.terminals ?? []
    const termName = tid => {
      const found = terminals().find(t => t.id === tid)
      return found ? `${found.component_id}.${found.name}` : tid
    }
    const revision = () => attempt()?.revision ?? 0

    function stopRun() {
      if (runTimer) { globalThis.clearInterval(runTimer); runTimer = 0 }
    }

    function resetAuth() {
      session.value = null
      api.userId = null
      courses.value = []
      courseId.value = ''
      clearCourse()
    }

    function clearCourse() {
      versions.value = []
      versionId.value = ''
      items.value = []
      total.value = 0
      closeDetail()
    }

    function closeDetail() {
      current.value = null
      localState.value = null
      pending.value = []
      undoStack.value = []
      feedback.value = null
      stopRun()
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
      } finally {
        busy.value = false
      }
    }

    async function loadVersions() {
      clearCourse()
      if (!courseId.value) return
      versions.value = (await api.versions(courseId.value))
        .filter(version => (version.submission_modes ?? []).includes('wiring'))
    }

    async function loadAttempts() {
      closeDetail()
      items.value = []
      total.value = 0
      if (!courseId.value || !versionId.value) return
      const result = await api.attempts(courseId.value, versionId.value)
      items.value = result.data
      total.value = result.total
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
      await loadVersions()
    }

    async function reload() {
      const row = attempt()
      if (!row || !panel()) return
      const fresh = await api.attempt(row.id)
      current.value.attempt = fresh
      const log = await api.actions(fresh.id)
      current.value.history = log.items
      // 与后端一致：从初态重放全部动作重建撤销栈，再以服务端已保存状态为准
      const stack = []
      let replayed = initialState(panel())
      for (const action of log.items) replayed = replayAction(panel(), replayed, action, stack)
      const saved = fresh.state ?? { wires: [], inputs: {} }
      const match = JSON.stringify(replayed.wires) === JSON.stringify(saved.wires ?? []) &&
        JSON.stringify(replayed.inputs) === JSON.stringify(saved.inputs ?? {})
      undoStack.value = match ? stack : []
      localState.value = JSON.parse(JSON.stringify(saved))
      pending.value = []
    }

    async function openAttempt(row) {
      const attemptData = await api.attempt(row.id)
      let version = versions.value.find(item => item.id === attemptData.experiment_version_id)
      if (!version) version = await api.version(attemptData.experiment_version_id)
      current.value = { attempt: attemptData, version, panel: version.panel, history: [] }
      await reload()
    }

    async function createAttempt() {
      const created = await api.create(versionId.value)
      await loadAttempts()
      await openAttempt(created)
    }

    function commit(type, payload) {
      if (readOnly()) throw new Error('当前状态不可编辑')
      const action = { type, payload, client_at: new Date().toISOString() }
      pending.value.push(action)
      localState.value = replayAction(panel(), localState.value, action, undoStack.value)
    }

    function doConnect() {
      const from = connectForm.from
      const to = connectForm.to
      if (!from || !to) throw new Error('请选择要连接的输出与输入端子')
      const src = terminals().find(t => t.id === from)
      const dst = terminals().find(t => t.id === to)
      if (!src || !dst) throw new Error('端子不存在，请刷新后重试')
      if (src.direction !== 'out' || dst.direction !== 'in') throw new Error('连接方向必须为输出到输入')
      if (src.width !== dst.width) throw new Error(`位宽不一致 ${src.width} 与 ${dst.width}`)
      commit('connect', { id: newWireId(), from_terminal: from, to_terminal: to })
      connectForm.from = ''
      connectForm.to = ''
    }

    function doDisconnect(wire) {
      commit('disconnect', { wire_id: wire.id })
    }

    function doSetInput(terminalId, value) {
      if (value === '' || !Number.isInteger(Number(value))) throw new Error('请输入整数输入值')
      const numeric = Number(value)
      const term = terminals().find(t => t.id === terminalId)
      if (numeric < 0) throw new Error('输入不能为负数')
      if (term && numeric >= 2 ** (term.width ?? 1)) throw new Error(`输入超出 ${term.width} 位上限`)
      commit('set_input', { terminal_id: terminalId, value: numeric })
      inputForm.terminal_id = ''
      inputForm.value = ''
    }

    function doUndo() {
      if (!undoStack.value.length) throw new Error('没有可撤销的编辑')
      commit('undo', {})
    }

    async function persist(extra = []) {
      if (!current.value) return
      const actions = [...pending.value, ...extra]
      if (!actions.length) return
      const row = attempt()
      let state = localState.value
      for (const action of extra) {
        if (action.type === 'step') state = stepSim(panel(), state)
        else if (action.type === 'reset') state = resetSim(panel(), state)
      }
      const data = await api.save(row.id, row.revision, state, actions)
      row.revision = data.revision
      undoStack.value = []
      await reload()
    }

    const stepOne = () => persist([{ type: 'step' }])
    const resetOne = () => persist([{ type: 'reset' }])

    function toggleRun() {
      if (runTimer) {
        stopRun()
        notice.value = '已暂停，可继续编辑。'
        return
      }
      runTimer = globalThis.setInterval(() => {
        if (!current.value || attempt()?.status !== 'draft' ||
            localState.value?.halted === 1 || localState.value?.error === 1) {
          stopRun()
          return
        }
        run(stepOne)
      }, 1000)
      notice.value = '连续运行中，每秒一个时钟拍。'
    }

    async function doValidate() {
      await persist()
      feedback.value = await api.validate(attempt().id, revision())
    }

    async function doSubmit() {
      await persist()
      const result = await api.submit(attempt().id, revision())
      feedback.value = result
      await reload()
    }

    function guardUnload(event) {
      if (pending.value.length) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    onMounted(() => {
      run(boot)
      if (typeof window !== 'undefined') globalThis.window.addEventListener('beforeunload', guardUnload)
    })
    onUnmounted(() => {
      stopRun()
      if (typeof window !== 'undefined') globalThis.window.removeEventListener('beforeunload', guardUnload)
    })

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)

    const select = (entries, value, onChange, blank) => h('select', {
      value, disabled: busy.value, onChange: event => onChange(event.target.value),
    }, [
      blank && h('option', { value: '' }, blank),
      ...entries.map(([key, label]) => h('option', { value: key, key }, label)),
    ])

    function headTable() {
      const state = localState.value ?? {}
      const halted = state.halted === 1 ? '已停机' : state.error === 1 ? '指令错误' : '运行中'
      return h('table', { class: 'wiring-head' }, h('tbody', [
        h('tr', [h('th', { scope: 'row' }, '拍数'),
          h('td', `${state.tick ?? 0} · ${PHASES[state.phase] ?? '—'} · ${halted}`)]),
        h('tr', [h('th', { scope: 'row' }, '版本'),
          h('td', `revision ${revision()} · 动作 ${attempt()?.latest_seq ?? 0}`)]),
      ]))
    }

    function signalsPanel() {
      if (!panel() || !localState.value) return null
      const values = propagate(panel(), localState.value)
      const leds = panel().components.filter(comp => comp.type === 'LED')
      const regs = panel().components.filter(comp => comp.type === 'REG8' || comp.type === 'PC4')
      return h('div', { class: 'wiring-signals' }, [
        h('h4', '信号'),
        h('table', { class: 'wiring-io-table' }, [
          h('thead', h('tr', ['指示灯', '状态'].map(text => h('th', text)))),
          h('tbody', leds.map(comp => h('tr', { key: comp.id }, [
            h('td', `${comp.id}(${comp.params?.width ?? 1}位)`),
            h('td', String(values.get(comp.ports.IN) ?? 'Z')),
          ]))),
        ]),
        h('table', { class: 'wiring-io-table' }, [
          h('thead', h('tr', ['寄存器', '值'].map(text => h('th', text)))),
          h('tbody', regs.map(comp => {
            const value = localState.value[`${comp.id}_q`] ?? 0
            return h('tr', { key: comp.id }, [
              h('td', `${comp.id}(${comp.type === 'PC4' ? 4 : 8}位)`),
              h('td', `${value}（0x${Number(value).toString(16).toUpperCase()}）`),
            ])
          })),
        ]),
      ])
    }

    function componentsPanel() {
      return h('div', { class: 'wiring-block' }, [
        h('h4', '器件端子'),
        h('table', { class: 'wiring-parts' }, [
          h('thead', h('tr', ['组件', '类型', '输入端子', '输出端子'].map(text => h('th', text)))),
          h('tbody', panel().components.map(comp => {
            const terms = terminals().filter(t => t.component_id === comp.id)
            const fmt = list => list.map(t => `${t.id}(w${t.width})`).join(' ') || '—'
            return h('tr', { key: comp.id }, [
              h('td', comp.id), h('td', comp.type),
              h('td', fmt(terms.filter(t => t.direction === 'in'))),
              h('td', fmt(terms.filter(t => t.direction === 'out'))),
            ])
          })),
        ]),
      ])
    }

    function canvasPanel() {
      const wires = localState.value?.wires ?? []
      const outs = terminals().filter(t => t.direction === 'out')
        .map(t => [t.id, `${termName(t.id)}(${t.width}位)`])
      const ins = terminals().filter(t => t.direction === 'in')
        .map(t => [t.id, `${termName(t.id)}(${t.width}位)`])
      return h('div', { class: 'wiring-block' }, [
        h('h4', '连线画布'),
        !readOnly() && h('form', {
          class: 'wiring-connect',
          onSubmit: event => { event.preventDefault(); run(doConnect, '导线已连接') },
        }, [
          h('label', ['从 ', select(outs, connectForm.from, value => { connectForm.from = value }, '请选择')]),
          h('label', ['到 ', select(ins, connectForm.to, value => { connectForm.to = value }, '请选择')]),
          h('button', { type: 'submit', disabled: busy.value }, '连接'),
          button('撤销', () => run(doUndo, '已撤销'), { class: 'secondary' }),
        ]),
        wires.length
          ? h('table', { class: 'wiring-wires' }, [
            h('thead', h('tr', ['导线', '从', '到', '操作'].map(text => h('th', text)))),
            h('tbody', wires.map(wire => h('tr', { key: wire.id }, [
              h('td', wire.id),
              h('td', termName(wire.from_terminal)),
              h('td', termName(wire.to_terminal)),
              h('td', !readOnly() ? button('断线', () => run(() => doDisconnect(wire), '导线已断开'), { class: 'secondary' }) : ''),
            ]))),
          ])
          : h('p', '暂无导线，请从上方选择端子连接。'),
      ])
    }

    function ioPanel() {
      const switches = panel().components.filter(comp => comp.type === 'SWITCH')
      const entries = switches.map(comp => {
        const tid = comp.ports.OUT
        return [tid, `${termName(tid)}(当前 ${localState.value?.inputs?.[tid] ?? comp.params?.initial ?? 0})`]
      })
      const running = Boolean(runTimer)
      return h('div', { class: 'wiring-block' }, [
        h('h4', '输入时钟'),
        !readOnly() && h('form', {
          class: 'wiring-input',
          onSubmit: event => {
            event.preventDefault()
            run(() => doSetInput(inputForm.terminal_id, inputForm.value), '输入已写入')
          },
        }, [
          h('label', ['端子 ', select(entries, inputForm.terminal_id, value => { inputForm.terminal_id = value }, '请选择')]),
          h('label', ['数值 ', h('input', {
            value: inputForm.value, inputmode: 'numeric', disabled: busy.value,
            onInput: event => { inputForm.value = event.target.value },
          })]),
          h('button', { type: 'submit', disabled: busy.value || !inputForm.terminal_id }, '写入'),
        ]),
        h('div', { class: 'wiring-clock' }, [
          !readOnly() && button('单步', () => run(stepOne, '已推进一拍')),
          !readOnly() && button('复位', () => run(resetOne, '已复位')),
          !readOnly() && button(running ? '暂停' : '连续', toggleRun, { class: 'secondary' }),
          headTable(),
        ]),
      ])
    }

    function historyPanel() {
      const rows = current.value.history ?? []
      return h('div', { class: 'wiring-block' }, [
        h('h4', '动作历史'),
        rows.length
          ? h('table', { class: 'wiring-history' }, [
            h('thead', h('tr', ['序号', '动作', '详情'].map(text => h('th', text)))),
            h('tbody', rows.map(row => h('tr', { key: row.seq }, [
              h('td', String(row.seq)),
              h('td', ACTIONS[row.type] ?? row.type),
              h('td', summaryOf(row) || '—'),
            ]))),
          ])
          : h('p', '暂无已保存动作。'),
      ])
    }

    function resultsTable() {
      const results = attempt()?.functional_results
      if (!results?.length) return null
      return h('table', { class: 'wiring-results' }, [
        h('thead', h('tr', ['检查', '结果', '期望', '实际'].map(text => h('th', text)))),
        h('tbody', results.map((item, index) => h('tr', { key: index }, [
          h('td', item.op ?? item.case ?? `#${index + 1}`),
          h('td', item.passed ? '通过' : '未通过'),
          h('td', JSON.stringify(item.expected ?? item.checks ?? '')),
          h('td', JSON.stringify(item.actual ?? '')),
        ]))),
      ])
    }

    function feedbackPanel() {
      const row = attempt()
      const errors = feedback.value?.errors ?? []
      return h('div', { class: 'wiring-block' }, [
        h('h4', '校验提交'),
        !readOnly() && h('div', { class: 'wiring-actions' }, [
          button('保存', () => run(() => persist(), '已保存'), { class: 'secondary' }),
          button('校验', () => run(doValidate, '校验完成')),
          button('提交', () => run(doSubmit, '已提交')),
          pending.value.length ? h('small', `未保存 ${pending.value.length} 条动作`) : h('small', '无未保存修改'),
        ]),
        readOnly() && row?.status === 'submitted' && h('div', { class: 'wiring-submitted' }, [
          h('p', `已提交 · 快照 ${(row.snapshot_hash ?? '').slice(0, 12)} · ${when(row.submitted_at)}`),
          h('p', row.completed ? '功能判定：全部通过。' : '功能判定：未全部通过，可重新连线再提交。'),
          !teacher() && button('重新连线', () => run(createAttempt, '已创建新连线'), { class: 'secondary' }),
        ]),
        errors.length
          ? h('table', { class: 'wiring-errors' }, [
            h('thead', h('tr', ['错误码', '说明', '相关端子'].map(text => h('th', text)))),
            h('tbody', errors.map((item, index) => h('tr', { key: index }, [
              h('td', item.code),
              h('td', item.message),
              h('td', (item.terminal_ids ?? []).join(' ') || '—'),
            ]))),
          ])
          : feedback.value && h('p', '结构校验通过。'),
        resultsTable(),
        button('重新加载', () => run(reload, '已恢复最新已保存状态'), { class: 'secondary' }),
      ])
    }

    function detail() {
      const row = attempt()
      const version = current.value.version
      return h('section', { class: 'wiring-detail' }, [
        h('h3', `连线 #${row.id} · ${version?.title ?? row.experiment_version_id} · ${STATUS[row.status] ?? row.status}`),
        signalsPanel(),
        h('div', { class: 'wiring-grid' }, [
          componentsPanel(),
          canvasPanel(),
          ioPanel(),
          historyPanel(),
          feedbackPanel(),
        ]),
      ])
    }

    function attemptsTable() {
      return h('table', { class: 'wiring-attempts' }, [
        h('thead', h('tr', ['编号', '状态', '版本', '动作', '保存', '操作'].map(text => h('th', text)))),
        h('tbody', items.value.map(row => h('tr', { key: row.id }, [
          h('td', `#${row.id}`),
          h('td', STATUS[row.status] ?? row.status),
          h('td', String(row.experiment_version_id)),
          h('td', String(row.action_count ?? 0)),
          h('td', when(row.saved_at)),
          h('td', button('打开', () => run(() => openAttempt(row)))),
        ]))),
      ])
    }

    return () => h('section', { class: 'card wiring-module' }, [
      h('h2', '实验箱连线'),
      error.value && h('p', { class: 'wiring-error', role: 'alert' }, error.value),
      notice.value && h('p', { class: 'wiring-notice' }, notice.value),
      !session.value && h('p', '正在加载…'),
      session.value && h('label', { class: 'wiring-course' }, ['课程 ',
        h('select', {
          value: courseId.value, disabled: busy.value,
          onChange: event => { courseId.value = event.target.value; run(loadVersions) },
        }, courses.value.map(course => h('option', {
          value: String(course.id), key: course.id,
        }, course.title)))]),
      session.value && h('label', { class: 'wiring-version' }, ['实验 ',
        select(versions.value.map(version => [String(version.id),
          `${version.experiment?.code ?? ''} ${version.title}`.trim()]),
        versionId.value, value => { versionId.value = value; run(loadAttempts) }, '请选择已发布实验')]),
      session.value && !versions.value.length && h('p', '当前课程暂无支持连线的已发布实验。'),
      session.value && versionId.value && h('h3', `连线记录（${total.value}）`),
      session.value && versionId.value && (items.value.length
        ? attemptsTable()
        : h('p', teacher() ? '该实验还没有学生的连线记录。' : '还没有连线记录，可发起新连线。')),
      session.value && !teacher() && versionId.value
        && button('发起连线', () => run(createAttempt, '连线已创建'), { class: 'secondary' }),
      current.value && detail(),
    ])
  },
}
