// 教学助手客户端：路径、CSRF、学生不能带别人 ID、错误信息透传。
import assert from 'node:assert/strict'
import test from 'node:test'

import { AssistantClient } from './assistant-client.js'

function stub(routes) {
  const calls = []
  const fetcher = async (path, options = {}) => {
    calls.push({ path, options })
    return (routes[path] ?? routes['*'])(path, options)
  }
  return { calls, fetcher }
}

const ok = data => ({ ok: true, status: 200, json: async () => ({ data }) })
const fail = (status, code, message) => ({
  ok: false, status, json: async () => ({ error: { code, message } }),
})

test('教师提问：POST 到课程助手接口，带 CSRF 和问题正文', async () => {
  const { calls, fetcher } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7, role: 'teacher' }, csrf_token: 'tk-1' }),
    '/api/v1/courses/3/assistant/ask': () => ok({ intent: 'attendance', title: '考勤', facts: [] }),
  })
  const client = new AssistantClient({ id: 7, role: 'teacher' }, fetcher)
  const data = await client.ask(3, '这周考勤怎么样？')
  assert.equal(data.intent, 'attendance')
  const posted = calls.find(entry => entry.path.endsWith('/assistant/ask'))
  assert.equal(posted.options.method, 'POST')
  assert.equal(posted.options.headers['X-CSRF-Token'], 'tk-1')
  assert.deepEqual(JSON.parse(posted.options.body), { question: '这周考勤怎么样？' })
})

test('教师指定学生时带上 student_id', async () => {
  const { calls, fetcher } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7, role: 'teacher' }, csrf_token: 'tk-1' }),
    '/api/v1/courses/3/assistant/ask': () => ok({ intent: 'my_progress', facts: [] }),
  })
  const client = new AssistantClient({ id: 7, role: 'teacher' }, fetcher)
  await client.ask(3, '他哪里薄弱？', 12)
  const posted = calls.find(entry => entry.path.endsWith('/assistant/ask'))
  assert.deepEqual(JSON.parse(posted.options.body), { question: '他哪里薄弱？', student_id: 12 })
})

test('登录角色变化立即拒绝，不把旧会话的答案给新角色', async () => {
  const { fetcher } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7, role: 'student' }, csrf_token: 'tk-1' }),
  })
  const client = new AssistantClient({ id: 7, role: 'teacher' }, fetcher)
  await assert.rejects(() => client.ask(3, '考勤'), error => error.status === 401)
})

test('后端校验失败时把可读信息交给界面', async () => {
  const { fetcher } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 7, role: 'teacher' }, csrf_token: 'tk-1' }),
    '/api/v1/courses/3/assistant/ask': () => fail(404, 'NOT_FOUND', '课程不存在'),
  })
  const client = new AssistantClient({ id: 7, role: 'teacher' }, fetcher)
  await assert.rejects(() => client.ask(3, '考勤'), error => error.status === 404 && error.message === '课程不存在')
})
