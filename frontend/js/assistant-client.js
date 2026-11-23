import { AttemptClient } from './attempt-client.js'

// SPEC-020 教学助手客户端：只读问答，不落库。
export class AssistantClient extends AttemptClient {
  async ask(courseId, question, studentId = null) {
    const session = await this.verifySession()
    const payload = studentId ? { question, student_id: studentId } : { question }
    return (await this.request(`/courses/${courseId}/assistant/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
      body: JSON.stringify(payload),
    })).data
  }
}
