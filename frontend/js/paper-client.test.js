import assert from 'node:assert/strict'
import test from 'node:test'
import { PaperClient, paperPayload, pointsValue, publicationPayload } from './paper-client.js'

test('draft payload keeps fixed versions and rejects duplicate identities and invalid precision', () => {
  const form = { title: ' CPU ', kind: 'exam', confidential: true }
  const items = [{ question_id: 1, question_version_id: 8, points: '10.01' }]
  assert.deepEqual(paperPayload(form, items), { title: 'CPU', kind: 'exam', confidential: true,
    items: [{ question_version_id: 8, points: 10.01 }] })
  for (const value of ['', '1e2', '-1', '0', '0.001', 'NaN', 'Infinity', '1.111', true, '9999999999999999']) {
    assert.throws(() => pointsValue(value))
  }
  assert.throws(() => paperPayload(form, [...items, { ...items[0], question_version_id: 9 }]))
})

test('ordinary publication requires ordered times and confidential confirmation', () => {
  const times = { start_at: '2026-10-13T21:00:00+08:00', end_at: '2026-10-13T22:00:00+08:00',
    review_at: '2026-10-13T22:00:00+08:00', confidentiality_note: ' 已确认 ' }
  assert.deepEqual(publicationPayload(times, true), { start_at: '2026-10-13T13:00:00.000Z',
    end_at: '2026-10-13T14:00:00.000Z', review_at: '2026-10-13T14:00:00.000Z', confidentiality_note: '已确认' })
  for (const values of [{ review_at: '' }, { review_at: times.start_at }, { end_at: times.start_at },
    { confidentiality_note: '' }]) assert.throws(() => publicationPayload({ ...times, ...values }, true))
  assert.equal(Object.hasOwn(publicationPayload(times, false), 'confidentiality_note'), false)
})

test('paper client sends CSRF and session changes block publication', async () => {
  let userId = 7
  const calls = []
  const client = new PaperClient(7, async (path, options) => {
    calls.push({ path, options })
    return { ok: true, status: 200, json: async () => ({ data: path.endsWith('/auth/session')
      ? { user: { id: userId }, csrf_token: 'test-token' } : { id: 1 } }) }
  })
  await client.publish(1, { start_at: 't' })
  assert.equal(calls[1].path, '/api/v1/papers/1/publish')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'test-token')
  userId = 8
  await assert.rejects(client.publish(1, {}), /登录状态已变化/)
  assert.equal(calls.filter(item => item.options.method).length, 1)
})
