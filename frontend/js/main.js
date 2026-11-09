import { computed, createApp, nextTick, onMounted, reactive, ref } from 'vue'
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
import { CircuitLabView } from './circuit-lab-view.js'
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
import '../styles/circuit-lab.css'
import '../styles/graph.css'
import '../styles/recognition.css'
import '../styles/warnings.css'
import '../styles/preparations.css'
import '../styles/wiring.css'
import '../styles/wiring-stats.css'

createApp({
  components: { KnowledgeView, QuestionBankView, PaperView, AttemptView, PracticeView, AnalyticsView, ResourceView, ExperimentView, GradingView, QAView, RecommendationView, DemoView, AluView, CircuitLabView, KnowledgeGraphView, RecognitionView, WarningView, PreparationView, WiringView, WiringStatsView, GesturePad },
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
    // 课程封面：按 id 取 B 色板里的纯色，同一门课颜色固定，避免刷新变来变去。
    // 纯展示常量，不参与任何逻辑判断；长度保持 8，取模结果不变。
    const COVERS = [
      '#3F4EA8', '#2B3675', '#0E8A8A', '#5A68BF',
      '#3F4EA8', '#2B3675', '#0E8A8A', '#5A68BF',
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
    // 应到人数优先用任务上冻结的 participants；拿不到才退回记录条数，
    // 否则进行中的任务会把「只来了 1 个人」算成 100%。
    const totalOf = id => tasks.value.find(item => item.id === id)?.participants ?? taskStats.value.get(id)?.total ?? 0
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
    // 后台业务数据就绪状态：空库登录后给出明确引导，避免「登录成功却一片空白」。
    const readiness = ref(null)
    const message = ref('')
    const courses = ref([])
    const people = ref([])
    const courseId = ref(null)
    const members = ref([])
    const membersTotal = ref(0)
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
    // 手势签到：图案由老师开课时定一次（画两遍确认），学生端只负责照着画。
    const taskPattern = reactive({ pattern: null, first: null, hint: '可选：画一个图案作为这次课的手势口令，全班照着它签到。' })
    // 学生点座位后弹出的签到浮层：签到码 / 手势二选一，用哪个由老师开课时决定
    const checkInSheet = reactive({ open: false, task: null, mode: 'code', code: '', hint: '', error: '' })
    // 签到结果：toast 三秒后自动消失，notice 一直留在座位图上方
    const checkInToast = ref('')
    const checkInNotice = ref(null)
    let toastTimer = 0
    const analysisFilter = reactive({ from: '', to: '', paper_ids: '' })
    // 课堂点到座位图：一整张平面网格，四个班混排在同一间教室里
    const seatData = ref(null)
    const seatDetail = ref(null)
    // 教室规模：教师可以按自己的教室改行列，预设只是快捷入口
    const room = ref(null)
    const roomForm = reactive({ name: '', template: 'custom', rows: 10, cols: 12, aisle_every: 0 })
    let courseEpoch = 0
    // 切课时先清空再拉数据，中间那一瞬间任务数是 0，概览里会闪「0 → 2」。
    // 加载期间改成显示省略号，等数据到了再出数字。
    const courseBusy = ref(false)

    function clearCourse() {
      courseEpoch += 1
      courseId.value = null
      members.value = []
      membersTotal.value = 0
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
      taskPattern.first = null
      checkInSheet.open = false
      checkInSheet.task = null
      checkInSheet.error = ''
      checkInNotice.value = null
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
    // 后端重启/会话轮换后，页面手里的 CSRF 值会失效：读接口照常 200，
    // 所有写操作却 403 CSRF_FAILED，界面上看着就是「点了没反应」。
    // 碰到这种情况重新取一次 token 再试一遍，用户不用重新登录。
    async function refreshCsrf() {
      const data = await readApi('/api/v1/auth/session')
      if (data?.csrf_token) csrf.value = data.csrf_token
      return data
    }
    async function write(path, method, payload, headers) {
      try {
        return await apiRequest(path, method, payload, csrf.value, headers)
      } catch (error) {
        if (error.code !== 'CSRF_FAILED') throw error
        await refreshCsrf()
        return apiRequest(path, method, payload, csrf.value, headers)
      }
    }
    async function loadReadiness() {
      // 端点需登录且无副作用；未登录或请求失败时静默降级，只影响引导条显示。
      try { readiness.value = await readApi('/api/v1/circuit-lab/bootstrap') }
      catch { readiness.value = null }
    }
    // 成员上限 100 一页，超过就继续拉，否则页面人数和列表会在大班被截断。
    async function readAll(path) {
      const rows = []
      let page = 1
      for (;;) {
        const response = await fetch(`${path}${path.includes('?') ? '&' : '?'}page=${page}&page_size=100`)
        const body = await response.json()
        if (!response.ok) throw new Error(body.error?.message ?? `HTTP ${response.status}`)
        const data = body.data ?? []
        rows.push(...data)
        const total = body.total ?? rows.length
        if (!data.length || rows.length >= total) return { rows, total }
        page++
      }
    }
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
      const [taskRows, leaveRows, recordRows, warningRows, memberPage, roomRow] = await Promise.all([
        readApi(`${base}/attendance-tasks?page_size=100`),
        readApi(`${base}/leave-requests?page_size=100`),
        readApi(`${base}/attendance-records?page_size=100`),
        teacher ? readApi(`${base}/warnings?page_size=100`) : Promise.resolve([]),
        teacher ? readAll(`${base}/members`) : Promise.resolve({ rows: [], total: 0 }),
        teacher ? readApi(`${base}/classroom`) : Promise.resolve(null),
      ])
      if (courseEpoch !== epoch || courseId.value !== id || user.value !== currentUser) return
      tasks.value = taskRows
      leaves.value = leaveRows
      records.value = recordRows
      warnings.value = warningRows
      members.value = memberPage.rows
      membersTotal.value = memberPage.total
      if (roomRow) syncRoom(roomRow)
    }
    async function session() {
      try {
        const data = await readApi('/api/v1/auth/session')
        clearCourse()
        user.value = data.user
        account.name = data.user.name
        csrf.value = data.csrf_token
        await refreshCourses()
        await loadReadiness()
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
      account.name = data.user.name
      csrf.value = data.csrf_token
      auth.password = ''
      await refreshCourses()
      await loadReadiness()
      // 登录后同样自动选中第一门课，否则直接切到「考勤与学情」会是一片空白。
      if (user.value.role !== 'admin' && !courseId.value && courses.value.length) {
        await selectCourse(courses.value[0].id)
      }
      // 别人在等他答复的换位申请，登录就弹出来
      await pollIncoming()
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
    // 座位图从任务卡里下拉展开：展开/收起都走 CSS grid-rows 过渡，先挂载再翻 open 类
    const seatOpen = ref(null)
    const seatDrop = ref(false)
    let seatTimer = 0
    async function toggleSeats(taskId) {
      window.clearTimeout(seatTimer)
      if (seatOpen.value === taskId) {
        seatDrop.value = false
        seatTimer = window.setTimeout(() => {
          if (seatOpen.value === taskId && !seatDrop.value) seatOpen.value = null
        }, 260)
        return
      }
      seatOpen.value = taskId
      seatDrop.value = false
      await loadSeats(taskId)
      await nextTick()
      window.requestAnimationFrame(() => { seatDrop.value = true })
    }
    const seatList = computed(() => seatData.value?.seats ?? [])
    // 我在图上的那一个座位；教师看的时候为 null
    const mySeat = computed(() => {
      if (user.value?.role !== 'student') return null
      return seatList.value.find(seat => seat.student_id === user.value.id) ?? null
    })
    // 这次课我签到了没有：优先看考勤记录，其次看座位格子上的状态。
    // 已签到就不该再弹签到面板——换座位、点格子都只当普通操作。
    const CHECKED = ['present', 'late', 'leave']
    const myRecord = computed(() => {
      const taskId = seatData.value?.task?.id
      return taskId ? records.value.find(item => item.task_id === taskId) ?? null : null
    })
    // 座位图是刚拉回来的，状态比列表里的 records 新；只要图正开着这张任务，就以图上的状态为准。
    // 否则「后端把记录清了，页面还留着旧 records」会让按钮消失、点座位也不弹签到。
    const isCheckedIn = taskId => {
      if (taskId && seatData.value?.task?.id === taskId && mySeat.value) return CHECKED.includes(mySeat.value.status)
      return CHECKED.includes(records.value.find(item => item.task_id === taskId)?.status)
    }
    const checkedIn = computed(() => isCheckedIn(seatData.value?.task?.id) || CHECKED.includes(myRecord.value?.status))
    const seatStats = computed(() => {
      const counts = { present: 0, late: 0, leave: 0, absent: 0, pending: 0 }
      seatList.value.forEach(seat => { counts[seat.status] = (counts[seat.status] ?? 0) + 1 })
      return counts
    })
    // 换位：学生点空位直接坐，点别人就发申请等答复；服务端 15 分钟不回就作废
    const seatSwap = reactive({
      outgoing: [], incoming: [], ttl: 15, modal: null, now: Date.now(), busy: false,
    })
    const SWAP_TEXT = {
      pending: '等待答复', accepted: '已换座', declined: '对方拒绝', expired: '已过期', cancelled: '已撤回',
    }
    const swapText = status => SWAP_TEXT[status] ?? status
    const swapLeft = row => {
      if (!row || row.status !== 'pending') return '—'
      const left = Math.max(0, Math.round((Date.parse(row.expires_at) - seatSwap.now) / 1000))
      return `${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}`
    }
    const mySwap = computed(() => seatSwap.outgoing.find(row => row.status === 'pending') ?? null)
    const seatOccupiedBy = cell => (cell?.seat ? cell.seat : null)
    const seatCellTitle = cell => {
      if (cell.seat) {
        const base = `${seatLabel(cell.seat)}　${cell.seat.student_no} ${cell.seat.name}　${seatText(cell.seat.status)}`
        if (user.value?.role !== 'student') return base
        if (cell.seat.student_id === user.value.id) return `${base}　（我的座位）`
        return `${base}　（点一下申请换位）`
      }
      return user.value?.role === 'student' ? `${cell.row} 排 ${cell.col} 座 · 空位，点一下坐这里` : '空座'
    }

    async function loadSwaps() {
      if (!courseId.value || user.value?.role !== 'student') return
      const data = await readApi(`/api/v1/courses/${courseId.value}/seat-swaps`)
      seatSwap.outgoing = data.outgoing
      seatSwap.incoming = data.incoming
      seatSwap.ttl = data.ttl_minutes
    }
    // 登录后和每 20 秒拉一次：对方答复 / 过期都要在界面上及时反映出来
    async function pollIncoming() {
      if (user.value?.role !== 'student') { seatSwap.modal = null; return }
      try {
        const data = await readApi('/api/v1/seat-swaps/incoming')
        seatSwap.modal = data.items[0] ?? null
        seatSwap.ttl = data.ttl_minutes
        seatSwap.now = Date.now()
        if (seatSwap.modal && courseId.value) await loadSwaps()
      } catch { /* 轮询失败不打断页面 */ }
    }
    async function sitHere(cell) {
      if (seatSwap.busy || user.value?.role !== 'student') return
      const seat = seatOccupiedBy(cell)
      if (seat && seat.student_id === user.value.id) {
        // 点自己的座位：没签到就直接弹签到；签过了只看座位详情，不再弹
        seatDetail.value = seat
        if (!checkedIn.value) openCheckIn(seatData.value?.task)
        return
      }
      if (seat) {
        if (mySwap.value) { message.value = '你已经有一个换位申请在等答复了，先撤回再申请。'; return }
        const yes = window.confirm(`申请和 ${seat.name}（${seatLabel(seat)}）换座位？对方有 ${seatSwap.ttl} 分钟答复时间。`)
        if (!yes) return
        seatSwap.busy = true
        await act(async () => {
          await write('/api/v1/courses/' + courseId.value + '/seat-swaps', 'POST',
            { target_student_id: seat.student_id })
          await loadSwaps()
        }, `已向 ${seat.name} 发出换位申请，等对方答复。`)
        seatSwap.busy = false
        return
      }
      if (!courseId.value) return
      // 不再弹「坐这里？」二次确认：点空位就是坐下，坐下立刻弹签到面板，
      // 学生从头到尾只点两下（座位 → 签到），中间不夹对话框。
      seatSwap.busy = true
      let seated = false
      await act(async () => {
        await write('/api/v1/courses/' + courseId.value + '/me/seat', 'PUT',
          { group_no: cell.row, seat_no: cell.col })
        if (seatData.value) await loadSeats(seatData.value.task.id)
        await loadSwaps()
        seated = true
      }, `已坐到 ${cell.row} 排 ${cell.col} 座。`)
      seatSwap.busy = false
      // 已经签过到了，换座位只是换位置，不再弹签到
      if (seated && !checkedIn.value) openCheckIn(seatData.value?.task)
    }
    async function answerSwap(row, accept) {
      if (!row || seatSwap.busy) return
      seatSwap.busy = true
      await act(async () => {
        await write(`/api/v1/courses/${row.course_id}/seat-swaps/${row.id}/${accept ? 'accept' : 'decline'}`,
          'POST')
        seatSwap.modal = null
        if (seatData.value) await loadSeats(seatData.value.task.id)
        await loadSwaps()
      }, accept ? '已换座，双方座位对调完成。' : '已拒绝这次换位。')
      seatSwap.busy = false
    }
    async function cancelSwap(row) {
      if (!row || seatSwap.busy) return
      seatSwap.busy = true
      await act(async () => {
        await write(`/api/v1/courses/${row.course_id}/seat-swaps/${row.id}`, 'DELETE')
        await loadSwaps()
      }, '已撤回换位申请。')
      seatSwap.busy = false
    }

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
          cells.push({ key: `${row}-${col}`, row, col, slot: seatSlot(col),
            seat: seatIndex.value.get(`${row}-${col}`) ?? null })
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
        readiness.value = null
        courses.value = []
        people.value = []
        notifications.value = []
      }, '已退出。')
    }
    async function selectCourse(id) {
      clearCourse()
      courseId.value = Number(id)
      courseBusy.value = true
      try {
        await act(refreshCourse, '课程已加载。')
      } finally {
        courseBusy.value = false
      }
      // 换位申请是按课程查的，切课后重新拉一次
      if (user.value?.role === 'student') await act(loadSwaps, '')
    }
    // 概览里的统计块：点一下就跳到对应分区，省得去下面找按钮
    function jump(name, anchor) {
      tab.value = name
      if (!anchor) return
      // 页签是 v-if，先等一帧让目标节点出现再滚
      window.requestAnimationFrame(() => window.setTimeout(() => {
        document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 0))
    }
    // 点课程卡片 = 进入这门课的考勤：要切课先切，然后直接落到「考勤与学情」。
    // 只有一门课时原来那句「点击卡片切换」点了毫无反应，现在卡片一律是入口。
    async function enterCourse(id) {
      if (Number(id) !== courseId.value) await selectCourse(id)
      tab.value = 'stats'
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
        // 手势口令是老师开课时定的一次性课堂口令，跟着任务一起发布；
        // 不画就是这次课不开手势签到，学生只填签到码。
        if (taskPattern.pattern) payload.pattern = taskPattern.pattern
        const data = await write(`/api/v1/courses/${id}/attendance-tasks`, 'POST', payload)
        if (courseEpoch === epoch && courseId.value === id) {
          secretCode.value = data.code
          if (taskPattern.pattern) {
            taskPattern.pattern = null
            taskPattern.first = null
            taskPattern.hint = '可选：画一个图案作为这次课的手势口令，全班照着它签到。'
          }
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
    // 老师开课时定手势口令：连画两次确认，创建任务时随 payload 一起提交
    function captureTaskPattern(pattern, pad) {
      if (pattern.length < 4) {
        taskPattern.first = null
        taskPattern.hint = '至少连接 4 个点，请重画。'
        pad?.reset()
        return
      }
      if (!taskPattern.first) {
        taskPattern.first = pattern
        taskPattern.hint = '请再画一次同样的图案确认。'
        pad?.reset()
        return
      }
      if (taskPattern.first.join('-') !== pattern.join('-')) {
        taskPattern.first = null
        taskPattern.hint = '两次不一致，请重新开始。'
        pad?.reset()
        return
      }
      taskPattern.pattern = pattern
      taskPattern.first = null
      taskPattern.hint = `已记下这次课的手势口令（${pattern.length} 个点），点「创建」时一起发布。`
      pad?.reset()
    }
    // Z 字形：左上 → 右上 → 对角 → 左下 → 右下，7 个点
    function useZPattern() {
      taskPattern.pattern = [0, 1, 2, 4, 6, 7, 8]
      taskPattern.first = null
      taskPattern.hint = '已用 Z 字形（0-1-2-4-6-7-8）作为这次课的手势口令。'
    }
    function clearTaskPattern() {
      taskPattern.pattern = null
      taskPattern.first = null
      taskPattern.hint = '已清除。这次课只发签到码。'
    }
    // 点座位就把签到弹出来：签到方式由老师开课时决定，学生只需要照做
    function openCheckIn(task) {
      if (!task) return
      checkInSheet.task = task
      checkInSheet.mode = 'code'
      checkInSheet.code = ''
      checkInSheet.error = ''
      checkInSheet.open = true
      // 请假是同一节课的事，跟着这张任务走
      check.task_id = task.id
      check.reason = ''
    }
    // 后端错误码翻成学生看得懂的话；认不出来才退回后端原文
    const CHECK_IN_ERRORS = {
      INVALID_ATTENDANCE_CODE: '签到码不对，再看一下老师给的 6 位数字',
      INVALID_GESTURE: '图案不对，照着老师画的那条再划一遍',
      GESTURE_NOT_ENABLED: '这次课没开手势签到，请用签到码',
      STATE_CONFLICT: '这次签到已经结束了',
      RATE_LIMITED: '试的次数太多了，等一分钟再试',
    }
    const checkInErrorText = error => CHECK_IN_ERRORS[error.code]
      ?? (error.status === 429 ? CHECK_IN_ERRORS.RATE_LIMITED : error.message || '签到失败，请重试')
    // 成功之后：顶部消息 + 三秒 toast + 座位图上方的常驻绿条
    function flash(text) {
      checkInToast.value = text
      window.clearTimeout(toastTimer)
      toastTimer = window.setTimeout(() => { checkInToast.value = '' }, 3000)
    }
    function showCheckInDone(task) {
      const seat = mySeat.value
      checkInNotice.value = {
        taskId: task?.id ?? null,
        title: task?.title ?? '',
        seat: seat ? seatLabel(seat) : '',
        time: seat?.checked_at ? shortTime(seat.checked_at) : shortTime(new Date().toISOString()),
        status: seat ? seatText(seat.status) : '已到',
      }
      flash(seat ? `签到成功 · ${seatLabel(seat)}` : '签到成功')
    }
    async function checkInFromSheet() {
      if (!checkInSheet.task) return
      const task = checkInSheet.task
      checkInSheet.error = ''
      try {
        await write(`/api/v1/attendance-tasks/${task.id}/check-ins`, 'POST', { code: checkInSheet.code })
      } catch (error) {
        // 失败不关弹层：把原因写在弹层里，改一下就能再提交
        checkInSheet.error = checkInErrorText(error)
        return
      }
      checkInSheet.code = ''
      checkInSheet.open = false
      await refreshCourse()
      // 座位格子的状态也要跟着刷，否则签到成功还写着「未签到」；
      // 顺手把座位数据拉一次，任务行直接签到时 toast 也能带上座位号
      await loadSeats(seatData.value?.task?.id ?? task.id)
      showCheckInDone(task)
    }
    async function checkInByGesture(pattern, pad) {
      const taskId = checkInSheet.task?.id || check.task_id
      if (!taskId) {
        message.value = '先点一个座位再签到。'
        pad?.reset()
        return
      }
      const task = checkInSheet.task
      checkInSheet.error = ''
      try {
        await write(`/api/v1/attendance-tasks/${taskId}/check-ins`, 'POST', { pattern })
      } catch (error) {
        checkInSheet.error = checkInErrorText(error)
        pad?.reset()
        return
      }
      await refreshCourse()
      await loadSeats(seatData.value?.task?.id ?? taskId)
      checkInSheet.open = false
      // 成功后不擦图案：让学生看到自己刚画的那一笔，下次按下时会自动清空
      showCheckInDone(task)
    }
    async function leave() {
      await act(async () => {
        await write(`/api/v1/attendance-tasks/${check.task_id}/leave-requests`, 'POST', { reason: check.reason })
        check.reason = ''
        if (checkInSheet.open) checkInSheet.open = false
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
    onMounted(async () => {
      await session()
      // 换位提醒：登录后先拉一次（已登录状态刷新页面也要弹），之后每 20 秒轮询；
      // 单独的 1 秒 tick 只负责把倒计时数字走动起来，不发请求。
      await pollIncoming()
      window.setInterval(pollIncoming, 20000)
      window.setInterval(() => { seatSwap.now = Date.now() }, 1000)
      // 切回这个页面时补一次刷新：后台数据（老师结算、管理员重置演示数据）变了，
      // 页面还留着旧 records，就会变成「我明明没签到，按钮却不见了」。
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible' || !user.value || !courseId.value) return
        refreshCourse().then(() => (seatData.value && seatOpen.value ? loadSeats(seatData.value.task.id) : null))
          .catch(() => {})
      })
    })
    return { user, practiceEntry, openRecommendedPractice, message, readiness, courses, people, courseId, members, membersTotal, tasks, leaves, records, warnings, notifications, analysis,
      recognition, draft, secretCode, auth, authMode, courseForm, memberNo, taskForm, check, analysisFilter, login, register,
      demoStudentNo, fillTeacher, fillStudent,
      seatData, seatDetail, loadSeats, seatList, seatStats, seatColumns, seatText, seatRows, seatClasses, mySeat,
      seatOpen, seatDrop, toggleSeats,
      courseBusy, jump, enterCourse,
      seatSwap, mySwap, swapLeft, swapText, seatCellTitle, sitHere, answerSwap, cancelSwap, loadSwaps, pollIncoming,
      classColor, seatRosters, sourceText, seatLabel, seatSlot, room, roomForm, applyPreset, saveRoom, autoSeat, unseat,
      logout, selectCourse, createCourse, promote, deactivate, transfer, addMember, removeMember, createTask, rotate, close, checkIn,
      leave, review, revokeLeave, resubmit, correct, markRead, analyze, warn, handle, upload, confirm, tab, tabs, attendedOf, totalOf, rateOf, myStatusOf, shortTime, coverOf, account, accountSaving, saveName, savePassword, resubmitTarget, resubmitReason, beginResubmit, cancelResubmit, correctTarget, correctStatus, correctReason, beginCorrect, cancelCorrect,
      taskPattern, captureTaskPattern, useZPattern, clearTaskPattern,
      checkInSheet, openCheckIn, checkInFromSheet, checkInByGesture,
      checkedIn, isCheckedIn, checkInNotice, checkInToast }
  },
  template: `
    <main :class="['page', user ? '' : 'page-auth']">
      <header v-if="user" class="hero compact"><p class="eyebrow">{{ user.student_no }} · 计算机组成原理</p>
        <h1>中央处理器课程学习系统</h1><p role="status" aria-live="polite">{{ message }}</p>
        <button type="button" @click="logout">退出</button></header>
      <section v-if="!user" class="auth">
        <aside class="auth-side">
        <span class="auth-logo" aria-hidden="true">计</span>
        <p class="auth-eyebrow">2024 级计算机科学与技术</p>
        <h1>中央处理器<br>课程学习系统</h1>
        <p class="auth-lead">课堂点到、座位图、练习与评测，一个入口。</p>
        <ul class="auth-points">
        <li><b>四班同堂</b>四个班共用一张座位图，按班分段排座，登录就能看到自己坐哪。</li>
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
        <label v-if="authMode === 'login'" class="auth-field"><span>密码</span>
          <input id="password" v-model="auth.password" type="password" placeholder="与学号相同"
            autocomplete="current-password" required></label>
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
        <p class="course-count">共 {{ courses.length }} 门课程，点卡片直接进考勤</p>
        <div class="course-grid">
        <button v-for="course in courses" :key="course.id" type="button"
        :class="['course-card', { active: courseId === course.id }]"
        :style="'--cover:' + coverOf(course.id)"
        @click="user.role === 'admin' ? selectCourse(course.id) : enterCourse(course.id)">
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
        <div v-if="readiness && !readiness.data_ready" class="bootstrap-hint" role="status">
          <strong>后台业务数据未初始化（登录本身已成功）</strong>
          <p>当前缺少：{{ readiness.missing.join(' / ') }}。资源、实验、评测与统计模块需要这些数据才有内容；
            「实验与演示 → 电路实验台」的电路模拟与验算不依赖业务数据，仍可正常使用。</p>
          <p class="bootstrap-cmd">初始化示例：<code>python scripts/seed_teacher_course.py</code>、
            <code>python scripts/seed_demo_roster.py</code>，随后由教师创建实验与测试集。</p>
        </div>
        <p v-if="!courses.length">课程列表为空：请由管理员或教师创建课程，或运行上面的初始化脚本后刷新。</p>
        <template v-if="courseId">
        <div class="course-summary">
        <button type="button" class="sum-tile" title="查看考勤与学情" @click="jump('stats')">
        <span>{{ user.role === 'teacher' ? '课程成员' : '进行中任务' }}</span>
        <strong>{{ courseBusy ? '…' : (user.role === 'teacher' ? membersTotal : tasks.filter(item => item.status === 'open').length) }}</strong>
        </button>
        <button type="button" class="sum-tile" title="查看考勤与学情" @click="jump('stats')">
        <span>考勤任务</span><strong>{{ courseBusy ? '…' : tasks.length }}</strong>
        </button>
        <button type="button" class="sum-tile" title="查看考勤与学情" @click="jump('stats')">
        <span>待批请假</span><strong>{{ courseBusy ? '…' : leaves.filter(item => item.status === 'pending').length }}</strong>
        </button>
        <button type="button" class="sum-tile" title="跳到通知列表" @click="jump('course', 'notices')">
        <span>未读通知</span><strong>{{ notifications.filter(item => !item.read_at).length }}</strong>
        </button>
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
        <section id="notices" class="card"><h2>通知</h2><ul class="rows"><li v-for="item in notifications" :key="item.id">{{ item.title }} · {{ item.read_at ? '已读' : '未读' }}
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
        <CircuitLabView :key="'circuit-lab:' + user.id" :user="user" />
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
        <span v-if="item.has_gesture" class="att-badge gesture">手势签到</span>
        <span class="att-time">截止 {{ shortTime(item.end_at) }}</span>
        </div>
        <p v-if="checkInNotice && checkInNotice.taskId === item.id" class="checkin-notice" role="status">
        <b>签到成功</b>
        <span>{{ checkInNotice.title }}</span>
        <span v-if="checkInNotice.seat">{{ checkInNotice.seat }}</span>
        <span>{{ checkInNotice.time }}</span>
        <span class="checkin-notice-status">{{ checkInNotice.status }}</span>
        <button type="button" class="secondary" @click="checkInNotice = null">知道了</button></p>
        <template v-if="user.role === 'teacher'">
        <div class="att-bar"><i :class="rateOf(item.id) >= 80 ? 'good' : rateOf(item.id) > 0 ? 'mid' : 'low'" :style="'width:' + rateOf(item.id) + '%'"></i></div>
        <p class="att-meta">到勤 {{ attendedOf(item.id) }} / {{ totalOf(item.id) }} 人次<b>{{ rateOf(item.id) }}%</b></p>
        </template>
        <p v-else class="att-meta">我的状态：{{ seatText(myStatusOf(item.id)) }}</p>
        <div class="att-actions">
        <button type="button" class="seat-trigger" :class="{ open: seatOpen === item.id }"
          :aria-expanded="seatOpen === item.id" :aria-controls="'seat-' + item.id" @click="toggleSeats(item.id)">
        <svg class="seat-ico" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="5" height="5" rx="1.3"></rect><rect x="9.5" y="4" width="5" height="5" rx="1.3"></rect><rect x="16" y="4" width="5" height="5" rx="1.3"></rect>
        <rect x="3" y="10.5" width="5" height="5" rx="1.3"></rect><rect x="9.5" y="10.5" width="5" height="5" rx="1.3"></rect><rect x="16" y="10.5" width="5" height="5" rx="1.3"></rect>
        <rect x="3" y="17" width="5" height="4" rx="1.3"></rect><rect x="9.5" y="17" width="5" height="4" rx="1.3"></rect><rect x="16" y="17" width="5" height="4" rx="1.3"></rect>
        </svg>
        <span>{{ seatOpen === item.id ? '收起座位图' : (user.role === 'teacher' ? '教室座位图' : '看看我坐哪') }}</span>
        <svg class="seat-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>
        </button>
        <button v-if="user.role === 'student' && item.status === 'open' && !isCheckedIn(item.id)"
          type="button" class="att-checkin-cta" @click="openCheckIn(item)">签到</button>
        <template v-if="user.role === 'teacher'">
        <button v-if="item.status === 'open'" type="button" class="secondary" @click="rotate(item.id)">轮换码</button>
        <button v-if="item.status === 'open'" type="button" @click="close(item.id)">结算</button>
        </template>
        </div>
        <div v-if="seatOpen === item.id" :id="'seat-' + item.id" class="att-seat-drop" :class="{ open: seatDrop }">
        <div class="att-seat-inner">
        <div v-if="seatData && seatData.task.id === item.id" class="seatmap">
        <div class="seatmap-head">
        <strong>教室座位图</strong>
        <span class="seatmap-room">{{ seatData.classroom.name }}　{{ seatData.classroom.rows }} 排 × {{ seatData.classroom.cols }} 座<template
          v-if="seatData.grid.rows > seatData.classroom.rows || seatData.grid.cols > seatData.classroom.cols"><b class="seatmap-warn">这张任务的座位快照还是 {{ seatData.grid.rows }} 排 × {{ seatData.grid.cols }} 座，图上已按快照撑开</b></template></span>
        <span>已选座 {{ seatList.length }}　未选座 {{ seatData.unseated || 0 }}　已到 {{ seatStats.present + seatStats.late }}　迟到 {{ seatStats.late }}　请假 {{ seatStats.leave }}　缺勤 {{ seatStats.absent }}　未签到 {{ seatStats.pending }}</span>
        </div>
        <p v-if="mySeat" class="seatmap-mine"><b>我坐这里</b>座位 {{ seatLabel(mySeat) }}　{{ mySeat.student_no }} {{ mySeat.name }}　{{ mySeat.class_name }}　状态：{{ seatText(mySeat.status) }}
        <button v-if="!checkedIn" type="button" class="secondary" @click="openCheckIn(seatData.task)">签到</button></p>
        <p v-else-if="user.role === 'student'" class="seatmap-mine empty"><b>我还没选座</b>教室现在是空的，点下面任意空位就能坐这里。</p>
        <p v-if="mySwap" class="swap-strip"><b>换位申请中</b>申请和 {{ mySwap.target_name }} 换座，等对方答复，剩余 <i>{{ swapLeft(mySwap) }}</i>
        <button type="button" class="secondary" @click="cancelSwap(mySwap)">撤回</button></p>
        <p v-if="user.role === 'student' && seatData" class="att-meta">点空位就坐下，坐下会顺手弹出签到面板（填签到码或画手势看老师这次课开的是哪种）；签到成功后不再弹面板，之后换座位直接点空位就行；点同学的格子是发换位申请，对方 {{ seatSwap.ttl }} 分钟内答复。</p>
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
          :class="['seat-cell', cell.seat ? cell.seat.status : 'empty', { mine: cell.seat && mySeat && cell.seat.student_id === mySeat.student_id, pickable: user.role === 'student' }]"
          :style="{ gridColumn: seatSlot(cell.col) + 1, gridRow: line.row, borderTopColor: cell.seat ? classColor(cell.seat.class_name) : 'transparent' }"
          :disabled="user.role === 'teacher' && !cell.seat"
          :title="seatCellTitle(cell)"
          @click="user.role === 'student' ? sitHere(cell) : (cell.seat && (seatDetail = cell.seat))">
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
        <p v-if="seatData.unseated && user.role === 'teacher'" class="seatmap-detail">另有 {{ seatData.unseated }} 名应到学生没有排座，可以先在上面的「教室设置」里一键排座，也可以让学生自己点空位选座。</p>
        <p v-else-if="seatData.unseated && user.role === 'student'" class="seatmap-detail">还有 {{ seatData.unseated }} 位同学没有选座。</p>

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
        <p v-else-if="seatOpen === item.id" class="seatmap-fallback">座位图没加载出来。点上面的「签到」一样能签到，也可以刷新页面再试。</p>
        </div>
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

        <details v-if="user.role === 'teacher'" class="att-panel">
        <summary>发布考勤任务</summary>
        <form class="inline-form" @submit.prevent="createTask">
        <label>任务 <input v-model.trim="taskForm.title" required></label>
        <label>开始 <input v-model="taskForm.start_at" type="datetime-local" required></label>
        <label>迟到起点 <input v-model="taskForm.late_at" type="datetime-local" required></label>
        <label>结束 <input v-model="taskForm.end_at" type="datetime-local" required></label><button>创建</button></form>
        <div class="task-pattern">
        <p class="task-pattern-head">手势签到口令
        <b :class="taskPattern.pattern ? 'set' : 'unset'">{{ taskPattern.pattern ? '已设置，随任务一起发布' : '未设置，这次课只用签到码' }}</b></p>
        <p class="att-meta">{{ taskPattern.hint }}</p>
        <gesture-pad ref="taskPad" label="老师设置本次课的手势口令" :preview="taskPattern.pattern" @done="captureTaskPattern($event, $refs.taskPad)" />
        <div class="att-actions">
        <button type="button" class="secondary" @click="useZPattern">用 Z 字形（测试数据）</button>
        <button v-if="taskPattern.pattern" type="button" class="secondary" @click="clearTaskPattern">清除口令</button>
        </div>
        </div>
        </details>

        <p v-if="user.role === 'student' && tasks.length" class="att-meta">签到：点任务的「看看我坐哪」打开座位图，点自己的座位（或先坐到一个空位）就会弹出面板，按老师这次课开的方式填签到码或画手势。</p>

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
        <summary>课程成员（{{ membersTotal }}）与加入</summary>
        <form class="inline-form" @submit.prevent="addMember">
        <label>学生完整学号 <input v-model.trim="memberNo" required></label><button>加入课程</button></form>
        <ul class="rows"><li v-for="member in members" :key="member.user_id">
        {{ member.name }} · {{ member.student_no }}<template v-if="member.class_name"> · {{ member.class_name }}</template> · {{ member.member_role }} · {{ member.active ? '在课' : '已移出' }}
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
        <WarningView v-if="user.role === 'teacher'" :key="'warning:' + user.id" :user="user" />
        <WiringStatsView v-if="user.role === 'teacher'" :key="'wiring-stats:' + user.id" :user="user" />
        </template>
      </template>
      </template>

      <div v-if="seatSwap.modal" class="swap-modal" role="dialog" aria-modal="true" aria-labelledby="swap-title">
        <div class="swap-dialog">
        <p class="swap-eyebrow">换位申请 · 剩余 <i>{{ swapLeft(seatSwap.modal) }}</i></p>
        <h3 id="swap-title">{{ seatSwap.modal.requester_name }} 想和你换座位</h3>
        <p class="swap-body">TA 现在坐 <b>{{ seatSwap.modal.from_group }} 排 {{ seatSwap.modal.from_seat }} 座</b>，
          想换到你现在的位置 <b>{{ seatSwap.modal.to_group }} 排 {{ seatSwap.modal.to_seat }} 座</b>。
          {{ seatSwap.modal.course_title }}</p>
        <p class="swap-tip">{{ seatSwap.ttl }} 分钟内不答复就自动失效，双方座位都不动。</p>
        <div class="swap-actions">
        <button type="button" :disabled="seatSwap.busy" @click="answerSwap(seatSwap.modal, true)">同意换位</button>
        <button type="button" class="secondary" :disabled="seatSwap.busy" @click="answerSwap(seatSwap.modal, false)">拒绝</button>
        </div>
        </div>
      </div>
      <div v-if="checkInSheet.open && checkInSheet.task" class="checkin-modal" role="dialog" aria-modal="true"
        aria-labelledby="checkin-title" @click.self="checkInSheet.open = false">
        <div class="checkin-dialog">
        <p class="checkin-eyebrow">{{ checkInSheet.task.title }}</p>
        <h3 id="checkin-title">{{ checkInSheet.task.has_gesture ? '签到 · 签到码或手势' : '签到' }}</h3>
        <p class="checkin-when">{{ shortTime(checkInSheet.task.start_at) }} 开始
        <template v-if="checkInSheet.task.status === 'open'">　进行中</template>
        <template v-else>　已结束</template>
        <template v-if="mySeat">　你坐 {{ seatLabel(mySeat) }}</template></p>
        <p v-if="!checkInSheet.task.has_gesture" class="att-meta">老师这次课只开了签到码，问老师要 6 位数字。</p>
        <div v-else class="check-modes" role="group" aria-label="签到方式">
        <button type="button" :class="{ active: checkInSheet.mode === 'code' }" @click="checkInSheet.mode = 'code'">签到码</button>
        <button type="button" :class="{ active: checkInSheet.mode === 'gesture' }" @click="checkInSheet.mode = 'gesture'">手势图案</button>
        </div>
        <p v-if="checkInSheet.error" class="checkin-error" role="alert">{{ checkInSheet.error }}</p>
        <form v-if="checkInSheet.mode === 'code'" class="checkin-form" @submit.prevent="checkInFromSheet">
        <label>6 位签到码
        <input v-model.trim="checkInSheet.code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="000000" required></label>
        <button>签到</button></form>
        <div v-else class="checkin-gesture">
        <p class="pad-step">照着老师课上画的图案划一遍，松手即签到</p>
        <gesture-pad ref="sheetPad" label="照着老师的手势口令签到" @done="checkInByGesture($event, $refs.sheetPad)" />
        </div>
        <details class="checkin-leave">
        <summary>今天来不了？申请请假</summary>
        <form class="inline-form" @submit.prevent="leave">
        <input v-model.trim="check.reason" maxlength="500" placeholder="请假理由（必填）" aria-label="请假理由" required>
        <button class="secondary">提交请假</button></form>
        </details>
        <div class="checkin-actions">
        <button type="button" class="secondary" @click="checkInSheet.open = false">关闭</button></div>
        </div>
      </div>

      <div v-if="checkInToast" class="checkin-toast" role="status">{{ checkInToast }}</div>
    </main>`,
}).mount('#app')
