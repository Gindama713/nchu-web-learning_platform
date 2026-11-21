# 罗浩铭负责模块测试与交接记录

负责人：24201723 罗浩铭。原始执行日期：2026-11-05，复测与缺陷修复日期：2026-11-09。范围为 SPEC-004 备课、SPEC-007 课堂演示、SPEC-017 实验箱连线、SPEC-010C 连线统计、SPEC-015 先修图谱。原始环境为本机 Windows 副本（Python 3.13.12、Node 22.22.2、SQLite `instance/app.db`）；11-09 三轮复测与修复使用 Python 3.12.10（项目依赖所在解释器）、ruff 0.17.0、Node 22.22.2，且**工作副本带未提交修改**（当前分支 `feature/luo-wiring-fix-20261108`），因此复测结果不代表 `develop` 的干净检出。命令在项目根目录运行。本机 Windows 结果不等于目标 Linux 环境、教师课堂验收或 `main` 发布放行。

## 2026-11-09 复测（当前工作副本）

| 检查 | 结果 | 说明 |
|---|---|---|
| `python -m unittest tests.test_wiring tests.test_wiring_analytics tests.test_preparations tests.test_demo tests.test_knowledge_graph tests.test_preparation_quiz_integration` | **72 项通过，86.257 秒** | 含 11-08 新增的 RE-001 与 DEF-005 回归用例；比 11-05 的 70 项多 2 项 |
| `node --test --experimental-test-isolation=none` 八个前端测试文件（`preparation-client`、`preparation-view`、`wiring-sim`、`wiring-view`、`wiring-stats-view`、`demo-client`、`knowledge-graph-client`、`knowledge-graph-layout`） | **51 项通过，0 失败**，238.689 毫秒 | 替代 11-05「七个文件含 `graph-view`」的口径：当前工作副本没有 `graph-view.test.js`，改用实际存在的图谱客户端与布局测试 |
| `npm run lint` | 通过，无输出 | ESLint 静态规则 |
| `npm run build` | 通过，1.31 秒；产物 JS 457.66 kB / CSS 63.40 kB | Vite 生产构建，产物体积随 11-07 前端重做变化 |
| `ruff check backend tests scripts` | **通过（All checks passed）** | ruff 0.17.0 |

**环境踩坑记录**：直接用默认 `python`（WorkBuddy 自带 3.13.12）跑会因 `ModuleNotFoundError: No module named 'cv2'` 导致 4 个测试模块导入失败（只跑 22 项、errors=4），`ruff` 也未安装在该解释器；项目依赖实际装在 `C:/Users/10411/AppData/Local/Programs/Python/Python312/python`。复测结论以 3.12.10 解释器为准，**不得把 3.13.12 下的导入失败写成模块缺陷**。

11-05 的原始记录保留在下一节，作为当时的历史口径；各批数字不同源于用例增加、前端测试文件替换与解释器差异，不混算。

## 2026-11-09 代码修复与回归（当日第二轮）

第一轮复测后做了代码级审查，按「先补回归测试固化现状 → 再修代码」处理了 SPEC-017 的三处 P0 缺陷与两处相关健壮性问题。新增用例在修复前分别失败（`test_submit_exp03_wrong_datapath_is_not_completed` 断言 `completed` 为 true、`test_undo_then_redo_restores_wire` 得到空导线表、伪造 `tick=999` 被落库），修复后全部通过。

| 缺陷 | 修复位置 | 处置 |
|---|---|---|
| EXP-03 提交判定只看首拍 `pc==1`，结构合法但接错线也记 `completed=true` | `backend/engines/wiring.py` `run_functional_tests` | 改为断言 12 拍后 `ACC=5 / IR=0xF0 / halted=1`，结果表含 `expected/actual/checks`；补「`pc_inc` 误接 `en_out`」的接口级反例 |
| `undo` 把自身压入 redo 栈、`redo` 静默无效，新编辑不清空 redo 栈 | `backend/engines/wiring.py` `_apply_edit`/`replay`、`frontend/js/wiring-sim.js`、`wiring-view.js` | 栈改为保存 `(原动作, 逆动作)` 对，前后端共用一套编辑实现；补「重做」按钮与 undo/redo 往返、新编辑清空 redo 栈的用例 |
| 保存时把客户端 `state` 整体落库，`snapshot_hash` 与功能判定可被伪造 | `backend/apis/wiring.py` `save_attempt` | 客户端 `state` 只用于比对 `wires/inputs`，落库改用服务端重放结果 `replayed` |
| 残缺 `connect` 导线（缺 `from_terminal/to_terminal`）与未知动作类型仍能进入动作表 | `backend/apis/wiring.py` `ACTION_REQUIRED_FIELDS`/`VALID_ACTION_TYPES` | 入口统一挡成 400 `VALIDATION_ERROR`，避免引擎跳过重放后动作表与状态不一致，也避免数据库 CHECK 约束把它变成 409 |

