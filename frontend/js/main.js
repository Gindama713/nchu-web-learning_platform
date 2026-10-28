import { computed, createApp, onMounted, reactive, ref } from 'vue'
import { apiRequest, readApi } from './api.js'
import { QuestionBankView } from './question-view.js'
import { PaperView } from './paper-view.js'
import { AttemptView } from './attempt-view.js'
import { PracticeView } from './practice-view.js'
import { KnowledgeView } from './knowledge-view.js'
import { AnalyticsView } from './analytics-view.js'
import { ResourceView } from './resource-view.js'
import { ExperimentView } from './experiment-view.js'
import { GradingView } from './grading-view.js'
import { QAView } from './qa-view.js'
import { RecommendationView } from './recommendation-view.js'
import { DemoView } from './demo-view.js'
import { KnowledgeGraphView } from './knowledge-graph-view.js'
import { RecognitionView } from './recognition-view.js'
import { WarningView } from './warning-view.js'
import '../styles/main.css'
import '../styles/knowledge.css'
import '../styles/questions.css'
import '../styles/papers.css'
import '../styles/attempts.css'
import '../styles/analytics.css'
import '../styles/resources.css'
import '../styles/experiments.css'
import '../styles/grading.css'
import '../styles/qa.css'
import '../styles/demos.css'
import '../styles/graph.css'
import '../styles/recognition.css'
import '../styles/warnings.css'

