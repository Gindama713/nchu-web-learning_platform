// 轻量 SVG 图表：零依赖，带入场动画（CSS 驱动，尊重 prefers-reduced-motion）。
// 三种：柱状 barChart、折线 lineChart、环形 donutChart。

const INK = '#182436'
const MUTED = '#60718a'
const GRID = '#e6ecf5'
const ACCENT = '#2f6fd0'

function format(value, unit) {
  if (unit === 'percent') return `${Math.round(value)}%`
  if (unit === 'ratio') return `${Math.round(value * 100)}%`
  return String(Math.round(value))
}

export function lineChart(points, options = {}) {
  const {
    width = 640, height = 200, max = 1, unit = 'ratio',
    color = ACCENT, empty = '本区间没有可画的数据点',
  } = options
  const data = (points ?? []).filter(point => Number.isFinite(point.value))
  if (data.length < 2) return { width, height, empty, nodes: [] }

  const padL = 46, padR = 16, padT = 18, padB = 32
  const innerW = width - padL - padR
  const innerH = height - padT - padB
  const stepX = innerW / (data.length - 1)
  const y = value => padT + innerH - (Math.max(0, Math.min(max, value)) / max) * innerH
  const x = index => padL + index * stepX
  const nodes = []

  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i
    const py = y(value)
    nodes.push({ kind: 'line', x1: padL, y1: py, x2: width - padR, y2: py, stroke: GRID })
    nodes.push({ kind: 'text', x: padL - 9, y: py + 4, text: format(value, unit), size: 10, fill: MUTED, anchor: 'end' })
  }

  const path = data.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.value)}`).join(' ')
  const area = `${path} L ${x(data.length - 1)} ${padT + innerH} L ${padL} ${padT + innerH} Z`
  nodes.push({ kind: 'path', d: area, fill: `${color}12`, stroke: 'none' })
  // pathLength=1 归一化：CSS 用 stroke-dashoffset 1→0 画描边动画，不用测量路径长度
  nodes.push({ kind: 'path', d: path, fill: 'none', stroke: color, width: 2.4, draw: true, 'stroke-linejoin': 'round' })

  data.forEach((point, index) => {
    nodes.push({ kind: 'dot', cx: x(index), cy: y(point.value), r: 4, fill: '#fff', stroke: color, width: 2.4, delay: index })
    nodes.push({ kind: 'text', x: x(index), y: height - 11, text: point.label ?? '', size: 9.5, fill: MUTED, anchor: 'middle' })
    nodes.push({
      kind: 'text', x: x(index), y: y(point.value) - 10, size: 10.5,
      text: format(point.value, unit), fill: color, anchor: 'middle', bold: true,
    })
  })

  return { width, height, empty: '', nodes }
}

export function barChart(series, options = {}) {
  const { width = 660, height = 210, baseColor = '#dbe6f5', fillColor = ACCENT, empty = '本区间没有可画的数据点' } = options
  const data = Array.isArray(series) ? series : []
  if (!data.length) return { width, height, empty, nodes: [] }

  const padL = 42, padR = 14, padT = 18, padB = 32
  const innerW = width - padL - padR
  const innerH = height - padT - padB
  const top = Math.max(1, ...data.map(item => Math.max(item.expected ?? 0, item.present ?? 0)))
  const bandW = innerW / data.length
  const barW = Math.min(44, bandW * 0.46)
  const nodes = []

  for (let i = 0; i <= 4; i += 1) {
    const value = (top / 4) * i
    const py = padT + innerH - (value / top) * innerH
    nodes.push({ kind: 'line', x1: padL, y1: py, x2: width - padR, y2: py, stroke: GRID })
    nodes.push({ kind: 'text', x: padL - 9, y: py + 4, text: String(Math.round(value)), size: 10, fill: MUTED, anchor: 'end' })
  }

  data.forEach((item, index) => {
    const cx = padL + bandW * index + bandW / 2
    const expected = Number(item.expected ?? 0)
    const present = Number(item.present ?? 0)
    const hExpected = (expected / top) * innerH
    const hPresent = (present / top) * innerH
    const baseY = padT + innerH
    nodes.push({
      kind: 'bar', x: cx - barW / 2, y: baseY - hExpected, width: barW,
      height: Math.max(hExpected, 1), fill: baseColor, delay: index, origin: baseY,
    })
    nodes.push({
      kind: 'bar', x: cx - barW / 2, y: baseY - hPresent, width: barW,
      height: Math.max(hPresent, 1), fill: fillColor, delay: index, origin: baseY,
    })
    if (expected > 0) {
      nodes.push({ kind: 'text', x: cx, y: baseY - hExpected - 7, text: `${present}/${expected}`, size: 10.5, fill: INK, anchor: 'middle', bold: true })
    }
    nodes.push({ kind: 'text', x: cx, y: height - 11, text: item.label ?? '', size: 9.5, fill: MUTED, anchor: 'middle' })
  })

  return { width, height, empty: '', nodes }
}

// 环形：扇区用 stroke-dasharray 画；整组旋转入场，扇区错开淡入
export function donutChart(slices, options = {}) {
  const { size = 190, thickness = 24, gap = 2 } = options
  const all = slices ?? []
  const rows = all.filter(slice => Number(slice.value) > 0)
  const total = rows.reduce((sum, slice) => sum + Number(slice.value), 0)
  if (!total) return { size, total: 0, empty: '没有可统计的数据', nodes: [], rows: [] }

  const radius = (size - thickness) / 2 - 2
  const circumference = 2 * Math.PI * radius
  const center = size / 2
  const nodes = []
  let offset = 0

  rows.forEach(slice => {
    const value = Number(slice.value)
    const length = (value / total) * circumference
    nodes.push({
      kind: 'arc',
      cx: center, cy: center, r: radius, thickness, color: slice.color,
      dash: `${Math.max(length - gap, 0.6)} ${circumference}`,
      offset: -offset,
      title: `${slice.label}：${value}（${((value / total) * 100).toFixed(1)}%）`,
    })
    offset += length
  })

  return {
    size, total, nodes, radius, center,
    // 图例保留 0 值项：让「没有迟到 / 没有请假」也能被看见
    rows: all.map(slice => ({
      ...slice,
      percent: ((Number(slice.value) / total) * 100).toFixed(1),
    })),
  }
}

export const chartColors = {
  ACCENT, INK, MUTED, GRID,
  present: '#2e8b57', late: '#f0a500', leave: '#5b8def', absent: '#d94c4c',
  high: '#d94c4c', mid: '#f0a500', low: '#8896aa',
}
