// SPEC-015 knowledge graph client: graph query, root focus and guarded edge writes.
export class GraphApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class GraphClient {
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
      throw new GraphApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new GraphApiError(body.error?.message ?? `请求失败（${response.status}）`,
        response.status, body.error?.code, body.request_id)
    }
    return body
  }

  async session() {
    return (await this.request('/auth/session')).data
  }

  async write(path, method, data) {
    const session = await this.session()
    if (!session.csrf_token || !this.userId || session.user?.id !== this.userId) {
      throw new GraphApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
    }
    return (await this.request(path, {
      method,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
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
        throw new GraphApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new GraphApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new GraphApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new GraphApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return items
  }

  courses() { return this.allPages('/courses') }

  graph(courseId, rootId = '') {
    const suffix = rootId ? `?root_id=${encodeURIComponent(rootId)}` : ''
    return this.request(`/courses/${courseId}/knowledge-graph${suffix}`).then(body => body.data)
  }

  addEdge(courseId, payload) {
    return this.write(`/courses/${courseId}/knowledge-edges`, 'POST', payload)
  }
}
