// SPEC-014 学习预警客户端：批次生成（幂等键）、预警列表与处理记录。
export class WarningClient {
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

  async write(path, method, values, extraHeaders = {}) {
    const session = await this.verifySession()
    return (await this.request(path, { method,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token, ...extraHeaders },
      body: JSON.stringify(values ?? {}) })).data
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
    return items
  }

  courses() { return this.all('/courses') }

  members(courseId) { return this.all(`/courses/${courseId}/members`) }

  // 返回整个响应：分页元信息里带 analysis_run_id 与 model_status。
  warnings(courseId, { status = '', from = '', to = '', page = 1, pageSize = 50 } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: pageSize })
    if (status) query.set('status', status)
    if (from) query.set('from', from)
    if (to) query.set('to', to)
    return this.request(`/courses/${courseId}/warnings?${query}`)
  }

  createRun(courseId) {
    return this.write(`/courses/${courseId}/warning-runs`, 'POST', {},
      { 'Idempotency-Key': globalThis.crypto.randomUUID() })
  }

  handle(warningId, note) {
    return this.write(`/warnings/${warningId}`, 'PATCH', { status: 'handled', note })
  }
}
