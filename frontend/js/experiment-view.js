// SPEC-009 实验中心：实验列表、指导内容、本人历史版本与两类提交入口。
// 提交入口只负责跳转/派发目标，不替代 SPEC-017 连线与 SPEC-018 评测界面（AC-04）。
import { h, onMounted, reactive, ref } from 'vue'
import { ExperimentClient, experimentCodes, publishPayload, versionPayload } from './experiment-client.js'

const emptyExperiment = () => ({ code: 'EXP-01', title: '', description: '' })
const emptyVersion = () => ({
  experimentId: '', title: '', objectives: '', instructions: '',
  wiring: true, circuit: false, knowledgeIds: [], panelText: '', rulesText: '{}',
})
const emptyPublish = () => ({ startAt: '', endAt: '' })

function windowState(version) {
  if (!version.start_at || !version.end_at) return ''
  const now = Date.now()
  const start = Date.parse(version.start_at)
  const end = Date.parse(version.end_at)
  if (now < start) return '未开始'
  if (now >= end) return '已截止'
  return '进行中'
}

export const ExperimentView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new ExperimentClient(props.user.id)
    const teacher = () => props.user.role === 'teacher'
    const courses = ref([]), courseId = ref('')
    const experiments = ref([]), page = ref(1), total = ref(0)
    const versions = ref([])
    const versionFilter = reactive({ experimentId: '', status: '' })
    const knowledge = ref([])
    const selected = ref(null)
    const busy = ref(false), error = ref(''), notice = ref('')
    const showExperimentForm = ref(false), showVersionForm = ref(false)
    const experimentForm = reactive(emptyExperiment())
    const versionForm = reactive(emptyVersion())
    const publishForm = reactive(emptyPublish())
    const publishTarget = ref(null)

    function clearCourse() {
      experiments.value = []; total.value = 0; page.value = 1; versions.value = []
      versionFilter.experimentId = ''; versionFilter.status = ''; selected.value = null
      showExperimentForm.value = false; showVersionForm.value = false; publishTarget.value = null
    }

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.status === 401 || failure.status === 404) {
          selected.value = null
          if (failure.status === 401) { courses.value = []; courseId.value = ''; clearCourse() }
        }
      } finally { busy.value = false }
    }

    async function loadExperiments() {
      experiments.value = []; total.value = 0
      if (!courseId.value) return
      const result = await api.experiments(courseId.value, page.value)
      experiments.value = result.data; total.value = result.total
    }

    async function loadVersions() {
      versions.value = []
      if (!courseId.value) return
      const result = await api.versions(courseId.value, { experimentId: versionFilter.experimentId,
        status: versionFilter.status })
      versions.value = result.data
    }

    async function loadCourse() {
      clearCourse()
      if (!courseId.value) return
      knowledge.value = []
      try { knowledge.value = await api.knowledge(courseId.value) } catch { knowledge.value = [] }
      await loadExperiments()
      await loadVersions()
    }

    async function boot() {
      clearCourse(); courses.value = []
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadCourse()
    }

    async function saveExperiment() {
      const values = { ...experimentForm, title: experimentForm.title.trim(),
        description: experimentForm.description.trim() }
      if (!values.title || !values.description.trim()) throw new Error('请填写实验标题与说明。')
      const created = await api.createExperiment(courseId.value, values)
      Object.assign(experimentForm, emptyExperiment())
      showExperimentForm.value = false
      versionForm.experimentId = String(created.id)
      await loadExperiments(); await loadVersions()
      return created
    }

    async function saveVersion() {
      if (!versionForm.experimentId) throw new Error('请先选择所属实验。')
      const created = await api.createVersion(versionForm.experimentId, versionPayload(versionForm))
      Object.assign(versionForm, emptyVersion())
      showVersionForm.value = false
      await loadExperiments(); await loadVersions()
      selected.value = created
    }

    async function publishVersion() {
      if (!publishTarget.value) return
      const published = await api.publish(publishTarget.value.id, publishPayload(publishForm))
      publishTarget.value = null
      Object.assign(publishForm, emptyPublish())
      await loadExperiments(); await loadVersions()
      selected.value = published
    }

    function openDetail(id) {
      return run(async () => { selected.value = await api.detail(id) })
    }

    function openEntry(mode, version) {
      // AC-02/AC-04：只派发目标与上下文，由 SPEC-017/018 的界面响应。
      document.dispatchEvent(new globalThis.CustomEvent('cpu-experiment-open', {
        detail: { mode, version_id: version.id, experiment_id: version.experiment_id },
      }))
      notice.value = mode === 'wiring'
        ? '已请求打开实验箱连线工作台（由 SPEC-017 模块提供）。'
        : '已请求打开 .circ 在线评测（由 SPEC-018 模块提供）。'
    }

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const field = (label, input) => h('label', [h('span', label), input])
    const text = (value, update, options = {}) => h('input', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const area = (value, update, options = {}) => h('textarea', {
      value, disabled: busy.value, rows: 4, onInput: event => update(event.target.value), ...options,
    })
    const select = (value, update, values, placeholder = '') => h('select', {
      value, disabled: busy.value, onChange: event => update(event.target.value),
    }, [...(placeholder ? [h('option', { value: '' }, placeholder)] : []),
      ...Object.entries(values).map(([key, label]) => h('option', { value: key }, label))])
    const toggle = (label, checked, update) => h('label', { class: 'experiment-check' }, [h('input', {
      type: 'checkbox', checked, disabled: busy.value, onChange: event => update(event.target.checked),
    }), label])
    const experimentOptions = Object.fromEntries(experiments.value.map(item =>
      [String(item.id), `${item.code} · ${item.title}`]))
    const knowledgeTitle = id => knowledge.value.find(item => item.id === id)?.title ?? `知识点 #${id}`

    function guidance(version) {
      return h('article', { class: 'experiment-guidance' }, [
        h('h3', `${version.experiment.code} · ${version.experiment.title} · v${version.version}`),
        h('p', `${version.status === 'published' ? '已发布' : '草稿'}${
          windowState(version) ? ` · ${windowState(version)}` : ''}${
          version.status === 'published' ? ` · 参与人数 ${version.participant_count ?? '—'}` : ''}`),
        h('h4', '实验目标'), h('p', version.objectives),
        version.panel && h('div', [
          h('h4', '实验器件'),
          h('ul', { class: 'rows' }, version.panel.components.map(component =>
            h('li', { key: component.id }, `${component.id} · ${component.type}`))),
        ]),
        h('h4', '实验步骤'), h('p', { class: 'experiment-text' }, version.instructions),
        h('h4', '验证规则（公开部分）'),
        h('pre', { class: 'experiment-rules' }, JSON.stringify(version.rules ?? {}, null, 2)),
        version.knowledge_ids.length > 0 && h('div', [
          h('h4', '关联知识点'),
          h('ul', { class: 'rows' }, version.knowledge_ids.map(id =>
            h('li', { key: id }, knowledgeTitle(id)))),
        ]),
        version.status === 'published' && h('div', [
          h('h4', '提交入口'),
          h('div', { class: 'actions' }, version.submission_modes.map(mode =>
            button(mode === 'wiring' ? '进入实验箱连线（SPEC-017）' : '上传 .circ 在线评测（SPEC-018）',
              () => openEntry(mode, version), { class: 'experiment-entry', 'data-mode': mode }))),
        ]),
      ])
    }

    function experimentCreator() {
      return h('form', { class: 'inline-form experiment-create', onSubmit: event => {
        event.preventDefault(); run(saveExperiment, '实验已创建，可继续添加版本。')
      } }, [
        h('h3', '新增实验'),
        field('实验代码', select(experimentForm.code, value => { experimentForm.code = value }, experimentCodes)),
        field('标题', text(experimentForm.title, value => { experimentForm.title = value }, { required: true, maxlength: 100 })),
        field('说明', text(experimentForm.description, value => { experimentForm.description = value }, { required: true, maxlength: 500 })),
        h('button', { type: 'submit', disabled: busy.value }, '创建实验'),
      ])
    }

    function versionCreator() {
      return h('form', { class: 'inline-form experiment-version-form', onSubmit: event => {
        event.preventDefault(); run(saveVersion, '版本草稿已创建；发布前请确认指导内容完整。')
      } }, [
        h('h3', '新增版本（保存后不可原地修改，只能再建新版本）'),
        field('所属实验', select(versionForm.experimentId, value => { versionForm.experimentId = value },
          experimentOptions, '请选择实验')),
        field('版本标题', text(versionForm.title, value => { versionForm.title = value }, { required: true, maxlength: 100 })),
        field('实验目标', area(versionForm.objectives, value => { versionForm.objectives = value }, { required: true, maxlength: 2000 })),
        field('实验步骤', area(versionForm.instructions, value => { versionForm.instructions = value }, { required: true, maxlength: 2000 })),
        h('fieldset', [h('legend', '提交方式（至少一种）'),
          toggle('实验箱连线（需提供面板 panel）', versionForm.wiring, value => { versionForm.wiring = value }),
          toggle('.circ 在线评测（发布需 SPEC-018 判分配置）', versionForm.circuit, value => { versionForm.circuit = value }),
        ]),
        field('面板 panel JSON（连线必填）', area(versionForm.panelText, value => { versionForm.panelText = value },
          { rows: 6, placeholder: '{"schema_version":1,"components":[],"terminals":[],"layout":{}}' })),
        field('规则 rules JSON（hidden 部分仅教师可见）', area(versionForm.rulesText, value => { versionForm.rulesText = value },
          { rows: 4 })),
        knowledge.value.length > 0 && h('fieldset', [h('legend', '关联知识点'),
          ...knowledge.value.map(item => toggle(item.title, versionForm.knowledgeIds.includes(item.id), value => {
            versionForm.knowledgeIds = value ? [...versionForm.knowledgeIds, item.id]
              : versionForm.knowledgeIds.filter(id => id !== item.id)
          })),
        ]),
        h('button', { type: 'submit', disabled: busy.value || !versionForm.experimentId }, '保存版本草稿'),
      ])
    }

    function publisher() {
      return h('form', { class: 'inline-form experiment-publish', onSubmit: event => {
        event.preventDefault(); run(publishVersion, '版本已发布，参与名单已冻结并通知学生。')
      } }, [
        h('h3', `发布版本 #${publishTarget.value.id}（v${publishTarget.value.version}）`),
        h('p', '发布将冻结当前学生名单并逐个通知；circuit 版本需先在 SPEC-018 完成判分配置。'),
        field('开始时间', text(publishForm.startAt, value => { publishForm.startAt = value }, { type: 'datetime-local', required: true })),
        field('截止时间', text(publishForm.endAt, value => { publishForm.endAt = value }, { type: 'datetime-local', required: true })),
        h('div', { class: 'actions' }, [
          h('button', { type: 'submit', disabled: busy.value }, '发布'),
          button('取消', () => { publishTarget.value = null }),
        ]),
      ])
    }

    onMounted(() => run(boot))
    return () => h('section', { class: 'card experiment-center', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [h('h2', '实验中心（实验辅助）'), button('重新加载', () => run(boot))]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { role: 'alert' }, [h('p', error.value), button('重试', () => run(boot))]),
      notice.value && h('p', { role: 'status' }, notice.value),
      !courses.value.length && !busy.value && !error.value && h('p', '暂无可访问课程。'),
      courses.value.length > 0 && field('实验课程', select(courseId.value, value => {
        courseId.value = value; run(loadCourse)
      }, Object.fromEntries(courses.value.map(item => [String(item.id), item.title])))),
      courseId.value && h('div', [
        teacher() && h('div', { class: 'actions' }, [
          button('新增实验', () => { showExperimentForm.value = !showExperimentForm.value; showVersionForm.value = false }),
          button('新增版本', () => { showVersionForm.value = !showVersionForm.value; showExperimentForm.value = false },
            { disabled: busy.value || !experiments.value.length }),
        ]),
        teacher() && showExperimentForm.value && experimentCreator(),
        teacher() && showVersionForm.value && versionCreator(),
        teacher() && publishTarget.value && publisher(),
        h('p', `共 ${total.value} 个实验${teacher() ? '' : '（仅显示本人参与名单内的已发布实验）'}`),
        h('ul', { class: 'rows' }, experiments.value.map(item => h('li', { key: item.id }, [
          h('div', [
            h('strong', `${item.code} · ${item.title}`),
            item.latest_version
              ? h('span', ` · v${item.latest_version.version} · ${
                item.latest_version.status === 'published' ? '已发布' : '草稿'}${
                item.latest_version.status === 'published'
                  ? ` · ${windowState(item.latest_version)} · ${item.latest_version.participant_count ?? '—'} 人`
                  : ''}`)
              : h('span', ' · 尚无版本'),
          ]),
          item.latest_version && button('查看指导', () => openDetail(item.latest_version.id)),
          button('历史版本', () => {
            versionFilter.experimentId = String(item.id)
            run(loadVersions)
          }),
        ]))),
        !experiments.value.length && !busy.value && !error.value && h('p', '暂无可见实验。'),
        h('div', { class: 'actions' }, [
          button('实验上一页', () => { page.value--; run(loadExperiments) }, { disabled: busy.value || page.value <= 1 }),
          h('span', `第 ${page.value} 页`),
          button('实验下一页', () => { page.value++; run(loadExperiments) }, { disabled: busy.value || page.value * 20 >= total.value }),
        ]),
        versions.value.length > 0 && h('div', [
          h('h3', teacher() ? '版本列表' : '本人可见历史版本'),
          h('ul', { class: 'rows' }, versions.value.map(row => h('li', { key: row.id }, [
            h('span', `#${row.id} · v${row.version} · ${row.title} · ${
              row.status === 'published' ? '已发布' : '草稿'}${
              row.start_at ? ` · ${row.start_at} ~ ${row.end_at}` : ''}`),
            button('查看指导', () => openDetail(row.id)),
            teacher() && row.status === 'draft' && button('发布', () => {
              publishTarget.value = row; Object.assign(publishForm, emptyPublish())
            }),
          ]))),
        ]),
        selected.value && guidance(selected.value),
      ]),
    ])
  },
}
