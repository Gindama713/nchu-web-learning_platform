// 轻量 SVG 图表：不引第三方库，保证离线可跑、体积为零。
// 只做本项目需要的两种：折线（趋势）与条形（分布）。

const INK = '#182436'
const MUTED = '#60718a'
const GRID = '#e6edf6'
const ACCENT = '#173b6c'
const SIGNAL = '#d18700'

export function lineChart(points, options = {}) {
  const {
    width = 620, height = 190, max = 1, unit = 'ratio',
    color = ACCENT, empty = '本区间没有可画的数据点',
  } = options
  const data = (points ?? []).filter(point => Number.isFinite(point.value))
  if (data.length < 2) {
    return { width, height, empty, nodes: [] }
  }
  const padL = 44, padR = 14, padT = 14, padB = 30
  const innerW = width - padL - padR
  const innerH = height - padT - padB
  const stepX = data.length > 1 ? innerW / (data.length - 1) : 0
  const y = value => padT + innerH - (Math.max(0, Math.min(max, value)) / max) * innerH
  const x = index => padL + index * stepX

  const nodes = []
  // 网格与 y 轴刻度
  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i
    const py = y(value)
    nodes.push({ kind: 'line', x1: padL, y1: py, x2: width - padR, y2: py, stroke: GRID })
    nodes.push({ kind: 'text', x: padL - 8, y: py + 4, text: format(value, unit), size: 10, fill: MUTED, anchor: 'end' })
  }

  const path = data.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.value)}`).join(' ')
  const area = `${path} L ${x(data.length - 1)} ${padT + innerH} L ${padL} ${padT + innerH} Z`
  nodes.push({ kind: 'path', d: area, fill: `${color}14`, stroke: 'none' })
  nodes.push({ kind: 'path', d: path, fill: 'none', stroke: color, width: 2, 'stroke-linejoin': 'round' })

  data.forEach((point, index) => {
    nodes.push({ kind: 'circle', cx: x(index), cy: y(point.value), r: 3.5, fill: '#fff', stroke: color, width: 2 })
    nodes.push({ kind: 'text', x: x(index), y: height - 10, text: point.label ?? '', size: 9, fill: MUTED, anchor: 'middle' })
    nodes.push({ kind: 'text', x: x(index), y: y(point.value) - 8, text: format(point.value, unit), size: 10, fill: color, anchor: 'middle', bold: true })
  })

  return { width, height, empty: '', nodes }
}

function format(value, unit) {
  if (unit === 'percent') return `${Math.round(value)}%`
  if (unit === 'ratio') return `${Math.round(value * 100)}%`
  return String(Math.round(value))
}

export function barRows(items, options = {}) {
  const { total = null, unit = 'count' } = options
  const rows = items ?? []
  const sum = total ?? rows.reduce((acc, item) => acc + item.value, 0)
  return { rows, sum, unit }
}

export const chartColors = { ACCENT, SIGNAL, INK, MUTED, GRID }

// 双色柱：浅色=应到人次，深色=实际到勤，空周也保留一列，避免"只有一周有数据"时图是空的。
export function barChart(series, options = {}) {
  const {
    width = 620, height = 200, legends = ['应到', '到勤'],
    baseColor = '#dbe6f5', fillColor = '#173b6c', empty = '本区间没有可画的数据点',
  } = options
  const data = Array.isArray(series) ? series : []
  if (!data.length) return { width, height, empty, nodes: [] }
  const padL = 40, padR = 12, padT = 16, padB = 30
  const innerW = width - padL - padR
  const innerH = height - padT - padB
  const top = Math.max(1, ...data.map(item => Math.max(item.expected ?? 0, item.present ?? 0)))
  const bandW = innerW / data.length
  const barW = Math.min(46, bandW * 0.46)
  const nodes = []

  for (let i = 0; i <= 4; i += 1) {
    const value = (top / 4) * i
    const py = padT + innerH - (value / top) * innerH
    nodes.push({ kind: 'line', x1: padL, y1: py, x2: width - padR, y2: py, stroke: GRID })
    nodes.push({ kind: 'text', x: padL - 8, y: py + 4, text: String(Math.round(value)), size: 10, fill: MUTED, anchor: 'end' })
  }

  data.forEach((item, index) => {
    const cx = padL + bandW * index + bandW / 2
    const expected = Number(item.expected ?? 0)
    const present = Number(item.present ?? 0)
    const hExpected = (expected / top) * innerH
    const hPresent = (present / top) * innerH
    const baseY = padT + innerH
    nodes.push({ kind: 'rect', x: cx - barW / 2, y: baseY - hExpected, width: barW, height: Math.max(hExpected, 0.5), fill: baseColor })
    nodes.push({ kind: 'rect', x: cx - barW / 2, y: baseY - hPresent, width: barW, height: Math.max(hPresent, 0.5), fill: fillColor })
    if (expected > 0) {
      nodes.push({ kind: 'text', x: cx, y: baseY - hExpected - 6, text: `${present}/${expected}`, size: 10, fill: INK, anchor: 'middle', bold: true })
    }
    nodes.push({ kind: 'text', x: cx, y: height - 10, text: item.label ?? '', size: 9, fill: MUTED, anchor: 'middle' })
  })

  return { width, height, empty: '', nodes, legends, baseColor, fillColor }
}
