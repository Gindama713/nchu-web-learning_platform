import assert from 'node:assert/strict'
import test from 'node:test'
import { readApi } from './api.js'

test('API wrapper returns data and rejects an error response', async () => {
  const data = await readApi('/ok', async () => ({ ok: true, json: async () => ({ data: [1] }) }))
  assert.deepEqual(data, [1])
  await assert.rejects(
    readApi('/fail', async () => ({ ok: false, status: 503, json: async () => ({ error: { message: 'unavailable' } }) })),
    /unavailable/,
  )
})