| 复测批次 | 后端 6 模块 | 前端 8 文件 | 静态检查 |
|---|---|---|---|
| 修复前（11-09 第一轮） | 72 项通过 / 86.257 秒 | 51 项通过 / 0 失败 | lint、build、ruff 通过 |
| 修复后（11-09 第二轮） | **78 项通过 / 122.449 秒** | **53 项通过 / 0 失败**（229.539 毫秒） | lint、build、ruff 通过；`npm run build` 产物 JS 458.19 kB / CSS 63.40 kB |

新增 6 条后端用例在 `tests/test_wiring.py`（undo/redo 往返、新编辑清空 redo 栈、服务端状态落库、动作类型与字段校验、EXP-03 正确/错误数据通路提交），2 条前端用例在 `frontend/js/wiring-sim.test.js` 与 `wiring-view.test.js`（重做往返与「重做」按钮）。**修复后数字同样只对应带未提交改动的工作副本**，不能替代 develop 合入后的 CI。

## 2026-11-09 第三轮：完善与优化（当日第三轮，仍未提交）

按第二轮审查留下的 P1/P2 清单继续处理，同样先补回归用例再改代码；目标是把「口径正确、交互可解释、复杂度可控」补齐，不改判定规则、不伪造验收结论。

| 问题 | 修复位置 | 处置 |
|---|---|---|
| 010C 用裸字符串比较 `start <= end_at < end`，遇到 `+08:00`、`+00:00`、无毫秒写法会把 10 月底截止误判到 11 月 | `backend/apis/analytics.py` `wiring_interval_metrics` | 统一用 `parse_time` 解析成 UTC 时刻再比较；脏值跳过而不是 500；`except BaseException` 收窄为 `Exception`。补 2 条用例覆盖 5 种区间内写法与 4 种区间外/非法写法 |
| `GET /demo-sessions/{id}?after_revision` 是死参数；推进接口返回更新前的 `updated_at` | `backend/apis/demo.py` `get_session` / `advance_state` | 保留真实 `revision`，新增 `unchanged` 提示供前端跳过重绘；推进后重读行返回最新 `updated_at`。补 I03-007-02「未来游标不得改写 revision」与时间戳回归 |
| `set_input.value` 可传字符串/布尔/对象，位运算会 500；动作上限检查写在插入循环中；列表逐行 `COUNT(*)`；`_row` 拼表名 | `backend/apis/wiring.py` | 数值类型前置校验、上限整体预检、`action_count` 一次聚合查询、表名白名单；补 2 条接口级用例 |
| 备课同课程校验函数带一个从未使用的 `column` 参数 | `backend/apis/preparations.py` | 删除死参数及 4 处调用实参 |
| DEF-001 放宽 Origin 后，非 http(s) / 带 userinfo / opaque Origin 也可能靠 Host 通过 | `backend/apis/knowledge_security.py` | 只接受 http/https 且无 userinfo 的绝对 Origin，保留第二道 CSRF token；在 `tests/test_knowledge_graph.py` 补单测，并在注释写明反向代理须固定 Host |
| 017 AC-05 只有 `beforeunload`，SPA 内换课程/版本会静默丢未保存动作；AC-08 缺键盘撤销/重做；连续运行保存超时静默丢拍 | `frontend/js/wiring-view.js` | 增加离开确认（取消时回滚选择值）、`Ctrl+Z` / `Ctrl+Shift+Z`、跳过拍数累计提示、`role=status` / `aria-live` / `aria-keyshortcuts` / 按钮 title |
| 图谱布局用 `queue.shift()`，节点多时 O(n²)；孤立节点只靠坐标区分 | `frontend/js/knowledge-graph-layout.js` | 改为队列游标遍历，`placed` 增加 `isolated` 标记；补 1200 节点长链用例 |

