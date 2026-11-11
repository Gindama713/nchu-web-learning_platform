# 罗浩铭模块集成待办（2026-11-09）

本文是**请求与待办清单，不是验收记录**。文中「已修复」仅指当前 `origin/develop` 代码与本人工作副本中的事实；是否关闭历史阻断项，由原作者按新 head 重跑、由教师检查决定，本人不代写队友结论。适用模块：SPEC-004 备课、007 课堂演示、017 实验箱连线、010C 连线统计、015 先修图谱。

核对基准：`origin/develop` = `919ef25a4442d6e9ebb4b11ad2acadb05819348f`（PR #69）；本地工作副本在 `feature/luo-wiring-fix-20261108`（head `d940b61`），带未提交修改（11-08 互测修复 + 11-09 文档同步 + 11-09 第二轮 P0 代码修复 + 11-09 第三轮完善优化）。按本人要求，本轮**不提交、不推送**。

> **2026-11-11 基准更新**：`origin/develop` 现为 `39ccbfef419b40b7862338c438402b00a8274c2f`（PR #83，2026-11-09 23:30）。本地工作副本已快进同步到该提交并保留全部未提交修改（24 个文件 + 集成待办文档），**仍未提交、未推送**。下文涉及「develop = 919ef25」「分支未合入」的表述均为 11-09 时的历史事实，现状见 B 节核对结论。

## A. 请黄俊诚按新 head 重跑并关闭的历史项

| 历史证据 | 绑定 head / 日期 | 当时结论 | 当前 develop 的事实 | 建议重跑入口 |
|---|---|---|---|---|
| `docs/evidence/spec-008/r37/handlers.json`、`handlers.txt` — R37-004-01 | `7204a140…` / 2026-10-16 | 未发布 quiz 发布备课实际 404 `NOT_FOUND`，APIC§3 要求 409；`expectedFailure` | `backend/apis/preparations.py:148-156` 单独查 `status!='published'` 并抛 409 `QUIZ_NOT_PUBLISHED`；`tests/test_preparations.py:165`、`tests/test_preparation_quiz_integration.py:211` 为普通断言，无 `expectedFailure` | `scripts/verify_r37_handlers.py --output <新目录>` |
| 同上 — R37-004-02 | `7204a140…` / 2026-10-16 | 学生关联元数据缺 `window_state`；`expectedFailure` | `backend/apis/preparations.py:90-96` 已生成 `window_state`（upcoming/open/closed）；`tests/test_preparation_quiz_integration.py:217` 断言该字段 | 同上 |
| `docs/evidence/spec-010b/i03/handlers/test_contract_future_cursor_must_return_actual_revision.json` — I03-007-02 | `4498fd97…` / 2026-10-17 | `GET /demo-sessions/1?after_revision=99` 返回 revision 99，DB 实为 1；`expectedFailure` | `backend/apis/demo.py` 的 `get_session` 不再用 `after_revision` 覆盖返回值，且新增 `unchanged` 轮询提示；`tests/test_i03_entry.py:69`、`tests/test_demo.py` 的 `test_after_revision_polling` 有真实 revision / 未来游标回归断言 | `scripts/verify_i03_handlers.py --output <新目录>` |
| `docs/evidence/spec-010b/i03/browsers/report.json`、`docs/evidence/spec-005/i01/browsers/report.json` — 007/010C/017/004 页面缺失 | `4498fd97…`、`96f4f298…` / 2026-10-17 | 无 demo 挂载、无备课/连线/连线统计页面；UI 阻断 | `frontend/js/main.js:955/958/972/976/1198` 分别挂载 KnowledgeGraphView、PreparationView、DemoView、WiringView、WiringStatsView；标题见 `demo-view.js:440`、`wiring-stats-view.js:164` | `scripts/verify_i03_browsers.py`、`scripts/verify_r37_browsers.py` |
| `docs/evidence/spec-005/i01/handlers/` — I01-017-01~04 四项 017 契约失败 | `96f4f298…` / 2026-10-17 | 窗口未开始/截止后提交、撤权成员旧写入、提交后重做等 4 项 `expectedFailure` | **可以重跑**：相关修复（11-08 分支与未提交改动中的窗口/撤权/重做处理）已随 11-09 的 develop 合入进入 `39ccbfe`（见 B 节核对结论），可按新 head 重跑对应 handler 脚本后据实关闭 | 按新 head 重跑对应 handler 脚本 |

