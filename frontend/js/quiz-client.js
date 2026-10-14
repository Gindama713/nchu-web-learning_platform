import { PaperClient } from './paper-client.js'

export class QuizClient extends PaperClient {
  list(courseId, { page = 1, status = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/quizzes?${query}`)
  }
  async publish(id, values, courseId) {
    await this.write(`/courses/${courseId}/quizzes`, 'POST', { paper_id: id, ...values })
    return this.detail(id)
  }
}
