# g24201710 自测计划（2026-11-12）

> 目的：把 11-06 两次互测踩过的坑、两个被测组暴露的问题、以及 11-06～11-12 自己项目修过的缺陷，
> 全部转成**可执行的回归用例**，对本组当前演示环境做一次自测。
> 本文件是计划；执行结果另见 `SELF_TEST_REPORT_20261112.md` 与 `SELF_DEFECTS_20261112.csv`。

## 0 复盘：错误、坑、别组的问题

### 0.1 测试方自己犯的错（最该记住，直接决定用例怎么写）

| # | 错误 | 当时现象 | 根因 | 固化成规则 |
|---|---|---|---|---|
| A1 | 把幂等键放 body | g24201803 `check-ins` 报 422「缺少有效幂等键」，一度记为对方缺陷 | 实际要 **请求头 `Idempotency-Key`**，不是 `request_id` 字段 | 判定 FAIL 前先读 `/help` 并试探字段，排除传参错 |
| A2 | 导出接口多传字段 | `POST /api/classes/5/exports` 422「不支持字段」 | 正确契约是 **空 body + `Idempotency-Key`** | 同上；先发最小 body |
| A3 | 套用本组路径 | 探 `/api/v1/health` 得 404，差点记缺陷 | 对方健康检查是 `/api/health/live\|ready` | **不同组的 API base 完全不同**，一律从 `/help` 动态取 |
| A4 | 选座字段名写错 | g24201807 签到 200 但 `seat_label=null`、座位图占用为空 | 正确字段是 **`seat_label`**；传 `seat` 被静默忽略仍 200 | 静默忽略未知字段的接口要专门测；别把 200 当成功 |
| A5 | HTTP 方法用错 | 教师代点 PUT 返回 405 | 正确是 **POST + `student_id`**（PUT 是结束任务） | 严格按 `/help` 的 methods 发请求 |
| A6 | 响应解析层级写死 | 座位图"占用 0 个" | 实际结构是 `seats[].blocks[].seats[]`，遍历少一层 | 解析前先打印一层真实 JSON |
| A7 | 账号不属于目标班 | 学生签到 403「只能在本班点到」 | `24201501` 不在 `class_id=1` | 测试账号先确认归属，别拿学号猜 |
| A8 | 响应外壳写死 | `/who` 解析成 None | 三组三种外壳：顶层 / `{data:{}}` / `{code,data,message}` | 解析函数兼容三种 |
| A9 | 服务中断误判 | 17:15 四个端点全超时 | 同期另一被测组仍 200，排除己方网络 | 服务不可达时先做对照探测，别记成功能缺陷 |
| A10 | 断言过宽 | `s in (200,400,409)` 把"第二人抢同一座位也成功"判成通过 | 没校验异常类型 | 冲突类用例必须校验 `seat_conflict` / `duplicate` 实体 |
| A11 | 状态与打印混淆 | "未执行"打印成 FAIL | 打印用 `passed` 而非 `status` | 统计与展示一律用 status |
| A12 | 脚本自身 bug | `login()` 返回 2 个值却按 3 个解包；`docs/tests/test2/` 没 mkdir | 代码疏漏 | 脚本先 `py_compile`，输出目录先建 |
| A13 | 把"计划 > 实现"当缺陷 | 计划列的知识图谱/题库/仿真接口全 404 | 对方实验内容其实存在，只是没公开仿真 API | 准确表述为「未提供公开 API，需前端确认」，不断言功能缺失 |

**一句话规则：任何 FAIL 先自证三次（字段、方法、账号/解析、网络），确认不是测试方的错再记缺陷。**

### 0.2 两个被测组的真实缺陷（别组出现的问题）

