// SPEC-005 consumes real session/course APIs. No default identity or fixture data.
export class KnowledgeApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export class KnowledgeClient {
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
      throw new KnowledgeApiError('服务暂时无法返回数据，请稍后重试', response.status)
    }
    if (!response.ok) {
      throw new KnowledgeApiError(body.error?.message ?? `请求失败（${response.status}）`,
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
      throw new KnowledgeApiError('登录状态已变化，请重新加载课程', 401, 'UNAUTHENTICATED')
    }
    return (await this.request(path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
      body: JSON.stringify(data),
    })).data
  }

  async allPages(path, revisionKey) {
    const items = []
    let total, revision
    for (let page = 1; ; page++) {
      const result = await this.request(`${path}?page=${page}&page_size=100`)
      if (page === 1) {
        total = result.total
        revision = revisionKey ? result[revisionKey] : undefined
      } else if (result.total !== total || (revisionKey && result[revisionKey] !== revision)) {
        throw new KnowledgeApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
      }
      if (!Array.isArray(result.data) || !Number.isInteger(total) || total < 0) {
        throw new KnowledgeApiError('列表响应格式不正确，请重试', 503)
      }
      items.push(...result.data)
      if (items.length >= total) break
      if (result.data.length === 0) throw new KnowledgeApiError('列表加载不完整，请重试', 503)
    }
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new KnowledgeApiError('列表已变化，请刷新后重试', 409, 'REVISION_CONFLICT')
    }
    return { items, revision }
  }

  courses() { return this.allPages('/courses') }
  chapters(courseId) { return this.allPages(`/courses/${courseId}/chapters`, 'chapters_revision') }

  list(courseId, { page = 1, q = '', chapterId = '' } = {}) {
    const params = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (q.trim()) params.set('q', q.trim())
    if (chapterId) params.set('chapter_id', chapterId)
    return this.request(`/courses/${courseId}/knowledge-points?${params}`)
  }

  async detail(id) { return (await this.request(`/knowledge-points/${id}`)).data }
  addChapter(courseId, title) { return this.write(`/courses/${courseId}/chapters`, 'POST', { title }) }
  renameChapter(id, title) { return this.write(`/chapters/${id}`, 'PATCH', { title }) }
  reorder(courseId, revision, ids) {
    return this.write(`/courses/${courseId}/chapter-order`, 'PUT', {
      chapters_revision: revision, chapter_ids: ids,
    })
  }
  create(chapterId, data) { return this.write(`/chapters/${chapterId}/knowledge-points`, 'POST', data) }
  update(id, data) { return this.write(`/knowledge-points/${id}`, 'PATCH', data) }
  bookmark(id, bookmarked) { return this.write(`/knowledge-points/${id}/bookmark`, 'PUT', { bookmarked }) }
  progress(id, completed) { return this.write(`/knowledge-points/${id}/progress`, 'PUT', { completed }) }
}

