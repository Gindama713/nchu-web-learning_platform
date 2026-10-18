// SPEC-018 客户端单元测试：HTTP 行为与入参组装（不依赖真实登录或浏览器）。
import assert from 'node:assert/strict'
import test from 'node:test'
import { GradingClient, casesPayload, profilePayload } from './grading-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

function client(userId = 7) {
  const calls = []
  const api = new GradingClient(userId, async (url, options = {}) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/session')) {
      return response({ data: { user: { id: userId }, csrf_token: 'fresh-token' } })
    }
    return response({ data: { ok: true } })
  })
  return { api, calls }
}

test('putProfile sends PUT with CSRF after session verification', async () => {
  const { api, calls } = client()
  await api.putProfile(11, { top_circuit: 'alu8' })
  assert.equal(calls[0].url, '/api/v1/auth/session')
  assert.equal(calls[1].url, '/api/v1/experiment-versions/11/judge-profile')
  assert.equal(calls[1].options.method, 'PUT')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh-token')
  assert.deepEqual(JSON.parse(calls[1].options.body), { top_circuit: 'alu8' })
})

test('createValidation and regrade attach UUID Idempotency-Key headers', async () => {
  const { api, calls } = client()
  await api.createValidation(3, 100, 101)
  await api.regrade(9, '复核', 4)
  const validationKey = calls.find(call => call.url.endsWith('/test-suites/3/validations'))
    .options.headers['Idempotency-Key']
  const regradeCall = calls.find(call => call.url.endsWith('/submissions/9/regrades'))
  assert.match(validationKey, /^[0-9a-f-]{36}$/)
  assert.match(regradeCall.options.headers['Idempotency-Key'], /^[0-9a-f-]{36}$/)
  assert.deepEqual(JSON.parse(regradeCall.options.body), { reason: '复核', test_suite_id: 4 })
  const bare = client()
  await bare.api.regrade(9, '默认套件')
  const body = JSON.parse(bare.calls.find(call => call.url.endsWith('/submissions/9/regrades')).options.body)
  assert.deepEqual(body, { reason: '默认套件' })
})

test('submitCircuit posts multipart body with Idempotency-Key and no JSON content type', async () => {
  const { api, calls } = client()
  const form = new globalThis.FormData()
  form.append('file', new globalThis.Blob(['<xml/>'], { type: 'text/xml' }), 'alu.circ')
  await api.submitCircuit(11, form.get('file'))
  const call = calls.find(item => item.url.endsWith('/experiment-versions/11/submissions'))
  assert.equal(call.options.method, 'POST')
  assert.equal(call.options.headers['Content-Type'], undefined)
  assert.match(call.options.headers['Idempotency-Key'], /^[0-9a-f-]{36}$/)
  assert.ok(call.options.body instanceof FormData)
})

test('courseSubmissions builds filter query and paging', async () => {
  const { api, calls } = client()
  await api.courseSubmissions(5, { experimentId: 3, status: 'wrong_answer', page: 2 })
  const url = calls.find(item => item.url.includes('/courses/5/submissions')).url
  assert.equal(url, '/api/v1/courses/5/submissions?page=2&page_size=20&experiment_id=3&status=wrong_answer')
})

test('setActiveSuite PUTs suite id and revision for optimistic lock', async () => {
  const { api, calls } = client()
  await api.setActiveSuite(11, 4, 2)
  const call = calls.find(item => item.url.endsWith('/experiment-versions/11/active-test-suite'))
  assert.equal(call.options.method, 'PUT')
  assert.deepEqual(JSON.parse(call.options.body), { test_suite_id: 4, revision: 2 })
})

test('profilePayload parses schema, components and limits with validation errors', () => {
  const good = profilePayload({ topCircuit: 'alu8',
    portSchemaText: '{"inputs":{"A":8},"outputs":{"Y":8}}',
    componentsText: 'Adder, AND  OR', limitsText: '{"cpu_seconds":10}' })
  assert.deepEqual(good, { top_circuit: 'alu8',
    port_schema: { inputs: { A: 8 }, outputs: { Y: 8 } },
    allowed_components: ['Adder', 'AND', 'OR'], limits: { cpu_seconds: 10 } })
  assert.throws(() => profilePayload({ topCircuit: ' ' }), /顶层电路名/)
  assert.throws(() => profilePayload({ topCircuit: 'a', portSchemaText: '{bad' }), /port_schema JSON/)
  assert.throws(() => profilePayload({ topCircuit: 'a', portSchemaText: '{}', componentsText: '  ' }), /允许元件/)
  assert.throws(() => profilePayload({ topCircuit: 'a', portSchemaText: '{}', componentsText: 'Adder',
    limitsText: '[1]' }), /limits 必须是 JSON 对象/)
})

test('casesPayload rejects empty array and non-array JSON', () => {
  assert.throws(() => casesPayload('[]'), /非空数组/)
  assert.throws(() => casesPayload('{"cases":1}'), /非空数组/)
  assert.throws(() => casesPayload('{bad'), /JSON 不合法/)
  assert.deepEqual(casesPayload('[{"label":"add-1"}]'), { cases: [{ label: 'add-1' }] })
})
