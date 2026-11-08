# 012推荐练习与013生成测验的有限消费接缝

黄俊诚（24201716），2026-10-17，Asia/Shanghai。本包完成用户指定两个相邻工作包的可执行范围；没有发现需要修复本人业务消费代码的缺陷。只新增两项真实联测、执行/复算脚本、证据及原矩阵增量；没有改业务源码、算法、迁移、API/DBD、CI或队友模块。完整012/013、I-01/I-03/R01、课堂及真实非作者验收仍未关闭。

## 基线、实际合入与复用边界

初始工作区干净，位于PR32固定head `066ff930730606a519d2c094caf7f25443eb9fca`。按用户首批顺序读取两份本地排除文件及该head的005接缝报告，没有将PR32材料复制进本分支。fetch后 `origin/develop=dfb23271b470a93d557a2695fed0e04caf59d0d2`；从此建立 `feature/spec-012-013-consumption-seams`。#27—#32的head、open/非draft/未合入状态均未变，真实comments/reviews/review_threads全部[]，复用固定CI38896062651/38904433916/38907219999/38909993594/38994482166/38996421357。其merge_commit_sha为临时测试引用，均无actual merge。

#9/#12/#13/#15/#16/#17已经实际合入，逐个actual merge经 `merge-base --is-ancestor <sha> origin/develop` 确认exit0，才消费其008/010B/013/012/006实现；详见[入口元数据与祖先结果](evidence/consumption-seams/entry-state.json)。没有复制未合入实现/材料、改写旧PR，或把合入说成真实批准。

