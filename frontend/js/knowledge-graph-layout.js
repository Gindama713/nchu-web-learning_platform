// SPEC-015 知识图谱分层布局：按先修关系做最长路径分层，同层纵向居中。
// 纯函数，不碰 DOM，便于单测。

export const NODE_W = 140
export const NODE_H = 46
const GAP_X = 48
const GAP_Y = 28
const PAD = 24

export function layoutGraph(nodes, edges) {
  const byId = new Map(nodes.map(node => [node.id, node]))
  const indeg = new Map(nodes.map(node => [node.id, 0]))
  const out = new Map(nodes.map(node => [node.id, []]))

  const usable = edges.filter(edge => byId.has(edge.source) && byId.has(edge.target))
  usable.forEach(edge => {
    out.get(edge.source).push(edge.target)
    indeg.set(edge.target, indeg.get(edge.target) + 1)
  })

  const layer = new Map(nodes.map(node => [node.id, 0]))
  const remaining = new Map(indeg)
  const queue = nodes.filter(node => indeg.get(node.id) === 0).map(node => node.id)
  const settled = new Set()

  while (queue.length) {
    const id = queue.shift()
    settled.add(id)
    out.get(id).forEach(target => {
      layer.set(target, Math.max(layer.get(target), layer.get(id) + 1))
      remaining.set(target, remaining.get(target) - 1)
      if (remaining.get(target) === 0) queue.push(target)
    })
  }

  // 理论上后端拒绝成环；真有环时把剩余节点压到最后一层，不丢节点。
  const orphans = nodes.filter(node => !settled.has(node.id))
  if (orphans.length) {
    const last = Math.max(0, ...nodes.filter(n => settled.has(n.id)).map(n => layer.get(n.id))) + 1
    orphans.forEach(node => layer.set(node.id, last))
  }

  const columns = new Map()
  nodes.forEach(node => {
    const index = layer.get(node.id) ?? 0
    if (!columns.has(index)) columns.set(index, [])
    columns.get(index).push(node)
  })
  const layerCount = columns.size ? Math.max(...columns.keys()) + 1 : 0
  const tallest = columns.size ? Math.max(...[...columns.values()].map(list => list.length)) : 0

  const width = PAD * 2 + layerCount * NODE_W + Math.max(0, layerCount - 1) * GAP_X
  const height = PAD * 2 + Math.max(1, tallest) * (NODE_H + GAP_Y) - GAP_Y

  const placed = new Map()
  ;[...columns.keys()].sort((a, b) => a - b).forEach(index => {
    const list = columns.get(index)
    const blockHeight = list.length * NODE_H + (list.length - 1) * GAP_Y
    const startY = (height - blockHeight) / 2
    list.forEach((node, row) => {
      placed.set(node.id, {
        x: PAD + index * (NODE_W + GAP_X),
        y: startY + row * (NODE_H + GAP_Y),
        layer: index,
      })
    })
  })

  return {
    width: Math.max(width, NODE_W + PAD * 2),
    height: Math.max(height, NODE_H + PAD * 2),
    placed,
    layers: layerCount,
    edges: usable,
    hasCycle: orphans.length > 0,
  }
}

// 三次贝塞尔：从源节点右缘到目标节点左缘，控制点横向外推，避免压住中间节点。
export function edgePath(from, to) {
  const x1 = from.x + NODE_W
  const y1 = from.y + NODE_H / 2
  const x2 = to.x
  const y2 = to.y + NODE_H / 2
  const bend = Math.max(36, Math.abs(x2 - x1) / 2)
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
}

export function truncate(text, limit = 14) {
  const value = String(text ?? '')
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}
