import { QuestionClient } from './question-client.js'

export class AttemptClient extends QuestionClient {
  constructor(user, fetcher = fetch) { super(user.id, fetcher); this.role = user.role }
  async verifySession() {
    const session = await super.verifySession()
    if (session.user.role !== this.role) throw Object.assign(new Error('登录角色已变化，请重新加载。'), { status: 401 })
    return session
  }
  list(courseId, { page = 1, paperId = '', status = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (paperId) query.set('paper_id', paperId)
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/attempts?${query}`)
  }
  papers(courseId) { return this.all(`/courses/${courseId}/papers`) }
  paper(id) { return this.request(`/papers/${id}`).then(result => result.data) }
  detail(id) { return this.request(`/attempts/${id}`).then(result => result.data) }
  grade(id, payload) { return this.write(`/attempts/${id}/manual-scores`, 'PATCH', payload) }
  async submit(id, payload, key, quiz = false) {
    const session = await this.verifySession()
    return (await this.request(`/${quiz ? 'quizzes' : 'papers'}/${id}/attempts`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token, 'Idempotency-Key': key },
      body: JSON.stringify(payload) })).data
  }
}

export function answerPayload(items, values) {
  return { answers: items.map(item => {
    let value = values[item.question_version_id] ?? null
    if (item.type === 'numeric' && value !== null) {
      if (String(value).trim() === '') value = null
      else {
        value = Number(value)
        if (!Number.isFinite(value)) throw new Error('数值作答须为有限数值。')
      }
    }
    return { question_version_id: item.question_version_id, value }
  }) }
}

export function scorePayload(revision, drafts) {
  const items = drafts.filter(item => item.include).map(item => {
    const text = String(item.score).trim()
    if (!/^\d+(\.\d{1,2})?$/.test(text)) throw new Error('评分须为非负数，最多两位小数。')
    const score = Number(text)
    if (!Number.isFinite(score) || score * 100 > Number.MAX_SAFE_INTEGER || score > item.max_score) throw new Error('评分超出可用范围或超过本题配分。')
    if (item.comment.length > 1000) throw new Error('评语最多1000字符。')
    return { question_version_id: item.question_version_id, score, comment: item.comment }
  })
  if (!items.length) throw new Error('请选择至少一道已作答简答题进行批阅。')
  return { revision, items }
}
