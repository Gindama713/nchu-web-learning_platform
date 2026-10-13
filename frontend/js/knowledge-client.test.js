// HTTP test doubles verify client behavior, not real login or browser acceptance.
import assert from 'node:assert/strict'
import test from 'node:test'
import { KnowledgeClient } from './knowledge-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('fetch is invoked without a KnowledgeClient receiver in browser-like environments', async () => {
  const client = new KnowledgeClient(function () {
    assert.equal(this, undefined)
    return Promise.resolve(response({ data: { user: { id: 2 } } }))
  })
  assert.equal((await client.session()).user.id, 2)
})

test('write refreshes server session CSRF and uses same-origin credentials', async () => {
  const calls = []
  const client = new KnowledgeClient(async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 2 }, csrf_token: 'fresh-token' } })
      : response({ data: { completed: true } })
  })
  client.userId = 2
  assert.deepEqual(await client.progress(10, true), { completed: true })
  assert.equal(calls[0].url, '/api/v1/auth/session')
  assert.equal(calls[1].url, '/api/v1/knowledge-points/10/progress')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh-token')
  assert.equal(calls[1].options.credentials, 'same-origin')
  assert.deepEqual(JSON.parse(calls[1].options.body), { completed: true })
})

test('missing token or changed user blocks writes before sending mutation', async () => {
  for (const session of [{ user: { id: 2 } }, { user: { id: 3 }, csrf_token: 'token' }]) {
    let calls = 0
    const client = new KnowledgeClient(async () => { calls++; return response({ data: session }) })
    client.userId = 2
    await assert.rejects(client.bookmark(10, true), error => error.status === 401)
    assert.equal(calls, 1)
  }
})

test('complete chapter IDs are loaded across all pages with a stable revision', async () => {
  const first = Array.from({ length: 100 }, (_, index) => ({ id: index + 1 }))
  const client = new KnowledgeClient(async url => response({
    data: url.includes('page=1&') ? first : [{ id: 101 }], total: 101, chapters_revision: 7,
  }))
  const chapters = await client.chapters(1)
  assert.equal(chapters.items.length, 101)
  assert.equal(chapters.revision, 7)
})

test('chapter pagination changes or duplicate identities require refresh', async () => {
  for (const second of [
    { data: [{ id: 2 }], total: 2, chapters_revision: 8 },
    { data: [{ id: 1 }], total: 2, chapters_revision: 7 },
    { data: [{ id: 2 }], total: 3, chapters_revision: 7 },
  ]) {
    const client = new KnowledgeClient(async url => response(url.includes('page=1&')
      ? { data: [{ id: 1 }], total: 2, chapters_revision: 7 } : second))
    await assert.rejects(client.chapters(1), error => error.status === 409)
  }
})

test('chapter reorder sends complete order and revision and preserves conflict', async () => {
  let mutation
  const client = new KnowledgeClient(async (url, options) => {
    if (url.endsWith('/auth/session')) return response({ data: { user: { id: 1 }, csrf_token: 'token' } })
    mutation = { url, options }
    return response({ error: { code: 'REVISION_CONFLICT', message: '章节已变化' }, request_id: 'request-1' }, 409)
  })
  client.userId = 1
  await assert.rejects(client.reorder(1, 7, [3, 2, 1]), error => {
    assert.equal(error.code, 'REVISION_CONFLICT')
    assert.equal(error.requestId, 'request-1')
    return error.status === 409
  })
  assert.equal(mutation.url, '/api/v1/courses/1/chapter-order')
  assert.deepEqual(JSON.parse(mutation.options.body), { chapters_revision: 7, chapter_ids: [3, 2, 1] })
})

test('search encodes literal text and keeps pagination metadata', async () => {
  let path
  const client = new KnowledgeClient(async url => {
    path = url
    return response({ data: [], total: 0, page: 3, page_size: 20 })
  })
  const result = await client.list(2, { page: 3, q: 'PC & 程序计数器', chapterId: 4 })
  const params = new globalThis.URLSearchParams(path.split('?')[1])
  assert.equal(params.get('q'), 'PC & 程序计数器')
  assert.equal(params.get('chapter_id'), '4')
  assert.equal(params.get('page'), '3')
  assert.equal(result.total, 0)
})

test('unavailable and non-JSON errors cannot become successful empty data', async () => {
  const unavailable = new KnowledgeClient(async () => response({ error: { message: '等待鉴权接入' } }, 503))
  await assert.rejects(unavailable.detail(1), error => error.status === 503)
  const html = new KnowledgeClient(async () => ({ status: 404, json: async () => { throw new Error('HTML') } }))
  await assert.rejects(html.session(), error => error.status === 404)
})

