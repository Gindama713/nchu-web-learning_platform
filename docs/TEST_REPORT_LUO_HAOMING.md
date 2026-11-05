# 罗浩铭负责模块测试与交接记录

负责人：24201723 罗浩铭。原始执行日期：2026-11-05。范围为 SPEC-004 备课、SPEC-007 课堂演示、SPEC-017 实验箱连线、SPEC-010C 连线统计、SPEC-015 先修图谱。执行环境为本机 Windows 副本（Python 3.13.12、Node 22.22.2、SQLite `instance/app.db`），命令在项目根目录运行。本机 Windows 结果不等于目标 Linux 环境、教师课堂验收或 `main` 发布放行。

## 已执行检查

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_wiring tests.test_wiring_analytics tests.test_preparations tests.test_demo tests.test_knowledge_graph tests.test_preparation_quiz_integration` | **70 项通过，214.813 秒** | 连线保存/校验/提交与 revision 冲突、010C 统计口径、备课状态机与发布通知、演示状态机与同步、先修图谱与成环拒绝 |
| 同上，拆分为 `test_wiring`+`test_wiring_analytics` | 26 项通过，78.415 秒 | 017 与 010C 的接口级行为 |
| 同上，拆分为 `test_preparations`+`test_preparation_quiz_integration` | 21 项通过，94.665 秒 | 004 备课与随堂测关联校验 |
| 同上，拆分为 `test_demo`+`test_knowledge_graph` | 23 项通过，54.557 秒 | 007 演示与 015 图谱 |
| `node --test` 七个前端测试文件（`wiring-sim`、`wiring-view`、`wiring-stats-view`、`preparation-client`、`preparation-view`、`graph-view`、`demo-client`） | **41 项通过，0 失败**，321 毫秒 | 网表仿真、连线视图、统计视图、备课客户端与视图、图谱视图、演示客户端契约 |
| `npm run lint` | 通过，无输出 | ESLint 静态规则 |
| `npm run build` | 通过，1.00 秒；产物 JS 429.55 kB / CSS 41.75 kB | Vite 生产构建 |
| `python -m ruff check backend tests scripts` | **通过（0 错误）**。ruff 0.17.3 本地执行；首查发现 1 处 SIM115（`scripts/md2docx_report.py:83` open 未用上下文管理器），当日修复后复查全绿。该问题与 PR #59 首次 CI run 42042690543 的 ci-lint 失败同源，修复提交后 CI 重跑 | 静态风格检查；此前曾记录为「未执行」，2026-11-05 已补做 |

上述 70 项与 41 项之和为本人模块可复现的本地自动化结论；全仓测试规模更大，不与本人范围混算。

最终合入记录的 CI 另计：head `c06156927c093f1dcda7f431d3342950f83866f8` 的 [Actions run 40862510430](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/40862510430)（run_attempt 2）中，`ci-policy`、`ci-lint`、`ci-build`、`ci-test`、`ci-required` 均为 success，`ci-grader` 为 skipped。该 run 的 `ci-test` 步骤实际执行 `python -m unittest discover -s tests -v` 与 `npm test`，属全仓口径，不能等同于本人 70+41 项的定向结果，也不能把 skipped 的评测写成通过。

## 规格与测试映射

规范性验收全集以 [PRD 第 11 节](PRD.md#accept-spec-004) 为准。下表只定位实际存在的可复现测试，不因单个测试含多步断言就推定该 SPEC 的全部 AC 已关闭。

| 本人范围 | 实际测试入口与已证明行为 | 仍需另行验收 |
|---|---|---|
| 004 备课 | `tests/test_preparations.py`、`tests/test_preparation_quiz_integration.py`：草稿创建、草稿可编辑而发布件不可改、复制生成新草稿且原单元不变、发布/撤回状态机、关联随堂测未发布时 409 `QUIZ_NOT_PUBLISHED`、发布写入学生通知 | 真实课堂中的模板复用效果、教师对排期语义的确认 |
| 007 课堂演示 | `tests/test_demo.py`：会话创建、状态推进、revision 冲突 409 `REVISION_CONFLICT`、关闭后拒绝推进 409 `STATE_CONFLICT`、按课程列会话 | 双浏览器真实跟随、投屏环境、断线重连后的同步时延 |
| 017 实验箱连线 | `tests/test_wiring.py`：端子方向与位宽校验、连接/拆线/写输入的动作重放、保存 revision 冲突、提交后不可编辑、结构校验、功能判定 | 真实课堂多人并发操作、教师端只读边界的人工核对 |
| 010C 连线统计 | `tests/test_wiring_analytics.py`：同一学生多次尝试只计一人（人数去重）、未完成不计入完成率、错误分布按类型计数、实验按结束时间归入区间 | 非空真实班级、教师手工复算、跨周趋势的业务解释 |
| 015 先修图谱 | `tests/test_knowledge_graph.py`：节点/边读取、先修可达路径、成环写入返回 422 `PREREQUISITE_CYCLE` | 教师对图谱完整性的学科判断；视图层未合入主干（见下） |

## 本地端到端演示（2026-11-05）

在演示库 `instance/app.db` 上以真实 HTTP 走通，不是单元测试替身：

1. 学生 24201725 对已发布版本 EXP-01 v2 发起连线，按 6 条导线连接 ALU 输入与指示灯，保存、校验、提交均返回 200，响应 `completed = true`，功能判定表逐条通过。
2. 010C 查询返回 `analysis_run_id`，`sample_size = 2`，`metrics` 为 `assigned_count = 2`、`attempt_count = 1`、`completed_student_count = 1`、`completion_rate = 0.5`、`error_counts = {}`；同一学生重复尝试未重复计入应做人数。
3. 备课 #1 处于 `published`；演示会话 #1（指令执行场景）停在第 4 拍且 revision 递增；图谱读取为 4 节点 3 条边。

## 发现的问题与处理

- **面板缺少 `layout` 会 400。** 创建实验版本时 `panel` 必须含 `layout`（如 `{"columns": 3}`），仅用引擎内置面板不含该字段。已按此构造演示数据，未改后端校验。
- **010C 的区间口径容易误判。** 统计按 `experiment_version.end_at` 归入区间，且结束时间不能填未来，窗口未结束的实验永远不进统计。演示时必须使用已结束窗口的版本，否则会得到空样本而非 0 人。该口径已写入用户说明。
- **管理员看不到本人五个模块。** `frontend/js/main.js` 中五个组件均带 `user.role !== 'admin'` 条件，属既有设计；演示与检查须用教师或学生账号。

## 未关闭的验收

真实 Logisim JAR 与固定 Java 的电路判分（当前健康检查 `grader_ready = false`，评测 worker 未配置）、目标 Linux 环境、50 会话并发、完整备份与恢复、教师课堂实际验收、Gitea 同 SHA 归档与超星提交均未完成。SPEC-007 的视图层采用 develop 既有实现、SPEC-015 的 `graph-view.js` 未合入 develop，两点已在[交付索引](LUO_HAOMING_DELIVERY.md)如实标注，不能作为本人视图代码已进入主干的证据。

复现入口与设计说明见[个人设计报告](reports/24201723_罗浩铭_设计报告.md)、[PRD](PRD.md)、[APIC](APIC.md)。回退时保留数据库与上传文件一致副本，不改历史统计快照。
