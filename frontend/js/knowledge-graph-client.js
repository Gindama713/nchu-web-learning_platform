// SPEC-015 知识图谱客户端：课程知识节点、先修边与传递闭包。
export const edgeTypes = { prerequisite: '先修', contains: '包含' }

export class KnowledgeGraphClient {
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
    return items
  }

  courses() { return this.all('/courses') }

  points(courseId) { return this.all(`/courses/${courseId}/knowledge-points`) }

  graph(courseId, rootId = null) {
    const suffix = Number.isInteger(rootId) ? `?root_id=${rootId}` : ''
    return this.request(`/courses/${courseId}/knowledge-graph${suffix}`).then(content => content.data)
  }

  addEdge(courseId, { sourceId, targetId, type }) {
    if (!(type in edgeTypes)) throw new Error(`未知关系类型：${type}`)
    if (Number(sourceId) === Number(targetId)) throw new Error('边两端不能是同一个知识点。')
    return this.write(`/courses/${courseId}/knowledge-edges`, 'POST',
      { source_id: Number(sourceId), target_id: Number(targetId), type })
  }
}
