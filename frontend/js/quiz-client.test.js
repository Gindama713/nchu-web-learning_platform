import assert from 'node:assert/strict'
import test from 'node:test'
import { QuizClient } from './quiz-client.js'
import { publicationPayload } from './paper-client.js'

test('dedicated quiz publication omits review time and preserves confidential confirmation', () => {
  const form = { start_at: '2026-10-13T21:00:00+08:00', end_at: '2026-10-13T22:00:00+08:00',
    review_at: '', confidentiality_note: ' 已确认 ' }
  const payload = publicationPayload(form, true, true)
  assert.deepEqual(payload, { start_at: '2026-10-13T13:00:00.000Z', end_at: '2026-10-13T14:00:00.000Z',
    confidentiality_note: '已确认' })
  assert.throws(() => publicationPayload({ ...form, end_at: form.start_at }, true, true))
  assert.throws(() => publicationPayload({ ...form, confidentiality_note: '' }, true, true))
  assert.throws(() => publicationPayload({ ...form, start_at: '' }, false, true))
})

test('quiz list and publication use dedicated endpoints then read the original paper', async () => {
  let userId = 7
  const calls = []
  const api = new QuizClient(7, async (path, options) => {
    calls.push({ path, options })
    return { ok: true, status: 200, json: async () => ({ data: path.endsWith('/auth/session')
      ? { user: { id: userId }, csrf_token: 'fresh' } : { id: 3, kind: 'quiz', review_at: null } }) }
  })
  await api.list(1, { status: 'published', kind: 'exam', page: 2 })
  assert.equal(calls[0].path, '/api/v1/courses/1/quizzes?page=2&page_size=20&status=published')
  const payload = { start_at: 'start', end_at: 'end' }
  const paper = await api.publish(3, payload, 1)
  assert.equal(paper.review_at, null)
  assert.equal(calls[2].path, '/api/v1/courses/1/quizzes')
  assert.equal(calls[2].options.headers['X-CSRF-Token'], 'fresh')
  assert.deepEqual(JSON.parse(calls[2].options.body), { paper_id: 3, ...payload })
  assert.equal(calls[3].path, '/api/v1/papers/3')
  userId = 8
  await assert.rejects(api.publish(3, payload, 1), /登录状态已变化/)
  assert.equal(calls.filter(item => item.options.method).length, 1)
})
