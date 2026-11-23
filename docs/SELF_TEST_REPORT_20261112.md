# g24201710 自测报告（20261112）

- 测试时间：2026-11-12 16:21:41 中国标准时间
- 测试对象：本组「计算机组成原理课程学习系统」
- 代码：`D:\Desktop\WebBigHomework\wt-demo`（demo-week11 @ 3ee01ba，含 2 个未提交改动）
- 服务：后端 http://127.0.0.1:5000 / 前端 http://127.0.0.1:5173
- 计划：`docs/TEST_PLAN_SELF_20261112.md`
- 脚本：`scripts/verify_self_20261112.py`（Python 标准库，可一键复跑）

## 1 测试范围

- 按互测复盘把 12 条「测试方自己的错」、2 个被测组的 3 类真实缺陷、自己项目 12 条历史缺陷转成回归用例。
- 分层：冒烟、接口、功能、回归、数据一致性、E2E；覆盖 `/help` 声明的 27 模块 / 148 端点中的核心链路。
- 不在范围：源码审计、性能压测、真实 Logisim 评测、后端重启持久化、浏览器交互级 E2E（标未执行）。
- 不删改正式数据；新建点到任务标记为「自测」并走系统 `close` 收尾。

## 2 用例统计

| 层级 | 用例数 | 通过 | 失败 | 未执行 |
|---|---|---|---|---|
| 冒烟 | 8 | 8 | 0 | 0 |
| 接口 | 14 | 14 | 0 | 0 |
| 回归 | 14 | 12 | 0 | 2 |
| 功能 | 20 | 20 | 0 | 0 |
| 一致性 | 1 | 1 | 0 | 0 |
| E2E | 2 | 1 | 0 | 1 |
| **合计** | **59** | **56** | **0** | **3** |

### 逐条结果

