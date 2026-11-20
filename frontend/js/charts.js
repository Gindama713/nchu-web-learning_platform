// 轻量 SVG 图表：零依赖，带入场动画（CSS 驱动，尊重 prefers-reduced-motion）。
// 四种：柱状 barChart、横向条 rankChart、折线 lineChart、环形 donutChart。
// 这里只算几何，不碰业务数据；chartNode 负责把几何节点转成 Vue 元素。

import { h } from 'vue'

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

// 横向条形：中文知识点名很长，竖排柱状图放不下，这里标签在左、条在右。
// 值按 max 归一（掌握度/百分比传 100），不足一个像素的条也留 1px，避免「有数据但看不见」。
export function rankChart(items, options = {}) {
  const {
    width = 660, max = 100, unit = 'percent', labelWidth = 186,
    rowHeight = 34, barHeight = 12, gap = 10, suffix = '',
  } = options
  const data = (items ?? []).filter(item => item.value !== null && item.value !== undefined
    && Number.isFinite(Number(item.value)))
  if (!data.length) return { width, height: 0, empty: '没有可比较的数据', nodes: [] }

  const height = data.length * rowHeight + gap
  const trackX = labelWidth
  const valueWidth = 54
  const trackW = Math.max(40, width - trackX - valueWidth)
  const top = Math.max(1, Number(max) || 1)
  const nodes = []

  data.forEach((item, index) => {
    const value = Math.max(0, Math.min(top, Number(item.value)))
    const rowTop = index * rowHeight
    const barY = rowTop + (rowHeight - barHeight) / 2
    const barW = Math.max(1, (value / top) * trackW)
    const label = String(item.label ?? '')
    nodes.push({
      kind: 'text', x: trackX - 12, y: barY + barHeight * 0.78, anchor: 'end',
      text: label.length > 11 ? label.slice(0, 10) + '…' : label, size: 11, fill: INK,
    })
    nodes.push({ kind: 'rect', x: trackX, y: barY, width: trackW, height: barHeight, rx: barHeight / 2, fill: '#eef2f8' })
    nodes.push({
      kind: 'rect', x: trackX, y: barY, width: barW, height: barHeight, rx: barHeight / 2,
      fill: item.color ?? ACCENT, class: 'chart-hbar', style: `animation-delay:${index * 60}ms`,
    })
    nodes.push({
      kind: 'text', x: trackX + trackW + 10, y: barY + barHeight * 0.78, anchor: 'start',
      text: `${format(value, unit)}${suffix}`, size: 11, fill: MUTED, bold: true,
    })
  })

  return { width, height, empty: '', nodes }
}

// 几何节点 → Vue 元素。统计页和教学助手共用这一份，避免两处画出不同的图。
export function chartNode(node) {
  if (node.kind === 'line') return h('line', { x1: node.x1, y1: node.y1, x2: node.x2, y2: node.y2, stroke: node.stroke })
  if (node.kind === 'path') return h('path', {
    d: node.d, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width ?? 1,
    'stroke-linejoin': node['stroke-linejoin'],
    class: node.draw ? 'chart-line' : undefined,
    pathLength: node.draw ? 1 : undefined,
  })
  if (node.kind === 'bar') return h('rect', {
    x: node.x, y: node.y, width: node.width, height: node.height, fill: node.fill, rx: 3,
    class: 'chart-bar', style: `animation-delay:${(node.delay ?? 0) * 70}ms`,
  })
  if (node.kind === 'dot') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width,
    class: 'chart-dot', style: `animation-delay:${560 + (node.delay ?? 0) * 70}ms`,
  })
  if (node.kind === 'arc') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: 'none', stroke: node.color,
    'stroke-width': node.thickness, 'stroke-dasharray': node.dash, 'stroke-dashoffset': node.offset,
    transform: `rotate(-90 ${node.cx} ${node.cy})`, class: 'chart-arc',
  }, [h('title', {}, node.title)])
  if (node.kind === 'rect') return h('rect', {
    x: node.x, y: node.y, width: node.width, height: node.height, fill: node.fill, rx: node.rx,
    class: node.class, style: node.style,
  })
  if (node.kind === 'circle') return h('circle', {
    cx: node.cx, cy: node.cy, r: node.r, fill: node.fill, stroke: node.stroke, 'stroke-width': node.width,
  })
  return h('text', {
    x: node.x, y: node.y, 'font-size': node.size, fill: node.fill,
    'text-anchor': node.anchor, 'font-weight': node.bold ? 700 : 400,
  }, node.text)
}

export const chartColors = {
  ACCENT, INK, MUTED, GRID,
  present: '#2e8b57', late: '#f0a500', leave: '#5b8def', absent: '#d94c4c',
  high: '#d94c4c', mid: '#f0a500', low: '#8896aa',
  ok: '#2e8b57', warn: '#f0a500', danger: '#d94c4c', track: '#eef2f8', accent: ACCENT,
}

// 后端只给 colorKey，配色留在前端一处维护：换主题不会出现「统计页绿、助手页蓝」。
export const chartColorOf = key => chartColors[key] ?? chartColors.ACCENT
