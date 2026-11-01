import assert from 'node:assert/strict'
import test from 'node:test'
import { GenerationClient, generationFailure, generationPayload } from './generation-client.js'

const form = { title: ' 草稿 ', kind: 'exam', count: '3', total_points: '10.01', easy: '3', medium: '0', hard: '0',
  knowledge_ids: [1], confidential: true, seed: '9223372036854775807', history_until: '', replay_of: '12' }

test('replay only sends title and snapshot, ignoring original form constraints', () => {
  assert.deepEqual(generationPayload({ ...form, count: 'bad', seed: 'bad' }, true), { title: '草稿', replay_of: 12 })
  for (const values of [{ count: '' }, { easy: '2' }, { total_points: '.01' }, { total_points: '1001' },
    { seed: '9223372036854775808' }, { seed: '-9223372036854775809' }, { seed: '1e3' }]) {
    assert.throws(() => generationPayload({ ...form, ...values }))
  }
})

test('signed64 JSON seed travels exactly with CSRF and no auto publication', async () => {
  const calls = []
  const client = new GenerationClient(7, async (path, options) => {
    calls.push({ path, options })
    return { ok: true, status: 200, json: async () => ({ data: path.endsWith('/auth/session')
      ? { user: { id: 7 }, csrf_token: 'token' } : { paper_id: 3 } }) }
  })
  await client.generate(1, form)
  assert.equal(calls[1].path, '/api/v1/courses/1/generated-papers')
  assert.match(calls[1].options.body, /"seed":9223372036854775807[,}]/)
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'token')
  await client.generate(1, { ...form, seed: '-9223372036854775808' })
  assert.match(calls[3].options.body, /"seed":-9223372036854775808[,}]/)
  await client.generate(1, form, true)
  assert.deepEqual(JSON.parse(calls[5].options.body), { title: '草稿', replay_of: 12 })
  assert.equal(calls.filter(call => /publish/.test(call.path)).length, 0)
})

test('failure guidance distinguishes no solution from budget exhaustion', () => {
  assert.match(generationFailure({ message: '无解', code: 'INFEASIBLE_CONSTRAINTS' }), /调整难度/)
  assert.match(generationFailure({ message: '预算耗尽', code: 'SEARCH_LIMIT' }), /没有生成草稿/)
})