| 复测批次 | 后端 6 模块 | 前端 8 文件 | 静态检查 |
|---|---|---|---|
| 第三轮（完善后） | **84 项通过 / 110.452 秒** | **57 项通过 / 0 失败**（240.606 毫秒） | lint、build、ruff 全绿；`npm run build` 产物 JS 459.65 kB / CSS 63.40 kB |

第三轮新增 6 条后端用例（`test_wiring_analytics.py` ×2、`test_demo.py` ×1、`test_wiring.py` ×2、`test_knowledge_graph.py` ×1）与 4 条前端用例（`wiring-view.test.js` ×3、`knowledge-graph-layout.test.js` ×1）。**全部结果仍只对应带未提交改动的工作副本，且未推送、未合入 `develop`。** 被取消的全仓 `unittest discover` 未重跑，本报告不引用其结论。

## 2026-11-05 原始执行记录

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_wiring tests.test_wiring_analytics tests.test_preparations tests.test_demo tests.test_knowledge_graph tests.test_preparation_quiz_integration` | **70 项通过，214.813 秒** | 连线保存/校验/提交与 revision 冲突、010C 统计口径、备课状态机与发布通知、演示状态机与同步、先修图谱与成环拒绝 |
| 同上，拆分为 `test_wiring`+`test_wiring_analytics` | 26 项通过，78.415 秒 | 017 与 010C 的接口级行为 |
| 同上，拆分为 `test_preparations`+`test_preparation_quiz_integration` | 21 项通过，94.665 秒 | 004 备课与随堂测关联校验 |
| 同上，拆分为 `test_demo`+`test_knowledge_graph` | 23 项通过，54.557 秒 | 007 演示与 015 图谱 |
| `node --test` 七个前端测试文件（`wiring-sim`、`wiring-view`、`wiring-stats-view`、`preparation-client`、`preparation-view`、`graph-view`、`demo-client`） | **41 项通过，0 失败**，321 毫秒 | 网表仿真、连线视图、统计视图、备课客户端与视图、图谱视图、演示客户端契约 |
| `npm run lint` | 通过，无输出 | ESLint 静态规则 |
| `npm run build` | 通过，1.00 秒；产物 JS 429.55 kB / CSS 41.75 kB | Vite 生产构建 |
| `python -m ruff check backend tests scripts` | **通过（0 错误）**。ruff 0.17.3 本地执行；首查发现 1 处 SIM115（`scripts/md2docx_report.py:83` open 未用上下文管理器），当日修复后复查全绿。该问题与 PR #59 首次 CI run 42042690543 的 ci-lint 失败同源；修复提交 `7a0a96a` 推送后 CI run 42044409767 重跑，ci-lint 等 5 个 required job 全部 success | 静态风格检查；此前曾记录为「未执行」，2026-11-05 已补做 |

上述 70 项与 41 项之和是 2026-11-05 当时的本地自动化结论；11-09 三轮依次为 72/51、78/53、84/57（后端/前端），四批不混算。全仓测试规模更大，不与本人范围混算。其中「七个前端测试文件含 `graph-view`」在当前工作副本已无法按原命令复现，见上方复测节。

最终合入记录的 CI 另计：head `c06156927c093f1dcda7f431d3342950f83866f8` 的 [Actions run 40862510430](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/40862510430)（run_attempt 2）中，`ci-policy`、`ci-lint`、`ci-build`、`ci-test`、`ci-required` 均为 success，`ci-grader` 为 skipped。该 run 的 `ci-test` 步骤实际执行 `python -m unittest discover -s tests -v` 与 `npm test`，属全仓口径，不能等同于本人 70+41 项的定向结果，也不能把 skipped 的评测写成通过。

## 规格与测试映射

规范性验收全集以 [PRD 第 11 节](PRD.md#accept-spec-004) 为准。下表只定位实际存在的可复现测试，不因单个测试含多步断言就推定该 SPEC 的全部 AC 已关闭。

| 本人范围 | 实际测试入口与已证明行为 | 仍需另行验收 |
|---|---|---|
| 004 备课 | `tests/test_preparations.py`、`tests/test_preparation_quiz_integration.py`：草稿创建、草稿可编辑而发布件不可改、复制生成新草稿且原单元不变、发布/撤回状态机、关联随堂测未发布时 409 `QUIZ_NOT_PUBLISHED`、发布写入学生通知 | R37-004-01/02 历史契约缺陷已在 develop 修复（`preparations.py` 返回 409、`window_state` 已补），两项测试现为普通断言、无 `expectedFailure`，docstring 于 11-09 同步；仍需真实课堂的模板复用效果与教师对排期语义的确认，以及队友按新 head 重跑关闭矩阵 |
| 007 课堂演示 | `tests/test_demo.py`：会话创建、状态推进、revision 冲突 409 `REVISION_CONFLICT`、关闭后拒绝推进 409 `STATE_CONFLICT`、按课程列会话；11-09 补 `after_revision` 的 `unchanged` 提示、未来游标不得改写真实 revision、推进响应 `updated_at` 为最新值 | 双浏览器真实跟随、投屏环境、断线重连后的同步时延 |
| 017 实验箱连线 | `tests/test_wiring.py`：端子方向与位宽校验、连接/拆线/写输入的动作重放、undo/redo 往返与新编辑清空 redo 栈、服务端重放状态落库、动作类型/字段与 `set_input` 数值校验、列表 `action_count` 批量口径、保存 revision 冲突、提交后不可编辑、结构校验、EXP-01/02/03 功能判定（含 EXP-03「结构合法但接错线不计完成」反例）；前端 `wiring-view.test.js` 补 AC-05 离开确认、AC-08 键盘撤销/重做与跳拍提示 | 真实课堂多人并发操作、教师端只读边界的人工核对、窗口缩放的人工检查 |
| 010C 连线统计 | `tests/test_wiring_analytics.py`：同一学生多次尝试只计一人（人数去重）、未完成不计入完成率、错误分布按类型计数、实验按 `end_at` 的真实时刻归入区间（`+08:00`/`+00:00`/无毫秒/脏值） | 非空真实班级、教师手工复算、跨周趋势的业务解释 |
| 015 先修图谱 | `tests/test_knowledge_graph.py`：节点/边读取、先修可达路径、成环写入返回 422 `PREREQUISITE_CYCLE`；11-08 DEF-005 子图包含关系回归；11-09 补 Origin 校验回归；`knowledge-graph-layout.test.js` 补 1200 节点长链与孤立节点标记 | 教师对图谱完整性的学科判断；本人命名的 `graph-view.js` 未合入 develop，功能由 `knowledge-graph-view.js` 承接（见交付索引） |

## 本地端到端演示（2026-11-05）

在演示库 `instance/app.db` 上以真实 HTTP 走通，不是单元测试替身：

1. 学生 24201725 对已发布版本 EXP-01 v2 发起连线，按 6 条导线连接 ALU 输入与指示灯，保存、校验、提交均返回 200，响应 `completed = true`，功能判定表逐条通过。
2. 010C 查询返回 `analysis_run_id`，`sample_size = 2`，`metrics` 为 `assigned_count = 2`、`attempt_count = 1`、`completed_student_count = 1`、`completion_rate = 0.5`、`error_counts = {}`；同一学生重复尝试未重复计入应做人数。
3. 备课 #1 处于 `published`；演示会话 #1（指令执行场景）停在第 4 拍且 revision 递增；图谱读取为 4 节点 3 条边。

## 发现的问题与处理

- **面板缺少 `layout` 会 400。** 创建实验版本时 `panel` 必须含 `layout`（如 `{"columns": 3}`），仅用引擎内置面板不含该字段。已按此构造演示数据，未改后端校验。
- **010C 的区间口径容易误判。** 统计按 `experiment_version.end_at` 归入区间，且结束时间不能填未来，窗口未结束的实验永远不进统计。演示时必须使用已结束窗口的版本，否则会得到空样本而非 0 人。该口径已写入用户说明。
- **管理员看不到本人五个模块。** `frontend/js/main.js` 中五个组件均带 `user.role !== 'admin'` 条件，属既有设计；演示与检查须用教师或学生账号。
- **11-08 互测缺陷已在工作副本修复，但未进主干。** RE-001（非法动作 payload 使重放 `KeyError` 冒泡成 500）、DEF-002/003（备课与连线视图时间处理）、DEF-001（局域网写入全 403）、DEF-005（添加「包含」关系后聚焦子图无变化）分别在 `backend/apis/wiring.py`、`backend/engines/wiring.py`、`backend/apis/knowledge_security.py`、`backend/models/knowledge.py`、`frontend/js/knowledge-graph-layout.js` 修复，并在 `tests/test_wiring.py`、`tests/test_knowledge_graph.py` 增加回归用例（11-09 后端 72 项即含这些用例）。相关提交在 `feature/luo-wiring-*-20261108` 等分支、另有多个文件尚未提交，**都不是 develop 祖先**；检查时只能说「本地已修、主干未交付」。2026-11-09 第二轮另修三处 P0 缺陷（EXP-03 提交判定、undo/redo 重放、服务端状态落库）与两处动作入口校验，见上文「代码修复与回归」节；这些修复同样尚未进入主干。

## 未关闭的验收

真实 Logisim JAR 与固定 Java 的电路判分（当前健康检查 `grader_ready = false`，评测 worker 未配置）、目标 Linux 环境、50 会话并发、完整备份与恢复、教师课堂实际验收、Gitea 同 SHA 归档与超星提交均未完成。SPEC-007 的视图层采用 develop 既有实现、SPEC-015 本人命名的 `graph-view.js` 未合入 develop（功能由 `knowledge-graph-view.js` 承接），两点已在[交付索引](LUO_HAOMING_DELIVERY.md)如实标注，不能作为本人视图代码已进入主干的证据。

此外以下本人责任项仍未关闭，均不因 11-09 本地复测通过而自动勾选：

1. **技术验证与检查点**：TV-02（本人执行、黄俊诚复核）在 PRD §10.4.3 仍记为「验证状态均为未执行」；第 9 周 M9 的 EXP-01/02/03 三项连线整包、CP-4「真实交互演示」无实测结论。[检查点材料](checkpoints/LUO_HAOMING_2026-11-05.md) 的演示步骤明确标为待执行脚本，课堂记录表的日期、执行人、输入、预期、实际与截图均待补。PRD §10.2 规定 CP-4 未完成个人成绩不高于 80 分。
2. **队友验收矩阵**：2026-10-28 的 [C12A 审计](C12A_ACCEPTANCE_AUDIT.md) 与 [C12c 交付](C12C_DELIVERY_HUANG_JUNCHENG.md) 仍把 004/007 契约失败记为「阻断」；代码已修但未请原作者按新 head 重跑并更新矩阵，`docs/evidence/` 也无本人五个 SPEC 的专用证据目录。重跑请求见[集成待办](LUO_HAOMING_INTEGRATION_TODO_2026-11-09.md)。
3. **AC 覆盖缺口**：11-09 第三轮已为 017 的 AC-05（SPA 离开确认）与 AC-08（键盘撤销/重做、状态文字与无障碍属性）补定向用例，但**窗口缩放、信号不只靠颜色的人工核对**与 R28 中 RESET/ENABLE 持久化、前后端逐拍重放一致仍缺课堂级证据（undo/redo 往返用例不等于 R28 全部关闭）；010C 父 AC-02（学生仅看自己、教师仅看本班）与 AC-04（导出与页面使用同一 `analysis_run_id` 快照）目前只有端到端文字记录。
4. **主干交付**：11-08 修复分支、未提交改动以及 11-09 第二/三轮的全部代码修复均尚未合入 `develop`，也未推送；合入并跑全量 CI 之前，本报告所有「已修复」只适用于本地工作副本。

复现入口与设计说明见[个人设计报告](reports/24201723_罗浩铭_设计报告.md)、[PRD](PRD.md)、[APIC](APIC.md)。回退时保留数据库与上传文件一致副本，不改历史统计快照。
