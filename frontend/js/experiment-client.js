// SPEC-009 实验辅助客户端：实验、不可变版本与发布。
// 连线过程属 SPEC-017，判分配置/测试集管理属 SPEC-018，本客户端不提供入口。
export const experimentCodes = {
  'EXP-01': 'EXP-01 · 8位ALU',
  'EXP-02': 'EXP-02 · 寄存器与总线',
  'EXP-03': 'EXP-03 · CPU数据通路连线',
  'EXP-04': 'EXP-04 · 简易CPU综合',
}
export const submissionModes = { wiring: '实验箱连线', circuit: '.circ 在线评测' }

export class ExperimentClient {
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
    if (items.length !== total || new Set(items.map(item => item.id)).size !== total) {
      throw new Error('列表已变化，请重新加载。')
    }
    return items
  }

  courses() { return this.all('/courses') }
  knowledge(courseId) { return this.all(`/courses/${courseId}/knowledge-points`) }
  experiments(courseId, page = 1) {
    return this.request(`/courses/${courseId}/experiments?page=${page}&page_size=20`)
  }
  versions(courseId, { page = 1, experimentId = '', status = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (experimentId) query.set('experiment_id', experimentId)
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/experiment-versions?${query}`)
  }
  async detail(id) { return (await this.request(`/experiment-versions/${id}`)).data }
  createExperiment(courseId, values) { return this.write(`/courses/${courseId}/experiments`, 'POST', values) }
  createVersion(experimentId, values) { return this.write(`/experiments/${experimentId}/versions`, 'POST', values) }
  publish(id, values) { return this.write(`/experiment-versions/${id}/publish`, 'POST', values) }
}

export function versionPayload(form) {
  const title = String(form.title || '').trim()
  const objectives = String(form.objectives || '').trim()
  const instructions = String(form.instructions || '').trim()
  if (!title || !objectives || !instructions) throw new Error('请填写版本标题、目标与步骤说明。')
  const modes = [form.wiring && 'wiring', form.circuit && 'circuit'].filter(Boolean)
  if (!modes.length) throw new Error('请至少选择一种提交方式。')
  let panel
  const panelText = String(form.panelText || '').trim()
  if (panelText) {
    try { panel = JSON.parse(panelText) } catch { throw new Error('面板 panel JSON 不合法。') }
  }
  if (form.wiring && !panel) throw new Error('连线提交必须提供面板 panel JSON。')
  let rules
  const rulesText = String(form.rulesText || '').trim()
  try { rules = JSON.parse(rulesText || '{}') } catch { throw new Error('规则 rules JSON 不合法。') }
  if (typeof rules !== 'object' || rules === null || Array.isArray(rules)) {
    throw new Error('规则 rules 必须是 JSON 对象。')
  }
  return { title, objectives, instructions, submission_modes: modes, panel, rules,
    knowledge_ids: [...form.knowledgeIds] }
}

export function publishPayload(form) {
  const times = {}
  for (const key of ['startAt', 'endAt']) {
    if (!form[key]) throw new Error('请填写开始和截止时间。')
    const date = new Date(form[key])
    if (!Number.isFinite(date.getTime())) throw new Error('时间格式不合法。')
    times[key] = date.toISOString()
  }
  if (times.startAt >= times.endAt) throw new Error('开始时间必须早于截止时间。')
  return { start_at: times.startAt, end_at: times.endAt }
}