重跑后建议据实更新的材料：`docs/evidence/c12a/acceptance-matrix.md` 与 `.json` 的 SPEC-008/R37 行、`docs/SPEC-008_R37_INTEGRATION.md:46/48/50`、`docs/SPEC-010B_I03_SUBCHAIN_INTEGRATION.md:25/26`、`docs/SPEC-005_I01_RESOURCE_SEAMS.md:44-48`、`docs/C12A_ACCEPTANCE_AUDIT.md:23/27/225`、`docs/C12C_DELIVERY_HUANG_JUNCHENG.md:82`。

### 重跑前必须注意：三个脚本硬编码了旧结论

直接按新 head 运行这些脚本，报告里仍会写出「阻断」，无法据此关闭矩阵：

- `scripts/verify_r37_handlers.py:45` 固定写 `'acceptance': 'blocked while R37-004-01/02 or preparation UI gaps remain'`；
- `scripts/verify_r37_browsers.py:99-100` 固定写入两条 `known_contract_failures`（404 ≠ 409、缺 `window_state`）；
- `scripts/verify_i03_handlers.py:25` 固定写 `'007_contract_defects': ['future after_revision replaces current revision; owner 罗浩铭']`。

请原作者先按重跑结果更新脚本中的这些静态字段，或在报告中明确标注该字段为历史快照、不代表本次结果；本人不代改队友的验证脚本与证据文件。另请注意 `scripts/verify_i03_handlers.py` 会把 `git status --porcelain` 记入 `dirty_paths`，重跑应在干净检出上进行，并把真实 `git rev-parse HEAD` 写入 `tested_head`。

## B. 请组长安排合入的本人改动（尚未交付）

> **2026-11-10 核对结论**：下表三个分支 head（`d940b61`、`23342c0`、`7156eb8`，含 `7d5e2ae`、`ea8f92b`、`0b5d77b`、`89bd484`）**已全部是 `origin/develop=39ccbfe` 的祖先**——「是否 develop 祖先」列的「否」为 11-09 时的历史状态，现已作废。仍待交付的是**当前工作副本的未提交改动**（11-09 第二/三轮修复与文档），见下表第四行。

| 分支 / 位置 | head | 内容 | 是否 develop 祖先 |
|---|---|---|---|
| `origin/feature/luo-wiring-fix-20261108` | `d940b61` | DEF-002/003 备课与连线视图时间处理、`7d5e2ae` 连线接口/引擎修正、`ea8f92b` vite 配置修复、`d940b61` 动作历史契约 | 否 |
| `origin/feature/luo-wiring-re001-20261108` | `23342c0` | RE-001 动作 payload 前置校验与重放兜底（避免 500），含 `tests/test_wiring.py` 回归 | 否 |
| `origin/feature/luo-graph-layout-20261108` | `7156eb8` | 图谱「添加/显示全部」按钮静默失效、孤立节点布局、`89bd484` DEF-001/DEF-005 | 否 |
| 当前工作副本（未提交） | — | 11-08 互测修复：`backend/apis/wiring.py`、`backend/engines/wiring.py`、`backend/apis/knowledge_security.py`、`backend/models/knowledge.py`、`frontend/js/knowledge-graph-layout.js` 及其测试、`frontend/js/knowledge-graph-view.js`、`tests/test_knowledge_graph.py`、`tests/test_wiring.py`；11-09 第二轮 P0 修复：`backend/engines/wiring.py`（EXP-03 判定、undo/redo）、`backend/apis/wiring.py`（服务端状态落库、动作入口校验）、`frontend/js/wiring-sim.js`、`wiring-view.js` 及两者测试；11-09 第三轮完善：`backend/apis/analytics.py`、`backend/apis/demo.py`、`backend/apis/preparations.py`、`backend/apis/knowledge_security.py`、`frontend/js/wiring-view.js`、`frontend/js/knowledge-graph-layout.js` 及 `tests/test_wiring.py`、`test_demo.py`、`test_wiring_analytics.py`、`test_knowledge_graph.py`、`frontend/js/wiring-view.test.js`、`knowledge-graph-layout.test.js`；另含本人交付文档与个人设计报告（.md/.docx） | 否 |

建议顺序：先把未提交改动按「11-08 互测修复 / 11-09 P0 修复 / 个人文档」拆成可审阅的提交，再把三个分支按 re001 → fix → graph-layout 依次合入 `develop`（或合并为一个 PR），跑全仓 CI；合入后更新 [交付索引](LUO_HAOMING_DELIVERY.md) 的「待合入修复」表，并回到 A 节重跑 I01-017 四项契约。

