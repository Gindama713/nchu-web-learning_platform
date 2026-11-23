// 图表的几何计算是纯函数，这里锁住比例、空态和配色回退——
// 教学助手的「图」和统计页共用同一份，改坏了这边先红。
import assert from 'node:assert/strict'
import test from 'node:test'

import { barChart, chartColorOf, chartColors, chartNode, donutChart, lineChart, rankChart } from './charts.js'

test('条形、柱状与折线悬停显示完整标签和原始值', () => {
  const rank = rankChart([{ label: '一二三四五六七八九十十一十二', value: 125 }])
  const bar = rank.nodes.find(node => node.class === 'chart-hbar')
  assert.equal(chartNode(bar).children[0].children, '一二三四五六七八九十十一十二：125%')
  const columns = barChart([{ label: '11-23', expected: 10, present: 8 }])
  assert.equal(chartNode(columns.nodes.find(node => node.kind === 'bar' && node.title.includes('到勤'))).children[0].children, '11-23 到勤：8 / 10')
  const line = lineChart([{ label: '11-16', value: 0.5 }, { label: '11-23', value: 0.8 }])
  assert.equal(chartNode(line.nodes.find(node => node.kind === 'dot')).children[0].children, '11-16：50%')
})

test('横向条形按 max 归一：满值占满轨道，短板按比例', () => {
  const chart = rankChart([
    { label: '定点数与补码表示', value: 50, color: '#111' },
    { label: 'ALU 的运算选择', value: 100, color: '#222' },
  ], { max: 100, width: 620 })
  const bars = chart.nodes.filter(node => node.class === 'chart-hbar')
  const track = chart.nodes.find(node => node.kind === 'rect' && !node.class)
  assert.equal(bars.length, 2)
  assert.equal(bars[1].width, track.width)
  assert.equal(bars[0].width, track.width / 2)
  assert.ok(chart.height > 0)
})

test('横向条形：空输入、null、非数字都不画', () => {
  assert.equal(rankChart([]).empty, '没有可比较的数据')
  assert.equal(rankChart([{ label: 'x', value: null }]).empty, '没有可比较的数据')
  assert.equal(rankChart([{ label: 'x', value: undefined }]).empty, '没有可比较的数据')
  assert.equal(rankChart([{ label: 'x', value: Number.NaN }]).empty, '没有可比较的数据')
})

test('横向条形：0 值保留一根 1px 的条，标签过长截断', () => {
  const chart = rankChart([{ label: '一二三四五六七八九十十一十二', value: 0 }])
  const bar = chart.nodes.find(node => node.class === 'chart-hbar')
  const label = chart.nodes.find(node => node.kind === 'text')
  assert.equal(bar.width, 1)
  assert.match(label.text, /…$/)
})

test('环形：total 只累加正值，0 值项仍留在图例里', () => {
  const chart = donutChart([
    { label: '出勤', value: 3, color: '#2e8b57' },
    { label: '迟到', value: 0, color: '#f0a500' },
  ], { size: 152 })
  assert.equal(chart.total, 3)
  assert.equal(chart.rows.length, 2)
  assert.equal(chart.rows[1].percent, '0.0')
  assert.equal(donutChart([{ label: 'x', value: 0 }]).total, 0)
})

test('折线少于 2 个点直接给空态，不画半截趋势', () => {
  assert.equal(lineChart([{ label: '11-02', value: 0.3 }]).empty !== '', true)
  const chart = lineChart([{ label: '11-02', value: 0.3 }, { label: '11-09', value: 0.5 }])
  assert.equal(chart.empty, '')
  assert.ok(chart.nodes.some(node => node.kind === 'path' && node.draw))
})

test('colorKey 未知时回退主题色，不抛错也不画黑', () => {
  assert.equal(chartColorOf('present'), chartColors.present)
  assert.equal(chartColorOf('没有这个键'), chartColors.ACCENT)
})
