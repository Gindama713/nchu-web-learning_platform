import { h, nextTick, ref, watch } from 'vue'

import { AssistantClient } from './assistant-client.js'
import { chartColorOf, chartNode, donutChart, lineChart, rankChart } from './charts.js'

const TEACHER_DEFAULTS = ['这周学情怎么样？', '哪个知识点最薄弱？', '谁需要重点关注？', '下节课该讲什么？']
const STUDENT_DEFAULTS = ['程序计数器是什么？', '我哪里薄弱？', '下一步该练什么？', '我这段时间考勤怎么样？']

const factValue = fact => fact.value === null || fact.value === undefined
  ? '无数据'
  : `${fact.value}${fact.unit ? ' ' + fact.unit : ''}`

// 后端给 kind + 数字 + colorKey，几何与配色都在前端算，保证和统计页同一套。
function chartBlock(chart, index) {
  if (!chart || !chart.kind) return null
  const title = chart.title ? h('p', { class: 'assistant-chart-title' }, chart.title) : null
  if (chart.kind === 'donut') {
    const donut = donutChart((chart.slices ?? []).filter(slice => Number.isFinite(slice.value)).map(slice => ({
      label: slice.label, value: slice.value, color: chartColorOf(slice.colorKey),
    })), { size: 152, thickness: 20 })
    if (donut.empty) return null
    return h('div', { class: 'assistant-chart', key: index }, [
      title,
      h('div', { class: 'chart-donut-wrap' }, [
        h('div', { class: 'assistant-donut' }, [
          h('svg', {
            viewBox: `0 0 ${donut.size} ${donut.size}`, width: donut.size, height: donut.size,
            role: 'img', 'aria-label': chart.title || '构成环形图',
          }, [h('g', { class: 'chart-donut' }, donut.nodes.map(chartNode))]),
          h('div', { class: 'chart-center' }, [
            h('strong', {}, String(donut.total)),
            h('span', {}, chart.unit || ''),
          ]),
        ]),
        h('ul', { class: 'chart-legend' }, donut.rows.map(row => h('li', {}, [
          h('i', { style: `background:${row.color}` }),
          h('b', {}, String(row.value)),
          h('small', {}, `${row.label} · ${row.percent}%`),
        ]))),
      ]),
    ])
  }
  if (chart.kind === 'bar') {
    const percent = chart.unit === 'percent'
    const model = rankChart((chart.items ?? []).filter(item => Number.isFinite(item.value)).map(item => ({
      label: item.label, value: item.value, color: chartColorOf(item.colorKey),
    })), {
      max: chart.max ?? 100, unit: percent ? 'percent' : 'number', width: 620,
      suffix: percent ? '' : (chart.unit ?? ''),
    })
    if (model.empty) return null
    return h('div', { class: 'assistant-chart', key: index }, [
      title,
      h('svg', {
        viewBox: `0 0 ${model.width} ${model.height}`, width: '100%',
        style: `max-width:${model.width}px;height:auto;display:block`,
        role: 'img', 'aria-label': chart.title || '条形图',
      }, model.nodes.map(chartNode)),
    ])
  }
  if (chart.kind === 'line') {
    const model = lineChart((chart.points ?? []).filter(point => Number.isFinite(point.value)).map(point => ({
      label: point.label, value: point.value,
    })), { max: chart.max ?? 1, unit: chart.unit === 'percent' ? 'percent' : 'ratio', width: 620, height: 180 })
    if (model.empty) return null
    return h('div', { class: 'assistant-chart', key: index }, [
      title,
      h('svg', {
        viewBox: `0 0 ${model.width} ${model.height}`, width: '100%',
        style: `max-width:${model.width}px;height:auto;display:block`,
        role: 'img', 'aria-label': chart.title || '折线图',
      }, model.nodes.map(chartNode)),
    ])
  }
  return null
}

