// 课堂即时投票的界面：老师在这里出题、看分布与逐人明细；学生用浮层投票。
//
// 两块东西共用一个模型，但形态不一样：
// - PollPanel 贴在「考勤与请假」卡片里，老师出题 / 结束 / 看详细表，学生看自己投过哪几场；
// - PollModal 是学生桌面上的浮层，挂在整个页面根上，学生在哪个页签都能被弹到。
// 之所以拆开，是因为弹窗不能只在「考勤」页签可见——演示时学生正停在别的页面上。

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { PollClient } from './poll-client.js'

export const TYPE_TEXT = { single: '单选', multiple: '多选', boolean: '判断' }
export const typeText = kind => TYPE_TEXT[kind] ?? kind

// 后端错误码翻成学生看得懂的话，认不出来才退回后端原文
export const REASON_TEXT = {
  NOT_CHECKED_IN: '签到之后才能投票',
  NOT_IN_CLASS: '你不在这次课上，不能参与表决',
  ALREADY_VOTED: '你已经投过票了',
  POLL_CLOSED: '这场投票已经结束了',
  EMPTY_CHOICE: '至少选一项',
  TOO_MANY_CHOICES: '选多了',
  INVALID_OPTION: '选项已经变了，刷新一下再投',
}
export const reasonText = code => REASON_TEXT[code] ?? ''

export const percent = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0)

// 一题最多能选几项：只有多选才有上限，单选和判断恒为 1
export const maxPicks = poll => (poll?.type === 'multiple'
  ? (poll.max_choices || (poll.options?.length ?? 1))
  : 1)

// 点一下就选 / 取消，选满上限时给提示而不是默默吞掉
export function togglePick(poll, chosen, optionId) {
  const limit = maxPicks(poll)
  if (chosen.includes(optionId)) return { picks: chosen.filter(id => id !== optionId), error: '' }
  if (limit <= 1) return { picks: [optionId], error: '' }
  if (chosen.length >= limit) return { picks: chosen, error: `这道题最多选 ${limit} 项` }
  return { picks: [...chosen, optionId], error: '' }
}

// 学生视角的一句话状态：弹窗自己不会解释「为什么没弹」出来
export function studentState(poll) {
  if ((poll.my_option_ids ?? []).length) return '已投票'
  if (poll.open && poll.can_vote) return '待投票'
  if (!poll.open) return '已结束'
  return reasonText(poll.reason) || '不能投票'
}

// 和 main.js 里那份保持一致：明细表里只显示到分钟，日期没有意义（都是今天的课）
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
export const shortTime = value => {
  const date = new Date(value)
  return value && Number.isFinite(date.getTime()) ? timeFormat.format(date) : '时间未知'
}

