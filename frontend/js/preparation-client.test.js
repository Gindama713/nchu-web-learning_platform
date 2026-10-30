// HTTP test doubles verify client behavior, not real login or browser acceptance.
import assert from 'node:assert/strict'
import test from 'node:test'
import { PreparationClient } from './preparation-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })
const session = () => response({ data: { user: { id: 4 }, csrf_token: 'token' } })

test('create posts link arrays with CSRF and returns the draft', async () => {
  const calls = []
  const client = new PreparationClient(async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/session')) return session()
    return response({ data: { id: 9, status: 'draft' } }, 201)
  })
  client.userId = 4
  const data = await client.create(3, {
    title: '第 3 讲', knowledge_ids: [5], resource_version_ids: [],
    question_version_ids: [11, 12], quiz_ids: [7], scheduled_at: '2026-11-02T08:00:00Z',
  })
  assert.equal(data.id, 9)
  assert.equal(calls[1].url, '/api/v1/courses/3/preparations')
  assert.equal(calls[1].options.method, 'POST')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'token')
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    title: '第 3 讲', knowledge_ids: [5], resource_version_ids: [],
    question_version_ids: [11, 12], quiz_ids: [7], scheduled_at: '2026-11-02T08:00:00Z',
  })
})

test('publish omits replaces_id unless provided', async () => {
  const posts = []
  const client = new PreparationClient(async (url, options) => {
    if (url.endsWith('/auth/session')) return session()
    posts.push({ url, options })
    return response({ data: { id: 1, status: 'published' } })
  })
  client.userId = 4
  await client.publish(1)
  await client.publish(1, 6)
  assert.deepEqual(JSON.parse(posts[0].options.body), {})
  assert.deepEqual(JSON.parse(posts[1].options.body), { replaces_id: 6 })
  assert.equal(posts[1].url, '/api/v1/preparations/1/publish')
})

test('withdraw sends the required reason text', async () => {
  const posts = []
  const client = new PreparationClient(async (url, options) => {
    if (url.endsWith('/auth/session')) return session()
    posts.push({ url, options })
    return response({ data: { id: 1, status: 'withdrawn' } })
  })
  client.userId = 4
  await client.withdraw(1, '讲义更新')
  assert.equal(posts[0].url, '/api/v1/preparations/1/withdraw')
  assert.deepEqual(JSON.parse(posts[0].options.body), { reason: '讲义更新' })
})

test('list keeps paging contract and detail unwraps data', async () => {
  const calls = []
  const client = new PreparationClient(async url => {
    calls.push(url)
    if (url.endsWith('/preparations/3')) return response({ data: { id: 3, title: 'x' } })
    return response({ data: [{ id: 3, title: 'x' }], total: 1 })
  })
  const list = await client.list(5, 2)
  assert.equal(list.total, 1)
  assert.equal(calls[0], '/api/v1/courses/5/preparations?page=2&page_size=20')
  const item = await client.detail(3)
  assert.equal(item.id, 3)
  assert.equal(calls[1], '/api/v1/preparations/3')
})

test('stale session user blocks writes before sending mutation', async () => {
  let calls = 0
  const client = new PreparationClient(async () => { calls++; return response({ data: { user: { id: 9 }, csrf_token: 't' } }) })
  client.userId = 4
  await assert.rejects(client.update(2, { title: 'x' }), error => error.status === 401)
  assert.equal(calls, 1)
})

test('server error message and request id surface to the caller', async () => {
  const client = new PreparationClient(async () => response(
    { error: { code: 'QUIZ_NOT_PUBLISHED', message: '关联随堂测未发布' }, request_id: 'req-2' }, 409))
  await assert.rejects(client.publish(1), error => {
    assert.equal(error.status, 409)
    assert.equal(error.code, 'QUIZ_NOT_PUBLISHED')
    assert.equal(error.requestId, 'req-2')
    assert.equal(error.message, '关联随堂测未发布')
    return true
  })
})
