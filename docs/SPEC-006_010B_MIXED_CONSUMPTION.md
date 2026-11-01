# 生成作业/考试与混合客观来源的有限消费核对

黄俊诚（24201716），2026-10-18 Asia/Shanghai。本轮完成两个相邻工作包的可执行范围；未发现需要修复本人业务消费代码的缺陷。新增两项真实API联测、执行与独立复算脚本、脱敏证据和原矩阵增量；没有改业务源码、算法、API/DBD、迁移、CI或队友实现。完整模块和原跨链判定保持。

## 基线与固定证据复用

初始工作区干净，PR33分支head为`789745151a7885ca1e615be4660d6b80e92439b4`。首批只读本地计划§6/7、交接§3/10.1及该固定head的消费报告。fetch后`origin/develop=dfb23271b470a93d557a2695fed0e04caf59d0d2`，从它新建`feature/spec-006-010b-mixed-consumption`。

实读#27—#33的head均未变，全部open/非draft/未合入，真实comments/reviews/review_threads均[]；复用固定CI38896062651、38904433916、38907219999、38909993594、38994482166、38996421357、38998602097。临时merge引用不当作actual merge。#9/#12/#13/#15/#16/#17 actual merge分别核验属于origin/develop祖先（exit0）后，才消费008/010B/013/012/006；见[入口与祖先证据](evidence/mixed-consumption/entry-state.json)。没有复制未合入代码、测试或报告，没有改写旧PR。

先查[原矩阵](evidence/c12a/acceptance-matrix.json)、既有测试及PR，复用以下固定覆盖，不重跑算法或整包：

- [006实施](SPEC-006_IMPLEMENTATION.md)、`test_attempts.py`/`test_manual_scores.py`：五题型判分、原版本、窗口、幂等与批阅；[010B实施](SPEC-010B_IMPLEMENTATION.md)、`test_score_analytics.py`：分类/不同满分百分比、冻结名单、待批/缺交、旧ID/CSV；原C07浏览器tested=`29ade52f8ef27eeb7f287dd7f41ab35aaa83b88e`。
- [012实施](SPEC-012_IMPLEMENTATION.md)、`test_recommendations.py`：公式、reason、n=5/m=.8、28天半开边界以及混合来源数字ID；`test_knowledge_analytics.py`：固定多标签和知识周序列。这里仅补同一学生两周事实经过两个消费者后的逐条对照。
- [013实施](SPEC-013_IMPLEMENTATION.md)、`test_generated_papers.py`及原C08/C09：候选、求解、预算、成功重放及配分。原C09合并树浏览器tested=`641d6aeb2cb116478de0b0c5599de7606272b9b3`。PR33固定head已覆盖生成quiz→008→010B及公开练习→推荐/错题，本轮没有复制或重跑该整包。

依据为PRD§4.2/4.3及006/010B/012/013有效验收、APIC§4/5.1—5.3、DBD§4/5。本人职责见PRD§10.1。A/B只是工作包名称，不新增验收编号、成绩事实表、跨模块关联或跳转。

## A：013生成homework/exam→006→010B

同课三名学生经真实API注册/入课。013分别生成两张homework（10.01与20.02分）和一张exam（30.03分），seed42，各两题；两张作业使用同一对私有题，考试使用独立hard题对。草稿来源generation_snapshot_id、有序固定版本和配分经paper_item原表核对：作业1简答/单选顺序为501/500，作业2为1001/1001，考试简答/单选为1502/1501，均为百分之一分。生成只建草稿，发布另走006实际入口，冻结每卷三人。

作业1开始于10月6日，作业2/考试开始于10月13日，受控时钟分别真实受理交卷。S1作业1客观正确、简答待批；S2作业1空白交卷得真实0；作业2仅S1交卷并批至20.02分，其他缺交。首次homework查询为应交6/已交3/缺交3/已批2/待批1、均百分比50.00%，跨卷mean_score=null。quiz类别为0任务，没有把生成草稿或公开练习算作成绩。

考试S1客观错误/简答待批，S2仅客观正确、漏简答0，S3缺交；首次exam为应交3/已交2/缺交1/已批1/待批1，均百分比49.98%。批阅后S1简答满分15.02、S2客观15.01，两份最终成绩均百分比50.00%，原分均分15.02（同卷、保留两位）。没有把待批partial_score或缺交当最终0分。

随后真实批作业1简答3分，再追加单选v2（答案B、标签仅点2）。作业1旧客观仍v1答案A、原配分5.00，S1最终8.00/10.01；新跨作业平均百分比为`(0 + 100 + 800/1001×100)/3 = 59.97%`，分箱为1/0/1/0/1，mean_score仍null。单独筛选作业2得到原分20.02及百分比100%，exam类别不混入作业。周序列按paper.start_at分到两个上海周，而非按提交或批阅日期重分任务。

