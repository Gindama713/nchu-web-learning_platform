import { AttemptClient, answerPayload } from './attempt-client.js'

export class PracticeClient extends AttemptClient {
  questions(courseId, { page = 1, knowledgeId = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (knowledgeId) query.set('knowledge_id', knowledgeId)
    return this.request(`/courses/${courseId}/questions?${query}`)
  }
  wrong({ page = 1, knowledgeId = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (knowledgeId) query.set('knowledge_id', knowledgeId)
    return this.request(`/users/me/wrong-questions?${query}`)
  }
  async practice(questionId, payload, key) {
    const session = await this.verifySession()
    if (session.user.role !== 'student') throw new Error('仅学生可提交练习。')
    return (await this.request(`/questions/${questionId}/practice-attempts`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token, 'Idempotency-Key': key },
      body: JSON.stringify(payload) })).data
  }
}

export function practicePayload(question, value) {
  const id = question.version_id
  const result = answerPayload([{ ...question, question_version_id: id }], { [id]: value })
  return { question_version_id: id, answer: result.answers[0].value }
}
