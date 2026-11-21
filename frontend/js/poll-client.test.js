// 接口封装的两条硬要求：路径拼对、CSRF 票据过期能自己救回来。
// 后者在课堂上是真会发生的——页面开着两小时，学生再点提交时旧票据已经失效。
import assert from 'node:assert/strict'
import test from 'node:test'
import { PollClient, PollError } from './poll-client.js'

function stub(routes) {
  const calls = []
  const fetcher = async (path, options = {}) => {
    calls.push({ path, options })
    const handler = routes[path] ?? routes['*']
    return handler(path, options, calls)
  }
  return { client: new PollClient(fetcher), calls }
}

const ok = data => ({ ok: true, status: 200, json: async () => ({ data, total: 1 }) })
const fail = (status, code) => ({ ok: false, status, json: async () => ({ error: { code, message: '受控失败' } }) })

test('列表走 /courses/<id>/polls 并按状态过滤，返回 items 与 total', async () => {
  const { client, calls } = stub({
    '/api/v1/courses/2/polls?status=open&page_size=50': () => ok([{ id: 9 }]),
  })
  const data = await client.openPolls(2)
  assert.equal(calls[0].path, '/api/v1/courses/2/polls?status=open&page_size=50')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.deepEqual(data.items, [{ id: 9 }])
  assert.equal(data.total, 1)
})

test('写操作自动取票据并缓存：两次提交只读一次 session', async () => {
  const { client, calls } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 1 }, csrf_token: 'tk-1' }),
    '/api/v1/polls/9/ballots': () => ok({ id: 9, voted: 1 }),
  })
  await client.vote(9, [22])
  await client.vote(9, [22])
  assert.equal(calls.filter(entry => entry.path.endsWith('/session')).length, 1)
  const posted = calls.filter(entry => entry.path.endsWith('/ballots'))
  assert.equal(posted.length, 2)
  assert.equal(posted[0].options.headers['X-CSRF-Token'], 'tk-1')
  assert.deepEqual(JSON.parse(posted[0].options.body), { option_ids: [22] })
})

test('票据过期（CSRF_FAILED）时自动换一张重试，学生不看到这条错', async () => {
  let sessions = 0
  const { client, calls } = stub({
    '/api/v1/auth/session': () => {
      sessions += 1
      return ok({ user: { id: 1 }, csrf_token: `tk-${sessions}` })
    },
    '*': (path, options) => (options.headers['X-CSRF-Token'] === 'tk-1'
      ? fail(403, 'CSRF_FAILED')
      : ok({ id: 7, status: 'closed' })),
  })
  const closed = await client.close(7)
  assert.equal(closed.status, 'closed')
  assert.equal(sessions, 2, '应当重新取了一张票据')
  assert.equal(calls.filter(entry => entry.options.method === 'POST').length, 2)
})

test('业务错误直接抛出，带 code 让界面翻成人话，不重试', async () => {
  const { client, calls } = stub({
    '/api/v1/auth/session': () => ok({ user: { id: 1 }, csrf_token: 'tk' }),
    '*': (_path, _options, all) => (all.filter(entry => entry.options.method === 'POST').length > 1
      ? ok({})
      : fail(409, 'ALREADY_VOTED')),
  })
  await assert.rejects(() => client.vote(9, [22]), error => {
    assert.ok(error instanceof PollError)
    assert.equal(error.status, 409)
    assert.equal(error.code, 'ALREADY_VOTED')
    return true
  })
  assert.equal(calls.filter(entry => entry.options.method === 'POST').length, 1)
})

test('后端返回的不是 JSON 时给一句能看懂的话，而不是抛 SyntaxError', async () => {
  const client = new PollClient(async () => ({ ok: false, status: 502, json: async () => { throw new Error('boom') } }))
  await assert.rejects(() => client.get(1), error => {
    assert.equal(error.status, 502)
    assert.match(error.message, /服务暂时没有响应/)
    return true
  })
})
