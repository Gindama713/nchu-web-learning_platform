// SPEC-015 客户端单元测试：图谱查询与建边入参。
import assert from 'node:assert/strict'
import test from 'node:test'
import { KnowledgeGraphClient, edgeTypes } from './knowledge-graph-client.js'

const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })

test('关系类型与后端保持一致', () => {
  assert.deepEqual(Object.keys(edgeTypes), ['prerequisite', 'contains'])
})

test('graph 不传 root 时不附加查询串', async () => {
  const urls = []
  const client = new KnowledgeGraphClient(7, async url => {
    urls.push(url)
    return response({ data: { nodes: [], edges: [], prerequisite_paths: [] } })
  })
  await client.graph(3)
  await client.graph(3, 12)
  assert.equal(urls[0], '/api/v1/courses/3/knowledge-graph')
  assert.equal(urls[1], '/api/v1/courses/3/knowledge-graph?root_id=12')
})

test('addEdge 先取 CSRF，再把 id 转成数字', async () => {
  const calls = []
  const client = new KnowledgeGraphClient(7, async (url, options) => {
    calls.push({ url, options })
    return url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 'tk' } })
      : response({ data: {} }, 201)
  })
  await client.addEdge(3, { sourceId: '11', targetId: '12', type: 'prerequisite' })
  assert.equal(calls[1].url, '/api/v1/courses/3/knowledge-edges')
  assert.equal(calls[1].options.method, 'POST')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'tk')
  assert.deepEqual(JSON.parse(calls[1].options.body),
    { source_id: 11, target_id: 12, type: 'prerequisite' })
})

test('自环与未知类型在发请求前就被拒绝', () => {
  const client = new KnowledgeGraphClient(7, async () => { throw new Error('不该发请求') })
  assert.throws(() => client.addEdge(3, { sourceId: 5, targetId: 5, type: 'prerequisite' }), /同一个知识点/)
  assert.throws(() => client.addEdge(3, { sourceId: 5, targetId: 6, type: 'related' }), /未知关系类型/)
})

test('成环错误把 code 透传出来', async () => {
  const client = new KnowledgeGraphClient(7, async url => (
    url.endsWith('/auth/session')
      ? response({ data: { user: { id: 7 }, csrf_token: 't' } })
      : response({ error: { code: 'PREREQUISITE_CYCLE', message: '先修关系存在环' } }, 422)
  ))
  await assert.rejects(client.addEdge(3, { sourceId: 1, targetId: 2, type: 'prerequisite' }),
    error => error.status === 422 && error.code === 'PREREQUISITE_CYCLE')
})

test('知识点列表按分页取全量', async () => {
  const client = new KnowledgeGraphClient(7, async url => {
    const page = Number(new globalThis.URL(url, 'http://x').searchParams.get('page'))
    if (page === 1) return response({ data: [{ id: 1 }, { id: 2 }], total: 3 })
    return response({ data: [{ id: 3 }], total: 3 })
  })
  const all = await client.points(3)
  assert.deepEqual(all.map(item => item.id), [1, 2, 3])
})
