import assert from 'node:assert/strict'
import test from 'node:test'
import { RecommendationClient, recommendationReasons, recommendationStates } from './recommendation-client.js'

function makeClient(data) {
  const paths = []
  const client = new RecommendationClient({ id: 7, role: 'student' }, async (path, options) => {
    paths.push({ path, options })
    return { ok: true, status: 200, json: async () => ({ data }) }
  })
  return { client, paths }
}

test('recommendations encodes limit and returns the data envelope', async () => {
  const payload = { items: [{ knowledge_id: 1 }], reason: 'ok' }
  const { client, paths } = makeClient(payload)
  assert.deepEqual(await client.recommendations(3, 7), payload)
  assert.equal(paths[0].path, '/api/v1/courses/3/recommendations?limit=7')
})

test('limit defaults to 5 and rejects non-integers outside 1..20 without a request', async () => {
  const { client, paths } = makeClient({ items: [] })
  await client.recommendations(3)
  assert.equal(paths[0].path, '/api/v1/courses/3/recommendations?limit=5')
  for (const limit of [0, 21, 1.5, -1, 'abc']) {
    await assert.rejects(() => client.recommendations(3, limit), /1至20/)
  }
  assert.equal(paths.length, 1)
  await client.recommendations(3, '20')
  assert.equal(paths[1].path, '/api/v1/courses/3/recommendations?limit=20')
})

test('knowledgeDetail reads the shared knowledge endpoint', async () => {
  const detail = { id: 9, title: '程序计数器' }
  const { client, paths } = makeClient(detail)
  assert.deepEqual(await client.knowledgeDetail(9), detail)
  assert.equal(paths[0].path, '/api/v1/knowledge-points/9')
})

test('reason and state wording keep the published explanation', () => {
  assert.match(recommendationReasons.insufficient_sample, /不足5次/)
  assert.match(recommendationReasons.weakness, /80%/)
  assert.match(recommendationStates.cold_start, /28天/)
  assert.match(recommendationStates.all_mastered, /暂无推荐/)
})
