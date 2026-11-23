// SPEC-016 客户端：图片走 FormData（不手写 Content-Type）、确认只提交结构草稿。
import assert from 'node:assert/strict'
import test from 'node:test'

import { RecognitionClient } from './recognition-client.js'

function stub(routes) {
  const calls = []
  const fetcher = async (path, options = {}) => {
    calls.push({ path, options })
    return (routes[path] ?? routes['*'])(path, options)
  }
  return { calls, client: new RecognitionClient(7, fetcher) }
}

const ok = data => ({ ok: true, status: 200, json: async () => ({ data }) })
const fail = (status, code, message) => ({ ok: false, status, json: async () => ({ error: { code, message } }) })

test('上传图片用 FormData 且不覆盖浏览器 boundary', async () => {
  const { calls, client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/courses/3/recognitions': () => ok({ id: 11, status: 'recognized', items: [] }),
  })
  const file = new globalThis.Blob(['fake'], { type: 'image/png' })
  const data = await client.create(3, file)
  const post = calls.find(entry => entry.path.endsWith('/recognitions'))
  assert.equal(post.options.method, 'POST')
  assert.ok(post.options.body instanceof FormData)
  assert.equal(post.options.body.get('image') instanceof globalThis.Blob, true)
  assert.equal(post.options.headers['Content-Type'], undefined)
  assert.equal(post.options.headers['X-CSRF-Token'], 'tk')
  assert.equal(data.id, 11)
})

test('确认只保留 symbol/bbox/label，多余字段丢掉', async () => {
  const { calls, client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/recognitions/11/confirm': () => ok({ id: 11, status: 'confirmed', confirmed_items: [] }),
  })
  await client.confirm(11, [
    { symbol: 'AND', bbox: [10, 20, 30, 40], label: 'A', confidence: 0.91, tight_bbox: [1, 2, 3, 4] },
    { symbol: 'NOT', bbox: [50, 60, 30, 40], label: undefined, confidence: 0.6 },
  ])
  const post = calls.find(entry => entry.path.endsWith('/confirm'))
  assert.deepEqual(JSON.parse(post.options.body), {
    items: [
      { symbol: 'AND', bbox: [10, 20, 30, 40], label: 'A' },
      { symbol: 'NOT', bbox: [50, 60, 30, 40], label: null },
    ],
  })
})

test('识别结果原样返回：低置信度与未识别由界面决定怎么显示', async () => {
  const payload = {
    id: 12, status: 'recognized',
    items: [
      { symbol: 'AND', bbox: [0, 0, 10, 10], confidence: 0.6, confidence_band: 'low', label: null },
      { symbol: 'NOT', bbox: [20, 0, 10, 10], confidence: 0.9, confidence_band: 'high', label: 'Y' },
    ],
  }
  const { client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/courses/3/recognitions': () => ok(payload),
  })
  const data = await client.create(3, new globalThis.Blob(['x'], { type: 'image/png' }))
  assert.equal(data.items.length, 2)
  assert.equal(data.items[0].confidence_band, 'low')
  assert.equal(data.items[1].label, 'Y')
})

test('不支持的图片把 415 与可读信息透传', async () => {
  const { client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/courses/3/recognitions': () => fail(415, 'UNSUPPORTED_IMAGE', 'PNG or JPEG required'),
  })
  await assert.rejects(
    () => client.create(3, new globalThis.Blob(['x'], { type: 'image/gif' })),
    error => error.status === 415 && error.message === 'PNG or JPEG required',
  )
})
