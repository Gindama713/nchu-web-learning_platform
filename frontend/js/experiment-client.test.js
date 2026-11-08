// SPEC-009 客户端单元测试：HTTP 行为与入参组装（不依赖真实登录或浏览器）。
import assert from 'node:assert/strict'
import test from 'node:test'
import { ExperimentClient, publishPayload, versionPayload } from './experiment-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('write refreshes server session CSRF and uses same-origin credentials', async () => {
  const calls = []
  const client = new ExperimentClient(7, async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 'fresh-token' } })
      : response({ data: { id: 1, title: '8位ALU' } })
  })
  const created = await client.createExperiment(3, { code: 'EXP-01', title: '8位ALU', description: 'x' })
  assert.deepEqual(created, { id: 1, title: '8位ALU' })
  assert.equal(calls[0].url, '/api/v1/auth/session')
  assert.equal(calls[1].url, '/api/v1/courses/3/experiments')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh-token')
  assert.equal(calls[1].options.credentials, 'same-origin')
  assert.deepEqual(JSON.parse(calls[1].options.body), { code: 'EXP-01', title: '8位ALU', description: 'x' })
})

test('changed session user blocks writes before sending any mutation', async () => {
  let calls = 0
  const client = new ExperimentClient(7, async () => {
    calls++
    return response({ data: { user: { id: 8 }, csrf_token: 'token' } })
  })
  await assert.rejects(client.publish(11, { start_at: 'a', end_at: 'b' }), error => error.status === 401)
  assert.equal(calls, 1)
})

test('version and experiment listing endpoints build paging and filters', async () => {
  const calls = []
  const client = new ExperimentClient(7, async (url, options) => {
    calls.push({ url, options })
    if (url.startsWith('/api/v1/courses?')) return response({ data: [{ id: 3 }], total: 1 })
    return response({ data: [], total: 0 })
  })
  await client.experiments(3, 2)
  await client.versions(3, { experimentId: 5, status: 'draft' })
  assert.equal(calls[0].url, '/api/v1/courses/3/experiments?page=2&page_size=20')
  assert.equal(calls[1].url, '/api/v1/courses/3/experiment-versions?page=1&page_size=20&experiment_id=5&status=draft')
})

test('detail unwraps the data field of a version response', async () => {
  const client = new ExperimentClient(7, async url => {
    assert.equal(url, '/api/v1/experiment-versions/11')
    return response({ data: { id: 11, rules: {} } })
  })
  assert.equal((await client.detail(11)).id, 11)
})

test('versionPayload parses modes, panel and rules JSON with validation errors', () => {
  const base = { title: 't', objectives: 'o', instructions: 'i', wiring: true, circuit: false,
    knowledgeIds: [10], panelText: '{"schema_version":1}', rulesText: '{"a":1}' }
  assert.deepEqual(versionPayload(base), {
    title: 't', objectives: 'o', instructions: 'i', submission_modes: ['wiring'],
    panel: { schema_version: 1 }, rules: { a: 1 }, knowledge_ids: [10],
  })
  assert.deepEqual(versionPayload({ ...base, wiring: false, circuit: true, panelText: '' }).submission_modes,
    ['circuit'])
  for (const broken of [
    { ...base, title: ' ' }, { ...base, objectives: '' }, { ...base, instructions: '' },
    { ...base, wiring: false, circuit: false },
    { ...base, panelText: 'not-json' },
    { ...base, wiring: true, panelText: '' },
    { ...base, rulesText: 'not-json' },
    { ...base, rulesText: '["array"]' },
  ]) {
    assert.throws(() => versionPayload(broken), Error)
  }
})

test('publishPayload validates the window and converts to ISO strings', () => {
  assert.throws(() => publishPayload({ startAt: '', endAt: '2026-11-08T08:00' }), /开始和截止/)
  assert.throws(() => publishPayload({ startAt: 'not-a-date', endAt: '2026-11-08T08:00' }), /时间格式/)
  assert.throws(() => publishPayload({ startAt: '2026-11-08T08:00', endAt: '2026-11-01T08:00' }), /早于/)
  assert.throws(() => publishPayload({ startAt: '2026-11-01T08:00', endAt: '2026-11-01T08:00' }), /早于/)
  assert.deepEqual(publishPayload({ startAt: '2026-11-01T08:00', endAt: '2026-11-08T08:00' }), {
    start_at: new Date('2026-11-01T08:00').toISOString(),
    end_at: new Date('2026-11-08T08:00').toISOString(),
  })
})
