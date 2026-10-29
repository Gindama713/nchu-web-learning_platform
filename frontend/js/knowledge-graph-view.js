// SPEC-015 知识图谱可视化：分层布局、先修箭头、传递闭包与教师建边。
// 图的节点与边全部来自后端 knowledge-graph，前端只做布局与绘制。
import { computed, h, onMounted, reactive, ref } from 'vue'
import { KnowledgeGraphClient, edgeTypes } from './knowledge-graph-client.js'
import { NODE_H, NODE_W, edgePath, layoutGraph, truncate } from './knowledge-graph-layout.js'

const INK = '#182436'
const MUTED = '#60718a'
const LINE = '#9cabc0'
const ACCENT = '#173b6c'
const FOUND = '#fff4d6'
const DONE = '#e6f6ea'

const FILL_BY_TYPE = { prerequisite: '#3a5f8f', contains: '#9cabc0' }

export const KnowledgeGraphView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new KnowledgeGraphClient(props.user.id)
    const isTeacher = () => props.user.role === 'teacher'

    const courses = ref([])
    const courseId = ref('')
    const graph = ref({ nodes: [], edges: [], prerequisite_paths: [], root_id: null })
    const points = ref([])
    const rootId = ref(null)
    const showClosure = ref(false)
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const form = reactive({ sourceId: '', targetId: '', type: 'prerequisite' })

    const laid = computed(() => layoutGraph(graph.value.nodes, graph.value.edges ?? []))
    const stats = computed(() => ({
      nodes: graph.value.nodes?.length ?? 0,
      edges: graph.value.edges?.length ?? 0,
      layers: laid.value.layers,
      foundational: (graph.value.nodes ?? []).filter(node => node.is_foundational).length,
      mastered: (graph.value.nodes ?? []).filter(node => Number(node.mastery) >= 1).length,
    }))

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.status === 401) { courses.value = []; courseId.value = '' }
      } finally { busy.value = false }
    }

    async function loadGraph() {
      graph.value = { nodes: [], edges: [], prerequisite_paths: [] }
      if (!courseId.value) return
      graph.value = await api.graph(courseId.value, rootId.value)
    }

    async function loadPoints() {
      points.value = []
      if (!courseId.value) return
      try { points.value = await api.points(courseId.value) } catch { points.value = [] }
    }

    async function bindCourse() {
      rootId.value = null
      form.sourceId = ''; form.targetId = ''
      if (!courseId.value) { graph.value = { nodes: [], edges: [], prerequisite_paths: [] }; points.value = []; return }
      await loadGraph()
      await loadPoints()
      if (points.value.length) {
        form.sourceId = String(points.value[0].id)
        form.targetId = String((points.value[1] ?? points.value[0]).id)
      }
    }

    async function pick(node) {
      const next = rootId.value === node.id ? null : node.id
      await run(async () => { rootId.value = next; await loadGraph() },
        next ? `只看「${node.title}」的先修相关子图` : '已显示全部知识点')
    }

    async function resetRoot() {
      await run(async () => { rootId.value = null; await loadGraph() }, '已显示全部知识点')
    }

    async function addEdge() {
      await run(async () => {
        await api.addEdge(courseId.value, {
          sourceId: form.sourceId, targetId: form.targetId, type: form.type,
        })
        await loadGraph()
      }, '已添加关系')
    }

    async function boot() {
      courses.value = []
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
      await bindCourse()
    }

    onMounted(() => { boot().catch(failure => { error.value = failure.message }) })

    const tone = node => {
      if (rootId.value === node.id) return 'root'
      if (Number(node.mastery) >= 1) return 'done'
      if (node.is_foundational) return 'found'
      return 'plain'
    }
    const fillOf = node => {
      const kind = tone(node)
      if (kind === 'root') return ACCENT
      if (kind === 'done') return DONE
      if (kind === 'found') return FOUND
      return '#ffffff'
    }
    const textOf = node => (tone(node) === 'root' ? '#ffffff' : INK)

    function renderGraph() {
      const L = laid.value
      if (!L.placed.size) {
        return h('p', { class: 'graph-empty' }, '本课程还没有知识点，先到「章节与知识」建立知识点与先修关系。')
      }
      const nodes = []
      const edges = []

      // 传递闭包（间接先修）：默认关闭，开启后画在最底层虚线
      if (showClosure.value) {
        ;(graph.value.prerequisite_paths ?? []).forEach(pair => {
          const from = L.placed.get(pair.from)
          const to = L.placed.get(pair.to)
          if (!from || !to) return
          edges.push(h('path', {
            d: edgePath(from, to), fill: 'none',
            stroke: '#d7b26a', 'stroke-width': 1, 'stroke-dasharray': '4 5', opacity: 0.75,
          }))
        })
      }

      L.edges.forEach(edge => {
        const from = L.placed.get(edge.source)
        const to = L.placed.get(edge.target)
        if (!from || !to) return
        const color = FILL_BY_TYPE[edge.type] ?? LINE
        edges.push(h('path', {
          d: edgePath(from, to), fill: 'none',
          stroke: color, 'stroke-width': edge.type === 'prerequisite' ? 1.7 : 1.2,
          'stroke-dasharray': edge.type === 'contains' ? '6 4' : undefined,
          'marker-end': `url(#graph-arrow-${edge.type === 'contains' ? 'contains' : 'prereq'})`,
        }))
      })

      graph.value.nodes.forEach(node => {
        const spot = L.placed.get(node.id)
        if (!spot) return
        const isRoot = rootId.value === node.id
        const caption = node.is_foundational ? '基础' : ''
        const done = Number(node.mastery) >= 1
        nodes.push(h('g', {
          class: ['graph-node', tone(node)],
          style: 'cursor:pointer',
          onClick: () => pick(node),
        }, [
          h('title', {}, `${node.title}${node.is_foundational ? '（基础知识点）' : ''}${done ? '（本人已完成）' : ''}${isRoot ? ' — 点击取消筛选' : ' — 点击只看相关子图'}`),
          h('rect', {
            x: spot.x, y: spot.y, width: NODE_W, height: NODE_H, rx: 9,
            fill: fillOf(node),
            stroke: isRoot ? ACCENT : node.is_foundational ? '#d18700' : LINE,
            'stroke-width': isRoot ? 2.2 : 1.2,
          }),
          h('text', {
            x: spot.x + 12, y: spot.y + 21, 'font-size': 12, 'font-weight': 600,
            fill: textOf(node),
          }, truncate(node.title, 9)),
          h('text', {
            x: spot.x + 12, y: spot.y + 37, 'font-size': 10,
            fill: isRoot ? '#c8d8ef' : MUTED,
          }, [caption, done ? '已掌握' : '', isRoot ? '当前根' : ''].filter(Boolean).join(' · ') || `#${node.id}`),
        ]))
      })

      return h('svg', {
        viewBox: `0 0 ${L.width} ${L.height}`,
        width: L.width,
        height: L.height,
        style: `width:${L.width}px;height:${L.height}px;max-width:none;display:block`,
        role: 'img',
        'aria-label': '知识点先修关系图',
      }, [
        h('defs', {}, [
          h('marker', {
            id: 'graph-arrow-prereq', viewBox: '0 0 10 10', refX: '9', refY: '5',
            markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse',
          }, [h('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: FILL_BY_TYPE.prerequisite })]),
          h('marker', {
            id: 'graph-arrow-contains', viewBox: '0 0 10 10', refX: '9', refY: '5',
            markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse',
          }, [h('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: FILL_BY_TYPE.contains })]),
        ]),
        ...edges,
        ...nodes,
      ])
    }

    return () => {
      const teacher = isTeacher()
      return h('section', { class: 'card graph-card' }, [
        h('h2', {}, '知识图谱'),
        h('p', {}, '按先修关系自动分层：左边是前置知识，箭头指向后继。点任意知识点只看它相关的子图，再点一次取消。'),

        h('div', { class: 'inline-form' }, [
          h('label', {}, ['课程', h('select', {
            value: courseId.value,
            onChange: event => {
              courseId.value = event.target.value
              run(bindCourse).catch(() => {})
            },
          }, courses.value.map(course => h('option', { value: String(course.id) }, course.title ?? `课程 ${course.id}`)))]),
          h('button', {
            type: 'button', class: 'secondary', disabled: busy.value || rootId.value === null,
            onClick: () => run(resetRoot),
          }, '显示全部'),
          h('button', {
            type: 'button', class: 'secondary',
            onClick: () => { showClosure.value = !showClosure.value },
          }, showClosure.value ? '隐藏传递关系' : '显示传递关系'),
        ]),

        error.value && h('p', { class: 'graph-alert', role: 'alert' }, error.value),
        notice.value && h('p', { class: 'graph-notice', role: 'status' }, notice.value),

        h('p', { class: 'graph-stats' },
          `${stats.value.nodes} 个知识点 · ${stats.value.edges} 条关系 · ${stats.value.layers} 层 · 基础 ${stats.value.foundational} 个 · 本人已掌握 ${stats.value.mastered} 个`),

        h('div', { class: 'graph-canvas' }, [renderGraph()]),

        h('div', { class: 'graph-legend' }, [
          h('span', {}, [h('i', { class: 'sw found' }), '基础知识点']),
          h('span', {}, [h('i', { class: 'sw done' }), '本人已完成']),
          h('span', {}, [h('i', { class: 'sw line solid' }), '先修']),
          h('span', {}, [h('i', { class: 'sw line dashed' }), '包含']),
          showClosure.value && h('span', {}, [h('i', { class: 'sw line closure' }), '间接先修（传递）']),
          laid.value.hasCycle && h('span', { class: 'graph-warn' }, '检测到环路，已把涉及的知识点压到末层显示'),
        ]),

        teacher && h('div', { class: 'graph-editor' }, [
          h('h3', {}, '添加关系'),
          points.value.length < 2
            ? h('p', { class: 'graph-empty' }, '至少需要两个知识点才能建立关系。')
            : h('div', { class: 'inline-form' }, [
              h('label', {}, ['前置 / 起点', h('select', {
                value: form.sourceId,
                onChange: event => { form.sourceId = event.target.value },
              }, points.value.map(point => h('option', { value: String(point.id) }, `${point.id} · ${point.title}`)))]),
              h('label', {}, ['后继 / 终点', h('select', {
                value: form.targetId,
                onChange: event => { form.targetId = event.target.value },
              }, points.value.map(point => h('option', { value: String(point.id) }, `${point.id} · ${point.title}`)))]),
              h('label', {}, ['关系', h('select', {
                value: form.type,
                onChange: event => { form.type = event.target.value },
              }, Object.entries(edgeTypes).map(([key, name]) => h('option', { value: key }, name)))]),
              h('button', { type: 'button', disabled: busy.value, onClick: () => run(addEdge) }, '添加'),
            ]),
          h('p', { class: 'graph-hint' }, '先修关系不允许成环，也不允许跨课程；重复添加同一条关系不会重复写入。'),
        ]),
      ])
    }
  },
}