| 组 | 缺陷 | 级别 | 我们的对应检查 |
|---|---|---|---|
| g24201803 | `/help.public_endpoints` 只声明 `/help` `/who`，实测 `/api/health/live`、`/api/health/ready`、`/api/auth/csrf` 也可匿名访问 | 低 | 自测要比对 `/help` 声明与匿名实测，见 I-09 |
| g24201807 | 匿名可访问的 `/help.accounts.admin.password` **明文返回管理员口令**（提交前已脱敏） | 高 | 自测要检查公开接口是否泄露凭据，见 I-10 |
| g24201807 | 测试计划列出知识图谱/题库/练习/推荐/组卷/仿真，但 8 条常见路径全部 404；`/help` 只有 8 模块 46 端点 | 待确认 | 自测要核对「文档/计划声明」与「实际路由」一致，见 I-11 |
| 两组共性 | 计划写得很全，实际 `/help` 声明窄得多；`accounts` 段给的是演示账号，文档未说明必填字段 | — | 自测不照抄别组计划，按自己 `/help` 的 27 模块 148 端点来 |

### 0.3 我们自己项目修过的缺陷（回归清单，必须有用例）

| # | 历史缺陷 | 后果 | 回归用例 |
|---|---|---|---|
| C1 | `courses.py:member_json()` 对 `sqlite3.Row` 调 `.get()` | `GET /courses/{id}/members` 恒 500 → 前端 `Promise.all` 整批挂 → 考勤任务 0、座位图按钮不出现 | R-01 |
| C2 | 登录页六个 DOM ID 缺失 / 登录校验 8–20 位挡住 7 位 `teacher` | 验收脚本找不到元素、teacher 登不进 | R-02 / S-04 |
| C3 | CSRF 只认 `APP_ORIGIN`，单进程端口不同即 403 | 写操作全被拒 | R-03 |
| C4 | 无 `frontend/dist` 时 Flask 不注册静态路由；`docs/index.html` 缺失 | 老师沙箱「无法运行 / 无法访问」 | **R-04（当前 develop 仍存在，见下）** |
| C5 | `seatSlot` 没写进 Vue `setup` 的 return | 座位图整块不渲染 | R-05（浏览器层） |
| C6 | 教室尺寸改了但旧任务座位快照没重建 | 图被撑成 13×14、坐标重叠 | R-06 |
| C7 | `attendance_record.source` 的 CHECK 没有 `code`，用 `code` 被 `OR IGNORE` 静默吞 | 签到码记录丢失 | R-07 |
| C8 | `attendance-records?page_size=100` 只拉第一页 | 301 条记录把已结束任务挤出 → 「到勤 0/160」 | R-08 |
| C9 | `expire_stale()` 在事务里被回滚 | 库里留永远 pending 的僵尸换位申请 | R-09 |
| C10 | 改签到窗口只改 `start_at/end_at` | 违反 CHECK `start_at <= late_at <= end_at` | R-10 |
| C11 | 换位成功只改 `class_seat` 没改 `attendance_seat` | 座位图停在旧位置 | R-11 |
| C12 | 迁移文件 checksum 锁定后改文件 | 迁移不生效 | 只查不改，见 I-12 |

### 0.4 环境与工具坑（写进脚本约束）

- 全局 `http.proxy=127.0.0.1:7890` 会劫持 git/curl；脚本用 `ProxyHandler({})`，curl 加 `--noproxy '*'`。
- 后台服务必须用后台任务方式启动，命令末尾 `&` 会随 shell 退出被回收（表现为 curl 000）。
- 登录限流 `login:ip` **20 次/分钟**，批量脚本要复用会话，不能每用例重新登录。
- 后端测试解释器是 `E:/Python/python.exe`（3.14，带 pytest/flask）；主仓 `.venv` 历史上被清空过，重装修复要 `--reinstall` 残留 dist-info 包。
- 前端测试是 **`npm test` = `node --test`**，不是 vitest；`npx vitest` 会抓到缓存里的另一个包报错。
- `DATABASE_PATH` 一律用带盘符的显式路径（`D:/...`），MSYS 风格 `/tmp/x.db` 会落到两个不同文件。
- `/api/v1/health` 返回 **503 / degraded / `grader_ready:false` 是正常**（Logisim JAR 未落地），业务不受影响，**不得记为缺陷**。
- 迁移必须手动 `flask --app backend.app db-upgrade`，Flask 启动不会自动迁移。

