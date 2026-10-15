import assert from 'node:assert/strict'
import test from 'node:test'
import { AnalyticsClient } from './analytics-client.js'

test('knowledge excludes stale score filters; scores requires category; restore sends ID only', async () => {
  const requests = []
  const api = new AnalyticsClient({ id: 1, role: 'teacher' }, async path => {
    requests.push(path); return { ok: true, json: async () => ({ data: {} }) }
  })
  await api.query(3, { dimension: 'knowledge', kind: 'exam', paper_id: '9', student_id: '2' })
  assert.equal(requests.at(-1), '/api/v1/courses/3/analytics?dimension=knowledge&student_id=2')
  await api.query(3, { dimension: 'scores', kind: 'exam', paper_id: '9' })
  assert.equal(requests.at(-1), '/api/v1/courses/3/analytics?dimension=scores&kind=exam&paper_id=9')
  await api.restore(3, 17)
  assert.equal(requests.at(-1), '/api/v1/courses/3/analytics?analysis_run_id=17')
})

test('CSV validates current identity/role and downloads only saved ID, rejecting failures', async () => {
  const paths = []
  let session = { user: { id: 1, role: 'teacher' }, csrf_token: 'current' }, status = 200
  const api = new AnalyticsClient(session.user, async path => {
    paths.push(path)
    if (path.endsWith('/session')) return { ok: true, json: async () => ({ data: session }) }
    return { ok: status === 200, status, headers: new Map([['Content-Type', 'text/csv; charset=utf-8']]),
      blob: async () => 'saved-csv', json: async () => ({ error: { message: 'snapshot missing' } }) }
  })
  assert.equal(await api.csv(3, 17), 'saved-csv')
  assert.equal(paths.at(-1), '/api/v1/courses/3/analytics/export?analysis_run_id=17&format=csv')
  status = 404
  await assert.rejects(api.csv(3, 17), /snapshot missing/)
  session = { ...session, user: { id: 2, role: 'teacher' } }
  await assert.rejects(api.csv(3, 17), /登录状态已变化/)
})
