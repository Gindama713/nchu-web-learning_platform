import assert from 'node:assert/strict'
import test from 'node:test'
import { apiRequest, readApi } from './api.js'

test('API wrapper returns data and rejects an error response', async () => {
  const data = await readApi('/ok', async () => ({ ok: true, json: async () => ({ data: [1] }) }))
  assert.deepEqual(data, [1])
  await assert.rejects(
    readApi('/fail', async () => ({ ok: false, status: 503, json: async () => ({ error: { message: 'unavailable' } }) })),
    /unavailable/,
  )
})

test('write requests send JSON with the CSRF token and session cookie', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (_path, options) => {
      assert.equal(options.credentials, 'same-origin')
      assert.equal(options.headers['X-CSRF-Token'], 'token')
      assert.deepEqual(JSON.parse(options.body), { status: 'handled' })
      return { ok: true, status: 200, json: async () => ({ data: { id: 1 } }) }
    }
    assert.deepEqual(await apiRequest('/warnings/1', 'PATCH', { status: 'handled' }, 'token'), { id: 1 })
  } finally {
    globalThis.fetch = original
  }
})

test('failed requests carry status and backend code so callers can retry CSRF', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => ({
      ok: false,
      status: 403,
      json: async () => ({ error: { code: 'CSRF_FAILED', message: 'Invalid CSRF token' } }),
    })
    await assert.rejects(apiRequest('/attendance', 'POST', {}, 'stale'), { code: 'CSRF_FAILED', status: 403 })
    globalThis.fetch = async () => ({
      ok: false,
      status: 422,
      json: async () => ({ error: { code: 'INVALID_ATTENDANCE_CODE', message: '签到码不对' } }),
    })
    await assert.rejects(readApi('/x'), { code: 'INVALID_ATTENDANCE_CODE', status: 422 })
  } finally {
    globalThis.fetch = original
  }
})
