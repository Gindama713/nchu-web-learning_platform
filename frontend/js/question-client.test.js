import assert from 'node:assert/strict'
import test from 'node:test'
import { emptyQuestion, QuestionClient, questionPayload } from './question-client.js'

const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('question writes revalidate identity and use the freshly issued CSRF token', async () => {
  const calls = []
  const client = new QuestionClient(7, async (path, options) => {
    calls.push({ path, options })
    return reply({ data: path.endsWith('/auth/session')
      ? { user: { id: 7 }, csrf_token: 'fresh' } : { id: 1, version_id: 2 } })
  })
  assert.equal((await client.update(1, { answer: false })).version_id, 2)
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh')
  assert.equal(calls[1].options.credentials, 'same-origin')
  assert.deepEqual(JSON.parse(calls[1].options.body), { answer: false })
  for (const session of [{ user: { id: 8 }, csrf_token: 'token' }, { user: { id: 7 } }]) {
    let sent = 0
    const changed = new QuestionClient(7, async () => { sent++; return reply({ data: session }) })
    await assert.rejects(changed.create(1, {}), error => error.status === 401)
    assert.equal(sent, 1)
  }
})

test('question list encodes independent filters and retains total and page', async () => {
  let path
  const client = new QuestionClient(7, async url => {
    path = url
    return reply({ data: [], page: 2, page_size: 20, total: 25 })
  })
  assert.equal((await client.list(3, { page: 2, type: 'numeric', difficulty: 'hard', knowledgeId: 11 })).total, 25)
  const params = new globalThis.URLSearchParams(path.split('?')[1])
  assert.equal(params.get('knowledge_id'), '11')
  assert.equal(params.get('type'), 'numeric')
  assert.equal(params.get('page'), '2')
})

test('all knowledge tags are collected across pages and inconsistent sets are rejected', async () => {
  const first = Array.from({ length: 100 }, (_, index) => ({ id: index + 1 }))
  const client = new QuestionClient(7, async path => reply({ data: path.includes('page=1&') ? first : [{ id: 101 }], total: 101 }))
  assert.equal((await client.knowledge(3)).length, 101)
  for (const second of [{ data: [], total: 101 }, { data: [{ id: 100 }], total: 101 }, { data: [{ id: 101 }], total: 102 }]) {
    const bad = new QuestionClient(7, async path => reply(path.includes('page=1&') ? { data: first, total: 101 } : second))
    await assert.rejects(bad.knowledge(3))
  }
})

test('dependency errors and malformed responses are not successful empty lists', async () => {
  const unavailable = new QuestionClient(7, async () => reply({ error: { code: 'DEPENDENCY_UNAVAILABLE', message: '知识未接入' } }, 503))
  await assert.rejects(unavailable.knowledge(3), error => error.status === 503 && error.code === 'DEPENDENCY_UNAVAILABLE')
  const malformed = new QuestionClient(7, async () => ({ status: 503, json: async () => { throw new Error('HTML') } }))
  await assert.rejects(malformed.list(3), error => error.status === 503)
})

test('numeric form values become finite JSON numbers without turning blank input into zero', () => {
  const form = { ...emptyQuestion('numeric'), answer: ' -1.25 ', tolerance: '0.1' }
  const payload = questionPayload(form)
  assert.equal(payload.answer, -1.25)
  assert.equal(payload.tolerance, 0.1)
  assert.equal(form.answer, ' -1.25 ')
  for (const answer of ['', ' ', 'NaN', 'Infinity', '1e9999']) {
    assert.throws(() => questionPayload({ ...form, answer }))
  }
  assert.throws(() => questionPayload({ ...form, tolerance: '-1' }))
  assert.equal(questionPayload(emptyQuestion('boolean')).answer, true)
  assert.deepEqual(questionPayload(emptyQuestion('multiple')).answer, [])
})
