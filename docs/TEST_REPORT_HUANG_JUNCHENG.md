# 黄俊诚七个SPEC测试报告

黄俊诚（24201716），2026-10-28，Asia/Shanghai。适用范围为005、006、008、010B、011、012、013。本文把已有测试和完整验收记录组织为可复核报告，供课程检查及小组汇总使用。代码已进入develop的事实、本人适用本地通过和完整课程验收分别登记；本轮C12c没有重新运行这些业务测试，只重算矩阵和材料。

## 依据与测试环境

完整集合以[PRD§11.5](PRD.md#acceptance-index)及[131行逐项矩阵](evidence/c12a/acceptance-matrix.md)为准，包含31项AC、37项业务R、28项共通R和35组NF；010B继承父SPEC-010/AC-01—05，不新造010B验收编号。每行的输入/预期、实际、执行人、测试入口、结果、head/tested及附件保留在[原JSON](evidence/c12a/acceptance-matrix.json)，不以本报告的概述替代。

原本地运行使用Windows、临时隔离SQLite、真实Flask handler或socket HTTP及Vue页面；具体Python/Node版本随历史报告记录，不能统一改称课程目标版本。远程Actions使用其原始日志记录的Python3.12和Node22。浏览器版本、时区、dirty_paths及测试时间按每份原报告固定。账号bootstrap、TEST_NOW、网络中断、构建/计算失败等夹具均与真实业务请求分层记录。

目标Linux4核8GB、50会话、一个真实worker仍是待实测条件。单次测试耗时不是API百分位性能，也不能证明生产可恢复或教学账号验收。

## 2026-10-28矩阵口径

按develop `8e32fb41ab9453f8b4b4f8e7be86153a183b88dc` 已合入代码、测试、证据和PR状态重算：131行本地81通过/0失败/50阻断/0待执行，集成81通过/0失败/50阻断/0待执行。16行由旧阻断改为通过：SPEC-005/R20、SPEC-011/AC-02/R20/R35/R46/NF-SEC/NF-UI六行、SPEC-012/AC-01—04/R20/R34/R35/R46/NF-SEC九行。依据是#14 actual merge `3368060`、#15 actual merge `0a2b84c`、#27/#29—#35 develop合入提交及固定证据；每行旧值和重算依据保存在JSON的`C12c_重算`/`C12c_历史记录`。

历史数字保留：2026-10-15 C12a为本地80/0/51、集成59/72；2026-10-16 C12b为本地80/0/51、集成62/69；按本文件逐行实数为集成65/66（#27及#29—#35已合入但行状态未同步）。旧数字不删除，但不再作为当前结论。未合入的PR #40（head `7a99ca2`）也登记81/50，本材料没有把其文件或数字当作develop事实。

## 复用的测试与固定证据

| SPEC及重点 | 测试入口 | 原有效证据与范围 |
|---|---|---|
| 005章节、发布可见性、收藏/完成 | [test_knowledge.py](../tests/test_knowledge.py)、[真实集成](../tests/test_knowledge_integration.py) | [实施说明](SPEC-005_IMPLEMENTATION.md)、[双浏览器JSON](evidence/spec-005/browsers/browser-results.json)；真实权限/进度及390px，图片接缝未关闭 |
| 006五题型、版本、交卷、批阅、练习/错题 | [试卷受理](../tests/test_attempts.py)、[公开练习](../tests/test_practices.py) | [实施说明](SPEC-006_IMPLEMENTATION.md)、C12a[干净真实HTTP/UI报告](evidence/c12a/report.json)；五题型/旧版本/错题/权限等，原C02—C04夹具证据按原性质保留 |
| 008专用发布、冻结名单、逐题统计、显式讲评 | [test_quizzes.py](../tests/test_quizzes.py) | [实施说明](SPEC-008_IMPLEMENTATION.md)、[2026-10-14旧基线双浏览器](evidence/spec-008/browsers/browser-results.json)（tested `917ea087`，各8组）；[2026-10-28 C05补证引用](evidence/c12c/spec-008-20261028-reference.md)（PR #46 head `9a8343c`，open/未合并，tested `55167f6`，双浏览器各10组、390px、page_errors=[]） |
| 010B真实样本、空样本、成绩、旧ID/CSV | [知识统计](../tests/test_knowledge_analytics.py)、[分类成绩](../tests/test_score_analytics.py)、[专用quiz联合](../tests/test_quiz_analytics_integration.py) | [实施说明](SPEC-010B_IMPLEMENTATION.md)、[C12a审计](C12A_ACCEPTANCE_AUDIT.md)及其中固定C07/专用联合证据；4答3对75%、批分后新旧快照分离等 |
| 011检索、revision失效、失败恢复 | [test_qa.py](../tests/test_qa.py) | [17项专题日志](evidence/spec-011/c10-focused-tests.txt)、[干净双浏览器报告](evidence/spec-011/browsers/REPORT.md)，tested `36854081`，各9组；#14 actual merge `3368060` 已合入develop；阈值边界是算法夹具 |
| 012同口径推荐、冷启动、练习资格 | [test_recommendations.py](../tests/test_recommendations.py) | [13项专题日志](evidence/spec-012/c11-topic-tests.txt)、[干净双浏览器报告](evidence/spec-012/browsers/REPORT.md)，tested `e8da2410`，各7组；#15 actual merge `0a2b84c` 已合入develop；计算失败为明确夹具 |
| 013确定性求解、预算、草稿、重放 | [输入](../tests/test_generation_input.py)、[求解](../tests/test_generation_solver.py)、[快照](../tests/test_generation_snapshot.py)、[HTTP](../tests/test_generated_papers.py) | [实施说明](SPEC-013_IMPLEMENTATION.md)、[干净C09报告](evidence/spec-013/c09-browsers/REPORT.md)，tested `641d6aeb`，各5组；100000节点等HTTP/组件证据分开 |

以上短SHA仅导航；完整tested值以原报告字段为准，不能把后续证据提交SHA替换进去。上述组数来自各历史版本，不相加作为当前head的新通过数量。原始失败、预跑、未提交树和正式干净运行亦不合并计数。006 C02/C03的PR #45补证仍open，本材料忽略且未引用其未合入证据。

## C12b三个NF-UI与矩阵版本

006/008共用时间显示及012依据截止已在干净 `dfb23271` 受影响集成通过。Chrome155.0.8059.41（UTC）、Edge155.0.4283.45（America/Los_Angeles）中paper各4组、recommendation各3组，dirty_paths=[]、page_errors=[]；两报告和10图在#27固定head中，[历史入口](C12C_DELIVERY_HUANG_JUNCHENG.md#验收矩阵重算cp-5核心)提供来源限定。#27已由develop合入提交`4b8a5fb`合入，不再是“待合入”；其head `7096b49`已核验为develop祖先。

该补验不改UTC存储/GET data/CSV、不改服务器截止、讲评保护和成功键快照。组件替身、真实handler、socket HTTP/UI、截图目视是不同证据。C12c不重跑26+8组件、5+2 handler或两个浏览器脚本。当前矩阵按行实数为本地80/0/51、集成65/66，2026-10-28重算为81/50；完整131行没有新增“不适用”或虚构批准。

## 本轮远程读取与新增检查

本轮fetch后develop为`8e32fb41ab9453f8b4b4f8e7be86153a183b88dc`。已合入PR及Git祖先核验见[2026-10-28接入快照](evidence/c12c/entry-state-20261028.json)：#4/#7/#9/#10/#11/#12/#13/#14/#15/#16/#17及#27/#28/#29—#35均在develop链上。PR #46（008补证）open/未合并/reviews=[]，head CI run40647967505 success（按PR #46说明和上一轮交接记录），但未实际合并；PR #45（006补证）open并忽略；PR #41（005图文）draft；PR #40（010B合入后收口）open/未合并。

008补证为PR #46 head的真实执行：定向后端48项（113.238秒）、前端135项、lint/build、ruff、check_docs通过；Chrome/Edge各10组、page_errors=[]、390px。该证据不在本分支或develop，只作未合入补证引用，不改变008相关行基于#9的判定；逐项见[008补证引用](evidence/c12c/spec-008-20261028-reference.md)。

本轮新增验证限六文档检查、新材料本地链接、131行矩阵/JSON一致性、合入祖先、Word内容与结构检查。实际检查输出保存在[2026-10-28材料检查记录](evidence/c12c/material-checks-20261028.json)。C12c最终head的远程CI结果独立写对应PR及本地交接，未产生前不预填通过。

## 2026-10-28 PR #47 CI 偶发失败留痕

PR #47 head `7fb7b56` 的首次 CI run 40669449969 attempt 1 中，ci-test 在 376 项全量后端测试的 `tests.test_qa.QAIntegrationTest.test_parallel_queries_and_restart_backup_rebuild_from_facts`（`tests/test_qa.py:279`）失败：三个并发查询之一返回 503 `DB_BUSY`（期望 200），共 1 failure/376 tests，耗时 349.677 秒。该提交只改 docs/evidence，未改 backend/tests；本地同一测试重复 14 次，1 次失败、13 次通过，失败现象与 CI 相同。

该失败是 SPEC-011 QA 并发/数据库 busy 重试的既有偶发稳定性问题，不是本材料包引入；本轮不改业务，列入 SPEC-011 后续待办（负责人黄俊诚），在独立 SPEC-011 feature 修复后重跑。同一 head 的 attempt 2 已由 GitHub rerun 成功（ci-required success）；首次失败和 rerun 结果分别保留，不能把 rerun 成功写成首次通过或教师验收。

## 未完成验收与失败留痕

完整SPEC、跨模块I-01/02/03、R22/R45全组证据、R47完整复核、目标性能、生产同点恢复/90天保留、Gitea/课堂仍未凭材料整理关闭。其余115行结果及所有固定head/tested、编号、附件保持；50条阻断行中的待执行条件写在矩阵缺口列。

保留原006会话/JSON信封/late表单、008同线程嵌套请求及重复文本定位、010B页面加载与CSV/日期、012 Edge空图与日志空行、013约束/种子和C12a/b辅助检查失败记录。每个修正的实际原因和复验位于对应实施说明及固定报告；不把失败删除后汇总成“全程无异常”。C12c读取助手的范围数组和输出编码问题已在历史材料中记录，未影响业务结果。
