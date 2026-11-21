# 课堂互测测试报告（第 1 次）

- 提交人：姜苏豪（24201718），英文名 jiangsuhao
- 测试方：242017 班第 10 组 g24201710
- 被测组：g24201803（242018班第3组）
- 被测地址：http://10.83.88.135:5000
- 测试时间：2026-11-06 16:52:04 中国标准时间
- 测试依据：老师《下午的测试方案》、被测组公开的 `/who` 与 `/help`、被测组测试计划
- 自动化脚本：`scripts/verify_g24201803.py`（Python 3 标准库，无第三方依赖）；运行 `python scripts/verify_g24201803.py` 可复现全部用例并重新生成本报告与缺陷表。脚本按 `/help` 动态适配被测组的 `/api` 契约；原始请求日志另存本地，不随文档提交

## 1 测试范围

- 被测对象为 g24201803（242018班第3组）的 CPU-Learn 系统，`/help` 声明 15 个模块 / 198 条接口。
- 本组今日为 C 组；除老师要求的**冒烟 + 接口**外，另扩展到 15 个业务模块逐项抽查、权限与越权、参数边界、数据一致性、日志导出、实验端点、取消分支、座位图及浏览器入口验证，并给出「主要功能是否正确」的明确结论。
- 未执行项（不计为通过，也不计为被测组缺陷）：74181 全 512 组运算、并发占座与座位边界、浏览器交互级双会话 E2E、后端重启持久化；源码审计、性能压测、安全渗透、真实设备定位不在范围。
- 环境：课堂局域网，Python 3 标准库脚本直连（显式禁用系统代理）；所有写请求先取 `/api/auth/csrf` 令牌并带同源 `Origin`。
- 被测系统关键契约（实测）：登录用 `username/password`；写操作需 `X-CSRF-Token`；发布/关闭任务需携带 `revision`；签到需 `method=code` 与 `Idempotency-Key` 请求头（幂等键），重复提交同一键值返回同一条记录。

## 2 用例统计

| 层级 | 用例数 | 通过 | 失败 | 未执行 | 阻塞 |
|---|---|---|---|---|---|
| 冒烟 | 8 | 8 | 0 | 0 | 0 |
| 接口 | 10 | 9 | 1 | 0 | 0 |
| 功能 | 12 | 11 | 0 | 1 | 0 |
| E2E | 3 | 2 | 0 | 1 | 0 |
| 模块抽查 | 15 | 15 | 0 | 0 | 0 |
| 权限 | 5 | 5 | 0 | 0 | 0 |
| 边界 | 5 | 5 | 0 | 0 | 0 |
| 一致性 | 1 | 1 | 0 | 0 | 0 |
| 日志 | 2 | 2 | 0 | 0 | 0 |
| 实验 | 2 | 1 | 0 | 1 | 0 |
| 回归 | 1 | 0 | 0 | 1 | 0 |
| **合计** | **64** | **59** | **1** | **4** | **0** |

### 逐条结果

