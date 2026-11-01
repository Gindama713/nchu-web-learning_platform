// SPEC-007 课堂演示客户端：六个内置场景、动作推进与状态同步。
// 场景引擎在后端 demo.py，前端只负责展示服务端返回的 state，不自行推算。
export const demoPresets = {
  gate: '门电路',
  comb: '组合逻辑',
  sequential: '时序逻辑',
  alu: '运算器',
  memory: '存储器',
  cpu: '指令执行',
}

export const demoActions = { step: '单步', run: '连续运行', pause: '暂停', reset: '复位' }

export const cpuCycles = { fetch: '取指', decode: '译码', execute: '执行', halt: '停机' }

export class DemoClient {
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
        { status: response.status, code: content.error?.code, detail: content.error?.detail })
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

  sessions(courseId, { active = '', page = 1, pageSize = 10 } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: pageSize })
    if (active === true || active === false) query.set('active', String(active))
    return this.request(`/courses/${courseId}/demo-sessions?${query}`)
  }

  createSession(courseId, { preset, experimentVersionId = null } = {}) {
    const values = { preset }
    if (experimentVersionId) values.experiment_version_id = Number(experimentVersionId)
    return this.write(`/courses/${courseId}/demo-sessions`, 'POST', values)
  }

  // afterRevision 交给服务端判定增量；前端用它决定是否重绘。
  session(demoId, afterRevision = null) {
    const suffix = Number.isInteger(afterRevision) ? `?after_revision=${afterRevision}` : ''
    return this.request(`/demo-sessions/${demoId}${suffix}`).then(content => content.data)
  }

  advance(demoId, revision, action) {
    if (!(action in demoActions)) throw new Error(`未知动作：${action}`)
    return this.write(`/demo-sessions/${demoId}/state`, 'PUT', { revision, action })
  }

  close(demoId, revision) {
    return this.write(`/demo-sessions/${demoId}/close`, 'POST', { revision })
  }
}