createApp({
  components: { KnowledgeView, QuestionBankView, PaperView, AttemptView, PracticeView, AnalyticsView, ResourceView, ExperimentView, GradingView, QAView, RecommendationView, DemoView, KnowledgeGraphView, RecognitionView, WarningView },
  setup() {
    const user = ref(null)
    const practiceEntry = ref(null)
    // 分页导航：一屏放 18 个板块太长，按使用场景分组
    const tabs = [
      { id: 'course', label: '课程与通知' },
      { id: 'content', label: '教学内容' },
      { id: 'exam', label: '测评与练习' },
      { id: 'lab', label: '实验与演示' },
      { id: 'stats', label: '考勤与学情' },
    ]
    const tab = ref('course')
    // 按任务聚合考勤记录，用于任务卡片的到勤进度条
    const taskStats = computed(() => {
      const map = new Map()
      records.value.forEach(record => {
        if (!map.has(record.task_id)) map.set(record.task_id, { present: 0, late: 0, leave: 0, absent: 0, total: 0 })
        const slot = map.get(record.task_id)
        slot[record.status] = (slot[record.status] ?? 0) + 1
        slot.total += 1
      })
      return map
    })
    const attendedOf = id => {
      const slot = taskStats.value.get(id)
      return slot ? slot.present + slot.late : 0
    }
    const totalOf = id => taskStats.value.get(id)?.total ?? 0
    const rateOf = id => {
      const total = totalOf(id)
      return total ? Math.round((attendedOf(id) / total) * 100) : 0
    }
    const myStatusOf = id => records.value.find(record => record.task_id === id)?.status ?? '未记录'
    const timeFormat = new globalThis.Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    })
    const shortTime = value => {
      const date = new Date(value)
      return value && Number.isFinite(date.getTime()) ? timeFormat.format(date) : '时间未知'
    }
    function openRecommendedPractice(entry) {
      practiceEntry.value = entry
      document.querySelector('.practice-bank')?.scrollIntoView({ behavior: 'smooth' })
    }
    const csrf = ref('')
    const message = ref('请登录或注册。')
    const courses = ref([])
    const people = ref([])
    const courseId = ref(null)
    const members = ref([])
    const tasks = ref([])
    const leaves = ref([])
    const records = ref([])
    const warnings = ref([])
    const notifications = ref([])
    const analysis = ref(null)
    const recognition = ref(null)
    const draft = ref('[]')
    const secretCode = ref('')
    const auth = reactive({ student_no: '', name: '', password: '' })
    const courseForm = reactive({ title: '', teacher_id: '', retain_previous_teacher: false })
    const memberNo = ref('')
    const taskForm = reactive({ title: '', start_at: '', late_at: '', end_at: '' })
    const check = reactive({ task_id: '', code: '', reason: '' })
    const analysisFilter = reactive({ from: '', to: '', paper_ids: '' })
    let courseEpoch = 0

    function clearCourse() {
      courseEpoch += 1
      courseId.value = null
      members.value = []
      tasks.value = []
      leaves.value = []
      records.value = []
      warnings.value = []
      analysis.value = null
      recognition.value = null
      draft.value = '[]'
      secretCode.value = ''
      check.task_id = ''
      check.code = ''
      check.reason = ''
      memberNo.value = ''
      analysisFilter.from = ''
      analysisFilter.to = ''
      analysisFilter.paper_ids = ''
    }

    async function act(operation, success) {
      try {
        await operation()
        if (success) message.value = success
      } catch (error) {
        message.value = error.message
      }
    }
    const write = (path, method, payload, headers) => apiRequest(path, method, payload, csrf.value, headers)
    async function refreshCourses() {
      const currentUser = user.value
      const [courseRows, peopleRows, noticeRows] = await Promise.all([
        readApi('/api/v1/courses?page_size=100'),
        currentUser.role === 'admin' ? readApi('/api/v1/users?page_size=100') : Promise.resolve([]),
        readApi('/api/v1/notifications?page_size=100'),
      ])
      if (user.value !== currentUser) return
      courses.value = courseRows
      people.value = peopleRows
      notifications.value = noticeRows
    }
    async function refreshCourse() {
      const id = courseId.value
      const currentUser = user.value
      const epoch = courseEpoch
      if (!id || currentUser.role === 'admin') return
      const base = `/api/v1/courses/${id}`
      const teacher = currentUser.role === 'teacher'
      const [taskRows, leaveRows, recordRows, warningRows, memberRows] = await Promise.all([
        readApi(`${base}/attendance-tasks?page_size=100`),
        readApi(`${base}/leave-requests?page_size=100`),
        readApi(`${base}/attendance-records?page_size=100`),
        teacher ? readApi(`${base}/warnings?page_size=100`) : Promise.resolve([]),
        teacher ? readApi(`${base}/members?page_size=100`) : Promise.resolve([]),
      ])
      if (courseEpoch !== epoch || courseId.value !== id || user.value !== currentUser) return
      tasks.value = taskRows
      leaves.value = leaveRows
      records.value = recordRows
      warnings.value = warningRows
      members.value = memberRows
    }
    async function session() {
      try {
        const data = await readApi('/api/v1/auth/session')
        clearCourse()
        user.value = data.user
        csrf.value = data.csrf_token
        await refreshCourses()
        // 登录后自动选中第一门课，否则考勤/预警/识别三块要手动点课程才出现。
        if (data.user.role !== 'admin' && !courseId.value && courses.value.length) {
          await selectCourse(courses.value[0].id)
        }
        message.value = `欢迎，${data.user.name}。`
      } catch {
        clearCourse()
        user.value = null
        csrf.value = ''
        courses.value = []
        people.value = []
        notifications.value = []
      }
    }
    async function loginRequest() {
      const data = await apiRequest('/api/v1/auth/login', 'POST',
        { student_no: auth.student_no, password: auth.password })
      clearCourse()
      user.value = data.user
      csrf.value = data.csrf_token
      auth.password = ''
      await refreshCourses()
    }
    async function login() {
      await act(loginRequest, '登录成功。')
    }
    async function register() {
      await act(async () => {
        await apiRequest('/api/v1/auth/register', 'POST', { ...auth })
        await loginRequest()
      }, '学生账号已注册。')
    }
    async function logout() {
      await act(async () => {
        await write('/api/v1/auth/logout', 'POST')
        clearCourse()
        user.value = null
        practiceEntry.value = null
        csrf.value = ''
        courses.value = []
        people.value = []
        notifications.value = []
      }, '已退出。')
    }
    async function selectCourse(id) {
      clearCourse()
      courseId.value = Number(id)
      await act(refreshCourse, '课程已加载。')
    }
    async function createCourse() {
      await act(async () => {
        await write('/api/v1/courses', 'POST',
          { title: courseForm.title, teacher_id: Number(courseForm.teacher_id) })
        courseForm.title = ''
        await refreshCourses()
      }, '课程已创建。')
    }
    async function promote(person) {
      await act(async () => {
        await write(`/api/v1/users/${person.id}`, 'PATCH', { role: 'teacher' })
        await refreshCourses()
      }, '教师角色已授予。')
    }
    async function deactivate(person) {
      await act(async () => {
        await write(`/api/v1/users/${person.id}`, 'PATCH', { active: false })
        await refreshCourses()
      }, '账号已停用，旧会话失效。')
    }
    async function transfer() {
      await act(async () => {
        await write(`/api/v1/courses/${courseId.value}`, 'PATCH',
          { teacher_id: Number(courseForm.teacher_id),
            retain_previous_teacher: courseForm.retain_previous_teacher })
        await refreshCourses()
      }, '课程负责人已移交。')
    }
    async function addMember() {
      await act(async () => {
        const id = courseId.value
        const epoch = courseEpoch
        const found = await readApi(`/api/v1/users/lookup?student_no=${encodeURIComponent(memberNo.value)}`)
        if (courseEpoch !== epoch || courseId.value !== id) return
        await write(`/api/v1/courses/${id}/members`, 'POST',
          { user_id: found.id, member_role: 'student' })
        if (courseEpoch === epoch && courseId.value === id) {
          memberNo.value = ''
          await refreshCourse()
        }
      }, '学生已加入课程。')
    }
    async function removeMember(id) {
      await act(async () => {
        await write(`/api/v1/courses/${courseId.value}/members/${id}`, 'DELETE')
        await refreshCourse()
      }, '学生已移出课程；历史冻结名单保留。')
    }
    async function createTask() {
      await act(async () => {
        const id = courseId.value
        const epoch = courseEpoch
        const payload = Object.fromEntries(Object.entries(taskForm).map(([key, value]) =>
          [key, key === 'title' ? value : new Date(value).toISOString()]))
        const data = await write(`/api/v1/courses/${id}/attendance-tasks`, 'POST', payload)
        if (courseEpoch === epoch && courseId.value === id) {
          secretCode.value = data.code
          await refreshCourse()
        }
      }, '任务已创建；明文签到码仅显示本次。')
    }
    async function rotate(id) {
      await act(async () => {
        const epoch = courseEpoch
        const data = await write(`/api/v1/attendance-tasks/${id}/rotate-code`, 'POST')
        if (courseEpoch === epoch) secretCode.value = data.code
      }, '新签到码已生效，旧码失效。')
    }
    async function close(id) {
      await act(async () => {
        const epoch = courseEpoch
        await write(`/api/v1/attendance-tasks/${id}/close`, 'POST')
        if (courseEpoch === epoch) {
          secretCode.value = ''
          await refreshCourse()
        }
      }, '缺勤已结算。')
    }
    async function checkIn() {
      await act(async () => {
        await write(`/api/v1/attendance-tasks/${check.task_id}/check-ins`, 'POST', { code: check.code })
        check.code = ''
        await refreshCourse()
      }, '签到成功。')
    }
    async function leave() {
      await act(async () => {
        await write(`/api/v1/attendance-tasks/${check.task_id}/leave-requests`, 'POST', { reason: check.reason })
        check.reason = ''
        await refreshCourse()
      }, '请假已提交。')
    }
    async function review(id, status) {
      const note = window.prompt('审批理由（必填）')
      if (!note) return
      await act(async () => {
        await write(`/api/v1/leave-requests/${id}`, 'PATCH', { status, note })
        await refreshCourse()
      }, '审批已保存。')
    }
    async function revokeLeave(id) {
      const note = window.prompt('撤销批准理由（必填）')
      if (!note) return
      const restore_status = window.prompt('恢复考勤状态：present / late / absent')
      if (!restore_status) return
      await act(async () => {
        await write(`/api/v1/leave-requests/${id}`, 'PATCH',
          { status: 'rejected', note, restore_status })
        await refreshCourse()
      }, '批准已撤销，考勤状态已更正。')
    }
    async function resubmit(id) {
      const reason = window.prompt('重新填写请假理由（必填）')
      if (!reason) return
      await act(async () => {
        await write(`/api/v1/leave-requests/${id}`, 'PUT', { reason })
        await refreshCourse()
      }, '请假已重新提交。')
    }
    async function correct(record) {
      const status = window.prompt('更正状态：present / late / leave / absent')
      if (!status) return
      const reason = window.prompt('更正理由（必填）')
      if (!reason) return
      await act(async () => {
        await write(`/api/v1/attendance-records/${record.id}`, 'PATCH', { status, reason })
        await refreshCourse()
      }, '考勤更正已记录并通知学生。')
    }
    async function markRead(id) {
      await act(async () => {
        await write(`/api/v1/notifications/${id}`, 'PATCH', { read: true })
        await refreshCourses()
      }, '通知已读。')
    }
    async function analyze() {
      await act(async () => {
        const id = courseId.value
        const epoch = courseEpoch
        const params = new globalThis.URLSearchParams({ dimension: 'attendance' })
        if (analysisFilter.from) params.set('from', new Date(analysisFilter.from).toISOString())
        if (analysisFilter.to) params.set('to', new Date(analysisFilter.to).toISOString())
        for (const paperId of analysisFilter.paper_ids.split(',').map(value => value.trim()).filter(Boolean)) {
          params.append('performance_paper_ids', paperId)
        }
        const data = await readApi(`/api/v1/courses/${id}/analytics?${params}`)
        if (courseEpoch === epoch && courseId.value === id) analysis.value = data
      }, '统计快照已生成。')
    }
    async function warn() {
      await act(async () => {
        const data = await write(`/api/v1/courses/${courseId.value}/warning-runs`, 'POST', undefined,
          { 'Idempotency-Key': crypto.randomUUID() })
        await refreshCourse()
        message.value = data.model_status === 'insufficient_data'
          ? '预警批次已生成；聚类样本不足，仅展示有证据的规则提示。'
          : '预警批次已生成。'
      })
    }
    async function handle(id) {
      const note = window.prompt('处理记录（必填）')
      if (!note) return
      await act(async () => {
        await write(`/api/v1/warnings/${id}`, 'PATCH', { status: 'handled', note })
        await refreshCourse()
      }, '预警已标记处理。')
    }
    async function upload(event) {
      const file = event.target.files?.[0]
      if (!file) return
      await act(async () => {
        const id = courseId.value
        const epoch = courseEpoch
        const data = new FormData()
        data.append('image', file)
        const recognized = await write(`/api/v1/courses/${id}/recognitions`, 'POST', data)
        if (courseEpoch !== epoch || courseId.value !== id) return
        recognition.value = recognized
        draft.value = JSON.stringify(recognized.items.map(({ symbol, bbox, label }) =>
          ({ symbol, bbox, label })), null, 2)
      }, '识别结果仅供人工确认；可修改或删除草稿项。')
    }
    async function confirm() {
      await act(async () => {
        const epoch = courseEpoch
        const id = recognition.value.id
        const confirmed = await write(`/api/v1/recognitions/${id}/confirm`, 'POST',
          { items: JSON.parse(draft.value) })
        if (courseEpoch === epoch && recognition.value?.id === id) recognition.value = confirmed
      }, '结构草稿已确认，不会自动运行或计分。')
    }
    onMounted(session)
    return { user, practiceEntry, openRecommendedPractice, message, courses, people, courseId, members, tasks, leaves, records, warnings, notifications, analysis,
      recognition, draft, secretCode, auth, courseForm, memberNo, taskForm, check, analysisFilter, login, register,
      logout, selectCourse, createCourse, promote, deactivate, transfer, addMember, removeMember, createTask, rotate, close, checkIn,
      leave, review, revokeLeave, resubmit, correct, markRead, analyze, warn, handle, upload, confirm, tab, tabs, attendedOf, totalOf, rateOf, myStatusOf, shortTime }
  },
  template: `
    <main class="page">
      <header :class="['hero', user && 'compact']"><p class="eyebrow">g24201710 · 计算机组成原理</p>
        <h1>中央处理器课程学习系统</h1><p role="status" aria-live="polite">{{ message }}</p>
        <button v-if="user" type="button" @click="logout">退出</button></header>
      <section v-if="!user" class="card"><h2>登录 / 学生注册</h2>
        <label>学号 <input v-model.trim="auth.student_no" minlength="8" maxlength="20" autocomplete="username"></label>
        <label>姓名（注册填写） <input v-model.trim="auth.name" maxlength="50" autocomplete="name"></label>
        <label>密码 <input v-model="auth.password" type="password" minlength="12" autocomplete="current-password"></label>
        <div class="actions"><button type="button" @click="login">登录</button>
          <button type="button" class="secondary" @click="register">注册学生账号</button></div></section>
      <template v-else>
        <nav class="tabbar" role="tablist" aria-label="功能分区">
          <button v-for="item in (user.role === 'admin' ? tabs.slice(0, 1) : tabs)" :key="item.id" type="button" role="tab"
            :aria-selected="tab === item.id" :class="{ active: tab === item.id }"
            @click="tab = item.id">{{ item.label }}</button>
        </nav>

        <template v-if="tab === 'course'">
        <section class="card"><h2>课程概览</h2><p>{{ user.name }} · {{ user.role }}</p>
        <div class="course-list"><button v-for="course in courses" :key="course.id" type="button"
        :class="['course-chip', { active: courseId === course.id }]"
        @click="selectCourse(course.id)">{{ course.title }}</button></div>
        <p v-if="!courses.length">暂无课程。</p>
        <template v-if="courseId">
        <div class="course-summary">
        <div class="sum-tile"><span>课程成员</span><strong>{{ members.length }}</strong></div>
        <div class="sum-tile"><span>考勤任务</span><strong>{{ tasks.length }}</strong></div>
        <div class="sum-tile"><span>待批请假</span><strong>{{ leaves.filter(item => item.status === 'pending').length }}</strong></div>
        <div class="sum-tile"><span>未读通知</span><strong>{{ notifications.filter(item => !item.read_at).length }}</strong></div>
        </div>
        <p class="course-hint">课程的具体功能按场景分在下面几个分区里，点按钮直接跳转：</p>
        <div class="actions">
        <button type="button" class="secondary" @click="tab = 'content'">教学内容</button>
        <button type="button" class="secondary" @click="tab = 'exam'">测评与练习</button>
        <button type="button" class="secondary" @click="tab = 'lab'">实验与演示</button>
        <button type="button" class="secondary" @click="tab = 'stats'">考勤与学情</button>
        </div>
        </template></section>
        <section v-if="user.role === 'admin'" class="card"><h2>课程与账号管理</h2>
        <section v-if="user.role === 'admin'" class="card"><h2>课程与账号管理</h2>
        <form class="inline-form" @submit.prevent="createCourse">
        <label>课程名称 <input v-model.trim="courseForm.title" required></label>
        <label>负责教师 <select v-model="courseForm.teacher_id" required><option value="">请选择</option>
        <option v-for="person in people.filter(p => p.role === 'teacher' && p.active)" :key="person.id" :value="person.id">{{ person.name }} · {{ person.student_no }}</option>
        </select></label><button>创建课程</button></form>
        <form v-if="courseId" class="inline-form" @submit.prevent="transfer">
        <p>当前选中课程 #{{ courseId }}。选择上方教师后可移交负责人。</p>
        <label><input v-model="courseForm.retain_previous_teacher" type="checkbox"> 保留原教师课程成员身份</label>
        <button>移交负责人</button></form>
        <ul class="rows"><li v-for="person in people" :key="person.id">{{ person.name }} · {{ person.student_no }} · {{ person.role }}
        <button v-if="person.role === 'student'" type="button" class="secondary" @click="promote(person)">设为教师</button>
        <button v-if="person.role !== 'admin' && person.active" type="button" class="secondary" @click="deactivate(person)">停用</button></li></ul></section>
        <section class="card"><h2>通知</h2><ul class="rows"><li v-for="item in notifications" :key="item.id">{{ item.title }} · {{ item.read_at ? '已读' : '未读' }}
        <button v-if="!item.read_at" type="button" class="secondary" @click="markRead(item.id)">标记已读</button></li></ul></section>
        </template>

        <template v-if="tab === 'content' && user.role !== 'admin'">
        <knowledge-view />
        <knowledge-graph-view v-if="user.role !== 'admin'" :key="'graph:' + user.id + ':' + user.role" :user="user" />
        <QAView :key="'qa:' + user.id + ':' + user.role" :user="user" />
        <ResourceView v-if="user.role !== 'admin'" :key="'resources:' + user.id + ':' + user.role" />
        </template>

        <template v-if="tab === 'exam' && user.role !== 'admin'">
        <QuestionBankView v-if="user.role !== 'admin'" :key="user.id + ':' + user.role" :user="user" />
        <PaperView v-if="user.role !== 'admin'" :key="'papers:' + user.id + ':' + user.role" :user="user" />
        <PaperView v-if="user.role !== 'admin'" :key="'quizzes:' + user.id + ':' + user.role" :user="user" quiz-only />
        <AttemptView v-if="user.role !== 'admin'" :key="'attempts:' + user.id + ':' + user.role" :user="user" />
        <RecommendationView v-if="user.role === 'student'" :key="'recommendation:' + user.id + ':' + user.role" :user="user" @practice="openRecommendedPractice" />
        <PracticeView v-if="user.role === 'student'" :key="'practice:' + user.id + ':' + user.role" :user="user" :entry="practiceEntry" />
        </template>

        <template v-if="tab === 'lab' && user.role !== 'admin'">
        <DemoView v-if="user.role !== 'admin'" :key="'demo:' + user.id + ':' + user.role" :user="user" />
        <ExperimentView v-if="user.role !== 'admin'" :key="'experiments:' + user.id + ':' + user.role" :user="user" />
        <GradingView v-if="user.role !== 'admin'" :key="'grading:' + user.id + ':' + user.role" :user="user" />
        <RecognitionView :key="'recog:' + user.id" :user="user" />
        </template>

        <template v-if="tab === 'stats' && user.role !== 'admin' && courseId">
        <template v-if="courseId && user.role !== 'admin'">
        <section class="card"><h2>考勤与请假</h2>
        <div class="att-summary">
        <div class="sum-tile"><span>考勤任务</span><strong>{{ tasks.length }}</strong></div>
        <div class="sum-tile"><span>进行中</span><strong>{{ tasks.filter(item => item.status === 'open').length }}</strong></div>
        <div class="sum-tile"><span>待批请假</span><strong>{{ leaves.filter(item => item.status === 'pending').length }}</strong></div>
        <div class="sum-tile"><span>考勤记录</span><strong>{{ records.length }}</strong></div>
        </div>

        <p v-if="secretCode" class="att-code">本次签到码 <strong>{{ secretCode }}</strong><small>刷新后不可找回，可轮换</small></p>

        <ul class="att-tasks">
        <li v-for="item in tasks" :key="item.id" :class="['att-task', item.status]">
        <div class="att-task-head">
        <strong>{{ item.title }}</strong>
        <span :class="['att-badge', item.status]">{{ item.status === 'open' ? '进行中' : '已结算' }}</span>
        <span class="att-time">截止 {{ shortTime(item.end_at) }}</span>
        </div>
        <template v-if="user.role === 'teacher'">
        <div class="att-bar"><i :class="rateOf(item.id) >= 80 ? 'good' : rateOf(item.id) > 0 ? 'mid' : 'low'" :style="'width:' + rateOf(item.id) + '%'"></i></div>
        <p class="att-meta">到勤 {{ attendedOf(item.id) }} / {{ totalOf(item.id) }} 人次<b>{{ rateOf(item.id) }}%</b></p>
        </template>
        <p v-else class="att-meta">我的状态：{{ myStatusOf(item.id) }}</p>
        <div v-if="user.role === 'teacher' && item.status === 'open'" class="att-actions">
        <button type="button" class="secondary" @click="rotate(item.id)">轮换码</button>
        <button type="button" @click="close(item.id)">结算</button>
        </div>
        </li>
        </ul>
        <p v-if="!tasks.length">还没有考勤任务。</p>

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>发布考勤任务</summary>
        <form class="inline-form" @submit.prevent="createTask">
        <label>任务 <input v-model.trim="taskForm.title" required></label>
        <label>开始 <input v-model="taskForm.start_at" type="datetime-local" required></label>
        <label>迟到起点 <input v-model="taskForm.late_at" type="datetime-local" required></label>
        <label>结束 <input v-model="taskForm.end_at" type="datetime-local" required></label><button>创建</button></form>
        </details>

        <form v-if="user.role === 'student' && tasks.length" class="inline-form att-checkin" @submit.prevent="checkIn">
        <label>任务 <select v-model="check.task_id" required><option value="">请选择</option><option v-for="item in tasks" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
        <label>签到码 <input v-model.trim="check.code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></label><button>签到</button></form>
        <form v-if="user.role === 'student' && check.task_id" class="inline-form" @submit.prevent="leave">
        <label>请假理由 <input v-model.trim="check.reason" maxlength="500" required></label><button class="secondary">申请请假</button></form>

        <h3>请假记录</h3>
        <ul class="att-leaves">
        <li v-for="item in leaves" :key="item.id" :class="['att-leave', item.status]">
        <span class="att-leave-reason">{{ item.reason }}</span>
        <span :class="['att-badge', item.status]">{{ item.status }}</span>
        <span class="att-actions">
        <button v-if="user.role === 'teacher' && item.status === 'pending'" type="button" @click="review(item.id, 'approved')">批准</button>
        <button v-if="user.role === 'teacher' && item.status === 'pending'" type="button" class="secondary" @click="review(item.id, 'rejected')">驳回</button>
        <button v-if="user.role === 'teacher' && item.status === 'approved'" type="button" class="secondary" @click="revokeLeave(item.id)">撤销批准</button>
        <button v-if="user.role === 'student' && item.status === 'rejected'" type="button" class="secondary" @click="resubmit(item.id)">修改重提</button>
        </span>
        </li>
        </ul>
        <p v-if="!leaves.length">暂无请假记录。</p>

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>课程成员（{{ members.length }}）与加入</summary>
        <form class="inline-form" @submit.prevent="addMember">
        <label>学生完整学号 <input v-model.trim="memberNo" required></label><button>加入课程</button></form>
        <ul class="rows"><li v-for="member in members" :key="member.user_id">
        {{ member.name }} · {{ member.student_no }} · {{ member.member_role }} · {{ member.active ? '在课' : '已移出' }}
        <button v-if="member.member_role === 'student' && member.active" type="button" class="secondary"
        @click="removeMember(member.user_id)">移出课程</button></li></ul>
        </details>

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>有效考勤明细（{{ records.length }} 条）</summary>
        <ul class="rows"><li v-for="item in records" :key="item.id">任务 #{{ item.task_id }} · 学生 #{{ item.student_id }} · {{ item.status }}
        <button type="button" class="secondary" @click="correct(item)">更正</button></li></ul>
        </details>
        </section>
        <AnalyticsView v-if="user.role !== 'admin'" :key="'analytics:' + user.id + ':' + user.role" :user="user" />
        <WarningView :key="'warning:' + user.id" :user="user" />
        </template>
      </template>
    </main>`,
}).mount('#app')
