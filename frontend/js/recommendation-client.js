import { AttemptClient } from './attempt-client.js'

export class RecommendationClient extends AttemptClient {
  async recommendations(courseId, limit = 5) {
    if (!Number.isInteger(Number(limit)) || Number(limit) < 1 || Number(limit) > 20) throw new Error('推荐数量须为1至20的整数。')
    return (await this.request(`/courses/${courseId}/recommendations?${new globalThis.URLSearchParams({ limit })}`)).data
  }
  async knowledgeDetail(id) { return (await this.request(`/knowledge-points/${id}`)).data }
}

export const recommendationReasons = {
  foundational: '教师标记的基础知识，尚未完成',
  insufficient_sample: '样本较少（不足5次），建议继续练习',
  weakness: '客观作答掌握度低于80%，建议巩固',
  incomplete: '尚未完成，建议继续学习',
}
export const recommendationStates = {
  ok: '已按薄弱程度和完成状态排序。',
  cold_start: '当前已发布知识暂无近28天有效客观作答，先学习未完成的基础内容。',
  no_foundational_candidates: '暂无未完成的基础知识可推荐，请联系教师确认基础标记或浏览课程知识。',
  all_mastered: '当前知识均已完成且有足够样本达到掌握标准，暂无推荐。',
  no_published_knowledge: '课程暂无已发布知识，请等待教师发布。',
}