export const PollPanel = {
  name: 'PollPanel',
  props: {
    user: { type: Object, required: true },
    courseId: { type: Number, default: null },
    tasks: { type: Array, default: () => [] },
  },
  setup(props) {
    const client = new PollClient()
    const polls = ref([])
    const error = ref('')
    const notice = ref('')
    const busy = ref(false)
    const opened = ref(false)
    const selected = ref(null)
    const report = ref(null)
    const detailFilter = ref('all')
    const detailsShown = ref(30)
    // 未投名单在 160 人的课上是一长串 chip，默认只铺前 12 个，剩下的点一下再展开
    const unvotedShown = ref(12)
    const form = reactive({
      taskId: '', type: 'single', title: '', options: ['', ''],
      maxChoices: 2, correctOne: 0, correct: [], anonymous: true,
    })

    const isTeacher = computed(() => props.user?.role === 'teacher')
    const openTasks = computed(() => (props.tasks ?? []).filter(task => task.status === 'open'))
    // 出题只挂在进行中的任务上：任务一结算，投票就自动作废，所以这里不给选已结束的
    const chosenTask = computed(() => openTasks.value.find(task => String(task.id) === String(form.taskId)) ?? null)
    const optionLabels = computed(() => (form.type === 'boolean'
      ? ['正确', '错误']
      : form.options.map(text => text.trim()).filter(Boolean)))
    const filteredDetails = computed(() => {
      const rows = report.value?.details ?? []
      if (detailFilter.value === 'all') return rows
      const want = detailFilter.value === 'right'
      return rows.filter(row => row.correct === want)
    })
    const visibleDetails = computed(() => filteredDetails.value.slice(0, detailsShown.value))
    const unvoted = computed(() => report.value?.unvoted ?? [])
    const visibleUnvoted = computed(() => unvoted.value.slice(0, unvotedShown.value))
    const unvotedFolded = computed(() => unvoted.value.length > unvotedShown.value)
    const selectedIsOpen = computed(() => Boolean(selected.value?.open))

    async function load() {
      if (!props.courseId) { polls.value = []; return }
      try {
        const data = await client.list(props.courseId)
        polls.value = data.items
        error.value = ''
        // 列表是新的对象，正在看的那一场要换成同一场的新快照，否则状态还停在「进行中」
        if (selected.value) {
          selected.value = data.items.find(item => item.id === selected.value.id) ?? selected.value
        }
      } catch (failure) {
        error.value = failure.message
      }
    }
    async function refreshReport() {
      if (!selected.value) { report.value = null; return }
      try {
        report.value = await client.results(selected.value.id)
      } catch (failure) {
        report.value = null
        error.value = failure.code === 'FORBIDDEN' ? '投完票才能看分布。' : failure.message
      }
    }
    async function look(poll) {
      if (!isTeacher.value && !(poll.my_option_ids ?? []).length) {
        error.value = '投完票才能看分布，先在上面的弹窗里投一票。'
        return
      }
      error.value = ''
      notice.value = ''
      selected.value = poll
      detailsShown.value = 30
      unvotedShown.value = 12
      detailFilter.value = 'all'
      await refreshReport()
    }
    function closeReport() {
      selected.value = null
      report.value = null
    }
    async function finish(poll) {
      if (!window.confirm(`结束「${poll.title}」？结束后学生投不了，结果照旧可看。`)) return
      busy.value = true
      try {
        await client.close(poll.id)
        notice.value = '投票已结束。'
        await load()
        if (selected.value?.id === poll.id) await refreshReport()
      } catch (failure) {
        error.value = failure.message
      } finally {
        busy.value = false
      }
    }
    async function submit() {
      if (busy.value) return
      error.value = ''
      notice.value = ''
      if (!form.taskId) { error.value = '先选一条进行中的考勤任务。'; return }
      if (!form.title.trim()) { error.value = '题目不能为空。'; return }
      const labels = optionLabels.value
      if (form.type !== 'boolean') {
        if (form.options.some(text => !text.trim())) { error.value = '选项不能留空。'; return }
        if (new Set(labels).size !== labels.length) { error.value = '选项不能重复。'; return }
      }
      if (labels.length < 2) { error.value = '至少两个选项。'; return }
      const correct = form.type === 'multiple'
        ? form.correct.filter(ordinal => ordinal >= 1 && ordinal <= labels.length)
        : (form.correctOne ? [form.correctOne] : [])
      busy.value = true
      try {
        const created = await client.create(props.courseId, {
          task_id: Number(form.taskId),
          title: form.title.trim(),
          type: form.type,
          options: form.type === 'boolean' ? [] : labels,
          max_choices: form.type === 'multiple' ? Number(form.maxChoices) : null,
          anonymous: form.anonymous,
          correct_ordinals: correct,
        })
        notice.value = `「${created.title}」已经发出去，签到过的学生几秒内会收到弹窗。`
        form.title = ''
        form.options = ['', '']
        form.correct = []
        form.correctOne = 0
        await load()
        selected.value = created
        detailsShown.value = 30
        unvotedShown.value = 12
        await refreshReport()
      } catch (failure) {
        error.value = reasonText(failure.code) || failure.message
      } finally {
        busy.value = false
      }
    }
    // 多选题的正确答案是集合，点一下加进去、再点一下拿出来
    function markCorrect(ordinal) {
      form.correct = form.correct.includes(ordinal)
        ? form.correct.filter(value => value !== ordinal)
        : [...form.correct, ordinal]
    }
    function addOption() {
      if (form.options.length < 8) form.options.push('')
    }
    function dropOption(index) {
      if (form.options.length > 2) form.options.splice(index, 1)
    }

    watch(() => props.courseId, () => {
      polls.value = []
      selected.value = null
      report.value = null
      form.taskId = ''
      load()
    })
    watch(detailFilter, () => { detailsShown.value = 30 })
    // 判断题只有两个固定选项、恒为一个答案；从别的题型切过来要把残留清掉
    watch(() => form.type, () => {
      form.maxChoices = 2
      form.correct = []
      form.correctOne = 0
    })
    watch(openTasks, list => {
      if (!list.length) { form.taskId = ''; return }
      if (!list.some(task => String(task.id) === String(form.taskId))) form.taskId = String(list[0].id)
    }, { immediate: true })

    // 老师在盯一场投票时 2 秒刷一次（演示时数字要肉眼可见地动），没人看结果时拉列表就够了
    let timer = 0
    let tick = 0
    onMounted(async () => {
      await load()
      timer = globalThis.setInterval(async () => {
        tick += 1
        if (selected.value?.open) await refreshReport()
        if (tick % 3 === 0 || !selected.value) await load()
      }, 2000)
    })
    onBeforeUnmount(() => globalThis.clearInterval(timer))

    return {
      polls, error, notice, busy, opened, selected, report, detailFilter, detailsShown, form,
      isTeacher, openTasks, chosenTask, optionLabels, filteredDetails, visibleDetails, selectedIsOpen,
      unvoted, unvotedShown, visibleUnvoted, unvotedFolded,
      load, look, closeReport, finish, submit, addOption, dropOption, markCorrect, refreshReport,
      typeText, percent, studentState, shortTime,
    }
  },
  template: `
    <section class="poll-panel">
      <div class="poll-head">
        <strong>课堂投票</strong>
        <span class="att-meta" v-if="isTeacher && chosenTask">发起后学生桌面会弹出投票框，签到过的才能投。
          当前挂在「{{ chosenTask.title }}」。</span>
        <span class="att-meta" v-else-if="isTeacher">现在没有进行中的考勤任务，先发布一条再发起投票。</span>
        <span class="att-meta" v-else>老师发起投票后，这里会自动弹出投票框；投完能看到分布。</span>
      </div>
      <p v-if="error" class="poll-error" role="alert">{{ error }}</p>
      <p v-if="notice" class="poll-notice" role="status">{{ notice }}</p>

      <template v-if="isTeacher">
      <button type="button" class="secondary poll-toggle" :disabled="!openTasks.length"
        @click="opened = !opened">{{ opened ? '收起出题' : '发起一场投票' }}</button>
      <form v-if="opened" class="poll-form" @submit.prevent="submit">
      <div class="poll-form-row">
      <label>题型 <select :value="form.type" aria-label="题型" @change="form.type = $event.target.value">
        <option value="single">单选题</option><option value="multiple">多选题</option>
        <option value="boolean">判断题</option></select></label>
      <label>挂在任务 <select :value="form.taskId" aria-label="挂在任务" @change="form.taskId = $event.target.value">
        <option v-for="task in openTasks" :key="task.id" :value="String(task.id)">{{ task.title }}</option>
        </select></label>
      <label class="poll-wide">题目 <input :value="form.title" aria-label="题目" maxlength="200"
        placeholder="例如：这段流水线有几处数据冒险？" required
        @input="form.title = $event.target.value"></label>
      </div>
      <div class="poll-form-row">
      <label v-if="form.type === 'multiple'">多选上限
        <select :value="form.maxChoices" aria-label="多选上限" @change="form.maxChoices = Number($event.target.value)">
        <option v-for="count in optionLabels.length" :key="count" :value="count">{{ count }} 项</option>
        </select></label>
      <label>正确答案 <select :value="form.correctOne" aria-label="正确答案" :disabled="form.type === 'multiple'"
        @change="form.correctOne = Number($event.target.value)">
        <option :value="0">不计对错</option>
        <option v-for="(label, index) in optionLabels" :key="index" :value="index + 1">{{ index + 1 }}. {{ label }}</option>
        </select></label>
      <label class="poll-check"><input type="checkbox" :checked="form.anonymous" aria-label="匿名投票"
        @change="form.anonymous = $event.target.checked">
        匿名投票<small>不勾就实名，明细里能看到谁选了什么</small></label>
      </div>
      <div v-if="form.type === 'boolean'" class="poll-fixed">
        <p class="att-meta">判断题固定两个选项：</p>
        <span class="poll-fixed-row"><b>1</b>正确　<b>2</b>错误</span>
      </div>
      <div v-else class="poll-editor">
        <label v-for="(option, index) in form.options" :key="index" class="poll-editor-row">
          <span>{{ index + 1 }}</span>
          <input :value="form.options[index]" :aria-label="'选项 ' + (index + 1)" maxlength="120"
            :placeholder="'选项 ' + (index + 1)" @input="form.options[index] = $event.target.value">
          <button v-if="form.type === 'multiple' && optionLabels.length > 1" type="button" class="secondary"
            :aria-label="'标记正确 ' + (index + 1)"
            :class="{ 'poll-correct-on': form.correct.includes(index + 1) }"
            @click="markCorrect(index + 1)">对</button>
          <button v-if="form.options.length > 2" type="button" class="secondary"
            :aria-label="'删除选项 ' + (index + 1)" @click="dropOption(index)">删</button>
        </label>
        <button v-if="form.options.length < 8" type="button" class="secondary" @click="addOption">加一项</button>
        <p v-if="form.type === 'multiple'" class="att-meta">多选时点「对」标记正确答案，全选对才算对。</p>
      </div>
      <div class="poll-actions"><button :disabled="busy">发起投票</button></div>
      </form>
      </template>

      <ul class="poll-list">
      <li v-for="item in polls" :key="item.id" :class="['poll-row', { picked: selected && selected.id === item.id }]">
      <div class="poll-row-head">
      <b>{{ item.title }}</b>
      <span :class="['poll-badge', item.type]">{{ typeText(item.type) }}</span>
      <span :class="['poll-badge', item.open ? 'open' : 'closed']">{{ item.open ? '进行中' : '已结束' }}</span>
      <span v-if="item.anonymous" class="poll-badge ghost">匿名</span>
      <span v-if="item.has_correct" class="poll-badge ghost">有答案</span>
      <span class="poll-rate">已投 {{ item.voted }} / {{ item.eligible }}　{{ percent(item.voted, item.eligible) }}%</span>
      </div>
      <div class="poll-actions">
      <button type="button" class="secondary" @click="look(item)">看结果</button>
      <button v-if="isTeacher && item.status === 'open'" type="button" class="secondary"
        :disabled="busy" @click="finish(item)">结束投票</button>
      <span v-if="!isTeacher" class="att-meta">我：{{ studentState(item) }}</span>
      </div>
      </li>
      </ul>
      <p v-if="!polls.length" class="att-meta">这门课还没有投票。</p>

      <div v-if="selected && report" class="poll-report">
      <div class="poll-report-head">
      <b>{{ selected.title }}</b>
      <span class="att-meta">已投 {{ report.voted }} / 应投 {{ report.eligible }}　参与率 {{ percent(report.voted, report.eligible) }}%</span>
      <span v-if="report.correct" class="poll-accuracy">对 {{ report.correct.right }} · 错 {{ report.correct.wrong }}
        · 正确率 {{ percent(report.correct.right, report.correct.answered) }}%</span>
      <button type="button" class="secondary" @click="closeReport">收起</button>
      </div>
      <ul class="poll-dist">
      <li v-for="row in report.counts" :key="row.option_id" :class="{ right: row.is_correct && report.correct }">
      <span class="poll-dist-label">{{ row.ordinal }}. {{ row.label }}
        <em v-if="row.is_correct && report.correct">正确答案</em></span>
      <span class="poll-bar"><i :style="{ width: percent(row.count, report.voted) + '%' }"></i></span>
      <span class="poll-dist-num">{{ row.count }} 人 · {{ percent(row.count, report.voted) }}%</span>
      </li>
      </ul>
      <p class="att-meta">应投人数只算这节课签到过的（已到 + 迟到）：{{ report.eligible }} 人。</p>

      <template v-if="isTeacher">
      <div v-if="report.details.length" class="poll-details">
      <div class="bulk-tools">
      <label>判定 <select :value="detailFilter" aria-label="按对错筛选"
        @change="detailFilter = $event.target.value">
        <option value="all">全部</option><option value="right">答对</option><option value="wrong">答错</option>
        </select></label>
      <span class="bulk-count">筛出 {{ filteredDetails.length }} 人</span>
      </div>
      <div v-if="filteredDetails.length" class="bulk">
      <table>
      <thead><tr><th>姓名</th><th>学号</th><th>所选</th><th>判定</th><th>提交时间</th></tr></thead>
      <tbody><tr v-for="row in visibleDetails" :key="row.student_id">
      <td>{{ row.name }}</td><td>{{ row.student_no }}</td>
      <td>{{ row.labels.join('、') || '—' }}</td>
      <td><span :class="['poll-badge', row.correct ? 'right' : 'wrong']">{{ row.correct ? '答对' : '答错' }}</span></td>
      <td>{{ row.submitted_at ? shortTime(row.submitted_at) : '—' }}</td>
      </tr></tbody>
      </table>
      </div>
      <p v-else class="att-meta">这个筛选下没有人。</p>
      <div v-if="visibleDetails.length < filteredDetails.length" class="bulk-more">
      <button type="button" class="secondary" @click="detailsShown += 100">
        再显示 100 人（{{ visibleDetails.length }}/{{ filteredDetails.length }}）</button>
      </div>
      </div>
      <p v-else-if="selected.anonymous" class="att-meta">匿名投票：只给分布、参与率和未投名单，不显示谁选了什么。</p>
      <p v-else class="att-meta">还没有人投票。</p>

      <p class="att-meta">未投票 {{ report.unvoted.length }} 人
        <span v-for="one in visibleUnvoted" :key="one.student_id" class="poll-chip">{{ one.name }}</span>
        <button v-if="unvotedFolded" type="button" class="secondary poll-chip-more"
          @click="unvotedShown = unvoted.length">还有 {{ unvoted.length - visibleUnvoted.length }} 人，展开</button>
        <button v-else-if="unvoted.length > 12" type="button" class="secondary poll-chip-more"
          @click="unvotedShown = 12">收起名单</button></p>
      </template>
      </div>
    </section>`,
}

