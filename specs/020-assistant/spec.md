# SPEC-020 教学助手规格

[统一验收 AC-01 至 AC-09](../../docs/PRD.md#accept-spec-020) · [接口契约 第16节](../../docs/APIC.md)

接口：`POST /api/v1/courses/{course_id}/assistant/ask`，必填 `question`（1—200 字），可选 `student_id` 仅允许教师传本课有效学生。学生身份取自会话；学生指定目标返回 403，非成员或教师查询非本课学生返回 404。写方法仍遵守既有 Origin 与 CSRF 校验。

返回 `intent/title/answer/facts/caveats/actions/suggestions/charts`，以及 `role/question/student_id/student/algorithm_version/window/source_until`。数字保留来源 `source`；缺样本返回空事实或 null 并解释，单源不可用只降级该部分。不落 `analysis_run`，不写业务事实。

教师支持班级学情、考勤、成绩、薄弱项、预警、教学建议、单生资料及最近点名缺勤。学生只支持本人考勤、成绩、做题、进度与下一步练习；知识问题复用已发布知识检索。无法匹配时给澄清候选；教师指代依靠显式上下文，班级问题不继承单生目标。

`assistant-rules-v2` 对重名或多目标问题先返回带完整学号的选人候选，不自动选第一人；「某同学没签到吗」保持单生考勤意图。学号格式与注册的 8—20 位字母/数字一致，前后端指代词保持一致；空图表数值不得转成 0。

图表最多两张，只用与文字同次计算的数字。环形、横条、折线由前端共享 SVG 绘制；折线至少两个有数据周，空样本不出图。动作仍调用原业务接口及其权限与幂等约束。本摘要不构成第二套接口，细节以主文档为准。
