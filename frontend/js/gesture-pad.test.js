// 手势画布的两个纯函数：命中判定与折线点串。DOM 事件换算不在这里测。
import assert from 'node:assert/strict'
import test from 'node:test'

import { padHitTest, padPoints } from './gesture-pad.js'

test('九个点按三行三列排布，坐标落在 60/150/240', () => {
  assert.equal(padPoints([0]), '60,60')
  assert.equal(padPoints([4]), '150,150')
  assert.equal(padPoints([8]), '240,240')
  assert.equal(padPoints([0, 1, 2]), '60,60 150,60 240,60')
})

test('点在半径内命中，取最近的一个', () => {
  assert.equal(padHitTest({ x: 60, y: 60 }), 0)
  assert.equal(padHitTest({ x: 64, y: 58 }), 0)      // 偏差 4，命中左上
  assert.equal(padHitTest({ x: 146, y: 152 }), 4)    // 接近中心点
  assert.equal(padHitTest({ x: 238, y: 242 }), 8)    // 右下
})

test('远离所有点返回 -1，不会误判到最近的格点', () => {
  assert.equal(padHitTest({ x: -100, y: -100 }), -1)
  assert.equal(padHitTest({ x: 150, y: 30 }), 1)      // 距上中点 (150,60) 30，仍在 34 命中半径内
  assert.equal(padHitTest({ x: 150, y: 10 }), -1)     // 距上中点 50，超出半径
  assert.equal(padHitTest({ x: 300, y: 300 }), -1)
})

test('空图案不产生折线点串', () => {
  assert.equal(padPoints([]), '')
  assert.equal(padPoints(), '')
})
