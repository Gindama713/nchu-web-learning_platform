// SPEC-015 布局纯函数测试：分层、坐标、边界。
import assert from 'node:assert/strict'
import test from 'node:test'
import { NODE_H, NODE_W, edgePath, layoutGraph, truncate } from './knowledge-graph-layout.js'

const node = (id, title = `K${id}`) => ({ id, title, is_foundational: false, mastery: 0 })
const edge = (source, target, type = 'prerequisite') => ({ source, target, type })

test('线性先修链按层递增', () => {
  const { placed, layers } = layoutGraph([node(1), node(2), node(3)], [edge(1, 2), edge(2, 3)])
  assert.equal(layers, 3)
  assert.equal(placed.get(1).layer, 0)
  assert.equal(placed.get(2).layer, 1)
  assert.equal(placed.get(3).layer, 2)
  assert.ok(placed.get(2).x > placed.get(1).x)
  assert.ok(placed.get(3).x > placed.get(2).x)
})

test('菱形依赖把汇合点放在最长路径层', () => {
  const edges = [edge(1, 2), edge(1, 3), edge(2, 4), edge(3, 4)]
  const { placed, layers } = layoutGraph([node(1), node(2), node(3), node(4)], edges)
  assert.equal(layers, 3)
  assert.equal(placed.get(4).layer, 2)
  assert.equal(placed.get(2).layer, 1)
  assert.equal(placed.get(3).layer, 1)
})

test('同层节点纵向错开且不重叠', () => {
  const { placed } = layoutGraph([node(1), node(2), node(3)], [edge(1, 2), edge(1, 3)])
  const a = placed.get(2)
  const b = placed.get(3)
  assert.equal(a.x, b.x)
  assert.ok(Math.abs(a.y - b.y) >= NODE_H)
})

test('孤立节点保留在第 0 层', () => {
  const { placed, layers } = layoutGraph([node(1), node(9)], [])
  assert.equal(layers, 1)
  assert.equal(placed.get(9).layer, 0)
  assert.ok(placed.has(9))
})

test('成环时节点不丢，标记 hasCycle', () => {
  const { placed, hasCycle } = layoutGraph([node(1), node(2)], [edge(1, 2), edge(2, 1)])
  assert.equal(hasCycle, true)
  assert.ok(placed.has(1))
  assert.ok(placed.has(2))
})

test('指向图外节点的边被忽略', () => {
  const { edges } = layoutGraph([node(1)], [edge(1, 99)])
  assert.equal(edges.length, 0)
})

test('画布尺寸能容纳所有节点', () => {
  const nodes = [node(1), node(2), node(3)]
  const { width, height, placed } = layoutGraph(nodes, [edge(1, 2), edge(1, 3)])
  nodes.forEach(n => {
    const spot = placed.get(n.id)
    assert.ok(spot.x + NODE_W <= width)
    assert.ok(spot.y + NODE_H <= height)
  })
})

test('边路径从右缘出发、左缘收口', () => {
  const path = edgePath({ x: 0, y: 0 }, { x: 300, y: 100 })
  assert.match(path, new RegExp(`^M ${NODE_W} ${NODE_H / 2} C `))
  assert.match(path, new RegExp(`300 ${100 + NODE_H / 2}$`))
})

test('标题截断保留省略号', () => {
  assert.equal(truncate('短标题'), '短标题')
  assert.equal(truncate('这是一个非常非常长的知识点标题', 8), '这是一个非常非常…')
})
