// SPEC-007 客户端单元测试：CSRF、动作入参与轮询查询构造。
import assert from 'node:assert/strict'
import test from 'node:test'
import { DemoClient, demoActions, demoPresets } from './demo-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('六个内置场景与四个动作与后端 PRESETS/ACTIONS 对齐', () => {
  assert.deepEqual(Object.keys(demoPresets), ['gate', 'comb', 'sequential', 'alu', 'memory', 'cpu'])
  assert.deepEqual(Object.keys(demoActions), ['step', 'run', 'pause', 'reset'])
})

test('createSession 先取会话 CSRF，再按 preset 建演示', async () => {
  const calls = []
  const client = new DemoClient(7, async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 'token-1' } })
      : response({ data: { id: 12, preset: 'cpu', revision: 0 } }, 201)
  })
  const created = await client.createSession(3, { preset: 'cpu' })
  assert.equal(created.id, 12)
  assert.equal(calls[1].url, '/api/v1/courses/3/demo-sessions')
  assert.equal(calls[1].options.method, 'POST')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'token-1')
  assert.deepEqual(JSON.parse(calls[1].options.body), { preset: 'cpu' })
})

test('关联实验版本时把 id 转成数字并带上', async () => {
  const calls = []
  const client = new DemoClient(7, async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 't' } })
      : response({ data: { id: 1 } }, 201)
  })
  await client.createSession(3, { preset: 'alu', experimentVersionId: '44' })
  assert.deepEqual(JSON.parse(calls[1].options.body), { preset: 'alu', experiment_version_id: 44 })
})

test('advance 用 PUT 提交 revision 与 action', async () => {
  const calls = []
  const client = new DemoClient(7, async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 't' } })
      : response({ data: { id: 12, revision: 3, state: { step: 2 } } })
  })
  const next = await client.advance(12, 2, 'step')
  assert.equal(next.revision, 3)
  assert.equal(calls[1].url, '/api/v1/demo-sessions/12/state')
  assert.equal(calls[1].options.method, 'PUT')
  assert.deepEqual(JSON.parse(calls[1].options.body), { revision: 2, action: 'step' })
})

test('未知动作在发请求前就被拒绝', async () => {
  let calls = 0
  const client = new DemoClient(7, async () => { calls++; return response({ data: {} }) })
  assert.throws(() => client.advance(12, 0, 'jump'), /未知动作/)
  assert.equal(calls, 0)
})

test('session 带 after_revision 供学生端增量轮询', async () => {
  const urls = []
  const client = new DemoClient(7, async url => {
    urls.push(url)
    return response({ data: { id: 12, revision: 5 } })
  })
  await client.session(12)
  await client.session(12, 4)
  assert.equal(urls[0], '/api/v1/demo-sessions/12')
  assert.equal(urls[1], '/api/v1/demo-sessions/12?after_revision=4')
})

test('revision 冲突错误带上服务端返回的 code 与 detail', async () => {
  const client = new DemoClient(7, async () => response(
    { error: { code: 'REVISION_CONFLICT', message: 'stale revision', detail: { current: 5, provided: 3 } } }, 409))
  await assert.rejects(client.session(12), error => {
    assert.equal(error.status, 409)
    assert.equal(error.code, 'REVISION_CONFLICT')
    assert.equal(error.detail.current, 5)
    return true
  })
})

test('sessions 只在明确传布尔值时附加 active 过滤', async () => {
  const urls = []
  const client = new DemoClient(7, async url => {
    urls.push(url)
    return response({ data: [], total: 0 })
  })
  await client.sessions(3)
  await client.sessions(3, { active: true })
  await client.sessions(3, { active: '' })
  assert.equal(urls[0], '/api/v1/courses/3/demo-sessions?page=1&page_size=10')
  assert.equal(urls[1], '/api/v1/courses/3/demo-sessions?page=1&page_size=10&active=true')
  assert.equal(urls[2], '/api/v1/courses/3/demo-sessions?page=1&page_size=10')
})