依据：[PRD§4.2/4.3及012/013有效验收](PRD.md#accept-spec-012)、[010B有效验收](PRD.md#accept-spec-010b)、APIC§4.3/4.4/5.1/5.2/5.3、DBD§4/5。有效编号沿用原矩阵；下述A/B是工作包名，不另造验收编号。本人负责005/006/008/010B/012/013，实名来源PRD§10.1。

先核对原矩阵和已有证据后，仅补“同一批对象跨消费者的对照”，以下均复用固定证据，不冒充新增：

- 012公式/所有reason、n=5/m=.8过滤、28天半开边界、保密入口及故障/竞态：原[012实施记录](SPEC-012_IMPLEMENTATION.md)、[C11专题原日志](evidence/spec-012/c11-topic-tests.txt)和 `tests/test_recommendations.py`。原C11浏览器tested=e8da2410c87c1cf2173fad36aaf92fcacdf46e38；C12b时间tested=03a03c7611bd2d00e07a33d8f8bd5842bc36f9c9。#27固定7096b496的develop时间补验保持独立，不复制其三行改判。
- 013候选/历史/求解、去重、穷举、搜索预算、配分及成功重放：原[013实施记录](SPEC-013_IMPLEMENTATION.md)、C08/C09证据及 `tests/test_generation_*.py` / `tests/test_generated_papers.py`。同步C09浏览器tested=d14054d，成功重放及既有008发布页面已覆盖，本包不重跑C08/C09整包。
- 008独立专用发布、人工评分、010B旧ID/CSV：原[010B记录](SPEC-010B_IMPLEMENTATION.md)及 `tests/test_quiz_analytics_integration.py`。PR31固定40bba87e的008→错题→010B→011有限子链只作既有边界参考，不复制其13行矩阵增量或测试/截图。

新增A把012实际练习入口、原版错题/新版入口及010B保存输入串在同一组practice原记录上；新增B把013生成来源、原008发布/作答及010B成绩快照串在同一张paper上。不存在“推荐自动创建错题关联”“生成快照就是成绩快照”或未定义跨模块跳转。统计页面按现有入口进入并查询/恢复，未新增一键跳转。

## A：012→006公开练习→错题及010B真实变化

005经API建立同课两点发布知识并标记基础；006公开客观题v1同时标记点1/2、答案A。真实推荐冷启动返回该固定version_id，浏览器点击现成“去练习”打开原006练习组件。先答B，真实错题wrong_count=1、resolved=false、来源为原practice ID/v1；handler还以原键重试原请求，响应字节相同，原事实/错题没有增加。

第一次010B统计保存一条实际客观样本、0正确；原输入以 `(practice,id)` 标识，两点各1次0正确，总体仍1次。教师CSV与个人旧ID分别保留。教师随后真实追加v2，答案改B、标签仅点2；新推荐点1的练习入口为null，点2选择v2。原错题仍供应v1，不跟着新版答案/标签漂移。

学生从原错题v1答A，再从最新推荐入口v2答B；005点1自报完成。新统计总体3次/2正确/掌握度66.67%，点1为2次/1正确，点2为3次/2正确；完成进度1/2=50%，不新增客观样本。原错题resolved=true、wrong_count仍1、last_attempt_id仍原错误来源；“已掌握”的错题状态不等同010B充分掌握阈值。

新推荐点2先于点1：点2样本3/mastery=2/3/score=.466667，点1样本2/mastery=.5/score=.4，两者reason均insufficient_sample。页面分别显示66.67%/50.00%及六位排序分数；点1明确提示没有合格公开练习。新推荐、010B当前输入及固定版本原表逐项一致，没有把两个标签样本相加当总作答数。

新事实/版本/进度发生后，原零样本/一错样本的个人ID仍返回原data，教师旧ID及CSV字节不变。handler进一步真实撤销学生成员：推荐404、个人旧ID404、错题列表空；历史practice/错题仍保存，教师原班级CSV不变。这是本包有限撤权消费核对，不重跑完整权限/并发专题。

主证据：[handler请求、阶段原事实及审计](evidence/consumption-seams/handlers/test_recommendation_practice_wrong_facts_and_saved_knowledge.json)。浏览器A另有独立socket/UI事实，见下方附件；本地handler与socket证据没有混称。

## B：013→008发布与作答→010B分类成绩及旧快照

教师经API创建三道私有题：单选easy/双标签、判断medium/点2、简答hard/点1。真实013生成quiz草稿，seed=42、三题、总分10.01，固定顺序配分为334/334/333百分之一分。handler约束显式要求点1/2覆盖；浏览器用现成表单设置难度各1，未勾选额外知识约束，实际结果同样覆盖两点；两种输入不混称相同约束快照。

生成只建draft，不自动发布。浏览器点击“查看草稿与发布设置”，再走现成008专用发布；start/end为2026-10-13T12:00Z/12:10Z，review_at=null，冻结3名经真实API注册/入课的学生。受控TEST_NOW位于窗口内；S1原单选A正确、判断False错误、简答待批，S2空白提交为已批0分，S3缺交。handler及浏览器各自的名单、题目版本和生成来源ID均保存。

截止后008逐题统计应交3/提交2/缺交1，客观正确率1/4=.25（两个提交×两道客观题，含漏答）；010B `kind=quiz` 则expected=3/submitted=2/missing=1/graded=1/partial=1，sample_size=1、均百分比0。homework/exam各0任务，没有把练习或生成草稿计作成绩任务。

教师按原简答配分批至满分并真实发布讲评；之后再新增原客观题v2（答案B/标签点2），handler另新增候选题。新010B quiz结果graded=2/partial=0，均百分比33.32%；原卷仍按固定单选v1答案A读取。010B原成绩ID、原data/CSV在批阅、讲评、新版本及浏览器刷新后逐项/字节不变。handler还核对原提交成功键重放仍为原partial成功字节，不拿重放结果当最新评分。

generation_snapshot原整行、输入哈希、有序版本和paper_item配分同样不变；这是独立的选题输入快照，不能和analysis_run成绩快照混用。原保密卷实际开放产生永久公开历史，此时严格重放必须409 QUESTION_PUBLIC；真实接口和页面均拒绝、清除旧生成结果，没有新增快照/草稿或替换题目。本包没有声称“已开放保密卷成功重放”；成功重放沿用原C09固定证据。handler真实撤销S1成员后旧卷404，教师新查询分母仍3，旧CSV仍不变。

主证据：[handler请求、名单/原题/原提交/两类快照与审计](evidence/consumption-seams/handlers/test_generated_quiz_attempts_classified_scores_and_two_immutable_snapshots.json)。[独立原事实复算](evidence/consumption-seams/reconciliation.json)不调用业务计算函数，核对practice来源与固定标签、去重/正确数、冻结名单左右连接状态、成绩均百分比/分箱及334/334/333配分/版本。

## 正式运行、截图与失败留痕

干净tested=`c5852ed6266184dd7e9682eb9683981b2a662f45`；[handler报告](evidence/consumption-seams/handlers/report.json)与[浏览器报告](evidence/consumption-seams/browsers/report.json)的dirty_paths均[]，附件随后提交，不声称在附件自身SHA运行。handler两项5.337秒、2通过/0失败/0expectedFailure，[原日志](evidence/consumption-seams/handlers/handlers.txt)。Chrome155.0.8059.41、Edge155.0.4283.45各完成A/B两组消费，page_errors=[]；这不是完整模块或所有UI状态通过。

所有成功业务对象均经真实API建立；只SQL bootstrap最初admin/teacher、随机口令与TEST_NOW是夹具。没有业务表直插、成功mock、引擎double或故障注入。两浏览器分别保存[Chrome handler](evidence/consumption-seams/browsers/chrome-handler-requests.json)/[socket](evidence/consumption-seams/browsers/chrome-socket-requests.json)/[原事实](evidence/consumption-seams/browsers/chrome-facts.json)，以及[Edge handler](evidence/consumption-seams/browsers/msedge-handler-requests.json)/[socket](evidence/consumption-seams/browsers/msedge-socket-requests.json)/[原事实](evidence/consumption-seams/browsers/msedge-facts.json)。请求响应已脱敏，保存原响应SHA、CSV文本及原始表/审计；未提交口令、CSRF、数据库或上传目录。浏览器S2空白提交及部分版本/进度变化为明确handler操作，不冒充全部由页面点击产生；S1练习/整卷、组卷、发布、讲评、查询/恢复/下载为真实socket/UI。

18张390px截图逐张目视：错题原版/已掌握、推荐理由和版本提示、新知识统计、原班级知识快照、组卷草稿、待批/新成绩/旧成绩及保密重放拒绝均与实际响应一致；无整页横向溢出。统计明细使用现成可横向滚动表格，截图没有同时展示所有列，完整数值另由原data/CSV与原事实核验。

| 检查 | Chrome | Edge |
|---|---|---|
| 原版错题已掌握 | [图](evidence/consumption-seams/browsers/chrome-a-fixed-wrong.png) | [图](evidence/consumption-seams/browsers/msedge-a-fixed-wrong.png) |
| 新知识统计 | [图](evidence/consumption-seams/browsers/chrome-a-new-knowledge.png) | [图](evidence/consumption-seams/browsers/msedge-a-new-knowledge.png) |
| 新推荐/无点1练习 | [图](evidence/consumption-seams/browsers/chrome-a-new-recommendation.png) | [图](evidence/consumption-seams/browsers/msedge-a-new-recommendation.png) |
| 原知识ID刷新恢复 | [图](evidence/consumption-seams/browsers/chrome-a-old-snapshot.png) | [图](evidence/consumption-seams/browsers/msedge-a-old-snapshot.png) |
| 生成草稿/精确配分 | [图](evidence/consumption-seams/browsers/chrome-b-generated-draft.png) | [图](evidence/consumption-seams/browsers/msedge-b-generated-draft.png) |
| 待批成绩原快照 | [图](evidence/consumption-seams/browsers/chrome-b-pending-scores.png) | [图](evidence/consumption-seams/browsers/msedge-b-pending-scores.png) |
| 批阅后新成绩 | [图](evidence/consumption-seams/browsers/chrome-b-new-scores.png) | [图](evidence/consumption-seams/browsers/msedge-b-new-scores.png) |
| 原成绩刷新恢复 | [图](evidence/consumption-seams/browsers/chrome-b-old-scores.png) | [图](evidence/consumption-seams/browsers/msedge-b-old-scores.png) |
| 当前保密资格拒绝 | [图](evidence/consumption-seams/browsers/chrome-b-replay-current-eligibility.png) | [图](evidence/consumption-seams/browsers/msedge-b-replay-current-eligibility.png) |

预检失败保留：[初次handler原日志](evidence/consumption-seams/preflight/initial-handler-failure.txt)/[报告](evidence/consumption-seams/preflight/initial-handler-report.json)误期望已开放保密题可成功重放，实际409符合现行契约，修正测试断言而非业务。初次[浏览器报告](evidence/consumption-seams/preflight/initial-browser-report.json)在已认证学生context的新页再次填写登录字段超时；改为恢复原会话，并按现成“提交整份答卷”按钮定位。另有新脚本宽异常诊断lint提示，已添加仅保存脱敏失败位置的说明。正式轮未混用预检截图。

```text
.venv/Scripts/python.exe -m scripts.verify_consumption_handlers --output logs/consumption/handlers
.venv/Scripts/python.exe -m scripts.verify_consumption_browsers --output logs/consumption/browsers
.venv/Scripts/python.exe -m scripts.reconcile_consumption_evidence --evidence docs/evidence/consumption-seams
```

需要既有依赖、Chrome/Edge及空闲5000/5173；执行结束关闭本次服务/浏览器并清理临时库。Context7已先解析/查询Git、GitHub CLI、Flask、Playwright及Ruff用法；本机无gh，GitHub实读和建更PR使用连接工具。没有安装/升级依赖。

## 原矩阵与继续保留事项

只在[原JSON矩阵](evidence/c12a/acceptance-matrix.json)和[原Markdown矩阵](evidence/c12a/acceptance-matrix.md)追加实际受测17行，逐行保存原整行及Markdown行、原head/tested/附件和判定；其他114行完全保留。[保全结果](evidence/consumption-seams/matrix-preservation.json)。131行仍本地80通过/51阻断、集成59通过/72阻断，没有套用未合入#27/#31的62/69或提升完整模块判定。旧“待合入”描述保留为历史原行；本包当前actual merge事实以上方入口为准，局部证据不关闭完整跨链。

004/007/017无新实际修复合入，以下仅沿用固定PR问题，不代修、不发协作消息，也未重跑其失败或整包：石佰合的R37-004-01错误码、R37-004-02缺window_state及004备课页面（#29，008/R37及APIC§3）；罗浩铭的I03-007-01演示缺页、I03-007-02未来cursor虚报revision（#31，007/AC-03/R02、APIC§4）；I01-017-01工作台缺页、I01-017-02窗口、I01-017-03撤权后写入、I01-017-04重做（#32，017/AC-01/05/07/10、R02/R16、APIC§9）。最小复现/原请求在原固定PR报告，本包没有新同类复现。PR29两项004、PR31一项007、PR32四项017 expectedFailure都不是通过；本分支没有复制那些未合入测试，不能用本PR CI消除旧缺陷。PR32的003图片分类/005引用契约、009时间显示和010C缺页亦继续保留。

本轮受测页面均已存在，没有新增页面阻断或本人业务修复。未执行：两个C12b整包、I-01/I-03/R37整包、018、完整模块算法/并发/幂等专题、目标4核8GB/50会话、完整R47、生产部署/同点恢复/90天保留及真实课堂验收。只在负责人真实修复且actual merge属于develop祖先后补受影响项。

回退只撤销本包联测/脚本/证据及17行增量，无迁移或原事实改写。不直推共享、强推、删分支、代合并、部署、归档或协作消息。最终head的CI独立读取run、全部jobs及测试原日志后，仅更新本PR和两份本地排除交接，不循环提交自身SHA。
