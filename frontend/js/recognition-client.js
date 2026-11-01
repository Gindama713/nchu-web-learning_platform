// SPEC-016 识别辅助客户端：上传图片做模板匹配，再人工确认结构草稿。
export const gateSymbols = ['NOT', 'AND', 'OR', 'XOR']
export const pinLabels = ['A', 'B', 'Y', 'D', 'Q', 'CLK', 'RESET', 'EN', 'PC', 'ACC', 'IR']

export class RecognitionClient {
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

  // FormData 不能手动设 Content-Type，交给浏览器带 boundary。
  async write(path, method, values) {
    const session = await this.verifySession()
    const form = values instanceof FormData
    return (await this.request(path, { method,
      headers: { ...(form ? {} : { 'Content-Type': 'application/json' }), 'X-CSRF-Token': session.csrf_token },
      body: form ? values : JSON.stringify(values) })).data
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

  create(courseId, file) {
    const form = new FormData()
    form.append('image', file)
    return this.write(`/courses/${courseId}/recognitions`, 'POST', form)
  }

  confirm(recognitionId, items) {
    return this.write(`/recognitions/${recognitionId}/confirm`, 'POST', {
      items: items.map(({ symbol, bbox, label }) => ({ symbol, bbox, label: label ?? null })),
    })
  }
}
