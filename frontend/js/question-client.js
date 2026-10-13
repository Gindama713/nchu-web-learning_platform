export class QuestionClient {
  constructor(userId, fetcher = fetch) {
    this.userId = userId
    this.fetcher = (...args) => fetcher(...args)
  }

  async request(path, options = {}) {
    const response = await this.fetcher(`/api/v1${path}`, { credentials: 'same-origin', ...options })
    let content
    try { content = await response.json() } catch {
      throw Object.assign(new Error('服务未返回有效数据，请重试。'), { status: response.status })
    }
    if (!response.ok) {
      throw Object.assign(new Error(content.error?.message ?? '请求失败，请重试。'),
        { status: response.status, code: content.error?.code })
    }
    return content
  }

  async verifySession() {
    const session = (await this.request('/auth/session')).data
    if (session.user?.id !== this.userId || !session.csrf_token) {
      throw Object.assign(new Error('登录状态已变化，请重新加载页面。'), { status: 401 })
    }
    return session
  }

  async write(path, method, values) {
    const session = await this.verifySession()
    return (await this.request(path, { method,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
      body: JSON.stringify(values) })).data
  }

  async all(path) {
    const items = []
    let total
    for (let page = 1; ; page++) {
      const result = await this.request(`${path}?page=${page}&page_size=100`)
      if (page === 1) total = result.total
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0 || total !== result.total) {
        throw new Error('列表已变化或响应不完整，请重新加载。')
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (!result.data.length) throw new Error('列表加载不完整，请重试。')
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new Error('列表已变化，请重新加载。')
    }
    return items
  }

  courses() { return this.all('/courses') }
  knowledge(courseId) { return this.all(`/courses/${courseId}/knowledge-points`) }
  list(courseId, { page = 1, type = '', difficulty = '', knowledgeId = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (type) query.set('type', type)
    if (difficulty) query.set('difficulty', difficulty)
    if (knowledgeId) query.set('knowledge_id', knowledgeId)
    return this.request(`/courses/${courseId}/questions?${query}`)
  }
  create(courseId, values) { return this.write(`/courses/${courseId}/questions`, 'POST', values) }
  update(id, values) { return this.write(`/questions/${id}`, 'PATCH', values) }
}

export const questionTypes = { single: '单选', multiple: '多选', boolean: '判断', numeric: '数值', short: '简答' }
export const difficulties = { easy: '简单', medium: '中等', hard: '困难' }

export function emptyQuestion(type = 'single') {
  const choice = type === 'single' || type === 'multiple'
  return { type, stem: '', difficulty: 'easy', knowledge_ids: [], explanation: '', tolerance: 0,
    practice_available: false, options: choice ? [{ key: 'A', text: '' }, { key: 'B', text: '' }] : [],
    answer: type === 'multiple' ? [] : type === 'boolean' ? true : '' }
}

export function questionPayload(form) {
  const value = { ...form, options: form.options.map(item => ({ ...item })), knowledge_ids: [...form.knowledge_ids] }
  if (form.type === 'numeric') {
    if (String(form.answer).trim() === '' || String(form.tolerance).trim() === '') throw new Error('数值答案和容差须填写。')
    value.answer = Number(form.answer)
    value.tolerance = Number(form.tolerance)
    if (!Number.isFinite(value.answer) || !Number.isFinite(value.tolerance) || value.tolerance < 0) {
      throw new Error('数值答案须有限，容差须为非负有限数值。')
    }
  }
  return value
}
