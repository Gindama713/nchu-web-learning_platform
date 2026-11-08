// SPEC-018 评测辅助客户端：判分配置、测试集验证发布、学生提交与结果轮询。
// 实验指导/发布入口属 SPEC-009；沙箱执行属后端引擎，本客户端只做 HTTP 组装。
export const runStatusText = {
  queued: '排队中', running: '评测中', accepted: '通过', wrong_answer: '答案错误',
  timeout: '超时', resource_limit: '资源超限', invalid_circuit: '电路无效',
  system_error: '系统故障',
}
export const terminalStatuses = ['accepted', 'wrong_answer', 'timeout', 'resource_limit',
  'invalid_circuit', 'system_error']

export class GradingClient {
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

  async write(path, method, values, extraHeaders = {}) {
    const session = await this.verifySession()
    return (await this.request(path, { method,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token, ...extraHeaders },
      body: JSON.stringify(values) })).data
  }

  // multipart 上传：浏览器自动生成 boundary，不能手工设 Content-Type。
  async upload(path, form, extraHeaders = {}) {
    const session = await this.verifySession()
    return (await this.request(path, { method: 'POST',
      headers: { 'X-CSRF-Token': session.csrf_token, ...extraHeaders }, body: form })).data
  }

  courses() { return this.all('/courses') }
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

  versions(courseId, { experimentId = '', status = '' } = {}) {
    const query = new globalThis.URLSearchParams({ page: 1, page_size: 100 })
    if (experimentId) query.set('experiment_id', experimentId)
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/experiment-versions?${query}`)
  }

  // ---------- 教师：判分配置与测试集 ----------
  putProfile(versionId, values) { return this.write(`/experiment-versions/${versionId}/judge-profile`, 'PUT', values) }
  createSuite(versionId, casesText) {
    return this.write(`/experiment-versions/${versionId}/test-suites`, 'POST', casesPayload(casesText))
  }
  suites(versionId, status = '') {
    const suffix = status ? `?status=${status}` : ''
    return this.request(`/experiment-versions/${versionId}/test-suites${suffix}`)
  }
  suiteDetail(suiteId) { return this.request(`/test-suites/${suiteId}`).then(body => body.data) }
  referenceFiles(versionId) { return this.request(`/experiment-versions/${versionId}/reference-files`) }
  uploadReference(versionId, file, kind) {
    const form = new FormData()
    form.append('kind', kind)
    form.append('file', file)
    return this.upload(`/experiment-versions/${versionId}/reference-files`, form)
  }
  createValidation(suiteId, referenceFileId, negativeFileId) {
    return this.write(`/test-suites/${suiteId}/validations`, 'POST',
      { reference_file_id: referenceFileId, negative_file_id: negativeFileId },
      { 'Idempotency-Key': crypto.randomUUID() })
  }
  validationDetail(validationId) {
    return this.request(`/test-suite-validations/${validationId}`).then(body => body.data)
  }
  publishSuite(suiteId, validationId) {
    return this.write(`/test-suites/${suiteId}/publish`, 'POST', { validation_id: validationId })
  }
  setActiveSuite(versionId, suiteId, revision) {
    return this.write(`/experiment-versions/${versionId}/active-test-suite`, 'PUT',
      { test_suite_id: suiteId, revision })
  }

  // ---------- 学生提交与结果 ----------
  submitCircuit(versionId, file) {
    const form = new FormData()
    form.append('file', file)
    return this.upload(`/experiment-versions/${versionId}/submissions`, form,
      { 'Idempotency-Key': crypto.randomUUID() })
  }
  submissionDetail(submissionId) {
    return this.request(`/submissions/${submissionId}`).then(body => body.data)
  }
  submissionRuns(submissionId, page = 1) {
    return this.request(`/submissions/${submissionId}/runs?page=${page}&page_size=20`)
  }
  runDetail(runId) { return this.request(`/grading-runs/${runId}`).then(body => body.data) }

  // ---------- 教师班级视图与重评 ----------
  courseSubmissions(courseId, { experimentId = '', status = '', page = 1 } = {}) {
    const query = new globalThis.URLSearchParams({ page, page_size: 20 })
    if (experimentId) query.set('experiment_id', experimentId)
    if (status) query.set('status', status)
    return this.request(`/courses/${courseId}/submissions?${query}`)
  }
  regrade(submissionId, reason, testSuiteId = null) {
    const values = testSuiteId ? { reason, test_suite_id: testSuiteId } : { reason }
    return this.write(`/submissions/${submissionId}/regrades`, 'POST', values,
      { 'Idempotency-Key': crypto.randomUUID() })
  }
}

export function profilePayload(form) {
  const topCircuit = String(form.topCircuit || '').trim()
  if (!topCircuit) throw new Error('请填写顶层电路名。')
  let portSchema, limits
  try { portSchema = JSON.parse(form.portSchemaText) } catch { throw new Error('端口 port_schema JSON 不合法。') }
  if (typeof portSchema !== 'object' || portSchema === null || Array.isArray(portSchema)) {
    throw new Error('端口 port_schema 必须是 JSON 对象。')
  }
  const componentList = String(form.componentsText || '').split(/[\s,]+/).filter(Boolean)
  if (!componentList.length) throw new Error('请至少填写一个允许元件。')
  try { limits = JSON.parse(form.limitsText || '{}') } catch { throw new Error('限额 limits JSON 不合法。') }
  if (typeof limits !== 'object' || limits === null || Array.isArray(limits)) {
    throw new Error('限额 limits 必须是 JSON 对象。')
  }
  return { top_circuit: topCircuit, port_schema: portSchema,
    allowed_components: componentList, limits }
}

export function casesPayload(text) {
  let cases
  try { cases = JSON.parse(text) } catch { throw new Error('测试用例 JSON 不合法。') }
  if (!Array.isArray(cases) || !cases.length) throw new Error('测试用例必须是非空数组。')
  return { cases }
}