首次homework/exam的analysis_run_id、完整data及教师CSV在批阅、新版本后逐项/字节保持；页面恢复与下载同样保持。三张generation_snapshot原整行及input_sha256、有序版本、paper_item配分不变，它们与成绩analysis_run属于两类不同快照。本轮不再执行013重放，成功重放复用C09。

主证据：[handler脱敏请求响应、阶段原表、名单、版本、两类快照和审计](evidence/mixed-consumption/handlers/test_generated_homework_exam_cross_paper_scores_and_saved_snapshots.json)。

## B：同一学生公开练习+quiz→012与010B知识/周序列

同课两点、公开单选v1标签[1,2]、私有quiz客观v1标签[1,2]；另含点2判断题及点1简答。10月11日23:58上海时间，学生公开v1答B错，推荐两点各n1/c0。23:59真实quiz交卷：单选A对、判断漏答、简答待批；推荐两点各n2/c1，知识总体2次/1对。practice.id=1与answer.id=1同时保留，来源命名空间不同，不能按数字ID合并。

10月12日08:05，教师将公开题新增v2（答案B、标签仅[2]），也给quiz单选新增v2；学生用公开v2答B对，另一次空答保留原事实但不入客观样本。旧quiz与旧practice仍以各自v1标签[1,2]计数，不能跟随最新标签漂移。新知识总体3次/2对/66.67%，点1为2/1，点2为3/2；漏答判断、简答及空practice不进入分母。固定区间`2026-10-04T16:00Z`至`2026-10-12T00:05:00.001Z`的两段周序列，在上海周一00:00（UTC10月11日16:00）切分，分别为2次/1对与1次/1对。

推荐相同28天输入：点1n2/m.5/score.600000、练习入口null；点2n3/m2/3/score.466667、入口为公开v2，reason均insufficient_sample。之后真实批quiz简答8分，知识metrics与推荐完整响应不变；这是“简答评分不新增客观样本”的消费核对。原学生知识ID、教师选学生ID及CSV仍是首次2次/1对快照，页面刷新恢复原ID。进度始终0/2，不将知识掌握度当自报完成。

主证据：[handler脱敏请求响应与原事实](evidence/mixed-consumption/handlers/test_mixed_practice_quiz_versions_recommendation_and_weekly_knowledge.json)。[独立复算](evidence/mixed-consumption/reconciliation.json)不调用业务算法：用原表重新连接practice/answer/attempt与固定标签，逐条对照保存输入，核对类别/冻结名单左右连接、等权百分比/分箱、两周及推荐变化；handler和两浏览器共六份场景均通过。

## 真实运行与页面证据

正式tested=`938a45c0b169cf0bbbe335c92ae4ec6841d20929`，[handler报告](evidence/mixed-consumption/handlers/report.json)及[浏览器报告](evidence/mixed-consumption/browsers/report.json)均dirty_paths=[]。handler 2项11.369秒，2通过/0失败/0expectedFailure，见[原日志](evidence/mixed-consumption/handlers/handlers.txt)。Chrome155.0.8059.41及Edge155.0.4283.62各完成两个场景，page_errors=[]。

只有最初admin/teacher SQL bootstrap、随机口令与TEST_NOW是夹具；学生、知识、题目、生成、发布、交卷、批阅及查询均真实API。没有业务表直插、成功mock、故障注入或算法double。本轮业务准备/交卷/批阅明确是handler操作；现成页面通过真实socket完成查看生成草稿/已发布名单、恢复知识/多类别成绩ID、显示、刷新推荐和CSV下载，不冒充全部业务由UI点击。两浏览器handler证据在[Chrome A](evidence/mixed-consumption/browsers/chrome-handlers/test_generated_homework_exam_cross_paper_scores_and_saved_snapshots.json)/[B](evidence/mixed-consumption/browsers/chrome-handlers/test_mixed_practice_quiz_versions_recommendation_and_weekly_knowledge.json)、[Edge A](evidence/mixed-consumption/browsers/msedge-handlers/test_generated_homework_exam_cross_paper_scores_and_saved_snapshots.json)/[B](evidence/mixed-consumption/browsers/msedge-handlers/test_mixed_practice_quiz_versions_recommendation_and_weekly_knowledge.json)，socket见[Chrome](evidence/mixed-consumption/browsers/chrome-socket-requests.json)/[Edge](evidence/mixed-consumption/browsers/msedge-socket-requests.json)。已脱敏口令/CSRF等，保留原响应SHA与CSV；未提交数据库或会话。

18张390px截图逐张目视：数据、分箱、旧ID、两周及推荐入口/无入口均与响应一致；无整页横向溢出。统计明细/周表沿用现成横向滚动表，图未同时展示全部列，完整字段由原data/CSV核对。

