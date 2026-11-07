# 罗浩铭个人交付索引

罗浩铭，学号 24201723，242017 班 g24201710 组。本文供组员和课程检查人员定位本人负责的设计、实现、测试及待补证据。依据为 [PRD 第 10.1 节实名分工](PRD.md#team-plan)。本人负责 SPEC-004 备课、SPEC-007 课堂演示、SPEC-017 实验箱连线三个基础模块，SPEC-010C 实验完成率与连线错误统计独立统计，SPEC-015 先修知识图谱智能模块；重点难点为交互网表与 CPU 单步仿真。实验箱与 Logisim 电路评测的全组集成由对应组员协作，不能用本人的模块测试代替整组验收。

| 课程所需材料 | 本人入口 | 证据范围 |
|---|---|---|
| 需求、接口、架构、数据库与变更 | [六份主文档索引](../README.md#1-文档入口)、本文 | 统一规范在 PRD/APIC/DBD；本人不另立契约，模块细节见[设计报告](reports/24201723_罗浩铭_设计报告.md) |
| 代码与测试 | `backend/apis/wiring.py`、`preparations.py`、`demo.py`、`knowledge.py`、`analytics.py`；`frontend/js/preparation-*.js`、`wiring-*.js`、`graph-view.js`；对应 `tests/test_*.py` | [测试报告](TEST_REPORT_LUO_HAOMING.md)逐项标明本地执行、CI 与未执行范围 |
| 阶段检查 | [个人检查点材料](checkpoints/LUO_HAOMING_2026-11-05.md) | CP-2 至 CP-5 的可演示内容及待教师确认项 |
| 运行与用户说明 | [本人模块使用说明](USER_GUIDE_LUO_HAOMING.md)、[README 本地运行](../README.md#8-本地运行与验证) | 教师、学生操作路径与失败处理；目标环境仍需实测 |
| 个人设计报告 | [Markdown 内容源](reports/24201723_罗浩铭_设计报告.md)、[Word 版](reports/24201723_罗浩铭_设计报告.docx) | 任务书要求的个人文件名；教师最终格式附件未提供，不能称为按附件定稿 |

## 可复核的 GitHub 记录

**后端实现（PR #20–#24，均已合并）。** 本人五个模块的实现以五个 PR 于 2026-10-16T05:50:33Z 批量合入 `develop`：[#20](https://github.com/Gindama713/nchu-web-learning_platform/pull/20) 备课（merge `4399cb8`）、[#21](https://github.com/Gindama713/nchu-web-learning_platform/pull/21) 课堂演示（`d3e0e33`）、[#22](https://github.com/Gindama713/nchu-web-learning_platform/pull/22) 实验箱连线（`5eea466`）、[#23](https://github.com/Gindama713/nchu-web-learning_platform/pull/23) 实验完成率与连线错误统计（`6ec4c53`）、[#24](https://github.com/Gindama713/nchu-web-learning_platform/pull/24) 先修知识图谱（`eaaf043`）。其中 #24 的 21 个改动文件全部为后端与测试（`backend/apis/wiring.py`、`preparations.py`、`demo.py`、`backend/engines/wiring.py`、迁移 004/007/010c/015/017、`tests/test_wiring.py`、`test_wiring_analytics.py`、`test_preparations.py`、`test_demo.py`、`test_knowledge_graph.py` 等），不含任何 `frontend/` 文件。本人模块的后端引擎、接口、迁移与后端测试自此均在主干。

**前端整合（PR #49，已合并）。** 前端收尾分支 `feature/spec-frontends-batch` 的 head 为 `c06156927c093f1dcda7f431d3342950f83866f8`。[PR #49](https://github.com/Gindama713/nchu-web-learning_platform/pull/49)（标题「feat: SPEC-004/017/010C 三个模块前端（挂入分区导航）」）于 2026-10-30T08:34:26Z 合入 `develop`，merge SHA `ffc5aa13de180a232cfc4b40c57abcca352dfd24`，改动 15 文件（+2417/−1）。[对应 Actions run 40862510430](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/40862510430)（run_attempt 2）的 ci-policy、ci-lint、ci-build、ci-test、ci-required 均为 success；`ci-grader` 在 develop 规则下为 skipped，不能写成通过。

该 PR 实际合入的前端文件为 `preparation-client.js`、`preparation-client.test.js`、`preparation-view.test.js`、`wiring-client.js`、`wiring-sim.js`、`wiring-sim.test.js`、`wiring-stats-view.js`、`wiring-stats-view.test.js`、`wiring-view.test.js`、`styles/preparations.css`、`styles/wiring.css`、`styles/wiring-stats.css` 及 `main.js` 的分区挂载。合并与 CI 属于工程证据，不等同教师检查、非作者规格复核或 `main` 发布验收。

## 需要在检查时说明的整合事实

1. **SPEC-007 课堂演示的视图层采用 develop 既有实现。** PR #49 提交说明记录了「SPEC-007 demo and SPEC-015 graph collisions resolved in favor of the develop versions」：`frontend/js/demo-view.js` 为姜苏豪版本，本人的同名实现与 `demo-view.test.js` 未进主干；本人保留 `demo-client.js`（在 develop 中）承担接口契约与前端测试。因此演示模块的组件测试在整合时被移除，验收走浏览器手工流程与后端 `tests/test_demo.py`。
2. **SPEC-015：后端已合入，视图层未合入 develop。** 本人图谱的后端部分（先修成环检测、迁移 015、图谱 API 与 `tests/test_knowledge_graph.py`）经 PR #24 于 2026-10-16 合入 develop；develop 的 `frontend/js/` 只有 `knowledge-graph-view.js`（力导向布局），不含本人的 `graph-view.js`（聚焦根、先修可达路径、加边表单）。该文件仅存在于本机工作副本，属未合并改动；先修成环拒绝在后端 `backend/models/knowledge.py`（`PREREQUISITE_CYCLE`，422）已生效，与视图层归属无关。
3. 本地工作副本无 `.git` 目录，本次补交的四份材料与个人报告经单独分支 `feature/luo-delivery-20261105` 提交，首个提交为 `b514f0b`（基于 `develop` 的 `e9d2940`）。该分支已开 [PR #59](https://github.com/Gindama713/nchu-web-learning_platform/pull/59)（7 文件 +410/−0）。首次 CI run 42042690543 中 ci-lint 因 `scripts/md2docx_report.py` 一处 SIM115 失败（其余 job 均 success）；当日本地 ruff 0.17.3 复现并修复，修复提交 `7a0a96a` 推送后 [CI run 42044409767](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/42044409767) 重跑：ci-lint、ci-build、ci-test、ci-policy、ci-required 均 success，`ci-grader` 为 skipped（仓库无 Logisim 判分环境），`mergeable_state=clean`。PR 评审与合并尚未发生，不能等同于已验收。

## 尚不能勾选的交付

真实 Logisim JAR 与固定 Java 的电路判分（健康检查 `grader_ready=false`）、目标 Linux 环境与 50 会话、完整备份恢复演练、教师课堂验收结论、Gitea 同 SHA 归档与超星提交均未由本材料证明。CP-4 是否被认定为「重点难点」由教师检查决定，本人不提前宣称得分。小组总报告、源码设计 ZIP 属组长汇总责任，不把个人 Word 报告改名充作小组报告。
