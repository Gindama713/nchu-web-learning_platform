// SPEC-004 preparation client: draft units, course links, copy, publish and withdraw.
export class PreparationApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class PreparationClient {
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
      throw new PreparationApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new PreparationApiError(body.error?.message ?? `请求失败（${response.status}）`,
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
      throw new PreparationApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
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
        throw new PreparationApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new PreparationApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new PreparationApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new PreparationApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return items
  }

  courses() { return this.allPages('/courses') }

  chapters(courseId) { return this.allPages(`/courses/${courseId}/chapters`) }

  knowledge(courseId) { return this.allPages(`/courses/${courseId}/knowledge-points`) }

  resources(courseId) { return this.allPages(`/courses/${courseId}/resources`) }

  questions(courseId) { return this.allPages(`/courses/${courseId}/questions`) }

  quizzes(courseId) { return this.allPages(`/courses/${courseId}/quizzes`) }

  list(courseId, page = 1) {
    return this.request(`/courses/${courseId}/preparations?page=${page}&page_size=20`)
  }

  detail(id) { return this.request(`/preparations/${id}`).then(body => body.data) }

  create(courseId, data) { return this.write(`/courses/${courseId}/preparations`, 'POST', data) }

  update(id, data) { return this.write(`/preparations/${id}`, 'PATCH', data) }

  copy(id, title) { return this.write(`/preparations/${id}/copy`, 'POST', { title }) }

  publish(id, replacesId = null) {
    return this.write(`/preparations/${id}/publish`, 'POST',
      replacesId ? { replaces_id: Number(replacesId) } : {})
  }

  withdraw(id, reason) { return this.write(`/preparations/${id}/withdraw`, 'POST', { reason }) }
}