| 页面 | Chrome | Edge |
|---|---|---|
| 生成固定草稿 | [图](evidence/mixed-consumption/browsers/chrome-a-fixed-generated-draft.png) | [图](evidence/mixed-consumption/browsers/msedge-a-fixed-generated-draft.png) |
| 作业待批旧快照 | [图](evidence/mixed-consumption/browsers/chrome-a-pending-homework.png) | [图](evidence/mixed-consumption/browsers/msedge-a-pending-homework.png) |
| 新跨卷作业 | [图](evidence/mixed-consumption/browsers/chrome-a-new-cross-homework.png) | [图](evidence/mixed-consumption/browsers/msedge-a-new-cross-homework.png) |
| 新考试 | [图](evidence/mixed-consumption/browsers/chrome-a-new-exam.png) | [图](evidence/mixed-consumption/browsers/msedge-a-new-exam.png) |
| 批阅后旧作业ID | [图](evidence/mixed-consumption/browsers/chrome-a-old-homework.png) | [图](evidence/mixed-consumption/browsers/msedge-a-old-homework.png) |
| 首周知识 | [图](evidence/mixed-consumption/browsers/chrome-b-first-week.png) | [图](evidence/mixed-consumption/browsers/msedge-b-first-week.png) |
| 两周知识 | [图](evidence/mixed-consumption/browsers/chrome-b-two-week-knowledge.png) | [图](evidence/mixed-consumption/browsers/msedge-b-two-week-knowledge.png) |
| 混合来源推荐 | [图](evidence/mixed-consumption/browsers/chrome-b-mixed-recommendation.png) | [图](evidence/mixed-consumption/browsers/msedge-b-mixed-recommendation.png) |
| 原知识ID | [图](evidence/mixed-consumption/browsers/chrome-b-old-knowledge.png) | [图](evidence/mixed-consumption/browsers/msedge-b-old-knowledge.png) |

首轮预检失败保留：[handler日志](evidence/mixed-consumption/preflight/handlers.txt)/[报告](evidence/mixed-consumption/preflight/report.json)误将客观题当作配分余数的首题，修正预期60.01为59.97及分箱；[浏览器报告](evidence/mixed-consumption/preflight/browser-report.json)/[定位说明](evidence/mixed-consumption/preflight/browser-failure.txt)误写页面“生成快照”，现成文案为“组卷快照”，修定位。均未改业务实现；正式轮没有混用预检截图。

```text
.venv/Scripts/python.exe -m scripts.verify_mixed_handlers --output logs/mixed-consumption/final/handlers
.venv/Scripts/python.exe -m scripts.verify_mixed_browsers --output logs/mixed-consumption/final/browsers
.venv/Scripts/python.exe -m scripts.reconcile_mixed_evidence --evidence logs/mixed-consumption/final
```

沿用已有依赖、空闲5000/5173及安装的Chrome/Edge；结束关闭本次服务/浏览器并清理临时库。具体Git/GitHub CLI/Flask/Playwright/Ruff用法先经Context7。未安装或升级依赖。

## 原矩阵与边界

[JSON](evidence/c12a/acceptance-matrix.json)与[Markdown](evidence/c12a/acceptance-matrix.md)仅19行追加本轮实际消费证据，原字段/判定/head/tested/附件保留，其他112行不变；[保全结果](evidence/mixed-consumption/matrix-preservation.json)保存19条原整行与Markdown行。131行仍本地80通过/51阻断、集成59通过/72阻断，不套用未合入#27/#31的判定，不关闭完整模块。旧“未合入/入口缺失”行是历史原文，当前实际合入以上方入口元数据为准，不能拿历史描述否认现有代码。

004/007/017没有新的真实修复合入，因此不补受阻项。继续沿用固定PR原最小复现，不在本轮冒充新复现：石佰合#29的R37-004-01（发布错误码）/02（缺window_state）及004 UI；罗浩铭#31的I03-007-01（演示缺页）/02（未来cursor虚报revision），#32的I01-017-01至04（工作台缺页、窗口、撤权后写入、重做），分别对应008/R37、007/AC-03与R02、017/AC-01/05/07/10与R02/R16及原APIC。原004两项、007一项、017四项expectedFailure不算通过。本分支没有复制其未合入测试，绿色CI不能消除旧缺陷。003图片/005引用契约、009 UTC显示、010C缺页保持原记录。未代修或发送协作消息。

本轮无新增业务修复或页面阻断，两个工作包可执行范围到此收尾。未执行I-01/I-03/R37、两个C12b或PR33整包、算法/并发/幂等专题、018、目标Linux4核8GB/50会话/worker、完整R47、生产恢复/90天保留、部署或课堂验收。回退只撤销本包测试/脚本/证据与19行增量，不改迁移和原事实。最终head CI独立核run、全部jobs和测试原日志后，仅更新本PR与两份本地排除交接，避免自身SHA循环提交；不直推共享、强推、删分支、代合并或归档。