| ID | 层级 | 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|---|---|
| SM-01 | 冒烟 | 首页可访问 | HTTP 200 且返回页面 | HTTP 200 | 通过 |
| SM-02 | 冒烟 | 公开接口 /who 返回小组信息 | HTTP 200，含班级/组号/组长/成员 | HTTP 200，组号=3组，组长=范一航 | 通过 |
| SM-03 | 冒烟 | 公开接口 /help 提供接口清单 | HTTP 200 且可解析的模块/端点清单 | HTTP 200，15 模块 / 198 端点 | 通过 |
| SM-04 | 冒烟 | 健康检查 /api/health/live | HTTP 200 且就绪标志为真 | HTTP 200，alive=True | 通过 |
| SM-05 | 冒烟 | 健康检查 /api/health/ready | HTTP 200 且就绪标志为真 | HTTP 200，ready=True | 通过 |
| SM-06 | 冒烟 | 公开获取 CSRF 令牌 | HTTP 200 且返回 csrf_token | HTTP 200，令牌=有 | 通过 |
| SM-07 | 冒烟 | 教师账号登录 | HTTP 200 且角色 teacher | HTTP 200，role=teacher | 通过 |
| SM-08 | 冒烟 | 教师可见任教班级 | HTTP 200 且至少 1 个班级 | HTTP 200，班级数=4 | 通过 |
| API-01 | 接口 | /who 拒绝非 GET 方法 | HTTP 405 | HTTP 405 HTTP_ERROR | 通过 |
| API-02 | 接口 | /help 拒绝非 GET 方法 | HTTP 405 | HTTP 405 HTTP_ERROR | 通过 |
| API-03 | 接口 | 匿名访问 /api/classes 被鉴权拒绝 | HTTP 401 UNAUTHENTICATED | HTTP 401 UNAUTHENTICATED | 通过 |
| API-04 | 接口 | 匿名访问 /api/audit-logs 被鉴权拒绝 | HTTP 401 UNAUTHENTICATED | HTTP 401 UNAUTHENTICATED | 通过 |
| API-05 | 接口 | 错误密码登录被拒绝 | HTTP 4xx 且不建立会话 | HTTP 401 INVALID_CREDENTIALS | 通过 |
| API-06 | 接口 | 登录请求拒绝不支持字段 | HTTP 422 VALIDATION_ERROR | HTTP 422 VALIDATION_ERROR | 通过 |
| API-07 | 接口 | 写请求缺少 CSRF 令牌被拒绝 | HTTP 403 CSRF_INVALID | HTTP 403 CSRF_INVALID | 通过 |
| API-08 | 接口 | 跨站 Origin 写请求被拒绝 | HTTP 403 | HTTP 403 CSRF_INVALID | 通过 |
| API-09 | 接口 | /help 公开端点声明与实际一致 | 实际可匿名访问的端点都列入 public_endpoints | /help 仅声明 2 个公开端点；实测另可匿名访问 3 个：/api/health/live, /api/health/ready, /api/auth/csrf | 失败 |
| API-10 | 接口 | 未登录读取班级成员被拒绝 | HTTP 401 | HTTP 401 UNAUTHENTICATED | 通过 |
| FUNC-01 | 功能 | 教师创建点到草稿任务 | HTTP 201 且 status=draft | HTTP 201，task_id=107，status=draft | 通过 |
| FUNC-02 | 功能 | 发布点到任务 | HTTP 200 且状态不再是 draft | HTTP 200，status=open | 通过 |
| FUNC-03 | 功能 | 教师获取 6 位点到码 | HTTP 200 且返回 6 位数字码 | HTTP 200，code=已返回 | 通过 |
| FUNC-04 | 功能 | 学生账号登录 | HTTP 200 且角色 student | HTTP 200，role=student | 通过 |
| FUNC-05 | 功能 | 错误点到码被拒绝 | HTTP 4xx 且不产生签到记录 | HTTP 422 CHECKIN_INVALID | 通过 |
| FUNC-06 | 功能 | 学生按正确点到码签到 | HTTP 200/201 且产生记录 | HTTP 200，记录 id=2718，状态=present | 通过 |
| FUNC-07 | 功能 | 重复签到不新增记录 | 返回同一条记录，不重复计数 | HTTP 200，首次 id=2718，重复 id=2718 | 通过 |
| FUNC-08 | 功能 | 教师读取座位图/签到记录/报表 | 三个接口均 HTTP 200 | seats=200，records=200，report=200 | 通过 |
| FUNC-09 | 功能 | 教师关闭任务并结算缺勤 | HTTP 200 且返回统计 | HTTP 200，present=1，absent=34 | 通过 |
| E2E-01 | E2E | 教师建任务→发布→取码→学生签到→读统计→关闭 | 全链路无阻断，状态与统计一致 | 关键环节全部通过 | 通过 |
| MOD-01 | 模块抽查 | analytics：/api/exports/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-02 | 模块抽查 | assessments：/api/papers/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-03 | 模块抽查 | attendance：/api/attendance-tasks/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-04 | 模块抽查 | auth：/api/me | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-05 | 模块抽查 | classroom：/api/classroom-sessions/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-06 | 模块抽查 | experiments：/api/judge-runs/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-07 | 模块抽查 | knowledge：/api/me/bookmarks | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 403，统一JSON | 通过 |
| MOD-08 | 模块抽查 | knowledge_graph：/api/knowledge/5/learning-path | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-09 | 模块抽查 | lesson_plans：/api/lesson-plans/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-10 | 模块抽查 | paper_generation：/api/paper-generations/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| MOD-11 | 模块抽查 | quizzes：/api/classroom-quizzes/5/review | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-12 | 模块抽查 | recognition：/api/recognitions/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-13 | 模块抽查 | recommendations：/api/classes/5/recommendations | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 403，统一JSON | 通过 |
| MOD-14 | 模块抽查 | resources：/api/resources/5 | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 404，统一JSON | 通过 |
| MOD-15 | 模块抽查 | warnings：/api/classes/5/warnings | 路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在） | HTTP 200，统一JSON | 通过 |
| PERM-01 | 权限 | 学生创建点到任务 | HTTP 403 FORBIDDEN，数据不被改变 | HTTP 403 FORBIDDEN | 通过 |
| PERM-02 | 权限 | 学生读取审计日志 | HTTP 403 FORBIDDEN，数据不被改变 | HTTP 403 FORBIDDEN | 通过 |
| PERM-03 | 权限 | 学生读取用户列表 | HTTP 403 FORBIDDEN，数据不被改变 | HTTP 403 FORBIDDEN | 通过 |
| PERM-04 | 权限 | 学生读取教师统计 | HTTP 403 FORBIDDEN，数据不被改变 | HTTP 403 FORBIDDEN | 通过 |
| PERM-05 | 权限 | 教师读取全局审计日志 | HTTP 403（审计日志为管理员专属） | HTTP 403 FORBIDDEN | 通过 |
| BND-01 | 边界 | 创建点到任务缺少必填字段 | HTTP 422 且返回明确错误码 | HTTP 422 VALIDATION_ERROR | 通过 |
| BND-02 | 边界 | 点到任务结束时间早于开始时间 | HTTP 422 且返回明确错误码 | HTTP 422 VALIDATION_ERROR | 通过 |
| BND-03 | 边界 | 非法分页参数 page_size=-5 | HTTP 422 且返回明确错误码 | HTTP 422 VALIDATION_ERROR | 通过 |
| BND-04 | 边界 | 访问不存在的点到任务 | HTTP 404 且返回明确错误码 | HTTP 404 NOT_FOUND | 通过 |
| BND-05 | 边界 | 访问不存在的班级成员 | HTTP 404 且返回明确错误码 | HTTP 404 NOT_FOUND | 通过 |
| DATA-01 | 一致性 | 签到明细与 CSV 报表数据一致 | records 中 present 学号均出现在 report 导出且状态一致 | records=200（20 条，present 1 人），report=200，学号匹配=是 | 通过 |
| LOG-01 | 日志 | 教师创建统计导出任务 | HTTP 202 且返回 export_id | HTTP 202，export_id=20 | 通过 |
| LOG-02 | 日志 | 查询导出任务结果 | HTTP 200 且返回导出状态 | HTTP 200  | 通过 |
| LAB-01 | 实验 | 74181 实验端点在 /help 中声明 | 存在 74181 相关端点 | 发现 1 条：/api/courses/<int:course_id>/experiments/74181 | 通过 |
| LAB-02 | 实验 | 74181 全 512 组加减运算向量校验 | 按独立参考实现逐组比对 F 与进位/借位 | 被测组未公开纯计算 GET 接口，运算需经实验仿真提交流程；本次未执行 | 未执行 |
| ROLL-10 | 功能 | 取消草稿任务不产生缺勤 | HTTP 200 且状态进入取消态，absent_count=0 | HTTP 200，status=cancelled，absent=0 | 通过 |
| SEAT-01 | 功能 | 座位图接口可读 | HTTP 200 且返回布局/占用结构 | HTTP 200，layout=未配置 | 通过 |
| SEAT-02 | 功能 | 并发占座冲突与座位边界 | 两学生抢同一座位仅一人成功；越界/禁用座位被拒 | 被测组本轮点到任务未配置 seat_layout，缺少测试数据，未执行 | 未执行 |
| BROWSER-01 | E2E | 无头浏览器打开登录页 | 页面渲染出登录表单且 DOM 非空 | DOM 3172 字节，登录表单=有 | 通过 |
| BROWSER-02 | E2E | 浏览器交互级教师/学生双会话 E2E | 教师发布点到 → 学生页面选座签到 → 教师页面状态刷新一致 | 需 Playwright/CDP 交互环境，本次仅完成 API 链路与页面 DOM 验证，未执行 | 未执行 |
| PERSIST-01 | 回归 | 后端重启后业务数据持久化 | 重启后账号、点到任务与签到记录仍可查询且统计一致 | 重启被测组服务不属于测试方权限，未执行 | 未执行 |

