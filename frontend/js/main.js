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
import { AluView } from './alu-view.js'
import { KnowledgeGraphView } from './knowledge-graph-view.js'
import { RecognitionView } from './recognition-view.js'
import { WarningView } from './warning-view.js'
import { PreparationView } from './preparation-view.js'
import { WiringView } from './wiring-view.js'
import { WiringStatsView } from './wiring-stats-view.js'
import { GesturePad } from './gesture-pad.js'
import '../styles/main.css'
import '../styles/knowledge.css'
import '../styles/questions.css'
import '../styles/papers.css'
import '../styles/attempts.css'
import '../styles/analytics.css'
import '../styles/charts.css'
import '../styles/resources.css'
import '../styles/experiments.css'
import '../styles/grading.css'
import '../styles/qa.css'
import '../styles/demos.css'
import '../styles/alu.css'
import '../styles/graph.css'
import '../styles/recognition.css'
import '../styles/warnings.css'
import '../styles/preparations.css'
import '../styles/wiring.css'
import '../styles/wiring-stats.css'

createApp({
  components: { KnowledgeView, QuestionBankView, PaperView, AttemptView, PracticeView, AnalyticsView, ResourceView, ExperimentView, GradingView, QAView, RecommendationView, DemoView, AluView, KnowledgeGraphView, RecognitionView, WarningView, PreparationView, WiringView, WiringStatsView, GesturePad },
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
    // 课程封面：按 id 取渐变，同一门课颜色固定，避免每次刷新变来变去
    const COVERS = [
      'linear-gradient(135deg, #2f6fd0, #17408a)',
      'linear-gradient(135deg, #16a394, #0d7368)',
      'linear-gradient(135deg, #f2994a, #c96f22)',
      'linear-gradient(135deg, #9b6dd6, #67409f)',
      'linear-gradient(135deg, #eb5757, #b13434)',
      'linear-gradient(135deg, #4a90d9, #2b64a8)',
      'linear-gradient(135deg, #56b98a, #35805e)',
      'linear-gradient(135deg, #7f8fa6, #55647a)',
    ]
    const coverOf = id => COVERS[Number(id) % COVERS.length]

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
    const account = reactive({ name: '', old_password: '', new_password: '', confirm: '' })
    const accountSaving = ref(false)
    const resubmitTarget = ref(null)
    const resubmitReason = ref('')
    const correctTarget = ref(null)
    const correctStatus = ref('present')
    const correctReason = ref('')
    async function saveName() {
      if (accountSaving.value) return
      accountSaving.value = true
      await act(async () => {
        const updated = await write('/api/v1/users/me', 'PATCH', { name: account.name })
        if (user.value) user.value = { ...user.value, name: updated.name }
      }, '姓名已更新。')
      accountSaving.value = false
    }
    async function savePassword() {
      if (accountSaving.value) return
      if (account.new_password !== account.confirm) {
        message.value = '两次输入的新密码不一致。'
        return
      }
      accountSaving.value = true
      await act(async () => {
        await write('/api/v1/users/me', 'PATCH',
          { old_password: account.old_password, new_password: account.new_password })
        account.old_password = ''
        account.new_password = ''
        account.confirm = ''
      }, '密码已修改，其他设备的登录已失效；当前会话保持。')
      accountSaving.value = false
    }
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
    const message = ref('')
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
    // 登录页把「登录」和「注册」分成两个页签，不再把注册姓名、演示账号、使用说明全堆在一个卡片里
    const authMode = ref('login')
    const demoStudentNo = ref('')
    const courseForm = reactive({ title: '', teacher_id: '', retain_previous_teacher: false })
    const memberNo = ref('')
    const taskForm = reactive({ title: '', start_at: '', late_at: '', end_at: '' })
    const check = reactive({ task_id: '', code: '', reason: '', mode: 'code' })
    // 手势签到：enrolled 表示是否已设置图案；first 暂存第一次画的图案等确认
    const gesture = reactive({ enrolled: false, updated_at: null, first: null, hint: '按住并划过至少 4 个点。' })
    const analysisFilter = reactive({ from: '', to: '', paper_ids: '' })
    // 课堂点到座位图：一整张平面网格，四个班混排在同一间教室里
    const seatData = ref(null)
    const seatDetail = ref(null)
    // 教室规模：教师可以按自己的教室改行列，预设只是快捷入口
    const room = ref(null)
    const roomForm = reactive({ name: '', template: 'custom', rows: 10, cols: 12, aisle_every: 0 })
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
      seatData.value = null
      seatDetail.value = null
      room.value = null
      check.task_id = ''
      check.code = ''
      check.reason = ''
      check.mode = 'code'
      gesture.first = null
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
      const [taskRows, leaveRows, recordRows, warningRows, memberRows, roomRow, gestureRow] = await Promise.all([
        readApi(`${base}/attendance-tasks?page_size=100`),
        readApi(`${base}/leave-requests?page_size=100`),
        readApi(`${base}/attendance-records?page_size=100`),
        teacher ? readApi(`${base}/warnings?page_size=100`) : Promise.resolve([]),
        teacher ? readApi(`${base}/members?page_size=100`) : Promise.resolve([]),
        teacher ? readApi(`${base}/classroom`) : Promise.resolve(null),
        currentUser.role === 'student' ? readApi('/api/v1/auth/gesture') : Promise.resolve(null),
      ])
      if (courseEpoch !== epoch || courseId.value !== id || user.value !== currentUser) return
      tasks.value = taskRows
      leaves.value = leaveRows
      records.value = recordRows
      warnings.value = warningRows
      members.value = memberRows
      if (roomRow) syncRoom(roomRow)
      if (gestureRow) {
        gesture.enrolled = gestureRow.enrolled
        gesture.updated_at = gestureRow.updated_at
        // 已录入时先提醒会被覆盖，否则学生一进来随手画两下就把旧图案换掉了
        if (gesture.enrolled && !gesture.first) {
          gesture.hint = '已设置图案。要更换就再连画两次新图案，不想换就别在这里画。'
        }
      }
    }
    async function session() {
      try {
        const data = await readApi('/api/v1/auth/session')
        clearCourse()
        user.value = data.user
        account.name = data.user.name
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
      // 登录后同样自动选中第一门课，否则直接切到「考勤与学情」会是一片空白。
      if (user.value.role !== 'admin' && !courseId.value && courses.value.length) {
        await selectCourse(courses.value[0].id)
      }
    }
    async function login() {
      await act(loginRequest, '登录成功。')
    }
    function fillTeacher() {
      auth.student_no = 'teacher'
      auth.password = 'teacher'
      message.value = '已填入教师账号 teacher，点击“登录”进入。'
    }
    function fillStudent() {
      const number = demoStudentNo.value.trim() || '24200000'
      auth.student_no = number
      auth.password = number
      message.value = `已填入学生账号 ${number}，密码与学号相同。`
    }
    async function register() {
      await act(async () => {
        const number = auth.student_no
        await apiRequest('/api/v1/auth/register', 'POST', { student_no: number, name: auth.name })
        auth.password = number
        await loginRequest()
      }, '学生账号已注册，默认密码为学号。')
    }
    async function loadSeats(taskId) {
      await act(async () => {
        const data = await readApi('/api/v1/attendance-tasks/' + taskId + '/seats')
        seatData.value = data
        // 学生打开座位图是为了找自己坐哪，所以默认就选中本人座位，不用在 133 个格子里翻
        seatDetail.value = user.value?.role === 'student'
          ? (data.seats ?? []).find(seat => seat.student_id === user.value.id) ?? null
          : null
      })
    }
    const seatList = computed(() => seatData.value?.seats ?? [])
    // 我在图上的那一个座位；教师看的时候为 null
    const mySeat = computed(() => {
      if (user.value?.role !== 'student') return null
      return seatList.value.find(seat => seat.student_id === user.value.id) ?? null
    })
    const seatStats = computed(() => {
      const counts = { present: 0, late: 0, leave: 0, absent: 0, pending: 0 }
      seatList.value.forEach(seat => { counts[seat.status] = (counts[seat.status] ?? 0) + 1 })
      return counts
    })
    // 四个班混排在一张图里，颜色是唯一能区分班级的线索，所以按班名固定取色
    const SEAT_COLORS = ['#2f6fd0', '#16a394', '#f2994a', '#9b6dd6', '#d9534f', '#4a90d9', '#56b98a']
    const seatClasses = computed(() => [...new Set(seatList.value.map(seat => seat.class_name))].sort())
    const classColor = name => SEAT_COLORS[Math.max(0, seatClasses.value.indexOf(name)) % SEAT_COLORS.length]
    const seatIndex = computed(() => {
      const map = new Map()
      seatList.value.forEach(seat => map.set(`${seat.group_no}-${seat.seat_no}`, seat))
      return map
    })
    const seatAisle = computed(() => seatData.value?.classroom?.aisle_every || 0)
    // 有过道时第 col 座落在第几列：把过道本身也算作一列，grid-column 才对得上
    const seatSlot = col => {
      const aisle = seatAisle.value
      return aisle ? col + Math.floor((col - 1) / aisle) : col
    }
    const seatColumns = computed(() => {
      if (!seatData.value) return ''
      const total = seatData.value.grid.cols
      // 第 1 列留给排号，座位从第 2 列起算
      const parts = ['34px']
      for (let col = 1; col <= total; col += 1) {
        parts.push('minmax(68px, 1fr)')
        if (seatAisle.value && col % seatAisle.value === 0 && col < total) parts.push('14px')
      }
      return parts.join(' ')
    })
    const seatRows = computed(() => {
      if (!seatData.value) return []
      const grid = []
      for (let row = 1; row <= seatData.value.grid.rows; row += 1) {
        const cells = []
        for (let col = 1; col <= seatData.value.grid.cols; col += 1) {
          cells.push({ key: `${row}-${col}`, col, slot: seatSlot(col), seat: seatIndex.value.get(`${row}-${col}`) ?? null })
        }
        grid.push({ row, cells })
      }
      return grid
    })
    // 图下面三栏名单：已到（含迟到）/ 未到（未签到 + 缺勤）/ 请假
    const seatRosters = computed(() => {
      const buckets = { here: [], away: [], leave: [] }
      seatList.value.forEach(seat => {
        const bucket = seat.status === 'leave' ? 'leave' : ['present', 'late'].includes(seat.status) ? 'here' : 'away'
        buckets[bucket].push(seat)
      })
      Object.values(buckets).forEach(list => list.sort(
        (left, right) => left.group_no - right.group_no || left.seat_no - right.seat_no))
      return buckets
    })
    const seatText = status => ({
      present: '已到', late: '迟到', leave: '请假', absent: '缺勤', pending: '未签到',
    }[status] ?? status)
    const sourceText = source => ({ checkin: '签到码', gesture: '手势图案', close: '系统结算' }[source] ?? '—')
    const seatLabel = seat => seat ? `${seat.group_no} 排 ${seat.seat_no} 座` : '未排座'

    function syncRoom(data) {
      room.value = data
      roomForm.name = data.name
      roomForm.template = data.template
      roomForm.rows = data.rows
      roomForm.cols = data.cols
      roomForm.aisle_every = data.aisle_every
    }
    function applyPreset(preset) {
      roomForm.name = preset.label
      roomForm.template = preset.template
      roomForm.rows = preset.rows
      roomForm.cols = preset.cols
      roomForm.aisle_every = preset.aisle_every
      message.value = `已套用「${preset.label}」${preset.rows} 排 × ${preset.cols} 座，点「保存教室」生效。`
    }
    async function refreshSeatmap() {
      if (seatData.value) await loadSeats(seatData.value.task.id)
      if (courseId.value) syncRoom(await readApi(`/api/v1/courses/${courseId.value}/classroom`))
    }
    async function saveRoom() {
      await act(async () => {
        const data = await write(`/api/v1/courses/${courseId.value}/classroom`, 'PUT', {
          name: roomForm.name, template: 'custom', rows: Number(roomForm.rows),
          cols: Number(roomForm.cols), aisle_every: Number(roomForm.aisle_every),
        })
        syncRoom(data)
        if (seatData.value) await loadSeats(seatData.value.task.id)
        message.value = data.removed
          ? `教室已保存，清理了 ${data.removed} 个越出教室的座位。`
          : '教室已保存。'
      })
    }
    async function autoSeat() {
      await act(async () => {
        const data = await write(`/api/v1/courses/${courseId.value}/classroom/auto-seat`, 'POST', {})
        syncRoom(data)
        if (seatData.value) await loadSeats(seatData.value.task.id)
        message.value = `已按班排座，${data.placed} 人入座。`
      })
    }
    async function unseat(studentId) {
      await act(async () => {
        await write(`/api/v1/courses/${courseId.value}/seats/${studentId}`, 'PATCH', { clear: true })
        await refreshSeatmap()
        message.value = '已把该学生撤出座位表。'
      })
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
    // 手势图案：录入要连画两次确认，签到则松手即提交
    async function enrollGesture(pattern, pad) {
      if (pattern.length < 4) {
        gesture.first = null
        gesture.hint = '至少连接 4 个点，请重画。'
        return
      }
      if (!gesture.first) {
        gesture.first = pattern
        gesture.hint = '请再画一次同样的图案确认。'
        return
      }
      if (gesture.first.join('-') !== pattern.join('-')) {
        gesture.first = null
        gesture.hint = '两次不一致，请重新开始。'
        pad?.reset()
        return
      }
      await act(async () => {
        await write('/api/v1/auth/gesture', 'PUT', { pattern })
        gesture.first = null
        gesture.enrolled = true
        gesture.hint = '手势图案已保存，以后可以画它签到。'
        pad?.reset()
      })
    }
    async function checkInByGesture(pattern, pad) {
      if (!check.task_id) {
        message.value = '请先选择要点到的任务。'
        pad?.reset()
        return
      }
      await act(async () => {
        await write(`/api/v1/attendance-tasks/${check.task_id}/check-ins`, 'POST', { pattern })
        await refreshCourse()
        // 成功后不擦图案：让学生看到自己刚画的那一笔，下次按下时会自动清空
      }, '手势签到成功。')
    }
    async function clearGesture() {
      await act(async () => {
        await write('/api/v1/auth/gesture', 'DELETE')
        gesture.enrolled = false
        gesture.first = null
        gesture.hint = '已清除手势图案，可以重新设置。'
      })
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
      const reason = resubmitReason.value.trim()
      if (!reason) {
        message.value = '请填写请假理由后再提交。'
        return
      }
      await act(async () => {
        await write(`/api/v1/leave-requests/${id}`, 'PUT', { reason })
        resubmitTarget.value = null
        resubmitReason.value = ''
        await refreshCourse()
      }, '请假已重新提交。')
    }
    function cancelResubmit() {
      resubmitTarget.value = null
      resubmitReason.value = ''
    }
    function beginResubmit(id) {
      resubmitTarget.value = id
      resubmitReason.value = ''
    }
    async function correct(record) {
      const reason = correctReason.value.trim()
      if (!reason) {
        message.value = '更正理由必填（会通知学生）。'
        return
      }
      await act(async () => {
        await write(`/api/v1/attendance-records/${record.id}`, 'PATCH',
          { status: correctStatus.value, reason })
        correctTarget.value = null
        correctReason.value = ''
        await refreshCourse()
      }, '考勤更正已记录并通知学生。')
    }
    function beginCorrect(id, status) {
      correctTarget.value = id
      correctStatus.value = status
      correctReason.value = ''
    }
    function cancelCorrect() {
      correctTarget.value = null
      correctReason.value = ''
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
      recognition, draft, secretCode, auth, authMode, courseForm, memberNo, taskForm, check, analysisFilter, login, register,
      demoStudentNo, fillTeacher, fillStudent,
      seatData, seatDetail, loadSeats, seatList, seatStats, seatColumns, seatText, seatRows, seatClasses, mySeat,
      classColor, seatRosters, sourceText, seatLabel, seatSlot, room, roomForm, applyPreset, saveRoom, autoSeat, unseat,
      logout, selectCourse, createCourse, promote, deactivate, transfer, addMember, removeMember, createTask, rotate, close, checkIn,
      leave, review, revokeLeave, resubmit, correct, markRead, analyze, warn, handle, upload, confirm, tab, tabs, attendedOf, totalOf, rateOf, myStatusOf, shortTime, coverOf, account, accountSaving, saveName, savePassword, resubmitTarget, resubmitReason, beginResubmit, cancelResubmit, correctTarget, correctStatus, correctReason, beginCorrect, cancelCorrect, gesture, enrollGesture, checkInByGesture, clearGesture }
  },
  template: `
    <main :class="['page', user ? '' : 'page-auth']">
      <header v-if="user" class="hero compact"><p class="eyebrow">g24201710 · 计算机组成原理</p>
        <h1>中央处理器课程学习系统</h1><p role="status" aria-live="polite">{{ message }}</p>
        <button type="button" @click="logout">退出</button></header>
      <section v-if="!user" class="auth">
        <aside class="auth-side">
        <span class="auth-logo" aria-hidden="true">计</span>
        <p class="auth-eyebrow">g24201710 · 2024 级计算机科学与技术</p>
        <h1>中央处理器<br>课程学习系统</h1>
        <p class="auth-lead">课堂点到、座位图、练习与评测，一个入口。</p>
        <ul class="auth-points">
        <li><b>四班同堂</b>133 人一张座位图，按班分段排座，登录就能看到自己坐哪。</li>
        <li><b>两种点到</b>签到码或者手势图案，学生自己挑一种。</li>
        <li><b>随堂留痕</b>练习、错题、讲评自动归档，不用另外记。</li>
        </ul>
        </aside>
        <section class="auth-card">
        <div class="auth-tabs" role="tablist" aria-label="登录或注册">
        <button type="button" role="tab" :aria-selected="authMode === 'login'" :class="{ active: authMode === 'login' }"
          @click="authMode = 'login'">登录</button>
        <button type="button" role="tab" :aria-selected="authMode === 'register'" :class="{ active: authMode === 'register' }"
          @click="authMode = 'register'">注册</button>
        </div>
        <h2>{{ authMode === 'login' ? '欢迎回来' : '创建学生账号' }}</h2>
        <p class="auth-sub">{{ authMode === 'login' ? '用学号登录，初始密码与学号相同。' : '填学号和姓名即可，默认密码就是学号。' }}</p>
        <form class="auth-form" @submit.prevent="authMode === 'login' ? login() : register()">
        <label class="auth-field"><span>学号</span>
          <input id="username" v-model.trim="auth.student_no" maxlength="20" autocomplete="username" placeholder="例如 24201718" required></label>
        <label v-if="authMode === 'register'" class="auth-field"><span>姓名</span>
          <input v-model.trim="auth.name" maxlength="50" autocomplete="name" placeholder="与名单一致" required></label>
        <label class="auth-field"><span>密码</span>
          <input id="password" v-model="auth.password" type="password" placeholder="与学号相同"
            :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" required></label>
        <button id="login" class="auth-submit" type="submit">{{ authMode === 'login' ? '登 录' : '注册并登录' }}</button>
        </form>
        <p class="auth-msg" role="status" aria-live="polite">{{ message }}</p>
        <div v-if="authMode === 'login'" class="auth-demo">
        <p class="auth-demo-title">演示账号</p>
        <label class="auth-demo-input"><span>学生学号</span>
          <input id="student-no" v-model.trim="demoStudentNo" maxlength="20" placeholder="24200000"></label>
        <div class="auth-demo-row">
        <button id="auto-fill-teacher" type="button" @click="fillTeacher">填入教师 teacher</button>
        <button id="auto-fill-student" type="button" @click="fillStudent">填入学生 {{ demoStudentNo || '24200000' }}</button>
        </div>
        <p class="auth-demo-tip">密码与学号相同，填好后点上面的登录。</p>
        </div>
        <details class="auth-help">
        <summary>使用说明</summary>
        <ol>
          <li>教师演示：点「填入教师 teacher」，再点登录。</li>
          <li>学生演示：在「学生学号」填学号，点「填入学生」，密码与学号相同。</li>
          <li>学生注册：切到上方「注册」，填学号与姓名，默认密码为学号。</li>
          <li>四个班的真实名单由管理员运行导入脚本建立，重复导入不会产生重复账号。</li>
        </ol>
        </details>
        </section>
      </section>
      <template v-else>
        <nav class="tabbar" role="tablist" aria-label="功能分区">
          <button v-for="item in (user.role === 'admin' ? tabs.slice(0, 1) : tabs)" :key="item.id" type="button" role="tab"
            :aria-selected="tab === item.id" :class="{ active: tab === item.id }"
            @click="tab = item.id">{{ item.label }}</button>
        </nav>

        <template v-if="tab === 'course'">
        <section class="card"><h2>课程概览</h2><p>{{ user.name }} · {{ user.role }}</p>
        <p class="course-count">共 {{ courses.length }} 门课程，点击卡片切换</p>
        <div class="course-grid">
        <button v-for="course in courses" :key="course.id" type="button"
        :class="['course-card', { active: courseId === course.id }]"
        :style="'--cover:' + coverOf(course.id)"
        @click="selectCourse(course.id)">
        <span class="course-cover">
        <span class="course-initial">{{ String(course.id).padStart(2, '0') }}</span>
        <span v-if="courseId === course.id" class="course-check">当前</span>
        </span>
        <span class="course-body">
        <strong class="course-title">{{ course.title }}</strong>
        <small class="course-meta">{{ course.description || ('课程 #' + course.id) }}</small>
        </span>
        </button>
        </div>
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
        </template>
        </section>
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
        <section class="card"><h2>账号设置</h2>
        <p class="account-hint">姓名会显示在成员列表与统计里；改密码需要先验证当前密码，修改后其他设备会被退出登录。</p>
        <div class="account-grid">
        <form class="account-form" @submit.prevent="saveName">
        <h3>修改姓名</h3>
        <label>姓名 <input v-model.trim="account.name" maxlength="50" required></label>
        <div class="actions"><button type="submit" :disabled="accountSaving">保存姓名</button></div>
        </form>
        <form class="account-form" @submit.prevent="savePassword">
        <h3>修改密码</h3>
        <label>当前密码 <input v-model="account.old_password" type="password" autocomplete="current-password" required></label>
        <label>新密码 <input v-model="account.new_password" type="password" minlength="12" autocomplete="new-password" required></label>
        <label>确认新密码 <input v-model="account.confirm" type="password" minlength="12" autocomplete="new-password" required></label>
        <div class="actions"><button type="submit" :disabled="accountSaving">修改密码</button></div>
        </form>
        </div></section>
        </template>

        <template v-if="tab === 'content' && user.role !== 'admin'">
        <knowledge-view />
        <knowledge-graph-view v-if="user.role !== 'admin'" :key="'graph:' + user.id + ':' + user.role" :user="user" />
        <QAView :key="'qa:' + user.id + ':' + user.role" :user="user" />
        <ResourceView v-if="user.role !== 'admin'" :key="'resources:' + user.id + ':' + user.role" />
        <PreparationView v-if="user.role !== 'admin'" :key="'preparations:' + user.id + ':' + user.role" :user="user" />
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
        <AluView :key="'alu:' + user.id" :user="user" />
        <DemoView v-if="user.role !== 'admin'" :key="'demo:' + user.id + ':' + user.role" :user="user" />
        <ExperimentView v-if="user.role !== 'admin'" :key="'experiments:' + user.id + ':' + user.role" :user="user" />
        <GradingView v-if="user.role !== 'admin'" :key="'grading:' + user.id + ':' + user.role" :user="user" />
        <RecognitionView :key="'recog:' + user.id" :user="user" />
        <WiringView v-if="user.role !== 'admin'" :key="'wiring:' + user.id + ':' + user.role" :user="user" />
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

        <p v-if="user.role === 'teacher'" class="att-meta">访问日志：<a href="/api/v1/logs/access.csv" target="_blank" rel="noopener">导出 CSV</a>　<a href="/api/v1/logs/audit.csv" target="_blank" rel="noopener">关键操作审计 CSV</a>　<a href="/api/v1/logs/access" target="_blank" rel="noopener">JSON</a></p>
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
        <p v-else class="att-meta">我的状态：{{ seatText(myStatusOf(item.id)) }}</p>
        <div class="att-actions">
        <button type="button" class="secondary" @click="loadSeats(item.id)">{{ user.role === 'teacher' ? '教室座位图' : '看看我坐哪' }}</button>
        <template v-if="user.role === 'teacher'">
        <button v-if="item.status === 'open'" type="button" class="secondary" @click="rotate(item.id)">轮换码</button>
        <button v-if="item.status === 'open'" type="button" @click="close(item.id)">结算</button>
        </template>
        </div>
        </li>
        </ul>
        <p v-if="!tasks.length">还没有考勤任务。</p>

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>教室设置（{{ room ? room.name + ' · ' + roomForm.rows + ' 排 × ' + roomForm.cols + ' 座' : '加载中' }}）</summary>
        <div v-if="room" class="room-presets">
        <button v-for="preset in room.presets" :key="preset.template" type="button" class="secondary"
          @click="applyPreset(preset)">{{ preset.label }} · {{ preset.rows }} 排 × {{ preset.cols }} 座</button>
        </div>
        <form v-if="room" class="inline-form" @submit.prevent="saveRoom">
        <label>教室名称 <input v-model.trim="roomForm.name" maxlength="40" required></label>
        <label>排数 <input v-model.number="roomForm.rows" type="number" min="1" :max="room.limits.rows" required></label>
        <label>每排座位 <input v-model.number="roomForm.cols" type="number" min="1" :max="room.limits.cols" required></label>
        <label>过道间隔 <input v-model.number="roomForm.aisle_every" type="number" min="0" :max="room.limits.aisle_every"></label>
        <button>保存教室</button></form>
        <p v-if="room" class="att-meta">容量 {{ room.capacity }} 座　学生 {{ room.students }} 人　已排座 {{ room.seated }} 人　未排 {{ room.unseated }} 人</p>
        <div v-if="room" class="att-actions">
        <button type="button" @click="autoSeat">一键按班排座</button>
        <span class="att-meta">按班级顺序整排起排，四个班各占一段连续排；教室不够时会直接报错而不是硬塞。</span>
        </div>
        </details>

        <div v-if="seatData" class="seatmap">
        <div class="seatmap-head">
        <strong>教室座位图 · {{ seatData.task.title }}</strong>
        <span class="seatmap-room">{{ seatData.classroom.name }}　{{ seatData.classroom.rows }} 排 × {{ seatData.classroom.cols }} 座<template
          v-if="seatData.grid.rows > seatData.classroom.rows || seatData.grid.cols > seatData.classroom.cols"><b class="seatmap-warn">这张任务的座位快照还是 {{ seatData.grid.rows }} 排 × {{ seatData.grid.cols }} 座，图上已按快照撑开</b></template></span>
        <span>应到 {{ seatList.length }}　已到 {{ seatStats.present + seatStats.late }}　迟到 {{ seatStats.late }}　请假 {{ seatStats.leave }}　缺勤 {{ seatStats.absent }}　未签到 {{ seatStats.pending }}</span>
        </div>
        <p v-if="mySeat" class="seatmap-mine"><b>我坐这里</b>座位 {{ seatLabel(mySeat) }}　{{ mySeat.student_no }} {{ mySeat.name }}　{{ mySeat.class_name }}　状态：{{ seatText(mySeat.status) }}</p>
        <p v-else-if="user.role === 'student'" class="seatmap-mine empty"><b>没有我的座位</b>这张图里没有排到你的座位，找任课老师确认一下。</p>
        <div class="seatmap-legend">
        <span v-for="name in seatClasses" :key="name"><i class="chip" :style="{ background: classColor(name) }"></i>{{ name }}</span>
        <span class="legend-gap"></span>
        <span><i class="dot present"></i>已到</span>
        <span><i class="dot late"></i>迟到</span>
        <span><i class="dot leave"></i>请假</span>
        <span><i class="dot absent"></i>缺勤</span>
        <span><i class="dot pending"></i>未签到</span>
        </div>
        <div class="seatmap-podium">讲 台 / 屏 幕</div>
        <div class="seatmap-grid" :style="{ gridTemplateColumns: seatColumns }">
        <template v-for="line in seatRows" :key="line.row">
        <span class="seat-row-label" :style="{ gridColumn: 1, gridRow: line.row }">{{ line.row }}</span>
        <button v-for="cell in line.cells" :key="cell.key" type="button"
          :class="['seat-cell', cell.seat ? cell.seat.status : 'empty', { mine: cell.seat && mySeat && cell.seat.student_id === mySeat.student_id }]"
          :style="{ gridColumn: seatSlot(cell.col) + 1, gridRow: line.row, borderTopColor: cell.seat ? classColor(cell.seat.class_name) : 'transparent' }"
          :disabled="!cell.seat"
          :title="cell.seat ? seatLabel(cell.seat) + '　' + cell.seat.student_no + ' ' + cell.seat.name + '　' + seatText(cell.seat.status) : '空座'"
          @click="cell.seat && (seatDetail = cell.seat)">
        <template v-if="cell.seat">
        <b>{{ cell.seat.seat_no }}</b>
        <span>{{ cell.seat.name }}</span>
        <em v-if="cell.seat.status === 'late'">迟</em>
        </template>
        </button>
        </template>
        </div>
        <p v-if="seatDetail" class="seatmap-detail">
        座位 {{ seatLabel(seatDetail) }}　{{ seatDetail.student_no }} {{ seatDetail.name }}　{{ seatDetail.class_name }}　状态：{{ seatText(seatDetail.status) }}　签到时间：{{ seatDetail.checked_at ? shortTime(seatDetail.checked_at) : '—' }}　方式：{{ sourceText(seatDetail.source) }}
        <button type="button" class="secondary" @click="seatDetail = null">关闭</button>
        </p>
        <p v-if="seatData.unseated" class="seatmap-detail">另有 {{ seatData.unseated }} 名应到学生没有排座，请先在上面的「教室设置」里一键排座。</p>

        <div v-if="user.role === 'teacher'" class="seat-rosters">
        <div class="roster-col">
        <h4>已到 <b>{{ seatRosters.here.length }}</b></h4>
        <ul>
        <li v-for="seat in seatRosters.here" :key="seat.student_id">
        <span class="roster-seat">{{ seatLabel(seat) }}</span>
        <span class="roster-name">{{ seat.name }}</span>
        <span class="roster-class" :style="{ color: classColor(seat.class_name) }">{{ seat.class_name }}</span>
        <em v-if="seat.status === 'late'" class="roster-late">迟到</em>
        <span class="roster-time">{{ seat.checked_at ? shortTime(seat.checked_at) : '—' }}</span>
        <span class="roster-source">{{ sourceText(seat.source) }}</span>
        </li>
        </ul>
        <p v-if="!seatRosters.here.length" class="roster-empty">暂无</p>
        </div>
        <div class="roster-col">
        <h4>未到 <b>{{ seatRosters.away.length }}</b></h4>
        <ul>
        <li v-for="seat in seatRosters.away" :key="seat.student_id">
        <span class="roster-seat">{{ seatLabel(seat) }}</span>
        <span class="roster-name">{{ seat.name }}</span>
        <span class="roster-class" :style="{ color: classColor(seat.class_name) }">{{ seat.class_name }}</span>
        <em class="roster-flag">{{ seatText(seat.status) }}</em>
        </li>
        </ul>
        <p v-if="!seatRosters.away.length" class="roster-empty">暂无</p>
        </div>
        <div class="roster-col">
        <h4>请假 <b>{{ seatRosters.leave.length }}</b></h4>
        <ul>
        <li v-for="seat in seatRosters.leave" :key="seat.student_id">
        <span class="roster-seat">{{ seatLabel(seat) }}</span>
        <span class="roster-name">{{ seat.name }}</span>
        <span class="roster-class" :style="{ color: classColor(seat.class_name) }">{{ seat.class_name }}</span>
        </li>
        </ul>
        <p v-if="!seatRosters.leave.length" class="roster-empty">暂无</p>
        </div>
        </div>
        </div>

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>发布考勤任务</summary>
        <form class="inline-form" @submit.prevent="createTask">
        <label>任务 <input v-model.trim="taskForm.title" required></label>
        <label>开始 <input v-model="taskForm.start_at" type="datetime-local" required></label>
        <label>迟到起点 <input v-model="taskForm.late_at" type="datetime-local" required></label>
        <label>结束 <input v-model="taskForm.end_at" type="datetime-local" required></label><button>创建</button></form>
        </details>

        <form v-if="user.role === 'student' && tasks.length" class="inline-form att-checkin" @submit.prevent="check.mode === 'code' && checkIn()">
        <label>任务 <select v-model="check.task_id" required><option value="">请选择</option><option v-for="item in tasks" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
        <span class="check-modes" role="group" aria-label="签到方式">
        <button type="button" :class="{ active: check.mode === 'code' }" @click="check.mode = 'code'">签到码</button>
        <button type="button" :class="{ active: check.mode === 'gesture' }" @click="check.mode = 'gesture'">手势图案</button>
        </span>
        <label v-if="check.mode === 'code'">签到码 <input v-model.trim="check.code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></label>
        <button v-if="check.mode === 'code'">签到</button></form>
        <div v-if="user.role === 'student' && tasks.length && check.mode === 'gesture'" class="gesture-checkin">
        <p class="pad-step">① 签到：画一遍你设置过的图案</p>
        <gesture-pad ref="checkPad" :disabled="!check.task_id" @done="checkInByGesture($event, $refs.checkPad)" />
        <p class="att-meta">{{ !check.task_id ? '先在上面选择要点到的任务。' : gesture.enrolled ? '按住并划过你自己设置的手势图案，松手即签到。' : '你还没有设置手势图案，先在下面的「② 设置 / 更换图案」里设一个。' }}</p>
        </div>
        <details v-if="user.role === 'student'" class="att-panel">
        <summary>② 设置 / 更换图案（{{ gesture.enrolled ? '已设置' : '未设置' }}）</summary>
        <p class="att-meta">{{ gesture.hint }}</p>
        <gesture-pad ref="enrollPad" @done="enrollGesture($event, $refs.enrollPad)" />
        <div v-if="gesture.enrolled" class="att-actions">
        <button type="button" class="secondary" @click="clearGesture">清除手势图案</button></div>
        </details>
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
        <button v-if="user.role === 'student' && item.status === 'rejected'" type="button" class="secondary" @click="beginResubmit(item.id)">修改重提</button>
        </span>
        <span v-if="resubmitTarget === item.id" class="resubmit-box">
        <input v-model.trim="resubmitReason" maxlength="500" placeholder="重新填写请假理由（必填）" aria-label="请假理由">
        <button type="button" @click="resubmit(item.id)">提交</button>
        <button type="button" class="secondary" @click="cancelResubmit">取消</button>
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
        <button type="button" class="secondary" @click="beginCorrect(item.id, item.status)">更正</button>
        <span v-if="correctTarget === item.id" class="resubmit-box">
        <select v-model="correctStatus" aria-label="更正后的状态">
        <option value="present">出勤</option><option value="late">迟到</option>
        <option value="leave">请假</option><option value="absent">缺勤</option></select>
        <input v-model.trim="correctReason" maxlength="500" placeholder="更正理由（必填，会通知学生）" aria-label="更正理由">
        <button type="button" @click="correct(item)">提交更正</button>
        <button type="button" class="secondary" @click="cancelCorrect">取消</button>
        </span></li></ul>
        </details>
        </section>
        <AnalyticsView v-if="user.role !== 'admin'" :key="'analytics:' + user.id + ':' + user.role" :user="user" />
        <WarningView :key="'warning:' + user.id" :user="user" />
        <WiringStatsView v-if="user.role !== 'admin'" :key="'wiring-stats:' + user.id + ':' + user.role" :user="user" />
        </template>
      </template>
      </template>
    </main>`,
}).mount('#app')
