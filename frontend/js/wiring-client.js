// SPEC-017 wiring client: attempts, guarded saves, validation and submission.
export class WiringApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class WiringClient {
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
      throw new WiringApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new WiringApiError(body.error?.message ?? `请求失败（${response.status}）`,
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
      throw new WiringApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
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
      const joiner = path.includes('?') ? '&' : '?'
      const result = await this.request(`${path}${joiner}page=${page}&page_size=100`)
      if (page === 1) total = result.total
      else if (result.total !== total) {
        throw new WiringApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new WiringApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new WiringApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new WiringApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return items
  }

  courses() { return this.allPages('/courses') }

  versions(courseId) {
    return this.allPages(`/courses/${courseId}/experiment-versions?status=published`)
  }

  attempts(courseId, versionId, page = 1) {
    return this.request(`/courses/${courseId}/wiring-attempts` +
      `?experiment_version_id=${versionId}&page=${page}&page_size=50`)
  }

  attempt(id) { return this.request(`/wiring-attempts/${id}`).then(body => body.data) }

  version(id) { return this.request(`/experiment-versions/${id}`).then(body => body.data) }

  actions(id, afterSeq = 0) {
    return this.request(`/wiring-attempts/${id}/actions?after_seq=${afterSeq}&page=1&page_size=200`)
      .then(body => body.data)
  }

  create(versionId) {
    return this.write(`/experiment-versions/${versionId}/wiring-attempts`, 'POST', {})
  }

  save(id, revision, state, actions) {
    return this.write(`/wiring-attempts/${id}`, 'PUT', { revision, state, actions })
  }

  validate(id, revision) {
    return this.write(`/wiring-attempts/${id}/validate`, 'POST', { revision })
  }

  submit(id, revision) {
    const key = globalThis.crypto?.randomUUID?.() ?? `wiring-${Date.now()}`
    return this.write(`/wiring-attempts/${id}/submit`, 'POST', { revision }, { 'Idempotency-Key': key })
  }
}