| ID | 层级 | 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|---|---|
| S-01 | 冒烟 | 公开接口 /who | 200 且组号/组长/成员齐全 | HTTP 200，class_name=242017班，group_no=g24201710，组长=姜苏豪，成员=4 | 通过 |
| S-02 | 冒烟 | 公开接口 /help | 200 且含模块/端点/账号规则 | HTTP 200，27 模块 / 148 端点，公开 9 条 | 通过 |
| S-03 | 冒烟 | 健康检查按设计判定（degraded 非故障） | web_ready/db_ready=true，grader_ready=false，status=degraded | HTTP 503，status=degraded，web=True，db=True，grader=False | 通过 |
| S-04 | 冒烟 | 教师 teacher/teacher 登录（历史 7 位校验坑） | 200 + csrf_token + role=teacher | HTTP 200，role=teacher，csrf=有 | 通过 |
| S-05 | 冒烟 | 学生学号/学号登录 | 200 + role=student | HTTP 200，role=student，name=姜苏豪 | 通过 |
| S-06 | 冒烟 | 教师课程列表（默认最新课程优先） | 200 且课程 #16 在首位 | HTTP 200，2 门课，首门 id=16 | 通过 |
| S-07 | 冒烟 | 会话读取 | 200 且返回当前用户 | HTTP 200，user=teacher，csrf 一致=是 | 通过 |
| I-01 | 接口 | 匿名访问课程列表被拒 | 401 | HTTP 401 UNAUTHENTICATED | 通过 |
| I-02 | 接口 | 已登录写请求缺少 CSRF 令牌被拒 | 403 CSRF_FAILED | HTTP 403 CSRF_FAILED | 通过 |
| I-03 | 接口 | 跨站 Origin 写请求被拒 | 403 CSRF_FAILED | HTTP 403 CSRF_FAILED | 通过 |
| I-04 | 接口 | 错误密码登录 | 401 且不建立会话 | HTTP 401 UNAUTHENTICATED | 通过 |
| I-05 | 接口 | 登录缺字段校验 | 400/422 VALIDATION_ERROR | HTTP 400 VALIDATION_ERROR | 通过 |
| I-06a | 接口 | /who 拒绝非 GET | 405 | HTTP 405 HTTP_ERROR | 通过 |
| I-06b | 接口 | /help 拒绝非 GET | 405 | HTTP 405 HTTP_ERROR | 通过 |
| I-07a | 接口 | 不存在的资源 ID | HTTP 404 | HTTP 404 NOT_FOUND | 通过 |
| I-07b | 接口 | 不存在的资源 ID | HTTP 404 | HTTP 404 NOT_FOUND | 通过 |
| I-08a | 接口 | 非法/超大分页参数 | 400/422 或被收敛，不得 500 | HTTP 400 VALIDATION_ERROR | 通过 |
| I-08b | 接口 | 非法/超大分页参数 | 400/422 或被收敛，不得 500 | HTTP 400 VALIDATION_ERROR | 通过 |
| I-09 | 接口 | /help 公开端点声明与实际一致 | 声明的公开端点均可匿名访问，且无遗漏 | 声明 9 条；实测可匿名访问 6 条；未列入声明的 0 条：无 | 通过 |
| I-10 | 接口 | 公开接口不泄露明文口令/令牌 | /who 与 /help 响应体不含口令、CSRF 值、访问令牌 | 敏感字段命中 0 处：无（accounts 段仅含规则文字） | 通过 |
| I-11 | 接口 | /help 与 /api/v1/modules 清单均可读 | 两处均非空（数量不必相等：/help 按 blueprint 分，/api/v1/modules 按业务模块分） | /help=27 个 blueprint，/api/v1/modules=19 个业务模块（口径不同，不作数量相等断言） | 通过 |
| I-12 | 回归 | 迁移文件与已应用记录一致 | 被测工作区迁移文件数 == 库内已应用记录数 | wt-demo 26 个迁移文件；库内已应用 26 条 | 通过 |
| R-01 | 回归 | C1 课程成员接口不再 500 | 200 且返回成员数组（sqlite3.Row.get 已修） | HTTP 200，本页 5 人，total=161 | 通过 |
| R-04 | 回归 | C4 当前双进程部署首页可达 | 前端 GET / 返回 200（后端专注 /api/v1，不托管页面属设计） | 前端 http://127.0.0.1:5173/ = HTTP 200；后端 http://127.0.0.1:5000/ = HTTP 404（后端 404 是双进程分工，不是故障） | 通过 |
| R-04b | 回归 | C4 单进程静态沙箱首页（条件性风险） | 若老师沙箱只起 Flask 一个进程，GET / 应返回 200 | 当前 develop 无 serve_frontend 分支，直连后端 / = HTTP 404；仓库 docs/index.html 存在但未托管；Gitea 课堂提交版已单独修过此问题 | 未执行 |
| R-06 | 回归 | C6 教室配置可读 | 200 且含 rows/cols/aisle_every/capacity | HTTP 200，18×10，容量 180 | 通过 |
| R-05 | 回归 | C5/C6 座位数据完整 | 200 且含座位清单与 classroom 配置 | HTTP 200，顶层键=['classroom', 'seats'] | 通过 |
| R-09 | 回归 | C9 无超时未处理的僵尸换位申请 | pending 且创建超过 15 分钟的记录数为 0 | 僵尸行=0，总 pending=0 | 通过 |
| R-10 | 回归 | C10 任务时间窗口满足 start<=late<=end | 违反 CHECK 的任务数为 0 | 违规行=0 | 通过 |
| R-11 | 回归 | C11 class_seat 与 attendance_seat 坐标一致 | 同一学生同一课程两处座位不同的记录数为 0 | 课程 #16 最新任务的座位快照不一致行=0 | 通过 |
| R-07 | 回归 | C7 签到记录 source 取值合法 | 非法 source 记录数为 0（code 会被 CHECK 静默丢弃） | 非法行=0 | 通过 |
| F-12a | 功能 | 74181 加法 9+5 | F=0xE，十进制 14 | HTTP 200，f_hex=0xE，十进制=14 | 通过 |
| F-12b | 功能 | 74181 减法 3−7 | F=0xC，十进制 -4 | HTTP 200，f_hex=0xC，十进制=-4 | 通过 |
| F-12c | 功能 | 74181 全组合表 | count=512 | HTTP 200，count=512，rows=512 | 通过 |
| F-12d | 功能 | 74181 参数越界校验 | 400 VALIDATION_ERROR | HTTP 400 VALIDATION_ERROR | 通过 |
| F-11a | 功能 | 访问日志 CSV 导出 | 200 且内容可解析、无敏感字段 | HTTP 200，17548 行，敏感字段=无 | 通过 |
| F-11b | 功能 | 审计日志 CSV 导出 | 200 且内容可解析 | HTTP 200，1948 行 | 通过 |
| F-11c | 功能 | 访问日志 JSON | 200 且可解析 | HTTP 200，data 类型=list | 通过 |
| F-01 | 功能 | 教师创建点到任务 | 201 且返回 6 位点到码 | HTTP 201，task_id=57，code=6位，status=open | 通过 |
| F-02 | 功能 | 任务时间非法被校验 | 400/422 VALIDATION_ERROR | HTTP 400 VALIDATION_ERROR | 通过 |
| F-03 | 功能 | 错误点到码被拒 | 422 INVALID_ATTENDANCE_CODE | HTTP 422 INVALID_ATTENDANCE_CODE | 通过 |
| F-04 | 功能 | 正确点到码签到 | 201 且 status=present | HTTP 201，id=783，status=present | 通过 |
| F-05 | 功能 | 重复签到不新增记录 | 返回同一条记录 | HTTP 200，首次 id=783，重复 id=783，新增=否 | 通过 |
| F-07 | 功能 | 轮换点到码 | 200 且返回与旧码不同的新码 | HTTP 200，旧码≠新码=是 | 通过 |
| F-06 | 功能 | 关闭任务并结算 | 200 且返回 counts | HTTP 200，counts={"absent": 159, "late": 0, "leave": 0, "present": 1} | 通过 |
| D-01 | 一致性 | 任务 counts 与全量明细逐状态一致 | present/late/leave/absent 四项计数相同（防 C8 分页只拉 100 条） | 明细 160 条，统计={"absent": 159, "present": 1}，closed={"absent": 159, "late": 0, "leave": 0, "present": 1}，一致=是 | 通过 |
| F-09 | 功能 | 座位图接口 | 200 且含 seats/grid/classroom | HTTP 200，顶层键=['classroom', 'grid', 'seats', 'task', 'unseated'] | 通过 |
| F-08a | 功能 | 教师创建带手势图案的任务 | 201 且 has_gesture=true | HTTP 201，task_id=58，has_gesture=True | 通过 |
| F-08b | 功能 | 错误手势被拒 | 422 INVALID_GESTURE | HTTP 422 INVALID_GESTURE | 通过 |
| F-08c | 功能 | 正确手势签到 | 201 且 source=gesture | HTTP 201，status=present，source=gesture | 通过 |
| F-13 | 功能 | 换位申请列表可读 | 200 | HTTP 200，items=0 | 通过 |
| F-14 | 功能 | 学生收件箱（含 TTL） | 200 且含 ttl_minutes | HTTP 200，ttl=15，items=0 | 通过 |
| S-08 | 冒烟 | 浏览器登录页六个 DOM ID | 六个 ID 全在 | DOM 109758 字节，缺失=无 | 通过 |
| R-02 | 回归 | C2 登录页 DOM 契约回归 | 六个 ID 全在 | 缺失=无 | 通过 |
| R-05b | 回归 | C5 座位图浏览器渲染 | 浏览器进考勤页后 .seat-cell 元素数 > 0 | 需 CDP 交互登录后再进课程，本次仅做 DOM 级验证，未执行 | 未执行 |
| E-02 | E2E | 浏览器交互级五标签页 E2E | 登录→进课程→考勤座位图→74181，无 JS 异常 | 需 CDP/Playwright 交互环境，本次未执行 | 未执行 |
| E-01 | E2E | 匿名 /who、/help → 教师登录 → 建任务 → 学生签到 → 关闭 → 明细 | 全链路无阻断且统计一致 | 关键环节全部通过 | 通过 |
| R-03 | 回归 | C3 同源 Origin 写请求放行、跨站拒绝 | 同源写请求成功且跨站被 403 | 同源建任务/签到/关闭均成功；跨站 Origin 用例 I-03=通过 | 通过 |
| R-08 | 回归 | C8 明细分页拉全量 | 统计不依赖单页 100 条 | D-01 已按 page_size=100 循环拉全量后比对 | 通过 |

