// SPEC-003 teaching resources client: upload, versions, list, content, update, import.
export class ResourceApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class ResourceClient {
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
      throw new ResourceApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new ResourceApiError(body.error?.message ?? `请求失败（${response.status}）`,
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
      throw new ResourceApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
    }
    const form = data instanceof FormData
    return (await this.request(path, {
      method,
      credentials: 'same-origin',
      headers: {
        ...(form ? {} : { 'Content-Type': 'application/json' }),
        'X-CSRF-Token': session.csrf_token,
        ...extraHeaders,
      },
      body: form ? data : JSON.stringify(data),
    })).data
  }

  async allPages(path) {
    const items = []
    let total
    for (let page = 1; ; page++) {
      const result = await this.request(`${path}?page=${page}&page_size=100`)
      if (page === 1) total = result.total
      else if (result.total !== total) {
        throw new ResourceApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new ResourceApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new ResourceApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new ResourceApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return items
  }

  courses() { return this.allPages('/courses') }

  chapters(courseId) { return this.allPages(`/courses/${courseId}/chapters`) }

  list(courseId, { page = 1, q = '', kind = '', chapterId = '' } = {}) {
    const params = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (q.trim()) params.set('q', q.trim())
    if (kind) params.set('kind', kind)
    if (chapterId) params.set('chapter_id', chapterId)
    return this.request(`/courses/${courseId}/resources?${params}`)
  }

  versions(resourceId, page = 1) {
    return this.request(`/resources/${resourceId}/versions?page=${page}&page_size=20`)
  }

  upload(courseId, form) { return this.write(`/courses/${courseId}/resources`, 'POST', form) }

  addVersion(resourceId, form) { return this.write(`/resources/${resourceId}/versions`, 'POST', form) }

  update(resourceId, data) { return this.write(`/resources/${resourceId}`, 'PATCH', data) }

  importQuestions(resourceId, versionId) {
    return this.write(`/resources/${resourceId}/question-imports`, 'POST',
      { resource_version_id: versionId },
      { 'Idempotency-Key': crypto.randomUUID() })
  }
}

// 每次明确打开预览或下载生成一个新 event_id；重试与 Range 分片复用同 ID 由调用方控制。
export function contentUrl(versionId, intent, eventId) {
  return `/api/v1/resource-versions/${versionId}/content?intent=${intent}&event_id=${encodeURIComponent(eventId)}`
}
