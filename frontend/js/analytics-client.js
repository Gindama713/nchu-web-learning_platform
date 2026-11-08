import { AttemptClient } from './attempt-client.js'

export class AnalyticsClient extends AttemptClient {
  query(courseId, filters) {
    const params = new globalThis.URLSearchParams({ dimension: filters.dimension })
    for (const key of ['from', 'to', 'student_id']) if (filters[key]) params.set(key, filters[key])
    if (filters.dimension === 'scores') {
      params.set('kind', filters.kind)
      if (filters.paper_id) params.set('paper_id', filters.paper_id)
    }
    return this.request(`/courses/${courseId}/analytics?${params}`).then(r => r.data)
  }
  restore(courseId, id) {
    return this.request(`/courses/${courseId}/analytics?${new globalThis.URLSearchParams({ analysis_run_id: id })}`).then(r => r.data)
  }
  async csv(courseId, id) {
    await this.verifySession()
    if (this.role !== 'teacher') throw Object.assign(new Error('仅教师可以导出统计。'), { status: 403 })
    const params = new globalThis.URLSearchParams({ analysis_run_id: id, format: 'csv' })
    const response = await this.fetcher(`/api/v1/courses/${courseId}/analytics/export?${params}`, { credentials: 'same-origin', cache: 'no-store' })
    if (!response.ok) {
      let message = '快照暂不可用，请重新查询。'
      try { message = (await response.json()).error?.message ?? message } catch { /* Use the fallback. */ }
      throw Object.assign(new Error(message), { status: response.status })
    }
    if (!response.headers.get('Content-Type')?.startsWith('text/csv')) throw new Error('导出响应无效，请重试。')
    return response.blob()
  }
}
