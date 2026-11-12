# 罗浩铭个人交付索引

罗浩铭，学号 24201723，242017 班 g24201710 组。本文供组员和课程检查人员定位本人负责的设计、实现、测试及待补证据。依据为 [PRD 第 10.1 节实名分工](PRD.md#team-plan)。本人负责 SPEC-004 备课、SPEC-007 课堂演示、SPEC-017 实验箱连线三个基础模块，SPEC-010C 实验完成率与连线错误统计独立统计，SPEC-015 先修知识图谱智能模块；重点难点为交互网表与 CPU 单步仿真。实验箱与 Logisim 电路评测的全组集成由对应组员协作，不能用本人的模块测试代替整组验收。

**最后核对：2026-11-09。** 本文 11-05 首次整理，11-09 依据当前 `develop`、远程分支与本地工作副本重新核对，修正 PR #59 合入状态、SPEC-015 视图归属与本地仓库状态三处过时表述，并新增「待合入修复」一节。核对只覆盖本人口径，不改写教师验收结论。

| 课程所需材料 | 本人入口 | 证据范围 |
|---|---|---|
| 需求、接口、架构、数据库与变更 | [六份主文档索引](../README.md#1-文档入口)、本文 | 统一规范在 PRD/APIC/DBD；本人不另立契约，模块细节见[设计报告](reports/24201723_罗浩铭_设计报告.md) |
| 代码与测试 | `backend/apis/wiring.py`、`preparations.py`、`demo.py`、`knowledge.py`、`analytics.py`；`frontend/js/preparation-*.js`、`wiring-*.js`、`demo-client.js`、`knowledge-graph-view.js`、`knowledge-graph-layout.js`；对应 `tests/test_*.py` | [测试报告](TEST_REPORT_LUO_HAOMING.md)逐项标明本地执行、CI 与未执行范围；本人命名的 `graph-view.js` 不在 `develop`，见下 |
| 阶段检查 | [个人检查点材料](checkpoints/LUO_HAOMING_2026-11-05.md) | CP-2 至 CP-5 的可演示内容及待教师确认项 |
| 运行与用户说明 | [本人模块使用说明](USER_GUIDE_LUO_HAOMING.md)、[README 本地运行](../README.md#8-本地运行与验证) | 教师、学生操作路径与失败处理；目标环境仍需实测 |
| 个人设计报告 | [Markdown 内容源](reports/24201723_罗浩铭_设计报告.md)、[Word 版](reports/24201723_罗浩铭_设计报告.docx) | 任务书要求的个人文件名；教师最终格式附件未提供，不能称为按附件定稿 |

## 可复核的 GitHub 记录

**后端实现（PR #20–#24，均已合并）。** 本人五个模块的实现以五个 PR 于 2026-10-16T05:50:33Z 批量合入 `develop`：[#20](https://github.com/Gindama713/nchu-web-learning_platform/pull/20) 备课（merge `4399cb8`）、[#21](https://github.com/Gindama713/nchu-web-learning_platform/pull/21) 课堂演示（`d3e0e33`）、[#22](https://github.com/Gindama713/nchu-web-learning_platform/pull/22) 实验箱连线（`5eea466`）、[#23](https://github.com/Gindama713/nchu-web-learning_platform/pull/23) 实验完成率与连线错误统计（`6ec4c53`）、[#24](https://github.com/Gindama713/nchu-web-learning_platform/pull/24) 先修知识图谱（`eaaf043`）。其中 #24 的 21 个改动文件全部为后端与测试（`backend/apis/wiring.py`、`preparations.py`、`demo.py`、`backend/engines/wiring.py`、迁移 004/007/010c/015/017、`tests/test_wiring.py`、`test_wiring_analytics.py`、`test_preparations.py`、`test_demo.py`、`test_knowledge_graph.py` 等），不含任何 `frontend/` 文件。本人模块的后端引擎、接口、迁移与后端测试自此均在主干。

**前端整合（PR #49，已合并）。** 前端收尾分支 `feature/spec-frontends-batch` 的 head 为 `c06156927c093f1dcda7f431d3342950f83866f8`。[PR #49](https://github.com/Gindama713/nchu-web-learning_platform/pull/49)（标题「feat: SPEC-004/017/010C 三个模块前端（挂入分区导航）」）于 2026-10-30T08:34:26Z 合入 `develop`，merge SHA `ffc5aa13de180a232cfc4b40c57abcca352dfd24`，改动 15 文件（+2417/−1）。[对应 Actions run 40862510430](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/40862510430)（run_attempt 2）的 ci-policy、ci-lint、ci-build、ci-test、ci-required 均为 success；`ci-grader` 在 develop 规则下为 skipped，不能写成通过。

该 PR 实际合入的前端文件为 `preparation-client.js`、`preparation-client.test.js`、`preparation-view.test.js`、`wiring-client.js`、`wiring-sim.js`、`wiring-sim.test.js`、`wiring-stats-view.js`、`wiring-stats-view.test.js`、`wiring-view.test.js`、`styles/preparations.css`、`styles/wiring.css`、`styles/wiring-stats.css` 及 `main.js` 的分区挂载。合并与 CI 属于工程证据，不等同教师检查、非作者规格复核或 `main` 发布验收。

## 需要在检查时说明的整合事实

1. **SPEC-007 课堂演示的视图层采用 develop 既有实现。** PR #49 提交说明记录了「SPEC-007 demo and SPEC-015 graph collisions resolved in favor of the develop versions」：`frontend/js/demo-view.js` 为姜苏豪版本，本人的同名实现与 `demo-view.test.js` 未进主干；本人保留 `demo-client.js`（在 develop 中）承担接口契约与前端测试。因此演示模块的组件测试在整合时被移除，验收走浏览器手工流程与后端 `tests/test_demo.py`。历史契约缺陷 I03-007-02（未来 `after_revision` 虚报 revision）已在 develop 的 `backend/apis/demo.py` 修正，`tests/test_i03_entry.py` 有回归用例；该失败证据绑定 2026-10-17 的 `4498fd97`，不代表当前主干状态。
2. **SPEC-015：后端已合入，视图功能由 develop 现有组件承接。** 后端部分（先修成环检测、迁移 015、图谱 API 与 `tests/test_knowledge_graph.py`）经 PR #24 于 2026-10-16 合入 develop。本人命名的 `graph-view.js`（聚焦根、可达先修路径、加边表单）**既不在 develop，也不在当前工作副本**，仅存在于远端 `origin/integration/final-20261029`。11-05 本文所写「仅存在于本机工作副本」「develop 只有力导向版」均已过时：2026-11-07 前端重做后，develop 的 `frontend/js/knowledge-graph-view.js` 已提供点节点聚焦子图、添加关系表单、成环拒绝与传递闭包开关，页面只挂载这一张图谱卡片，[使用说明](USER_GUIDE_LUO_HAOMING.md) 中「两个同名卡片」的说法同步作废。因此 015 的功能链路在主干可用，但**不能把 `graph-view.js` 这个文件名算作本人已合入的代码**；先修成环拒绝在 `backend/models/knowledge.py`（`PREREQUISITE_CYCLE`，422）生效，与视图归属无关。
3. **个人交付材料已合入 develop。** 四份材料与个人报告经 `feature/luo-delivery-20261105` 提交（首个提交 `b514f0b`），[PR #59](https://github.com/Gindama713/nchu-web-learning_platform/pull/59) 首次 CI run 42042690543 的 ci-lint 因 `scripts/md2docx_report.py` 一处 SIM115 失败，修复提交 `7a0a96a` 后 [CI run 42044409767](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/42044409767) 的 ci-lint、ci-build、ci-test、ci-policy、ci-required 均 success，`ci-grader` skipped。**该 PR 后续已由 `4feb30e`（Merge pull request #59, reviewed）合入 develop**；11-05 本文「PR 评审与合并尚未发生」已过时。合入属工程证据，不等于教师验收。
4. **本地工作副本有 `.git` 目录。** 当前在 `feature/luo-wiring-fix-20261108` 分支且有未提交修改，11-05 所写「本地无 `.git` 目录」是当时另一份副本的状态，不适用于当前工作区。

## 2026-11-08/09 待合入修复（本人责任）

11-08 互测后新增的修复已推送到远程个人分支，但**均不是 `develop` 的祖先**，按主干口径尚未交付：

| 提交 | 分支 | 内容 | 已入 develop |
|---|---|---|---|
| `7d5e2ae` | `feature/luo-wiring-fix-20261108` | DEF-002/003：备课与连线视图时间处理、连线接口与引擎修正 | 否 |
| `23342c0` | `feature/luo-wiring-re001-20261108` | RE-001：动作 payload 前置校验与重放兜底，避免 KeyError 冒泡成 500 | 否 |
| `7156eb8` | `feature/luo-graph-layout-20261108` | 图谱「添加/显示全部」按钮静默失效 | 否 |
| `89bd484`、`0b5d77b` | 同一批分支 | DEF-001 局域网写入 403、DEF-005 子图漏包含关系、孤立节点布局 | 否 |

工作副本另有未提交改动，分四类：① 11-08 互测修复（`backend/apis/wiring.py`、`backend/engines/wiring.py`、`knowledge_security.py`、`backend/models/knowledge.py`、`knowledge-graph-*.js` 与两个后端/前端测试）；② 2026-11-09 第二轮按代码审查修的三处 P0 缺陷（EXP-03 提交判定、undo/redo 前后端重放、服务端状态落库）与动作入口校验，涉及 `backend/engines/wiring.py`、`backend/apis/wiring.py`、`frontend/js/wiring-sim.js`、`wiring-view.js` 及对应测试，该轮本地回归为后端 78 项、前端 53 项；③ 2026-11-09 第三轮完善优化（010C 时间口径、演示轮询与时间戳、动作入口与列表查询、AC-05/08 交互、图谱布局与 Origin 校验），最终本地回归为**后端 84 项、前端 57 项**，lint/build/ruff 全绿；④ 本人交付文档与个人设计报告（.md/.docx）的 11-09 同步。**按本人要求本轮不提交、不推送；这些改动也不是 develop 祖先，合入前不能宣称修复已生效。** 逐文件清单见[集成待办](LUO_HAOMING_INTEGRATION_TODO_2026-11-09.md) B 节，测试口径见[测试报告](TEST_REPORT_LUO_HAOMING.md)。

## 尚不能勾选的交付

- 真实 Logisim JAR 与固定 Java 的电路判分（健康检查 `grader_ready=false`）、目标 Linux 环境与 50 会话、完整备份恢复演练、教师课堂验收结论、Gitea 同 SHA 归档与超星提交均未由本材料证明。
- TV-02（本人执行、黄俊诚复核）、第 9 周 M9 三项实验连线整包、CP-4「真实交互演示」仍无实测结论；PRD §10.2/§10.4.1 把技术验证记为未执行，[检查点材料](checkpoints/LUO_HAOMING_2026-11-05.md) 的演示步骤是待执行脚本，不是通过记录。CP-4 是否被认定为「重点难点」由教师检查决定，未完成该项个人成绩不高于 80 分（PRD §10.2）。
- 队友 2026-10-28 的 [C12A 审计](C12A_ACCEPTANCE_AUDIT.md) 与 [C12c 交付](C12C_DELIVERY_HUANG_JUNCHENG.md) 仍把 004/007 契约缺陷记为「阻断」；代码虽已修，但未请原作者按新 head 重跑并更新 131 行矩阵，`docs/evidence/` 亦无本人五个 SPEC 的专用证据目录。
- 部分 AC 缺定向测试：017 的 AC-05（刷新恢复与离开提示）、AC-08（键盘/缩放可访问性）、R28（RESET/ENABLE 持久化重放），010C 父 AC-02（权限边界）与 AC-04（导出与页面同一 `analysis_run_id`）。
- 小组总报告、源码设计 ZIP 属组长汇总责任，不把个人 Word 报告改名充作小组报告。