## 1 目标与环境

| 项 | 值 |
|---|---|
| 被测 | 本组 g24201710「计算机组成原理课程学习系统」 |
| 代码 | `D:\Desktop\WebBigHomework\wt-demo`，分支 `demo-week11`，HEAD `3ee01ba`（含 PR #85/#86）；工作区有 2 个未提交改动（`courses.py` 排序、`main.js` 全量分页） |
| 服务 | Flask `http://127.0.0.1:5000`（API）、Vite `http://127.0.0.1:5173`（前端 + `/api` 代理） |
| 数据库 | `wt-demo/instance/app.db`（四班同堂 160 人、教室 18×10、课程 #16） |
| 契约 | API base **`/api/v1`**；统一 `{data,request_id}` / `{error:{code,message,details},request_id}`；Cookie 会话 + `X-CSRF-Token` + 同源 `Origin` |
| 账号 | 教师 `teacher/teacher`；学生 `24201718/24201718`（姜苏豪，242017 班）、`24201502/24201502` |
| `/help` | 27 模块 / 148 端点；`public_endpoints` 9 条 |
| 不做 | 不删/不改正式演示数据；不重启被测服务；批量签到不超过限流；不测真实 Logisim 评测 |

## 2 测试分层

| 层 | 方式 | 重点 | 阻断条件 |
|---|---|---|---|
| 冒烟 S | HTTP | 首页、`/who`、`/help`、健康检查（按 degraded 口径）、三类账号登录、课程列表 | 服务不可达 / `/who` 契约错 / 无法登录 |
| 接口 I | 参数化 HTTP | 方法、鉴权、CSRF、字段校验、分页、幂等、返回码、公开接口声明一致性 | P0 接口或权限断言失败 |
| 功能 F | HTTP 场景 | 点到（码/手势）、座位图、教室、换位、日志导出、74181、课程成员 | 数据不持久化 / 状态不一致 |
| 回归 R | 定向 HTTP + 浏览器 DOM | 0.3 节 12 条历史缺陷逐条复验 | 任一历史 P0 复发 |
| 数据一致性 D | 读两处比对 | 明细 vs 统计、座位图 vs 记录、分页全量 | 数字对不上 |
| E2E | 浏览器入口 + API 链路 | 教师建任务 → 学生签到 → 教师读统计 | 链路阻断 |

## 3 用例清单

优先级：P0 阻断 / P1 主要功能 / P2 回归抽查。

### 3.1 冒烟（S）

| ID | 优先级 | 步骤 | 预期 |
|---|---|---|---|
| S-01 | P0 | 匿名 `GET /who` | 200，含 `class_name=242017班`、`group_no=g24201710`、组长与 4 名组员 |
| S-02 | P0 | 匿名 `GET /help` | 200，`counts.endpoints>0`、模块清单、账号规则、公开接口清单 |
| S-03 | P0 | 匿名 `GET /api/v1/health` | 503 但 `web_ready/db_ready=true`、`grader_ready=false`、`status=degraded`（**按设计判定**） |
| S-04 | P0 | `POST /api/v1/auth/login` teacher/teacher | 200 + `csrf_token` + `role=teacher` |
| S-05 | P0 | 学生 24201718/24201718 登录 | 200 + `role=student` |
| S-06 | P1 | 教师 `GET /api/v1/courses` | 200，课程 #16 在列表首位 |
| S-07 | P1 | `GET /api/v1/auth/session` | 200，返回当前用户与同一 `csrf_token` |
| S-08 | P0 | 浏览器打开 `5173/` | 200 且含登录表单；六个 DOM ID 全在 |

### 3.2 接口（I）