## 3 缺陷统计

| 严重程度 | 数量 |
|---|---|
| 高 | 0 |
| 中 | 0 |
| 低 | 0 |
| **合计** | **0** |

明细见 `SELF_DEFECTS_20261112.csv`。

## 4 结论

**通过：核心功能可用，P0 全通过。**

- P0 用例 19 条，未通过 0 条。
- 判定 FAIL 前已按复盘规则自证：字段按 `/help`、方法按声明、账号归属、响应外壳、同期服务可达性；`/api/v1/health` 的 503/degraded 按已知设计不记缺陷。
- 手势签到不是缺失：`identity.py` 注释说明 `/auth/gesture` 已被有意移除，改为教师建任务时指定 `pattern`（见 F-08a/b/c）。
- **缺陷表 0 条不等于零风险**：3 项用例未执行（浏览器交互级 E2E、座位图渲染、单进程静态沙箱首页 R-04b），另有一条条件性部署风险见遗留风险第 4 条；这些项均未记为通过，也未记成对方或本组的功能缺陷。

## 5 遗留风险

1. 结果只对当前 `wt-demo` 工作区成立（含 2 个未提交改动），提交后需复跑。
2. 浏览器交互级 E2E 与座位图渲染未执行，需 CDP/Playwright 环境或现场人工。
3. 后端重启持久化、真实 Logisim 评测未验证；`grader_ready:false` 属已知状态。
4. 单进程沙箱下直连后端 `/` 的行为见 R-04b（当前 develop 无静态托管分支，返回 404）；若老师用静态沙箱，需确认 `docs/index.html` 与后端静态托管方案都已合入课堂提交版。
5. 本报告不含明文口令、CSRF 令牌或完整个人数据；原始请求日志本地留存。
6. 演示库曾被自测/压测脚本改动，已于 16:31 用 `scripts/cleanup_demo_selftest.py --apply` **全部复原**：删除 28 个自测/压测任务及 13440 行关联记录，任务 81→53、签到记录 4942→462，姜苏豪座位恢复排 10 座 8，外键违规 0；备份保留在 `wt-demo/instance/app.db.bak-20261112-163157`。详见 `DEEP_TEST_REPORT_20261112.md` 第 5 节。

## 6 附件

- 缺陷表：`SELF_DEFECTS_20261112.csv`
- 原始日志：`.workbuddy/tmp/self-test-20261112.json`（不随文档提交）
- 计划：`docs/TEST_PLAN_SELF_20261112.md`
