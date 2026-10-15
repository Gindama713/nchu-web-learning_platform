import { PaperClient, pointsValue } from './paper-client.js'

const integer = (value, min, max, label) => {
  if (!/^\d+$/.test(String(value).trim())) throw new Error(`${label}须为整数。`)
  const number = Number(value)
  if (!Number.isSafeInteger(number) || number < min || number > max) throw new Error(`${label}超出范围。`)
  return number
}

export function generationPayload(form, replay = false) {
  const title = form.title.trim()
  if (!title || title.length > 100) throw new Error('请填写1至100字的新试卷标题。')
  if (replay) return { title, replay_of: integer(form.replay_of, 1, Number.MAX_SAFE_INTEGER, '快照编号') }
  const count = integer(form.count, 1, 100, '题量')
  const difficulty_counts = Object.fromEntries(['easy', 'medium', 'hard'].map(key =>
    [key, integer(form[key], 0, 100, '难度配额')]))
  if (Object.values(difficulty_counts).reduce((a, b) => a + b, 0) !== count) throw new Error('难度配额总和须等于题量。')
  const total_points = pointsValue(form.total_points)
  if (total_points < 1 || total_points > 1000) throw new Error('总分须在1至1000之间。')
  const body = { title, kind: form.kind, count, total_points, difficulty_counts,
    knowledge_ids: [...form.knowledge_ids], confidential: form.confidential }
  if (String(form.seed).trim()) {
    const seed = String(form.seed).trim()
    if (!/^-?\d+$/.test(seed) || BigInt(seed) < -(2n ** 63n) || BigInt(seed) >= 2n ** 63n) {
      throw new Error('随机种子须为64位有符号整数。')
    }
    body.seed = BigInt(seed).toString()
  }
  if (form.history_until) {
    const date = new Date(form.history_until)
    if (!Number.isFinite(date.getTime())) throw new Error('历史截止时间格式不合法。')
    body.history_until = date.toISOString()
  }
  return body
}

export class GenerationClient extends PaperClient {
  async generate(courseId, form, replay = false) {
    const values = generationPayload(form, replay)
    const session = await this.verifySession()
    // Keep signed 64-bit seed exact: encode its validated decimal as a JSON
    // number without passing it through JavaScript Number or changing API type.
    const body = '{' + Object.entries(values).map(([key, value]) =>
      `${JSON.stringify(key)}:${key === 'seed' ? value : JSON.stringify(value)}`).join(',') + '}'
    return (await this.request(`/courses/${courseId}/generated-papers`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token }, body })).data
  }
}

export function generationFailure(error) {
  const guidance = {
    INFEASIBLE_CONSTRAINTS: '请减少题量、调整难度配额或减少必选知识点。',
    SEARCH_LIMIT: '请缩小题量或知识覆盖范围后重试；本次没有生成草稿。',
    QUESTION_PUBLIC: '原选题已有公开历史。请重新生成，或取消保密后首次生成。',
    QUESTION_RESERVED: '题目正在其他试卷保护期内，请等待讲评后重试或重新选题。',
    QUESTION_UNAVAILABLE: '原选题已不可用，请使用首次生成选择当前题库。',
    SNAPSHOT_UNAVAILABLE: '快照校验失败，请联系教师管理员核查原快照。',
    DB_BUSY: '数据库忙，请稍后重试。',
  }
  return `${error.message}${guidance[error.code] ? ` ${guidance[error.code]}` : ''}`
}
