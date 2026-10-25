import assert from 'node:assert/strict'
import test from 'node:test'
import { AttemptClient, answerPayload, scorePayload } from './attempt-client.js'

test('five answer types preserve false, blank numeric and selected keys', () => {
  const items = ['single', 'multiple', 'boolean', 'numeric', 'short'].map((type, index) => ({ type, question_version_id: index + 1 }))
  assert.deepEqual(answerPayload(items, { 1: 'A', 2: ['B', 'A'], 3: false, 4: '', 5: '  原文  ' }).answers.map(a => a.value),
    ['A', ['B', 'A'], false, null, '  原文  '])
  assert.equal(answerPayload([items[3]], { 4: '0' }).answers[0].value, 0)
  assert.throws(() => answerPayload([items[3]], { 4: 'Infinity' }))
})

test('manual score client preserves zero and old revision without rounding', () => {
  const draft = { question_version_id: 2, score: '0', comment: '', include: true, max_score: 1.01 }
  assert.deepEqual(scorePayload(3, [draft]), { revision: 3, items: [{ question_version_id: 2, score: 0, comment: '' }] })
  for (const score of ['', '-1', '0.001', '1.02', 'Infinity']) assert.throws(() => scorePayload(3, [{ ...draft, score }]))
  assert.throws(() => scorePayload(3, [{ ...draft, include: false }]))
})

test('submit rechecks session and sends explicit stable idempotency key; role change refuses write', async () => {
  const requests = []
  let role = 'student'
  const api = new AttemptClient({ id: 7, role }, async (path, options) => {
    requests.push({ path, options })
    return { ok: true, json: async () => ({ data: path.endsWith('/session')
      ? { user: { id: 7, role }, csrf_token: 'fresh' } : { id: 9 } }) }
  })
  await api.submit(3, { answers: [] }, 'same-key')
  assert.equal(requests[1].options.headers['Idempotency-Key'], 'same-key')
  assert.equal(requests[1].options.headers['X-CSRF-Token'], 'fresh')
  role = 'teacher'
  await assert.rejects(api.submit(3, { answers: [] }, 'same-key'), /角色已变化/)
  assert.equal(requests.length, 3)
})
