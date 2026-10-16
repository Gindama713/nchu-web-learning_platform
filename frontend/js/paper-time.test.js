import assert from 'node:assert/strict'
import test from 'node:test'
import { paperTime } from './paper-time.js'

test('paper UTC Sunday crosses Shanghai day/week and midnight is 00, with no source mutation', () => {
  const raw = Object.freeze({ start_at: '2026-10-18T15:59:59.000Z', end_at: '2026-10-18T16:00:00.000Z' })
  const before = JSON.stringify(raw)
  assert.equal(paperTime(raw.start_at), '2026-10-18 23:59:59 (Asia/Shanghai)')
  assert.equal(paperTime(raw.end_at), '2026-10-19 00:00:00 (Asia/Shanghai)')
  assert.equal(paperTime('2026-10-19T00:00:00+08:00'), paperTime(raw.end_at))
  assert.equal(JSON.stringify(raw), before)
})

test('paper empty and malformed timestamps do not become epoch or browser-local dates', () => {
  for (const value of [null, undefined, '']) {
    assert.equal(paperTime(value), '—')
    assert.equal(paperTime(value, '待教师讲评'), '待教师讲评')
  }
  for (const value of ['bad', '2026-10-19T00:00:00', '2026-02-30T00:00:00Z', '2026-13-01T00:00:00Z', 0, {}, '2026-10-18T25:00:00Z']) {
    assert.equal(paperTime(value), '时间异常')
  }
})