| ID | 优先级 | 步骤 | 预期 |
|---|---|---|---|
| I-01 | P0 | 匿名访问 `GET /api/v1/courses` | 401 |
| I-02 | P0 | 写请求不带 `X-CSRF-Token` | 403 `CSRF_FAILED` |
| I-03 | P0 | 跨站 `Origin` 写请求 | 403 `CSRF_FAILED` |
| I-04 | P0 | 错误密码登录 | 401 `UNAUTHENTICATED`，无会话 |
| I-05 | P1 | 登录体缺字段 / 含不支持字段 | 400/422 `VALIDATION_ERROR` |
| I-06 | P1 | `POST /who`、`POST /help` | 405 |
| I-07 | P1 | 不存在的任务 / 课程 / 用户 ID | 404 `NOT_FOUND` |
| I-08 | P1 | `page_size=-5`、`page_size=999` | 400/422 或被收敛到上限，不 500 |
| I-09 | P1 | 比对 `/help.public_endpoints` 与匿名实测 | 声明的 9 条都能匿名访问；额外可匿名访问的端点要列出（对照 g24201803 缺陷） |
| I-10 | P0 | 检查 `/who`、`/help` 响应体 | **不含任何明文口令、CSRF 值、令牌**（对照 g24201807 高危缺陷） |
| I-11 | P1 | `/help` 声明的模块数与 `/api/v1/modules` 一致 | 两边对得上（对照"计划 > 实现"问题） |
| I-12 | P2 | 只读检查迁移目录 | 迁移文件数量与 `schema_migration` 记录一致，无篡改 |

### 3.3 功能（F）

| ID | 优先级 | 步骤 | 预期 |
|---|---|---|---|
| F-01 | P0 | 教师建点到任务（时间合法） | 201 + 6 位码，状态 open |
| F-02 | P0 | 建任务时间 `start_at > end_at` | 422 `VALIDATION_ERROR` |
| F-03 | P0 | 学生错误码签到 | 422 `INVALID_ATTENDANCE_CODE` |
| F-04 | P0 | 学生正确码签到 | 201，`status=present` |
| F-05 | P0 | 重复签到 | 不新增记录，返回同一条 |
| F-06 | P0 | 教师关闭任务 | 200，`counts{present,late,leave,absent}` |
| F-07 | P1 | `rotate-code` | 旧码失效、新码可用 |
| F-08 | P1 | 手势签到（已录入图案） | 成功且 `source=gesture`；未录入返回 `GESTURE_NOT_ENROLLED` |
| F-09 | P1 | `GET /attendance-tasks/{id}/seats` | 200，含 `seats/grid/classroom` 三块 |
| F-10 | P1 | 教室设置 `GET/PUT /courses/{id}/classroom` | 200，返回 rows/cols/aisle_every |
| F-11 | P1 | 日志 CSV/JSON 导出 | 200，内容可解析，无口令/令牌 |
| F-12 | P1 | 74181 `compute` 加/减 | 与 `9+5=0xE`、`3−7=0xC` 参考向量一致；`table` 512 行 |
| F-13 | P1 | 换位：空位直换 / 占用 / 越界 | 200 / 409 `SEAT_TAKEN` / 422 `OUT_OF_RANGE` |
| F-14 | P2 | 换位申请 → 答复 → 对调 | 两处座位数据一致 |

### 3.4 回归（R，对应 0.3 节）

| ID | 对应 | 检查 |
|---|---|---|
| R-01 | C1 | `GET /api/v1/courses/16/members` 必须 200 且 `total`/成员数与演示数据一致（历史恒 500） |
| R-02 | C2 | 浏览器 DOM 六 ID 全在 |
| R-03 | C3 | 同源 Origin 写请求通过；跨站拒绝 |
| R-04 | C4 | 直连 `5000/` 是否 200；`docs/index.html` 是否存在（当前 develop 预期 **404 → 记为待修**） |
| R-05 | C5 | 浏览器座位图 `.seat-cell` 元素数 >0、无 JS 异常 |
| R-06 | C6 | 座位图 `grid` 尺寸与教室设置一致，无坐标重叠 |
| R-07 | C7 | 签到记录 `source` 取值合法，无静默丢弃 |
| R-08 | C8 | 明细分页拉全量后统计与任务 `counts` 一致（历史「到勤 0/160」） |
| R-09 | C9 | `seat_swap_request` 无超过 15 分钟仍 pending 的僵尸行 |
| R-10 | C10 | 任务窗口满足 `start_at <= late_at <= end_at` |
| R-11 | C11 | `class_seat` 与 `attendance_seat` 对同一学生同一课程坐标一致 |
| R-12 | C12 | 只读核对迁移 checksum（不改文件） |

