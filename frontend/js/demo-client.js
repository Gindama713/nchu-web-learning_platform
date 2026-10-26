// SPEC-007 classroom demo client: preset sessions, revision-guarded actions, polling.
export class DemoApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class DemoClient {
  constructor(fetcher = fetch) {
    this.fetcher = (...args) => fetcher(...args)
    this.userId = null
  }

  async request(path, options = {}) {
    const response = await this.fetcher(`/api/v1${path}`, { credentials: 'same-origin', ...options })
    let body
    try {
      body = await response.json()
    } catch {
      throw new DemoApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new DemoApiError(body.error?.message ?? `请求失败（${response.status}）`,
        response.status, body.error?.code, body.request_id)
    }
    return body
  }

  async session() {
    return (await this.request('/auth/session')).data
  }

  async write(path, method, data, extraHeaders = {}) {
    const session = await this.session()
    if (!session.csrf_token || !this.userId || session.user?.id !== this.userId) {
      throw new DemoApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
    }
    return (await this.request(path, {
      method,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token, ...extraHeaders },
      body: JSON.stringify(data),
    })).data
  }

  async allPages(path) {
    const items = []
    let total
    for (let page = 1; ; page++) {
      const result = await this.request(`${path}?page=${page}&page_size=100`)
      if (page === 1) total = result.total
      else if (result.total !== total) {
        throw new DemoApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new DemoApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new DemoApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new DemoApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return items
  }

  courses() { return this.allPages('/courses') }

  list(courseId, page = 1) {
    return this.request(`/courses/${courseId}/demo-sessions?page=${page}&page_size=50`)
  }

  get(id) { return this.request(`/demo-sessions/${id}`).then(body => body.data) }

  create(courseId, preset) {
    return this.write(`/courses/${courseId}/demo-sessions`, 'POST', { preset })
  }

  advance(id, revision, action) {
    return this.write(`/demo-sessions/${id}/state`, 'PUT', { revision, action })
  }

  close(id, revision) { return this.write(`/demo-sessions/${id}/close`, 'POST', { revision }) }
}