**拆分提醒**：11-09 时工作副本相对旧 develop 的 diff 曾混入石佰合 SPEC-018 的判分引擎、Logisim fixtures 与 CI 脚本；**11-11 起本地已同步 `39ccbfe`，SPEC-018 已是 develop 的一部分，该提醒不再适用**，按分支挑选合入时以 `git diff` 实际清单为准。仓库里另有未跟踪目录 `.trae-html-share-packages/`、`.workbuddy/` 与桌面快捷方式，提交时不要一并带入。

11-09 本地复测（Python 3.12.10、Node 22.22.2、ruff 0.17.0）共三轮：72 项后端 / 51 项前端（复测基线）→ **78 项 / 122.449 秒、53 项前端**（第二轮 P0 修复）→ **84 项 / 110.452 秒、57 项前端**（第三轮完善），三轮 lint/build/ruff 均全绿。结果对应**带未提交改动的工作副本**，不等于 develop 合入后的 CI 结论；被取消的全仓 `unittest discover` 未重跑。详见[测试报告](TEST_REPORT_LUO_HAOMING.md)。

11-11 同步 `39ccbfe` 后定向复测：后端 100 项 / 112.288 秒（含 11-11 新增 6 条 010C 接口层用例，见 C 节第 4 条）、前端 218 项（develop 新增队友用例后总数）、ruff / lint / build 全绿。

## C. 本人待补的证据（不依赖队友）

1. **TV-02**（本人执行、黄俊诚复核）：EXP-01/02/03 同动作连接/拆线/撤销/重做/set_input/step/reset，记录动作 JSON、逐步状态、旧 revision 与跨时钟 undo 拒绝，附复核人；PRD §10.4.3 目前仍记「验证状态均为未执行」。
2. **M9 三项实验连线整包**：现有端到端只覆盖 EXP-01 v2 一条链路，不足以代替 M9。
3. **CP-4 真实交互演示**：双浏览器跟随、投屏、并发冲突现场；按 [检查点材料](checkpoints/LUO_HAOMING_2026-11-05.md) 的脚本填写日期、执行人、输入、预期、实际、日志/截图位置与 commit。PRD §10.2：CP-4 未完成个人成绩不高于 80 分。
4. **AC 覆盖缺口**：11-09 第三轮已补 017 的 AC-05（SPA 离开确认）与 AC-08（键盘撤销/重做、状态文字与无障碍属性）定向用例；**11-11 已补 010C 接口层定向用例 6 条**（`tests/test_wiring_analytics.py` 的 `WiringAnalyticsApiTest`：父 AC-01 同筛选可复算与快照读回、AC-02 学生/未选课学生权限边界、AC-03 空课程 rate=null、AC-04 导出 CSV 与页面同一 `analysis_run_id` 快照逐格一致、真实提交/草稿/结构错误对指标的影响）。仍需补：R28 中 RESET/ENABLE 持久化与前后端逐拍重放一致（已有 undo/redo 往返用例，但 R28 未全部关闭）、窗口缩放/信号不只靠颜色的人工核对。
5. **证据目录**：`docs/evidence/` 下补 004/007/017/010C/015 的专用证据，`acceptance-matrix` 中当前无这 5 个 SPEC 的验收行。
6. **TV-01 复核**（与石佰合协作）：真实 Logisim JAR 与固定 Java 基线，当前健康检查 `grader_ready=false`。

## D. 11-09 已同步的材料

[LUO_HAOMING_DELIVERY.md](LUO_HAOMING_DELIVERY.md)、[TEST_REPORT_LUO_HAOMING.md](TEST_REPORT_LUO_HAOMING.md)、[USER_GUIDE_LUO_HAOMING.md](USER_GUIDE_LUO_HAOMING.md)、[checkpoints/LUO_HAOMING_2026-11-05.md](checkpoints/LUO_HAOMING_2026-11-05.md)、[reports/24201723_罗浩铭_设计报告.md](reports/24201723_罗浩铭_设计报告.md) 及其 Word 版、`docs/index.html`，另修正 `tests/test_preparation_quiz_integration.py:212/218` 两条仍写「actual 404」的 docstring。11-09 第二轮还改了本人业务代码与测试：`backend/engines/wiring.py`、`backend/apis/wiring.py`、`frontend/js/wiring-sim.js`、`wiring-view.js`、`tests/test_wiring.py`、`frontend/js/wiring-sim.test.js`、`wiring-view.test.js`；第三轮按审查清单继续完善 `backend/apis/analytics.py`、`demo.py`、`preparations.py`、`knowledge_security.py`、`frontend/js/wiring-view.js`、`knowledge-graph-layout.js` 及对应测试，并同步本清单、测试报告与个人设计报告。以上均为本人材料，未改动队友的文档、脚本或证据文件；按本人要求未执行 git 提交或推送。
