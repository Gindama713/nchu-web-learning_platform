// 课堂投票的接口封装。
// 读接口（列表 / 详情 / 结果）不需要 CSRF；写接口（发起 / 投票 / 结束）需要，
// 所以票据拿到一次就缓存，遇到 CSRF_FAILED 再清掉重取一次——页面开着不动十几分钟，
// 票据过期是常态，不能让学生看到「提交失败」就结束。

const BASE = '/api/v1'

export class PollError extends Error {
  constructor(message, status, code) {
    super(message)
    this.name = 'PollError'
    this.status = status
    this.code = code
  }
}

export class PollClient {
  constructor(fetcher = fetch) {
    this.fetcher = (...args) => fetcher(...args)
    this.token = null
  }

  async open(path, options = {}) {
    const response = await this.fetcher(`${BASE}${path}`, { credentials: 'same-origin', ...options })
    let body
    try {
      body = await response.json()
    } catch {
      throw new PollError('服务暂时没有响应，稍后再试', response.status)
    }
    if (!response.ok) {
      throw new PollError(body.error?.message ?? `请求失败（${response.status}）`,
        response.status, body.error?.code)
    }
    return body
  }

  async csrf(force = false) {
    if (!this.token || force) {
      const session = await this.open('/auth/session')
      this.token = session.data.csrf_token
    }
    return this.token
  }

  async read(path) {
    return (await this.open(path)).data
  }

  async write(path, method, payload) {
    let last = null
    for (const attempt of [1, 2]) {
      const token = await this.csrf(attempt > 1)
      try {
        const body = await this.open(path, {
          method,
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
          body: JSON.stringify(payload ?? {}),
        })
        return body.data
      } catch (error) {
        // 票据过期才重试一次；业务错误（409/422）直接抛给调用方
        if (error.code !== 'CSRF_FAILED') throw error
        last = error
      }
    }
    throw last
  }

  async list(courseId, status = 'all') {
    const body = await this.open(`/courses/${courseId}/polls?status=${status}&page_size=50`)
    return { items: body.data, total: body.total }
  }

  openPolls(courseId) {
    return this.list(courseId, 'open')
  }

  get(id) {
    return this.read(`/polls/${id}`)
  }

  results(id) {
    return this.read(`/polls/${id}/results`)
  }

  create(courseId, payload) {
    return this.write(`/courses/${courseId}/polls`, 'POST', payload)
  }

  vote(id, optionIds) {
    return this.write(`/polls/${id}/ballots`, 'POST', { option_ids: optionIds })
  }

  close(id) {
    return this.write(`/polls/${id}/close`, 'POST', {})
  }
}
