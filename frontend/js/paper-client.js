import { QuestionClient } from './question-client.js'

export const paperKinds = { homework: '作业', exam: '考试', quiz: '随堂测' }
export const windowStates = { upcoming: '未开始', open: '进行中', closed: '已截止' }

export class PaperClient extends QuestionClient {
  list(courseId, { page = 1, kind = '', status = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (kind) query.set('kind', kind)
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/papers?${query}`)
  }
  questions(courseId) { return this.all(`/courses/${courseId}/questions`) }
  detail(id) { return this.request(`/papers/${id}`).then(result => result.data) }
  create(courseId, values) { return this.write(`/courses/${courseId}/papers`, 'POST', values) }
  publish(id, values) { return this.write(`/papers/${id}/publish`, 'POST', values) }
}

export function pointsValue(value) {
  if (!/^\d+(\.\d{1,2})?$/.test(String(value).trim())) throw new Error('配分须为正数，最多两位小数。')
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0 || number * 100 > Number.MAX_SAFE_INTEGER) {
    throw new Error('配分超出可用范围。')
  }
  return number
}

export function paperPayload(form, items) {
  if (!form.title.trim() || !items.length) throw new Error('请填写标题并选择至少一道题。')
  const ids = items.map(item => item.question_id)
  if (new Set(ids).size !== ids.length) throw new Error('同一题目不能重复入卷。')
  const values = items.map(item => ({ question_version_id: item.question_version_id, points: pointsValue(item.points) }))
  if (values.reduce((sum, item) => sum + Math.round(item.points * 100), 0) > Number.MAX_SAFE_INTEGER) {
    throw new Error('总配分超出可用范围。')
  }
  return { title: form.title.trim(), kind: form.kind, confidential: form.confidential, items: values }
}

export function publicationPayload(form, confidential, quiz = false) {
  const times = Object.fromEntries((quiz ? ['start_at', 'end_at'] : ['start_at', 'end_at', 'review_at']).map(key => {
    if (!form[key]) throw new Error(quiz ? '请填写开始和截止时间。' : '请填写开始、截止和讲评时间。')
    const date = new Date(form[key])
    if (!Number.isFinite(date.getTime())) throw new Error('时间格式不合法。')
    return [key, date.toISOString()]
  }))
  if (times.start_at >= times.end_at || (!quiz && times.end_at > times.review_at)) {
    throw new Error('开始须早于截止，讲评不得早于截止。')
  }
  if (confidential && (!form.confidentiality_note.trim() || form.confidentiality_note.trim().length > 1000)) {
    throw new Error('保密发布须填写1至1000字确认说明。')
  }
  return { ...times, ...(confidential ? { confidentiality_note: form.confidentiality_note.trim() } : {}) }
}