## 3 缺陷统计

| 严重程度 | 数量 |
|---|---|
| 高 | 0 |
| 中 | 0 |
| 低 | 1 |
| **合计** | **1** |

缺陷明细见同目录 `defects_1_20261106_jiangsuhao.csv`（字段：编号、标题、被测组、复现步骤、预期/实际结果、严重程度、截图、状态）。
按老师要求**不提交任何图片**，截图列以文字说明代替。

## 4 被测组主要功能是否正确

**结论：正确。**

- 全量共 64 条用例：通过 59、失败 1、未执行 4、阻塞 0；覆盖冒烟、接口、功能、E2E、15 模块抽查、权限、边界、一致性、日志、实验、座位、取消分支与浏览器入口。
- 依据：首页、`/who`、`/help`、健康检查、CSRF、教师/学生登录与班级接口可用；点到任务可创建、发布、取码、签到、读取座位/记录/报表并结算（present=1 / absent=34）；15 个模块路由均返回统一 JSON；学生越权全部 403；参数边界均被校验；签到明细与 CSV 报表一致；导出任务可创建与查询；取消分支不产生缺勤；无头浏览器登录页可渲染。
- 另有未通过项如下，按严重程度列出：
  - API-09 /help 公开端点声明与实际一致：/help 仅声明 2 个公开端点；实测另可匿名访问 3 个：/api/health/live, /api/health/ready, /api/auth/csrf

## 5 遗留风险

1. 15 个业务模块各做了一条代表性 GET 抽查，未逐模块执行「正常/异常/边界/权限」全场景回归；未测项一律不记为通过。
2. 抽查组名单与其他被测组地址课堂上才公布，本报告仅覆盖上述一个被测组；拿到新地址后按同一脚本补测并追加缺陷记录。
3. 点到任务使用明确标记为「互测」的独立任务，收尾走系统提供的关闭操作，未删除被测组任何正式名单、成绩或课程数据。
4. 未执行项已在用例表标为「未执行」：74181 全量运算、并发占座、浏览器交互级 E2E、重启持久化；这些需要被测组提供计算接口/座位布局/现场浏览器环境，不能记为通过。
5. 报告不含账号明文口令、Cookie、CSRF 令牌或完整个人数据；请求关联 ID 仅保留在本地日志。

## 6 附件

- 缺陷记录表：`defects_1_20261106_jiangsuhao.csv`
- 原始请求日志：本地留存（时间、账号角色、方法、路径、状态码、耗时），不随文档提交
- 本目录不提交任何图片
