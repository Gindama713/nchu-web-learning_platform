// SPEC-014 客户端：预警列表、批次幂等键、处理记录、分页合并与错误透传。
import assert from 'node:assert/strict'
import test from 'node:test'

import { WarningClient } from './warning-client.js'

function stub(routes) {
  const calls = []
  const fetcher = async (path, options = {}) => {
    calls.push({ path, options })
    return (routes[path] ?? routes['*'])(path, options)
  }
  return { calls, client: new WarningClient(7, fetcher) }
}

const ok = (data, extra = {}) => ({ ok: true, status: 200, json: async () => ({ data, ...extra }) })
const fail = (status, code) => ({ ok: false, status, json: async () => ({ error: { code, message: '受控失败' } }) })

test('预警列表带筛选并保留批次号与模型状态', async () => {
  const { calls, client } = stub({
    '/api/v1/courses/3/warnings?page=1&page_size=50&status=open': () => ok(
      [{ id: 9, student_id: 12, status: 'open', reasons: [] }],
      { total: 1, analysis_run_id: 44, model_status: 'clustered' }),
  })
  const content = await client.warnings(3, { status: 'open' })
  assert.equal(calls[0].path, '/api/v1/courses/3/warnings?page=1&page_size=50&status=open')
  assert.equal(content.total, 1)
  assert.equal(content.analysis_run_id, 44)
  assert.equal(content.model_status, 'clustered')
})

test('生成批次带幂等键，重复点击不会产生两个批次', async () => {
  const { calls, client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/courses/3/warning-runs': () => ok({ analysis_run_id: 45, status: 'completed' }),
  })
  const first = await client.createRun(3)
  const second = await client.createRun(3)
  const posts = calls.filter(entry => entry.path.endsWith('/warning-runs'))
  assert.equal(posts.length, 2)
  assert.equal(posts[0].options.method, 'POST')
  assert.equal(posts[0].options.headers['X-CSRF-Token'], 'tk')
  assert.ok(posts[0].options.headers['Idempotency-Key'])
  assert.notEqual(posts[0].options.headers['Idempotency-Key'], posts[1].options.headers['Idempotency-Key'])
  assert.equal(first.analysis_run_id, 45)
  assert.equal(second.analysis_run_id, 45)
})

test('标记处理只发 status=handled 与备注', async () => {
  const { calls, client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/warnings/9': () => ok({ id: 9, status: 'handled' }),
  })
  const data = await client.handle(9, '已单独联系')
  const patch = calls.find(entry => entry.path.endsWith('/warnings/9'))
  assert.equal(patch.options.method, 'PATCH')
  assert.deepEqual(JSON.parse(patch.options.body), { status: 'handled', note: '已单独联系' })
  assert.equal(data.status, 'handled')
})

test('多人页名单按 total 合并，不因一页 100 条截断', async () => {
  const { client } = stub({
    '/api/v1/courses/3/members?page=1&page_size=100': () => ok(
      Array.from({ length: 100 }, (_, index) => ({ user_id: index + 1 })), { total: 130 }),
    '/api/v1/courses/3/members?page=2&page_size=100': () => ok(
      Array.from({ length: 30 }, (_, index) => ({ user_id: 101 + index })), { total: 130 }),
  })
  const list = await client.members(3)
  assert.equal(list.length, 130)
})

test('权限失败时把错误码交给界面翻译', async () => {
  const { client } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7 }, csrf_token: 'tk' }),
    '/api/v1/courses/3/warning-runs': () => fail(403, 'FORBIDDEN'),
  })
  await assert.rejects(() => client.createRun(3), error => error.status === 403 && error.code === 'FORBIDDEN')
})
