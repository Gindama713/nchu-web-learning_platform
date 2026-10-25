# 黄俊诚七个SPEC测试报告

> 2026-10-19当前收口：#27—#35及#38修复已合入develop；原004/007/017接口缺陷复验通过，仍缺页面/全组环境另列。131行现为本地81通过/50阻断、集成81通过/50阻断，见[合入后复验与剩余工作](SPEC-010B_POSTMERGE_ACCEPTANCE.md)。以下旧日期、SHA、计数和“待合入/失败”均为当时记录，不覆盖本条当前结论；完整SPEC及课堂未关闭。

黄俊诚（24201716），2026-10-16，Asia/Shanghai。适用范围为005、006、008、010B、011、012、013。本文把已有测试和完整验收记录组织为可复核报告，供课程检查及小组汇总使用。代码已进入develop的事实、本人适用本地通过和完整课程验收分别登记；本轮C12c没有重新运行这些业务测试。

## 依据与测试环境

完整集合以[PRD§11.5](PRD.md#acceptance-index)及[131行逐项矩阵](evidence/c12a/acceptance-matrix.md)为准，包含31项AC、37项业务R、28项共通R和35组NF；010B继承父SPEC-010/AC-01—05，不新造010B验收编号。每行的输入/预期、实际、执行人、测试入口、结果、head/tested及附件保留在[原JSON](evidence/c12a/acceptance-matrix.json)，不以本报告的概述替代。

原本地运行使用Windows、临时隔离SQLite、真实Flask handler或socket HTTP及Vue页面；具体Python/Node版本随历史报告记录，不能统一改称课程目标版本。远程Actions使用其原始日志记录的Python3.12和Node22。浏览器版本、时区、dirty_paths及测试时间按每份原报告固定。账号bootstrap、TEST_NOW、网络中断、构建/计算失败等夹具均与真实业务请求分层记录。

目标Linux4核8GB、50会话、一个真实worker仍是待实测条件。单次测试耗时不是API百分位性能，也不能证明生产可恢复或教学账号验收。

## 复用的测试与固定证据

| SPEC及重点 | 测试入口 | 原有效证据与范围 |
|---|---|---|
| 005章节、发布可见性、收藏/完成 | [test_knowledge.py](../tests/test_knowledge.py)、[真实集成](../tests/test_knowledge_integration.py) | [实施说明](SPEC-005_IMPLEMENTATION.md)、[双浏览器JSON](evidence/spec-005/browsers/browser-results.json)；真实权限/进度及390px，图片接缝未关闭 |
| 006五题型、版本、交卷、批阅、练习/错题 | [试卷受理](../tests/test_attempts.py)、[公开练习](../tests/test_practices.py) | [实施说明](SPEC-006_IMPLEMENTATION.md)、C12a[干净真实HTTP/UI报告](evidence/c12a/report.json)；五题型/旧版本/错题/权限等，原C02—C04夹具证据按原性质保留 |
| 008专用发布、冻结名单、逐题统计、显式讲评 | [test_quizzes.py](../tests/test_quizzes.py) | [实施说明](SPEC-008_IMPLEMENTATION.md)、[原干净双浏览器报告](evidence/spec-008/browsers/browser-results.json)，tested `917ea087`，各8组 |
| 010B真实样本、空样本、成绩、旧ID/CSV | [知识统计](../tests/test_knowledge_analytics.py)、[分类成绩](../tests/test_score_analytics.py)、[专用quiz联合](../tests/test_quiz_analytics_integration.py) | [实施说明](SPEC-010B_IMPLEMENTATION.md)、[C12a审计](C12A_ACCEPTANCE_AUDIT.md)及其中固定C07/专用联合证据；4答3对75%、批分后新旧快照分离等 |
| 011检索、revision失效、失败恢复 | [test_qa.py](../tests/test_qa.py) | [17项专题日志](evidence/spec-011/c10-focused-tests.txt)、[干净双浏览器报告](evidence/spec-011/browsers/REPORT.md)，tested `36854081`，各9组；阈值边界是算法夹具 |
| 012同口径推荐、冷启动、练习资格 | [test_recommendations.py](../tests/test_recommendations.py) | [13项专题日志](evidence/spec-012/c11-topic-tests.txt)、[干净双浏览器报告](evidence/spec-012/browsers/REPORT.md)，tested `e8da2410`，各7组；计算失败为明确夹具 |
| 013确定性求解、预算、草稿、重放 | [输入](../tests/test_generation_input.py)、[求解](../tests/test_generation_solver.py)、[快照](../tests/test_generation_snapshot.py)、[HTTP](../tests/test_generated_papers.py) | [实施说明](SPEC-013_IMPLEMENTATION.md)、[干净C09报告](evidence/spec-013/c09-browsers/REPORT.md)，tested `641d6aeb`，各5组；100000节点等HTTP/组件证据分开 |

以上短SHA仅导航；完整tested值以原报告字段为准，不能把后续证据提交SHA替换进去。上述组数来自各历史版本，不相加作为当前head的新通过数量。原始失败、预跑、未提交树和正式干净运行亦不合并计数。

## C12b三个NF-UI与矩阵版本

006/008共用时间显示及012依据截止已在干净 `dfb23271b470a93d557a2695fed0e04caf59d0d2`受影响集成通过。Chrome155.0.8059.41（UTC）、Edge155.0.4283.45（America/Los_Angeles）中paper各4组、recommendation各3组，dirty_paths=[]、page_errors=[]；两报告和10图在待合入#27的固定head中，[来源入口](C12C_DELIVERY_HUANG_JUNCHENG.md#验收数字的两个来源)提供精确链接。

该补验不改UTC存储/GET data/CSV、不改服务器截止、讲评保护和成功键快照。组件替身、真实handler、socket HTTP/UI、截图目视是不同证据。C12c不重跑26+8组件、5+2 handler或两个浏览器脚本。develop现有登记59通过/72阻断，#27补验登记62通过/69阻断；两者本地均80通过/0失败/51阻断，完整131行没有新增“不适用”。

## 本轮远程读取与新增检查

本轮fetch后develop不变，原11个实现/补证PR的actual merge均核验为祖先，真实reviews另行读取，见[接入快照](evidence/c12c/entry-state.json)。PR #4/#7/#9/#10/#11/#12/#13各有Gindama713的一份APPROVED；#14/#15/#16/#17及#27的reviews为空。没有据此宣称R47完整关闭或两名非作者已满足；本轮只对#27重新读取threads/comments，均空。

#27精确head `7096b496504f62181f60987062b1397bdb96a937`的[Actions38896062651](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38896062651)重新读取run、6 jobs及ci-test原日志：policy/lint/test/build/required成功、grader依develop跳过；后端312项243.204秒、前端119项通过0失败。CI tested=`a4ed987609132694c08c59650f92721abc223e0d`只是测试引用，actual merge仍不存在。这是已有远程运行的重新读取，不是C12c本地业务运行，也不是C12c新head的CI。

本轮新增验证限六文档检查、新材料本地链接、原矩阵/证据字节保全、两个版本只差三行、合入祖先、设计报告内容与渲染检查。实际检查输出保存在[本轮材料检查记录](evidence/c12c/material-checks.json)。C12c最终head的远程CI结果独立写对应PR及本地交接，未产生前不预填通过。

## 未完成验收与失败留痕

完整SPEC、跨模块I-01/02/03、R22/R45全组证据、R47完整复核、目标性能、生产同点恢复/90天保留、Gitea/课堂仍未凭材料整理关闭。其余128行结果及所有固定head/tested、编号、附件保持。

保留原006会话/JSON信封/late表单、008同线程嵌套请求及重复文本定位、010B页面加载与CSV/日期、012Edge空图与日志空行、013约束/种子和C12a/b辅助检查失败记录。每个修正的实际原因和复验位于对应实施说明及固定报告；不把失败删除后汇总成“全程无异常”。C12c读取助手的范围数组和输出编码问题已修正，记录于接入快照，未影响业务结果。