### 3.5 数据一致性（D）与 E2E

| ID | 优先级 | 检查 |
|---|---|---|
| D-01 | P0 | 任务 `counts` 与 `attendance-records` 全量明细逐状态计数一致 |
| D-02 | P1 | 座位图 `seats` 中 present 人数与记录一致 |
| D-03 | P1 | `logs/access.csv` 行数与 `logs/summary.requests`（按时间窗口）口径可解释 |
| E-01 | P0 | 匿名 `/who`→`/help`→教师登录→建任务→学生错误码→签到→重复→关闭→明细→日志，全链路无阻断 |
| E-02 | P1 | 浏览器：登录 → 进课程 → 五个标签页 → 考勤座位图 → 实验 74181，无 JS 异常 |

## 4 自动化脚本与运行说明

- 脚本：`scripts/verify_self_20261112.py`，仅 Python 标准库，`ProxyHandler({})` 强制直连。
- 运行：
  ```bash
  E:/Python/python.exe scripts/verify_self_20261112.py \
      --base http://127.0.0.1:5000 --frontend http://127.0.0.1:5173
  ```
- 会话复用：教师/学生各登录一次，全脚本复用 Cookie + `csrf_token`，避免 20 次/分钟限流。
- 每个用例记录：`ID / 层级 / 预期 / 实际（HTTP 状态 + 错误码）/ 结论 / 耗时 / 复现步骤`。
- 结论五态：`通过 / 失败 / 未执行 / 阻塞`。**未执行不记缺陷、不记通过**。
- 输出：`docs/SELF_TEST_REPORT_20261112.md`、`docs/SELF_DEFECTS_20261112.csv`、原始 JSON 日志（本地留存）。
- 判定 FAIL 前的自检：字段是否按 `/help`、方法是否匹配、账号是否属于目标课程、响应外壳是否解析对、同期另一端口是否可达。
- 不写正式数据：新建的点到任务标记为「自测」，收尾走 `close`；不删任何课程/名单/成绩/日志。

## 5 判定标准

- 所有 P0 通过，无服务崩溃、数据错记、越权或凭据泄露。
- 0.3 节的 12 条历史缺陷**零复发**；复发的按严重级别登记。
- `/help`、`/who` 匿名可用且内容与实际一致；公开接口清单与实测一致。
- 点到链路（建/错码/签到/重复/关闭/统计/明细）数据一致。
- 未执行项必须写明原因（缺数据 / 无权限 / 需浏览器环境），不得记为通过。

## 6 交付物

| 文件 | 内容 |
|---|---|
| `docs/TEST_PLAN_SELF_20261112.md` | 本计划 |
| `docs/SELF_TEST_REPORT_20261112.md` | 执行结果（范围、用例统计、缺陷统计、结论、遗留风险） |
| `docs/SELF_DEFECTS_20261112.csv` | 缺陷记录表（编号、标题、模块、复现、预期/实际、严重级别、状态） |
| `scripts/verify_self_20261112.py` | 可复现自动化脚本 |

## 7 已知风险（不作为缺陷）

- `/api/v1/health` 的 503/degraded 是 Logisim 评测引擎未落地，属已知设计。
- `wt-demo` 工作区有 2 个未提交改动，测试结果只对**当前工作区**成立，提交后需复跑。
- 直连 5000 的 `/` 为 404，是 develop 版双进程部署的既定行为；但老师沙箱若为单进程静态模式，此项会变成阻断项，需单独决策是否合入 `serve_frontend`。
- 浏览器交互级 E2E 需要 CDP/Playwright 环境，本次若只做 DOM 级验证，明确标「未执行」。
