// SPEC-015 knowledge graph view: nodes, mastery, reachable paths and guarded edges.
import { h, onMounted, reactive, ref } from 'vue'
import { GraphClient } from './graph-client.js'

const EDGE = { prerequisite: '先修', contains: '包含' }
const selected = value => (value ? String(value) : '')

export const GraphView = {
  setup() {
    const api = new GraphClient()
    const session = ref(null)
    const courses = ref([])
    const courseId = ref('')
    const graph = ref(null)
    const focusId = ref('')
    const rootId = ref('')
    const edgeForm = reactive({ source_id: '', target_id: '', type: 'prerequisite' })
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')

    const teacher = () => session.value?.user.role === 'teacher'
    const nodes = () => graph.value?.nodes ?? []
    const edges = () => graph.value?.edges ?? []
    const paths = () => graph.value?.prerequisite_paths ?? []
    const titleOf = id => nodes().find(node => node.id === id)?.title ?? `#${id}`

    function resetAuth() {
      session.value = null
      api.userId = null
      courses.value = []
      courseId.value = ''
      graph.value = null
      focusId.value = ''
      rootId.value = ''
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

    async function loadGraph() {
      graph.value = null
      focusId.value = ''
      if (!courseId.value) return
      graph.value = await api.graph(courseId.value, rootId.value)
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
      await loadGraph()
    }

    function setRoot(value) {
      rootId.value = value
      return loadGraph()
    }

    function relations(nodeId) {
      return edges()
        .filter(edge => edge.source === nodeId || edge.target === nodeId)
        .map(edge => {
          if (edge.type === 'contains') {
            return edge.source === nodeId
              ? { key: `c-${edge.source}-${edge.target}`, text: `包含 ${titleOf(edge.target)}` }
              : { key: `c-${edge.source}-${edge.target}`, text: `属于 ${titleOf(edge.source)}` }
          }
          return edge.source === nodeId
            ? { key: `p-${edge.source}-${edge.target}`, text: `先修 → ${titleOf(edge.target)}` }
            : { key: `p-${edge.source}-${edge.target}`, text: `先学 ← ${titleOf(edge.source)}` }
        })
    }

    function reachPaths(nodeId) {
      return paths()
        .filter(path => path.from === nodeId || path.to === nodeId)
        .map((path, index) => ({
          key: `${path.from}-${path.to}-${index}`,
          text: `${titleOf(path.from)} → ${titleOf(path.to)}`,
        }))
    }

    async function addEdge() {
      const source = Number(edgeForm.source_id)
      const target = Number(edgeForm.target_id)
      if (!source || !target) throw new Error('请选择关系两端的知识点')
      if (source === target) throw new Error('边两端不能指向同一知识点')
      await api.addEdge(courseId.value, { source_id: source, target_id: target, type: edgeForm.type })
      edgeForm.source_id = ''
      edgeForm.target_id = ''
      await loadGraph()
    }

    onMounted(() => run(boot))

    const button = (label, action, options = {}) => h('button', {
      type: 'button', disabled: busy.value, onClick: action, ...options,
    }, label)

    const nodeOptions = (excludeId = '') => nodes()
      .filter(node => String(node.id) !== String(excludeId))
      .map(node => [String(node.id), node.title])

    const picker = (entries, value, onChange, blank) => h('select', {
      value, disabled: busy.value, onChange: event => onChange(event.target.value),
    }, [
      h('option', { value: '' }, blank),
      ...entries.map(([key, label]) => h('option', { value: key, key }, label)),
    ])

    function nodeTable() {
      return h('table', { class: 'graph-nodes' }, [
        h('thead', h('tr', ['编号', '名称', '基础', '掌握', '操作'].map(text => h('th', text)))),
        h('tbody', nodes().map(node => h('tr', { key: node.id, class: focusId.value === node.id ? 'graph-focus' : '' }, [
          h('td', `#${node.id}`),
          h('td', node.title),
          h('td', node.is_foundational ? '是' : '否'),
          h('td', node.mastery >= 1 ? '已掌握' : '未掌握'),
          h('td', button('查看', () => { focusId.value = String(node.id) }, { class: 'secondary' })),
        ]))),
      ])
    }

    function focusPanel() {
      const node = nodes().find(item => String(item.id) === focusId.value)
      if (!node) return null
      const related = relations(node.id)
      const reachable = reachPaths(node.id)
      return h('section', { class: 'graph-focus-panel' }, [
        h('h3', `节点 #${node.id} ${node.title}`),
        h('p', `掌握状态：${node.mastery >= 1 ? '已掌握' : '未掌握'}${node.is_foundational ? ' · 基础节点' : ''}`),
        h('h4', '直接关联'),
        related.length
          ? h('ul', related.map(item => h('li', { key: item.key }, item.text)))
          : h('p', '暂无直接关联。'),
        h('h4', '可达路径'),
        reachable.length
          ? h('ul', reachable.map(item => h('li', { key: item.key }, item.text)))
          : h('p', '暂无先修可达路径。'),
        button('收起', () => { focusId.value = '' }, { class: 'secondary' }),
      ])
    }

    function edgeFormView() {
      return h('form', {
        class: 'graph-edge-form',
        onSubmit: event => { event.preventDefault(); run(addEdge, '关系已保存') },
      }, [
        h('label', ['起点 ', picker(nodeOptions(), edgeForm.source_id,
          value => { edgeForm.source_id = value }, '请选择')]),
        h('label', ['终点 ', picker(nodeOptions(edgeForm.source_id), edgeForm.target_id,
          value => { edgeForm.target_id = value }, '请选择')]),
        h('label', ['类型 ', picker([['prerequisite', '先修'], ['contains', '包含']], edgeForm.type,
          value => { edgeForm.type = value }, '')]),
        h('button', { type: 'submit', disabled: busy.value }, '添加关系'),
        h('small', '先修方向：起点需先于终点学习；成环会被拒绝。'),
      ])
    }

    function edgeTable() {
      return h('table', { class: 'graph-edges' }, [
        h('thead', h('tr', ['类型', '起点', '终点'].map(text => h('th', text)))),
        h('tbody', edges().map((edge, index) => h('tr', { key: index }, [
          h('td', EDGE[edge.type] ?? edge.type),
          h('td', titleOf(edge.source)),
          h('td', titleOf(edge.target)),
        ]))),
      ])
    }

    return () => h('section', { class: 'card graph-module' }, [
      h('h2', '知识图谱'),
      error.value && h('p', { class: 'graph-error', role: 'alert' }, error.value),
      notice.value && h('p', { class: 'graph-notice' }, notice.value),
      !session.value && h('p', '正在加载…'),
      session.value && h('label', { class: 'graph-course' }, ['课程 ',
        h('select', {
          value: selected(courseId.value), disabled: busy.value,
          onChange: event => {
            courseId.value = event.target.value
            rootId.value = ''
            run(loadGraph)
          },
        }, courses.value.map(course => h('option', {
          value: String(course.id), key: course.id,
        }, course.title)))]),
      session.value && nodes().length > 1 && h('label', { class: 'graph-root' }, ['聚焦根 ',
        picker(nodes().map(node => [String(node.id), node.title]), rootId.value,
          value => run(() => setRoot(value)), '全图')]),
      session.value && rootId.value && h('p', { class: 'graph-root-hint' },
        `已聚焦 #${rootId.value} ${titleOf(Number(rootId.value))} 的关联子图。`),
      session.value && teacher() && nodes().length > 1 && edgeFormView(),
      session.value && (!nodes().length
        ? h('p', '课程暂无知识点，请先在知识库中创建。')
        : nodeTable()),
      graph.value && edges().length ? edgeTable() : null,
      focusId.value && focusPanel(),
    ])
  },
}
