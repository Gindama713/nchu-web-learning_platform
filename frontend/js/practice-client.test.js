import assert from 'node:assert/strict'
import test from 'node:test'
import { PracticeClient, practicePayload } from './practice-client.js'

test('practice payload binds exact version and preserves false/zero/multiple types', () => {
  assert.deepEqual(practicePayload({ version_id: 8, type: 'boolean' }, false), { question_version_id: 8, answer: false })
  assert.equal(practicePayload({ version_id: 8, type: 'numeric' }, '0').answer, 0)
  assert.equal(practicePayload({ version_id: 8, type: 'numeric' }, '').answer, null)
  assert.deepEqual(practicePayload({ version_id: 8, type: 'multiple' }, ['B', 'A']).answer, ['B', 'A'])
  assert.throws(() => practicePayload({ version_id: 8, type: 'numeric' }, 'Infinity'))
})

test('practice verifies current identity and CSRF, preserves caller key and lists own filtered history', async () => {
  const calls = []
  let user = { id: 1, role: 'student' }
  const api = new PracticeClient(user, async (path, options) => {
    calls.push({ path, options })
    return { ok: true, json: async () => ({ data: path.endsWith('/session') ? { user, csrf_token: 'fresh' } : [], total: 0 }) }
  })
  await api.practice(2, { question_version_id: 8, answer: false }, 'original-key')
  assert.equal(calls[1].options.headers['Idempotency-Key'], 'original-key')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh')
  assert.equal(calls[1].path, '/api/v1/questions/2/practice-attempts')
  await api.wrong({ page: 2, knowledgeId: 5 })
  assert.match(calls.at(-1).path, /users\/me\/wrong-questions\?page=2&page_size=20&knowledge_id=5/)
  user = { id: 2, role: 'student' }
  await assert.rejects(api.practice(2, {}, 'key'), /登录状态/)
  user = { id: 1, role: 'teacher' }
  await assert.rejects(api.practice(2, {}, 'key'), /登录角色/)
  assert.equal(calls.filter(c => c.options.method === 'POST').length, 1)
})