export const AssistantView = {
  props: {
    user: { type: Object, required: true },
    courseId: { type: Number, default: 0 },
  },
  emits: ['action'],
  setup(props, { emit }) {
    const api = new AssistantClient(props.user)
    const teacher = props.user.role === 'teacher'
    const defaults = teacher ? TEACHER_DEFAULTS : STUDENT_DEFAULTS
    const messages = ref([])
    const question = ref('')
    const busy = ref(false)
    const error = ref('')
    const suggestions = ref(defaults)
    const listNode = ref(null)
    // 多轮指代：教师问过某个学生后，下一句「他考得怎么样」直接接上。
    const lastStudent = ref(null)
    const PRONOUN = /(他|她|该生|这个学生|这位同学|刚才那位|这名学生|那名学生|那位同学|此人)/

    function welcome() {
      return {
        role: 'assistant',
        card: {
          title: teacher ? '教学助手 · 班级视角' : '教学助手 · 我的视角',
          answer: teacher
            ? '我会用本课程真实的考勤、作答和预警数据回答。每个数字都标出处；数据不够时我会直说，不猜。'
            : '我会用你自己的作答、考勤和已发布知识点回答。问知识点、薄弱项或下一步练什么都可以。',
          facts: [], caveats: [], actions: [], window: null,
        },
      }
    }
    messages.value = [welcome()]

    function scrollDown() {
      nextTick(() => {
        const node = listNode.value
        if (node) node.scrollTop = node.scrollHeight
      })
    }

    async function send(text) {
      const value = String(text ?? '').trim()
      if (!value || busy.value) return
      error.value = ''
      if (!props.courseId) {
        error.value = '先在「课程与通知」里选一门课，再提问。'
        return
      }
      messages.value.push({ role: 'user', text: value })
      question.value = ''
      busy.value = true
      scrollDown()
      const epoch = props.courseId
      const contextId = teacher && lastStudent.value && PRONOUN.test(value.replace(/其他|他人|他们|她们/g, ''))
        ? lastStudent.value.id : null
      try {
        const data = await api.ask(epoch, value, contextId)
        if (props.courseId !== epoch) return
        if (data.student) lastStudent.value = data.student
        else if (data.intent === 'clarify') lastStudent.value = null
        messages.value.push({ role: 'assistant', card: data })
        if (Array.isArray(data.suggestions) && data.suggestions.length) suggestions.value = data.suggestions
      } catch (failure) {
        if (props.courseId !== epoch) return
        error.value = failure.message || '提问失败，请重试。'
      } finally {
        if (props.courseId === epoch) busy.value = false
        scrollDown()
      }
    }

    function act(action) {
      if (action?.kind === 'ask' && action.payload?.question) return send(action.payload.question)
      emit('action', action)
    }

    watch(() => props.courseId, () => {
      messages.value = [welcome()]
      suggestions.value = defaults
      question.value = ''
      error.value = ''
      busy.value = false
      lastStudent.value = null
    })

    function cardNode(card) {
      if (!card) return h('p', {}, '（没有拿到回答，请重试）')
      const facts = (card.facts ?? []).map((fact, index) => h('div',
        { class: ['assistant-fact', fact.wide ? 'wide' : ''], key: index }, [
          h('dt', {}, fact.label),
          h('dd', {}, [
            h('strong', {}, factValue(fact)),
            fact.note && h('small', {}, fact.note),
          ]),
        ]))
      const sources = [...new Set((card.facts ?? []).map(fact => fact.source).filter(Boolean))]
      // 图放在结论句后面、明细数字前面：投屏时先看形状，再核对具体数。
      const charts = (card.charts ?? []).map(chartBlock).filter(Boolean)
      return h('div', { class: 'assistant-card' }, [
        h('h3', {}, card.title || '回答'),
        h('p', { class: 'assistant-answer' }, card.answer || ''),
        charts.length > 0 && h('div', { class: 'assistant-charts' }, charts),
        facts.length > 0 && h('dl', { class: 'assistant-facts' }, facts),
        (card.caveats ?? []).length > 0 && h('ul', { class: 'assistant-caveats' },
          card.caveats.map((item, index) => h('li', { key: index }, item))),
        (card.actions ?? []).length > 0 && h('div', { class: 'assistant-actions' },
          card.actions.map((action, index) => h('button', {
            type: 'button', class: 'secondary', key: index, onClick: () => act(action),
          }, action.label))),
        (facts.length > 0 || card.window) && h('p', { class: 'assistant-source' }, [
          sources.length ? `数据来源：${sources.join(' / ')}` : '没有引用统计数据',
          card.window ? ` · 窗口：最近 ${card.window.days} 天` : '',
        ].join('')),
      ])
    }

    return () => h('section', { class: 'card assistant' }, [
          h('header', { class: 'assistant-head' }, [
            h('div', {}, [
              h('h2', {}, '教学助手'),
              h('p', { class: 'assistant-sub' }, props.courseId
                ? (teacher ? '班级学情、薄弱知识点、预警名单，都能问。' : '你的知识点、薄弱项、考勤和下一步练习，都能问。')
                : '先选一门课程。'),
            ]),
            h('span', { class: 'assistant-badge' }, teacher ? '教师视角' : '学生视角'),
          ]),
          h('div', { class: 'assistant-log', ref: listNode, role: 'log', 'aria-live': 'polite' },
            messages.value.map((message, index) => message.role === 'user'
              ? h('div', { class: 'assistant-msg user', key: index }, [h('p', {}, message.text)])
              : h('div', { class: 'assistant-msg bot', key: index }, [cardNode(message.card)]))),
          error.value && h('p', { class: 'assistant-error', role: 'alert' }, error.value),
          teacher && lastStudent.value && h('p', { class: 'assistant-context' }, [
            `正在问：${lastStudent.value.name}（${lastStudent.value.student_no}），下句说「他/她」会接着问这个学生`,
            h('button', {
              type: 'button', class: 'secondary',
              onClick: () => { lastStudent.value = null },
            }, '清除'),
          ]),
          h('div', { class: 'assistant-asks' }, suggestions.value.map((item, index) => h('button', {
            type: 'button', class: 'secondary', key: index, disabled: busy.value,
            onClick: () => send(item),
          }, item))),
          h('form', {
            class: 'assistant-form',
            onSubmit: event => { event.preventDefault(); send(question.value) },
          }, [
            h('input', {
              value: question.value,
              maxlength: 200,
              placeholder: teacher ? '例如：哪个知识点最薄弱？' : '例如：ALU 是做什么的？',
              'aria-label': '向教学助手提问',
              onInput: event => { question.value = event.target.value },
            }),
            h('button', { type: 'submit', disabled: busy.value }, busy.value ? '思考中…' : '提问'),
          ]),
          h('p', { class: 'assistant-note' },
            '回答只引用本课程已记录的统计和已发布知识点；数据不足时会明确说明，不编造数字，也不自动改成绩。'),
    ])
  },
}