export const PollModal = {
  name: 'PollModal',
  props: { courseId: { type: Number, default: null } },
  setup(props) {
    const client = new PollClient()
    const poll = ref(null)
    const result = ref(null)
    const chosen = ref([])
    const error = ref('')
    const busy = ref(false)
    // 后端说「已经投过 / 已经结束」时，浮层不直接消失——那样学生只看到框一闪就没了，
    // 会把原因留在原地，改成按「知道了」才收。
    const blocked = ref(false)
    // 点过「稍后」的题目不再弹，否则学生关一次、五秒后又蹦出来
    const dismissed = ref([])

    const limit = computed(() => maxPicks(poll.value))
    const canSubmit = computed(() => Boolean(poll.value) && chosen.value.length > 0 && !busy.value)

    async function scan() {
      if (!props.courseId || result.value) return
      try {
        const data = await client.openPolls(props.courseId)
        const fresh = data.items.filter(item => item.can_vote && !dismissed.value.includes(item.id))
        const next = fresh[0] ?? null
        if (next?.id !== poll.value?.id) {
          chosen.value = []
          error.value = ''
        }
        poll.value = next
      } catch { /* 轮询失败不打断页面：下一轮还会再试 */ }
    }
    function pick(option) {
      const moved = togglePick(poll.value, chosen.value, option.id)
      chosen.value = moved.picks
      error.value = moved.error
    }
    function dismiss() {
      if (poll.value && !blocked.value) dismissed.value = [...dismissed.value, poll.value.id]
      poll.value = null
      chosen.value = []
      error.value = ''
      blocked.value = false
    }
    async function submit() {
      if (!canSubmit.value) return
      busy.value = true
      try {
        result.value = await client.vote(poll.value.id, chosen.value)
        poll.value = null
        chosen.value = []
        error.value = ''
      } catch (failure) {
        error.value = reasonText(failure.code) || failure.message
        // 已经投过 / 已经结束：这题不用再弹了，但原因要留在屏幕上
        if (failure.code === 'ALREADY_VOTED' || failure.code === 'POLL_CLOSED') blocked.value = true
      } finally {
        busy.value = false
      }
    }
    function closeResult() {
      result.value = null
      error.value = ''
    }

    watch(() => props.courseId, () => {
      poll.value = null
      result.value = null
      chosen.value = []
      dismissed.value = []
    })

    let timer = 0
    onMounted(() => {
      scan()
      timer = globalThis.setInterval(scan, 5000)
    })
    onBeforeUnmount(() => globalThis.clearInterval(timer))

    return { poll, result, chosen, error, busy, blocked, limit, canSubmit, scan, pick, dismiss, submit,
      closeResult, typeText, percent }
  },
  template: `
    <div v-if="poll || result" class="poll-modal" role="dialog" aria-modal="true" aria-labelledby="poll-title">
      <div class="poll-dialog">
      <template v-if="poll">
      <p class="poll-eyebrow">课堂投票 · {{ typeText(poll.type) }} · {{ poll.anonymous ? '匿名' : '实名' }}</p>
      <h3 id="poll-title">{{ poll.title }}</h3>
      <p class="poll-when">{{ poll.anonymous ? '匿名投票，老师只看参与率，看不到谁选了什么。' : '实名投票，老师能看到谁选了什么。' }}
        <template v-if="limit > 1">　最多选 {{ limit }} 项</template></p>
      <ul v-if="!blocked" class="poll-picks">
      <li v-for="option in poll.options" :key="option.id">
      <button type="button" :class="['poll-option', { picked: chosen.includes(option.id) }]"
        :aria-pressed="chosen.includes(option.id)" @click="pick(option)">
      <span class="poll-key">{{ option.ordinal }}</span>{{ option.label }}</button>
      </li>
      </ul>
      <p v-if="error" class="poll-error" role="alert">{{ error }}</p>
      <div class="poll-actions">
      <button v-if="!blocked" type="button" :disabled="!canSubmit" @click="submit">
        {{ busy ? '提交中…' : '提交' + (chosen.length ? '（已选 ' + chosen.length + ' 项）' : '') }}</button>
      <button type="button" :class="blocked ? '' : 'secondary'" @click="dismiss">
        {{ blocked ? '知道了' : '稍后' }}</button>
      </div>
      </template>
      <template v-else-if="result">
      <p class="poll-eyebrow">已提交 · {{ result.anonymous ? '匿名投票' : '实名投票' }}</p>
      <h3 id="poll-title">{{ result.title }}</h3>
      <p class="poll-when">共 {{ result.voted }} 人投票<template v-if="result.correct_option_ids">
        　正确答案：{{ result.correct_option_ids.length }} 项</template></p>
      <ul class="poll-dist">
      <li v-for="row in result.counts" :key="row.option_id"
        :class="{ right: (result.correct_option_ids || []).includes(row.option_id),
          mine: (result.my_option_ids || []).includes(row.option_id) }">
      <span class="poll-dist-label">{{ row.ordinal }}. {{ row.label }}
        <em v-if="(result.my_option_ids || []).includes(row.option_id)" class="mine">我选的</em>
        <em v-if="(result.correct_option_ids || []).includes(row.option_id)">正确</em></span>
      <span class="poll-bar"><i :style="{ width: percent(row.count, result.voted) + '%' }"></i></span>
      <span class="poll-dist-num">{{ row.count }} 人 · {{ percent(row.count, result.voted) }}%</span>
      </li>
      </ul>
      <div class="poll-actions"><button type="button" @click="closeResult">知道了</button></div>
      </template>
      </div>
    </div>`,
}
