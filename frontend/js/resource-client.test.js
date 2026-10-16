// HTTP test doubles verify client behavior, not real login or browser acceptance.
import assert from 'node:assert/strict'
import test from 'node:test'
import { ResourceClient, contentUrl } from './resource-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('list builds filters and keeps paging contract', async () => {
  const calls = []
  const client = new ResourceClient(async url => {
    calls.push(url)
    return response({ data: [{ id: 1 }], total: 1 })
  })
  const result = await client.list(3, { q: '寄存器', kind: 'slides', chapterId: 7 })
  assert.deepEqual(result.data, [{ id: 1 }])
  assert.equal(calls[0], '/api/v1/courses/3/resources?page=1&page_size=20&q=%E5%AF%84%E5%AD%98%E5%99%A8&kind=slides&chapter_id=7')
})

test('upload sends multipart form data with CSRF from a fresh session', async () => {
  const calls = []
  const client = new ResourceClient(async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/session')) return response({ data: { user: { id: 4 }, csrf_token: 'token' } })
    return response({ data: { resource_id: 9 } }, 201)
  })
  client.userId = 4
  const form = new FormData()
  form.append('title', '课件')
  const data = await client.upload(3, form)
  assert.equal(data.resource_id, 9)
  assert.equal(calls[1].url, '/api/v1/courses/3/resources')
  assert.equal(calls[1].options.method, 'POST')
  assert.equal(calls[1].options.body, form)
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'token')
  assert.equal(calls[1].options.headers['Content-Type'], undefined)
})

test('missing session user blocks writes before sending mutation', async () => {
  let calls = 0
  const client = new ResourceClient(async () => { calls++; return response({ data: { user: { id: 9 } } }) })
  client.userId = 4
  await assert.rejects(client.update(2, { title: 'x' }), error => error.status === 401)
  assert.equal(calls, 1)
})

test('import questions sends version id and an idempotency key', async () => {
  let mutation
  const client = new ResourceClient(async (url, options) => {
    if (url.endsWith('/auth/session')) return response({ data: { user: { id: 4 }, csrf_token: 'token' } })
    mutation = { url, options }
    return response({ data: { import_id: 1, count: 2 } }, 201)
  })
  client.userId = 4
  const data = await client.importQuestions(5, 11)
  assert.equal(data.count, 2)
  assert.equal(mutation.url, '/api/v1/resources/5/question-imports')
  assert.equal(mutation.options.headers['Idempotency-Key'].length, 36)
  assert.deepEqual(JSON.parse(mutation.options.body), { resource_version_id: 11 })
})

test('content url carries intent and encoded event id', () => {
  const url = contentUrl(12, 'download', 'evt-一')
  assert.equal(url, '/api/v1/resource-versions/12/content?intent=download&event_id=evt-%E4%B8%80')
})

test('server error message and request id surface to the caller', async () => {
  const client = new ResourceClient(async () => response(
    { error: { code: 'EVENT_CONFLICT', message: '事件冲突' }, request_id: 'req-1' }, 409))
  await assert.rejects(client.versions(2), error => {
    assert.equal(error.status, 409)
    assert.equal(error.code, 'EVENT_CONFLICT')
    assert.equal(error.requestId, 'req-1')
    assert.equal(error.message, '事件冲突')
    return true
  })
})
