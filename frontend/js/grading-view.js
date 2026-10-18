// SPEC-018 评测工作台：教师判分配置/测试集验证发布/班级提交与重评，
// 学生 .circ 上传与结果轮询（AC-02/AC-04；监听 cpu-experiment-open mode=circuit）。
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { GradingClient, profilePayload, runStatusText, terminalStatuses } from './grading-client.js'

const emptyProfile = () => ({ topCircuit: 'alu8',
  portSchemaText: '{"inputs":{"A":8,"B":8},"outputs":{"Y":8}}',
  componentsText: 'Adder AND OR', limitsText: '{}' })

function describeRun(run) {
  if (!run) return '暂无'
  const score = run.score == null ? '—' : `${run.score} 分`
  return `${runStatusText[run.status] ?? run.status} · ${score}` +
    (run.error_code ? ` · ${run.error_code}` : '')
}

export const GradingView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new GradingClient(props.user.id)
    const teacher = () => props.user.role === 'teacher'
    const courses = ref([]), courseId = ref('')
    const versions = ref([])
    const busy = ref(false), error = ref(''), notice = ref('')

    // 教师配置区状态。
    const targetVersion = ref(null)
    const profileForm = reactive(emptyProfile())
    const profileSaved = ref(null)
    const casesText = ref('[]')
    const suites = ref([])
    const suiteSelected = ref(null)
    const referenceFiles = ref([])
    const referencePick = reactive({ correct: '', knownWrong: '' })
    const validation = ref(null)
    const activeForm = reactive({ suiteId: '', revision: '1' })

    // 班级提交列表。
    const submissions = ref([]), submissionPage = ref(1), submissionTotal = ref(0)
    const submissionFilter = reactive({ experimentId: '', status: '' })
    const regradeTarget = ref(null), regradeReason = ref('')

    // 学生提交区状态（由 cpu-experiment-open 激活）。
    const entry = ref(null)
    const studentSubmission = ref(null)
    const studentRun = ref(null)
    let pollTimer = 0

    function stopPolling() {
      if (pollTimer) { globalThis.clearTimeout(pollTimer); pollTimer = 0 }
    }

    function run(action, success = '') {
      if (busy.value) return Promise.resolve()
      busy.value = true; error.value = ''; notice.value = ''
      return Promise.resolve(action()).then(() => { notice.value = success })
        .catch(failure => { error.value = failure.message })
        .finally(() => { busy.value = false })
    }

    async function loadVersions() {
      versions.value = []
      if (!courseId.value) return
      const result = await api.versions(courseId.value)
      versions.value = result.data.filter(row => row.submission_modes?.includes('circuit'))
    }

    async function loadSuites() {
      suites.value = []; suiteSelected.value = null
      if (!targetVersion.value) return
      const result = await api.suites(targetVersion.value.id)
      suites.value = result.data
      const references = await api.referenceFiles(targetVersion.value.id)
      referenceFiles.value = references.data
    }

    async function loadSubmissions() {
      submissions.value = []; submissionTotal.value = 0
      if (!courseId.value) return
      const result = await api.courseSubmissions(courseId.value, {
        experimentId: submissionFilter.experimentId, status: submissionFilter.status,
        page: submissionPage.value })
      submissions.value = result.data; submissionTotal.value = result.total
    }

    async function boot() {
      stopPolling(); entry.value = null; studentSubmission.value = null; studentRun.value = null
      courses.value = []
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await loadVersions()
      if (teacher()) await loadSubmissions()
    }

    // ---------- 教师操作 ----------
    function openVersion(row) {
      targetVersion.value = row
      validation.value = null; profileSaved.value = null
      Object.assign(profileForm, emptyProfile())
      referencePick.correct = ''; referencePick.knownWrong = ''
      activeForm.suiteId = ''; activeForm.revision = '1'
      return run(loadSuites)
    }

    async function saveProfile() {
      profileSaved.value = await api.putProfile(targetVersion.value.id, profilePayload(profileForm))
    }

    async function saveSuite() {
      const created = await api.createSuite(targetVersion.value.id, casesText.value)
      suiteSelected.value = created
      await loadSuites()
    }

    async function uploadReference(event, kind) {
      const file = event.target.files?.[0]
      if (!file) return
      event.target.value = ''
      await api.uploadReference(targetVersion.value.id, file, kind)
      await loadSuites()
    }

    async function startValidation() {
      if (!suiteSelected.value) throw new Error('请先选择要验证的测试集。')
      if (!referencePick.correct || !referencePick.knownWrong) throw new Error('请先上传标准与反例参考文件。')
      const created = await api.createValidation(suiteSelected.value.id,
        Number(referencePick.correct), Number(referencePick.knownWrong))
      validation.value = { id: created.validation_id, status: created.status }
      pollValidation()
    }

    function pollValidation() {
      stopPolling()
      const tick = async () => {
        try {
          validation.value = await api.validationDetail(validation.value.id)
          if (['passed', 'failed', 'system_error'].includes(validation.value.status)) return
        } catch { /* 下轮重试 */ }
        pollTimer = globalThis.setTimeout(tick, 2000)
      }
      pollTimer = globalThis.setTimeout(tick, 2000)
    }

    async function publishSuite() {
      if (!validation.value || validation.value.status !== 'passed') throw new Error('仅验证通过的测试集可发布。')
      const published = await api.publishSuite(suiteSelected.value.id, validation.value.id)
      notice.value = `测试集 v${published.version} 已发布。`
      await loadSuites()
    }

    async function switchActiveSuite() {
      const updated = await api.setActiveSuite(targetVersion.value.id,
        Number(activeForm.suiteId), Number(activeForm.revision))
      activeForm.revision = String(updated.revision)
      return updated
    }

    function startRegrade(row) {
      regradeTarget.value = row
      regradeReason.value = ''
    }

    async function confirmRegrade() {
      const reason = regradeReason.value.trim()
      if (reason.length < 1 || reason.length > 500) throw new Error('重评理由需 1—500 字符。')
      await api.regrade(regradeTarget.value.submission_id ?? regradeTarget.value.id, reason)
      regradeTarget.value = null
      await loadSubmissions()
    }

    // ---------- 学生提交与轮询（APIC 第7节：2 秒轮询，终态停止） ----------
    function onExperimentOpen(event) {
      const detail = event.detail ?? {}
      if (detail.mode !== 'circuit') return
      stopPolling()
      entry.value = { versionId: detail.version_id, experimentId: detail.experiment_id }
      studentSubmission.value = null; studentRun.value = null
      notice.value = '已打开 .circ 在线评测入口，请选择文件提交。'
    }

    async function submitFile(event) {
      const file = event.target.files?.[0]
      if (!file) return
      event.target.value = ''
      const created = await api.submitCircuit(entry.value.versionId, file)
      studentSubmission.value = created
      studentRun.value = null
      pollRun(created.run_id)
    }

    function pollRun(runId) {
      stopPolling()
      const tick = async () => {
        try {
          studentRun.value = await api.runDetail(runId)
          if (terminalStatuses.includes(studentRun.value.status)) return
        } catch { /* 下轮重试 */ }
        pollTimer = globalThis.setTimeout(tick, 2000)
      }
      pollTimer = globalThis.setTimeout(tick, 2000)
    }

    async function refreshSubmission() {
      if (!studentSubmission.value) return
      const detail = await api.submissionDetail(studentSubmission.value.submission_id)
      studentSubmission.value = { ...studentSubmission.value, ...detail }
      if (detail.latest_run?.id) {
        studentRun.value = await api.runDetail(detail.latest_run.id)
        if (!terminalStatuses.includes(studentRun.value.status)) pollRun(detail.latest_run.id)
      }
    }

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)
    const field = (label, input) => h('label', [h('span', label), input])
    const text = (value, update, options = {}) => h('input', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const area = (value, update, options = {}) => h('textarea', {
      value, disabled: busy.value, onInput: event => update(event.target.value), ...options,
    })
    const select = (value, update, values, placeholder = '') => h('select', {
      value, disabled: busy.value, onChange: event => update(event.target.value),
    }, [...(placeholder ? [h('option', { value: '' }, placeholder)] : []),
      ...Object.entries(values).map(([key, label]) => h('option', { value: key }, label))])

    const statusOptions = { '': '全部状态', queued: '排队中', running: '评测中',
      accepted: '通过', wrong_answer: '答案错误', timeout: '超时',
      resource_limit: '资源超限', invalid_circuit: '电路无效', system_error: '系统故障' }
    const versionOptions = Object.fromEntries(versions.value.map(row =>
      [String(row.id), `#${row.id} · v${row.version} · ${row.title}`]))
    const suiteOptions = Object.fromEntries(suites.value.map(row =>
      [String(row.id), `v${row.version} · ${row.status}`]))
    const fileOptions = kind => Object.fromEntries(referenceFiles.value
      .filter(row => row.kind === kind)
      .map(row => [String(row.reference_file_id ?? row.file_id ?? row.id), `${row.kind} · ${row.sha256?.slice(0, 8) ?? row.id}`]))

    function studentPanel() {
      if (!entry.value) return null
      return h('article', { class: 'grading-entry' }, [
        h('h3', `.circ 在线评测（版本 #${entry.value.versionId}）`),
        h('label', { class: 'grading-upload' }, ['选择 .circ 文件（≤2MiB）',
          h('input', { type: 'file', accept: '.circ,text/xml,application/xml',
            disabled: busy.value, onChange: submitFile })]),
        studentSubmission.value && h('div', [
          h('p', `提交 #${studentSubmission.value.submission_id ?? studentSubmission.value.id} · 任务 #${studentSubmission.value.run_id}`),
          studentRun.value && h('div', [
            h('p', { role: 'status' }, `当前状态：${describeRun(studentRun.value)}`),
            h('p', `通过 ${studentRun.value.passed_count}/${studentRun.value.total_count} · 隐藏用例 ${
              studentRun.value.hidden_summary?.passed ?? '—'}/${studentRun.value.hidden_summary?.total ?? '—'}`),
            Array.isArray(studentRun.value.public_cases) && studentRun.value.public_cases.length > 0
              && h('table', { class: 'grading-cases' }, [
                h('thead', h('tr', [h('th', '用例'), h('th', '输入'), h('th', '期望'), h('th', '实际'), h('th', '结果')])),
                h('tbody', studentRun.value.public_cases.map(item => h('tr', { key: item.label }, [
                  h('td', item.label),
                  h('td', JSON.stringify(item.input)),
                  h('td', JSON.stringify(item.expected)),
                  h('td', JSON.stringify(item.actual)),
                  h('td', item.passed ? '通过' : '失败'),
                ]))),
              ]),
            studentRun.value.status === 'system_error'
              && h('p', { role: 'alert' }, '系统故障未影响既有成绩，教师可重评或管理员重试。'),
          ]),
          button('刷新提交详情', () => run(refreshSubmission)),
        ]),
      ])
    }

    function teacherConfig() {
      if (!teacher() || !targetVersion.value) return null
      return h('article', { class: 'grading-config' }, [
        h('h3', `判分配置 · 版本 #${targetVersion.value.id}（v${targetVersion.value.version}）`),
        h('form', { class: 'inline-form', onSubmit: event => {
          event.preventDefault(); run(saveProfile, '判分配置已保存；配置变更会使旧验证失效。')
        } }, [
          field('顶层电路名', text(profileForm.topCircuit, value => { profileForm.topCircuit = value }, { required: true })),
          field('端口 port_schema JSON', area(profileForm.portSchemaText, value => { profileForm.portSchemaText = value }, { rows: 3 })),
          field('允许元件（空格或逗号分隔）', text(profileForm.componentsText, value => { profileForm.componentsText = value }, { required: true })),
          field('限额 limits JSON（留空用平台默认）', area(profileForm.limitsText, value => { profileForm.limitsText = value }, { rows: 2 })),
          h('button', { type: 'submit', disabled: busy.value }, '保存判分配置'),
        ]),
        profileSaved.value && h('p', { role: 'status' },
          `已保存 · 引擎 ${profileSaved.value.engine_version} · 指纹 ${profileSaved.value.canonical_sha256?.slice(0, 12)}…`),
        h('h4', '测试集'),
        h('form', { class: 'inline-form', onSubmit: event => {
          event.preventDefault(); run(saveSuite, '测试集草稿已创建，请上传参考文件并发起验证。')
        } }, [
          field('测试用例 cases JSON', area(casesText.value, value => { casesText.value = value }, { rows: 6 })),
          h('button', { type: 'submit', disabled: busy.value }, '新建测试集'),
        ]),
        suites.value.length > 0 && h('div', [
          field('选择测试集', select(String(suiteSelected.value?.id ?? ''),
            value => { suiteSelected.value = suites.value.find(row => String(row.id) === value) ?? null },
            suiteOptions, '请选择')),
          h('ul', { class: 'rows' }, suites.value.map(row => h('li', { key: row.id },
            `v${row.version} · ${row.status} · ${row.total_count ?? '—'} 例`))),
        ]),
        h('h4', '参考文件（与学生文件同样预检，教师身份不绕过沙箱）'),
        h('div', { class: 'actions' }, [
          h('label', ['上传标准电路（correct）', h('input', { type: 'file', accept: '.circ',
            disabled: busy.value, onChange: event => run(() => uploadReference(event, 'correct'), '标准参考已上传。') })]),
          h('label', ['上传已知错误电路（known_wrong）', h('input', { type: 'file', accept: '.circ',
            disabled: busy.value, onChange: event => run(() => uploadReference(event, 'known_wrong'), '反例参考已上传。') })]),
        ]),
        referenceFiles.value.length > 0 && h('div', [
          field('标准文件', select(referencePick.correct, value => { referencePick.correct = value }, fileOptions('correct'), '请选择')),
          field('反例文件', select(referencePick.knownWrong, value => { referencePick.knownWrong = value }, fileOptions('known_wrong'), '请选择')),
          button('发起验证（标准须全过、反例至少一项失败）', () => run(startValidation, '验证已排队，约 2 秒轮询一次。')),
        ]),
        validation.value && h('p', { role: 'status' }, `验证 #${validation.value.id} · 状态 ${validation.value.status}`),
        validation.value?.status === 'passed' && button('发布测试集', () => run(publishSuite)),
        h('h4', '切换生效测试集（revision 乐观锁，过期 409）'),
        h('form', { class: 'inline-form', onSubmit: event => {
          event.preventDefault(); run(switchActiveSuite, '生效测试集已切换。')
        } }, [
          field('测试集 ID', text(activeForm.suiteId, value => { activeForm.suiteId = value },
            { required: true, inputmode: 'numeric' })),
          field('当前 revision', text(activeForm.revision, value => { activeForm.revision = value },
            { required: true, inputmode: 'numeric' })),
          h('button', { type: 'submit', disabled: busy.value }, '切换'),
        ]),
      ])
    }

    function teacherSubmissions() {
      if (!teacher()) return null
      return h('article', { class: 'grading-list' }, [
        h('h3', '班级提交（effective_run 为计入教学的最新有效成绩）'),
        h('div', { class: 'actions' }, [
          select(submissionFilter.experimentId, value => { submissionFilter.experimentId = value }, versionOptions, '全部实验'),
          select(submissionFilter.status, value => { submissionFilter.status = value }, statusOptions),
          button('筛选', () => { submissionPage.value = 1; run(loadSubmissions) }),
        ]),
        submissions.value.length > 0 && h('table', { class: 'grading-cases' }, [
          h('thead', h('tr', [h('th', '提交'), h('th', '学生'), h('th', '最新'), h('th', '有效成绩'), h('th', '操作')])),
          h('tbody', submissions.value.map(row => h('tr', { key: row.id }, [
            h('td', `#${row.id}`),
            h('td', `#${row.student_id}`),
            h('td', describeRun(row.latest_run)),
            h('td', describeRun(row.effective_run)),
            h('td', button('重评', () => startRegrade(row))),
          ]))),
        ]),
        !submissions.value.length && !busy.value && h('p', '暂无提交记录。'),
        h('div', { class: 'actions' }, [
          button('上一页', () => { submissionPage.value--; run(loadSubmissions) },
            { disabled: busy.value || submissionPage.value <= 1 }),
          h('span', `第 ${submissionPage.value} 页 · 共 ${submissionTotal.value} 条`),
          button('下一页', () => { submissionPage.value++; run(loadSubmissions) },
            { disabled: busy.value || submissionPage.value * 20 >= submissionTotal.value }),
        ]),
        regradeTarget.value && h('form', { class: 'inline-form', onSubmit: event => {
          event.preventDefault(); run(confirmRegrade, '重评已排队，产生新 run，旧结果保留。')
        } }, [
          h('h4', `重评提交 #${regradeTarget.value.id}`),
          field('理由（1—500 字符）', text(regradeReason.value, value => { regradeReason.value = value },
            { required: true, maxlength: 500 })),
          h('div', { class: 'actions' }, [
            h('button', { type: 'submit', disabled: busy.value }, '提交重评'),
            button('取消', () => { regradeTarget.value = null }),
          ]),
        ]),
      ])
    }

    onMounted(() => {
      document.addEventListener('cpu-experiment-open', onExperimentOpen)
      run(boot)
    })
    onUnmounted(() => {
      document.removeEventListener('cpu-experiment-open', onExperimentOpen)
      stopPolling()
    })

    return () => h('section', { class: 'card grading-center', 'aria-busy': busy.value }, [
      h('div', { class: 'actions' }, [h('h2', '在线评测（SPEC-018）'), button('重新加载', () => run(boot))]),
      busy.value && h('p', { role: 'status' }, '正在加载或保存…'),
      error.value && h('div', { role: 'alert' }, [h('p', error.value)]),
      notice.value && h('p', { role: 'status' }, notice.value),
      !courses.value.length && !busy.value && !error.value && h('p', '暂无可访问课程。'),
      courses.value.length > 0 && field('评测课程', select(courseId.value, value => {
        courseId.value = value; targetVersion.value = null
        run(async () => { await loadVersions(); if (teacher()) await loadSubmissions() })
      }, Object.fromEntries(courses.value.map(item => [String(item.id), item.title])))),
      teacher() && versions.value.length > 0 && h('div', [
        h('p', '以下为含 circuit 模式的实验版本：'),
        h('ul', { class: 'rows' }, versions.value.map(row => h('li', { key: row.id }, [
          h('span', `#${row.id} · v${row.version} · ${row.title} · ${row.status}`),
          button('配置评测', () => openVersion(row)),
        ]))),
      ]),
      teacher() && versions.value.length === 0 && !busy.value && h('p', '本课程暂无 circuit 模式实验版本。'),
      teacherConfig(),
      teacherSubmissions(),
      props.user.role === 'student' && studentPanel(),
      props.user.role === 'student' && !entry.value
        && h('p', '请在实验中心（SPEC-009）选择已发布实验的「上传 .circ 在线评测」入口。'),
    ])
  },
}
