# SPEC-010B / C06—C07 知识与分类成绩分析实施与验证

> 2026-10-16 C12c材料导航：当前合入、真实评审、两个矩阵版本及交付状态见[个人交付索引](C12C_DELIVERY_HUANG_JUNCHENG.md)和[本轮远程快照](evidence/c12c/entry-state.json)。下文各节保留原日期、SHA及当时事实；旧“未合入/待实现/最新”措辞按其历史范围阅读，不覆盖索引中的当前状态。完整SPEC仍未凭材料整理关闭。

## 2026-10-15 C12a 当前恢复点（优先于下方历史）

七个本人SPEC完整AC/有效追加R/适用NF的131行登记、证据分层、实际PR/merge核验及本人接缝补验见[C12a正式验收审计](C12A_ACCEPTANCE_AUDIT.md)。继续原010B feature，经远端ab91dc1快进消费已合入develop f9c49b1；未复制仍open的011/012。新增真实005标签驱动五题型页面、固定旧版本练习→错题状态→统计/权限/受控恢复的Chrome/Edge各9组干净证据（tested2fa4a2b），复用008专用链与013既有有效证据，不重做C07或专用联测。

实际发现010B时间直接显示UTC，已修为明确Asia/Shanghai；存储/API/CSV与原快照不变，跨日组件/前端70项及实际浏览器通过。006/008共有时间显示与012依据截止显示仍为非阻断缺口，矩阵NF-UI失败保留，按所属feature留C12b。完整SPEC、真实非作者复核、目标Linux4核8GB/50会话、生产恢复/Gitea/课堂仍未关闭。本续包新PR最终head CI及真实评审另核验，不能沿用已合入#10/#12检查。下一恢复以C12a记录和本轮PR为准，不能沿用下方“尚未合入”等历史。

## 2026-10-15 PR #12 当前集成状态

PR #10 已合入 develop，C08 的 PR #11 亦以 `bcda8c468e9054579639f3f66c709a54283494aa` 合入。本续包 [PR #12](https://github.com/Gindama713/nchu-web-learning_platform/pull/12) 追加专用测验与分析快照的 HTTP/UI 联测和浏览器证据。合并最新 develop 后，组长在本机复跑双浏览器时发现重新登录期间课程尚未加载，提前填写快照编号会中止初始化，恢复按钮因无课程一直禁用；统计控件现等课程列表就绪才启用，并补前端回归。受影响后端18项、前端63项、lint/build/文档检查及 Chrome/Edge 专用联测均通过；最终干净提交的浏览器报告与 GitHub CI 以 PR 最终 SHA 核验。下文关于“PR 尚未创建”“网络阻断”“#11 未合入”等是当时的交接记录，不代表当前状态。003/004、目标环境性能、完整生产恢复和课堂验收仍待完成。

## 2026-10-15 PR #9 合入后的联合复核（优先于下方历史记录）

组长实际审查并批准 PR #9；必需 CI 重跑通过后，008 以 `b4a376b860e891a969c9507d69b4cefba5c7f290` 合入 develop。本010B分支吸收该基线，自动合并无文本冲突。新增 `test_dedicated_quiz_statistics_grading_review_and_saved_scores` 经真实教师/学生 API 验证专用发布、客观题与简答交卷、逐题待批统计、010B待批快照、人工批阅、截止后显式讲评、最新成绩，以及旧快照和 CSV 字节不变。首次测试在 `start_at` 精确边界查询，按左闭右开规则未选中该卷；改为截止时刻查询后通过，未改变业务窗口算法。最终合并提交与 CI 以 PR #10 最新 SHA 为准。

下方“008 未合入”“仅共享服务接缝”等文字保留为当时的历史状态。原 Chrome/Edge 报告只覆盖旧 tested_head，不充作本次整合后浏览器证据；003/004接缝、目标环境性能、完整恢复和课堂验收仍待完成。

责任人：黄俊诚（24201716）。2026-10-14，Asia/Shanghai。依据：[PRD有效验收](PRD.md#accept-spec-010b)、[APIC§5.1](APIC.md)、[DBD§5](DBD.md)。C06交付knowledge计算与持久快照API；C07分段追加分类成绩、同快照CSV和页面，当前状态及下一恢复见文末。010B整体验收未关闭，不新增自己的AC编号。下述C06段落保留当时证据，后续实现以文末C07记录为准。

## 基线、边界与依赖

本轮fetch的origin/develop为`253a736a79a6b6778e8bde0e58673d1f4c7641d7`；从此新建`feature/spec-010b-knowledge-analysis`，没有从008 feature复制代码或修改共享分支。已合入001/005/006及014漏答修复；008专用发布/统计/review仍在独立PR #9，未作为本分支依赖带入。复用001的`analysis_run`与analytics路由、原始question_version标签、practice_attempt/attempt/answer及learning_progress，不新增表、不修改旧SQL、锁文件、CI、010A或014算法。

| 依赖 | 当前接入 | 恢复/负责人 |
|---|---|---|
| 001会话、当前课程成员、analysis_run、公共runner | 真实实现已接入；计算前同事务授权、保存前再鉴权，原迁移重放及备份读取有测试 | 姜苏豪提供，黄俊诚消费；不接管010A |
| 005当前发布集合、本人完成事实 | 经真实章节/知识/进度API产生，R38全部数值及日期不改集合可复算 | 本包补005/R38聚合证据，图文/003缺口不因此解除 |
| 006固定题目版本、练习和卷内作答/批阅 | 真实HTTP提交、成功键重试与人工批分；漏答保留但不计掌握度 | 本包只读，不写评分或另建成绩来源 |
| 008专用测验链 | PR #9已由外部合入develop b4a376b，本010B分支已merge接入 | C07续包专用HTTP联测通过，最新浏览器/CI见文末；不以局部联合关闭008全部验收 |
| 页面、scores/CSV | C07a后端分类成绩及knowledge/scores CSV已实施 | C07b页面/浏览器分段验证见文末；不以API通过代替完整验收 |
| 003/004、Linux4核8GB/50会话/真实worker、课堂与正式评审 | 未执行/外部依赖 | 原负责人接缝与目标环境完成后补证，不用本机测试时间冒充性能 |

## 实现和可复算口径

- [knowledge_analysis.py](../backend/models/knowledge_analysis.py)：同一BEGIN读取当前发布集合K、本人K交集进度和本课实际已作答客观样本。练习按created_at、卷内答案按attempt.submitted_at选择左闭右开区间；漏答与简答排除。固定版本标签分别计入各点，总体以`(practice,id)`或`(answer,id)`去重，两表相同数字ID不碰撞。总体保留区间内本课历史作答，items只含当前K并按ID排序，零样本mastery=null。
- Pandas对原始样本drop_duplicates，explode标签后按knowledge分组count/sum，reindex当前K保留零样本；JSON显式禁止NaN。总体样本数是实际客观作答次数，不是人数/标签数；wrong_count=answered_count-correct_count；比率不额外舍入，单位ratio。
- 个人进度始终为K交集中completed=true数/|K|；日期只选作答，不选K或进度。下架同时排除分子分母，重新发布恢复历史完成状态；K空时0/0进度null。上海周一00:00切周，首尾裁剪，series的进度仍用同一当前快照。教师全班保留掌握度汇总，completed_knowledge_count/progress为null并提示选学生，published_knowledge_count仍为|K|；用户本轮采用推荐口径，已同步APIC，未冒充团队批准。
- [knowledge_analytics.py](../backend/apis/knowledge_analytics.py)：只允许knowledge/from/to/student_id；空值、重复字段、不适用筛选、非正/超SQLite范围ID拒绝400。学生只读本人；教师选学生必须是本课当前active学生。个人输入在SQL提取阶段限制该学生，不把其他学生事实存入个人快照。
- 读事务提交后计算，短写事务复核会话、课程权限及目标学生权限，把解析参数/实际knowledge_ids、完整必要输入、metrics/series/口径/警告/算法版本整体保存到analysis_run。插入及补结果ID的UPDATE同事务，失败回滚503且无可用ID；空样本照常保存。没有将旧输入回写作答或进度。
- 公共[analytics.py](../backend/apis/analytics.py)仅分派knowledge、按本人创建的attendance/knowledge快照读取、no-store及暂未就绪CSV的显式503；不改010A计算/导出字段。读取重新检查当前授权、创建者和范围；跨课/他人/撤权/非统计kind/已清理404，停用或失效会话401。旧快照不重读当前事实或因新作答/批分/上下架更新。

实现采用仓库已锁定Pandas，无依赖升级。通过Context7核对官方[分组统计](https://pandas.pydata.org/docs/user_guide/10min.html)、[explode](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.explode.html)及空值求和行为；空样本仍按正式API使用null，不把Pandas空和0当作掌握度。

## 测试及全部有效编号登记

执行人：黄俊诚任务下的Codex自动执行；2026-10-14本机Windows，临时独立SQLite与真实Flask API。初始admin/teacher账号bootstrap；学生注册、登录、课程/成员、知识/进度、题库、练习、发布、交卷、批阅和统计均经真实接口。沿用knowledge_fixture函数名，但该helper调用已合入005 API，没有知识/权限/事实HTTP替身。只有计算失败/计算时序用patch注入；权限变更和并发写仍通过独立线程真实API。WAL仅为并发测试临时库条件，没有改应用运行模式。

[test_knowledge_analytics.py](../tests/test_knowledge_analytics.py)提供以下可复核入口。结果仅指本包对应子集，不代表整个SPEC或课堂验收：

| 有效编号 | 入口与已覆盖输入/预期 | 仍需补证 |
|---|---|---|
| 父SPEC-010/AC-01 | four_answers：4答3对75%，固定旧标签、多标签总体去重、零样本；equal_numeric_ids：两源ID相同仍为2样本；保存输入复算metrics/series；half_open_bounds：四种客观题及事件边界 | C07 scores；008专用联合 |
| 父SPEC-010/AC-02 | student_teacher_scope、class_totals：本人/全班/选学生、他人/外课/管理员/无会话拒绝、个人快照输入隔离；revocation/session_deactivation：计算中撤权404、停用401且零快照 | 页面和真实教学账号 |
| 父SPEC-010/AC-03 | four_answers零样本items和r38空K：mastery/progress=null，空结果仍存可恢复快照 | 页面无数据展示 |
| 父SPEC-010/AC-04 | restore/backup/read_transaction/failed_insert：完整结果持久保存、按原ID恢复、并发事实变更不改旧输入、保存故障不交ID | C07页面/CSV，尚未通过完整AC |
| 父SPEC-010/AC-05 | 待执行 | C07分类scores全部字段/分母/CSV，不能以掌握度代替 |
| R12/R27 | real_paper_answers：漏答与简答不混掌握度；真实partial答卷、原键重放、人工评分更正不重复计样本/不改旧快照；half_open四种客观题 | 分类成绩/完整业务判分回归由原006及C07补 |
| R15/R16/R33 | class_totals：退出成员历史真实客观样本保留；原008逐题统计非本包 | C07成绩冻结应交名单及008统计接入，不将知识样本数当成绩分母 |
| R34（010B部分） | four_answers、equal_numeric_ids：多标签分别统计、总体去重；零样本items仍存在 | 012推荐非本包 |
| R38（010B及005聚合） | r38_current_set：2/3，下架完成点1/2，再发布/下架未完成点2/2，全部下架0/0=null；日期区间不改K/进度；旧ID仍恢复2/3 | 教学/生产验收未执行 |
| R22/R45 | 范围、责任、依赖与恢复点在本记录登记 | 全组工时/风险材料及课堂证据未核验 |
| R46 | APIC/DBD单一定义与公共路由/原始事实归属，未重复建表或修改旧迁移 | C07继续同步接口与页面/CSV |
| R47 | 本地自查不是非作者批准；PR/CI按下节真实状态记录 | 没有本包真实非作者批准记录，不自行合并 |
| NF-SEC | strict_filters、creator/cross_course/kind/deleted、撤权/停用及当前选定学生检查，no-store | 教学账号/完整跨模块验收未执行 |
| NF-DATA | INSERT或结果UPDATE触发器故障整体回滚、计算失败、缺表503且零快照；WAL中提取K/进度后真实第二请求下架/新练习，第一次保留原结果；公共runner重放、备份完整性/外键及恢复库原ID真实HTTP读取 | 完整资源/电路备份集和生产恢复未执行 |
| NF-UI / NF-PERF | 未执行 | 本包不新增页面；C07页面、目标Linux/50会话/worker仍待补 |

复现（根目录）：

```powershell
.venv/Scripts/python.exe -m unittest tests.test_knowledge_analytics -v
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend目录执行 npm test / npm run lint / npm run build
```

首轮10项有1项失败：75%用例在固定测试时钟等于默认to时查询，事件按右开区间正确被排除；测试把查询时钟推进到作答之后（at(13)），未改变生产区间规则。另修正SQLite.Row映射推导式的ruff SIM118告警。13项新增用例随后全通过（27.656秒）；后续补两源ID碰撞用例，完整后端121项通过（180.932秒，含本包14项）。之后在既有权限测试补教师knowledge导出503/学生403断言，受影响单项重跑通过（1.570秒）。前端现有46项、lint/build、全仓ruff、六文档链接及diff检查通过。008尚未合入，121/46与其feature的122/54属于不同分支/用例集合，不能混作退步或相同测试基线。

## 提交、PR、CI与下一恢复

代码/测试/契约提交`3de34d1d62a57282f61adbbf97cdb2abaa10e6f0`已推送origin/feature/spec-010b-knowledge-analysis；[PR #10](https://github.com/Gindama713/nchu-web-learning_platform/pull/10)为open/draft，目标develop `253a736a79a6b6778e8bde0e58673d1f4c7641d7`。未合并/部署/发布，没有本包真实非作者批准证据。

代码[Actions38571993686](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38571993686) completed/success；已核对jobs：ci-policy/ci-lint/ci-test/ci-build/ci-required全success，ci-grader按develop规则skipped，不视为真实评测通过。ci-test实际日志后端121项（69.554秒）、前端46项通过，checkout tested merge=`299d10fbf8a7122eb7bdbf7e5fb3fd3969b1116d`，head=3de34d1、base=253a736。该merge为CI测试引用，不是实际合并。后续证据文档提交需单独核对最新head CI，本代码run不冒充最终文档head的检查。

环境失败记录：GitHub连接器取状态/日志时曾返回临时403，专用工作流查询及后续重试成功；ci-test运行中第一次请求日志404 BlobNotFound，完成后取得日志并核对上述真实测试数/SHA，没有隐藏业务测试失败或用其他分支CI替代。

下一恢复：先fetch并核对origin/develop和008 PR #9。C06独立knowledge计算/快照API已实施，C07继续此010B分支：已共享分支使用merge同步develop；008合入后补专用quiz→knowledge真实链，再做scores分类指标、统计页面、原ID恢复与同快照CSV、公式转义及完整父AC-01—05/各R。008尚未合入时不能从其feature复制代码或误称联合已通过。005 R38本包仅补聚合证据，003图文/011索引/目标环境缺口仍保留。


## C07a：分类成绩与同快照CSV（2026-10-14）

本轮继续原010B分支；先fetch核验develop仍为253a736，008 [PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9)为open/draft、merged=false，head=fafc69a；没有复制其feature。公共analytics只新增scores分派/快照白名单及010B CSV出口；attendance计算及其CSV内容保持原实现。

实现为[score_analysis.py](../backend/models/score_analysis.py)、[score_analytics.py](../backend/apis/score_analytics.py)、[statistics_csv.py](../backend/apis/statistics_csv.py)及[真实API测试](../tests/test_score_analytics.py)。完整字段见APIC§5.1，存储见DBD§5。按任务start_at选卷，冻结名单左连source_until前提交；expected=submitted+missing，submitted=graded+partial。实际已批0分计均值，缺交/partial不计；跨卷只出等权百分比。Pandas均值及NumPy未舍入百分比分箱，100计最后箱。范围仅SQL中提取本人；保存前再次检查会话/当前课程及选定学生。新结果filters随快照保存，原ID不更新；CSV仅遍历result_json，包含总计/周序列/知识明细或全部分箱。公式前缀含空白、换行、逗号与引号用例通过。

验证执行人：Codex（黄俊诚授权开发下的自动验证，非非作者批准）。10项C07测试全部通过，21.661秒；此前knowledge+scores共22项通过46.177秒（当时scores为8项），新增停用及quiz共享服务/成绩备份两项后独立10项重跑。ruff通过。测试输入/预期/实际由测试断言保存：

| 编号 | 用例及结果 | 边界 |
|---|---|---|
| 父AC-01 / R15 | real_frozen_assignments、percentage_edges：3应交/2已交/1缺交/1待批/1已批0分；批阅后新查询均百分比40，旧JSON/CSV相同；7份不同满分的边界分箱为2/1/1/1/2，均百分比65.7 | 001/005/006真实API，非教学数据 |
| 父AC-02 | strict_filters、snapshot_export_permissions、deactivation：混筛选/重复参数400、跨课/他人/清理/非统计kind/撤权404、学生导出403、停用401；停用/撤权计算不保存 | 班级教师关系和会话重新鉴权；目标环境未测 |
| 父AC-03 | empty_quiz：0样本均值null，计数0；真实空白交卷为已批0且计入 | quiz空查询非008专用联合 |
| 父AC-04 | frozen_assignments、knowledge_csv、quiz_shared_service：批分后旧CSV字节一致，备份完整性/外键及同ID JSON/CSV相同 | 页面/双浏览器留C07b；非完整资源/生产恢复 |
| 父AC-05 / R16 | exit_and_join：冻结人卷分母3，退出后仍3；个人输入只含本人 | homework/exam由HTTP发布/提交；quiz_shared_service通过已有共享publish服务准备，仅作为服务接缝测试，008专用HTTP链仍阻断 |
| R12/R27 / NF-DATA | WAL期间真实第二请求批阅：原快照partial，下一查询80%；INSERT/UPDATE故障、缺表/计算失败503无半快照 | 不改判分规则/原迁移 |

失败与修复：首轮8项中3项失败，原因是测试时钟等于右开to及重复保密考试复用同一道题；调整查询时钟/独立题目后22项通过。新增停用测试最初试图停用仍负责课程的教师，被001真实约束拒绝；改为学生停用用例后通过，不修改001规则。没有删除失败测试或降低断言。

下一恢复：C07a后端已准备分段提交推送；继续C07b页面、刷新/重登原ID恢复、导出下载及真实Chrome/Edge验证，再全量回归并更新PR #10。008专用链、R33、目标Linux4核8GB/50会话/worker、完整资源恢复及课堂/实际评审仍未通过；不得关闭010B完整验收。


## C07b：统计页面、恢复与下载（2026-10-14）

[AnalyticsView](../frontend/js/analytics-view.js)接入原登录页面，复用现有课程与会话客户端；[AnalyticsClient](../frontend/js/analytics-client.js)仅生成适用筛选，恢复只传ID，导出只传ID/format并先核验当前身份。教师可选学生、类别及paper；知识明细表、同集合进度、百分比分布和周趋势使用已保存结果。实际筛选、数据截止、生成时间及算法版本随原快照显示。浏览器仅保存本账号/角色的课程与最后快照ID；刷新和重登读取原ID，失败提示显式重新查询，禁止静默重算。修改筛选/身份/卸载会递增请求代次，迟到响应不能恢复旧数据，导出失败也清空结果。旧C06无filters仍显示保存结果，不改写旧JSON。运行与用户步骤见README§8.5。

验证：前端54项通过（本包新增8项：2客户端、6组件），lint/build通过，ruff与六文档本地链接/diff通过；CSV补每周知识明细后受影响后端单项通过1.149秒。浏览器脚本为[scripts/verify_spec010b_analytics.py](../scripts/verify_spec010b_analytics.py)，初轮真实Chrome155.0.8059.40/Edge155.0.4283.45各10组通过，page_errors=[]。初轮报告含未提交改动，不把tested_head=3d1def6冒充完整页面源码；后续干净提交复核证据在文末登记。

浏览器输入/预期/实际：受控账号经001登录，005真实知识API准备标签，006公开练习4次对3次，页面75%；真实homework发布冻结3应交/2提交/1缺交/1partial/1已批0分，旧均百分比0。教师人工批8分后，新跨卷均百分比40、单卷8分/80%；刷新原ID仍显示旧结果、下载字节相同。教师选学生的knowledge CSV以标准引用保留逗号/换行，并在公式前缀加单引号。真实HTTP响应延迟后改筛选，旧响应不显示；不存在ID恢复失败后无报告，显式原ID恢复成功；390px整页无水平溢出（宽表在容器内滚动），重登恢复旧ID；撤销学生成员后，教师选该学生的旧快照读取/导出均404。浏览器每项检查代码与报告checks对应，非教学/课堂数据。

失败与修复：浏览器初轮定位“应交人卷次”同时命中摘要dt与表头，改为dt定位；第二轮共享旧write测试助手把成功DELETE204当JSON解析失败，脚本改为检查204而不解析响应。前端lint曾报URL/setTimeout/structuredClone未声明，使用globalThis显式访问后通过。手机截图发现时间列过窄，扩大首列并给滚动区域键盘焦点；最终截图需在干净代码提交上重新采集。以上未修改业务约束或共享测试助手。

| 完整有效编号 | 当前证据/状态 | 尚需恢复 |
|---|---|---|
| 父SPEC-010/AC-01 | 独立knowledge/scores输入重放、固定算法及全字段可复算；C07续包专用008→010B已通过 | 全系统/教学验收仍待执行 |
| 父AC-02 | 真实会话/跨课/创建者/范围/撤权/停用，API与页面失败清空 | 教学账号/全系统验收待执行 |
| 父AC-03 | 空样本null、实际已批0分与缺交/partial区分，页面与CSV可见 | 目标环境待执行 |
| 父AC-04 | 按原ID刷新/重登/显式恢复；后续批分旧JSON/CSV字节不变；知识及成绩备份副本原ID恢复 | 完整生产资源/电路备份集及目标环境待执行 |
| 父AC-05 / R15 | homework/exam及专用quiz真实HTTP发布/交卷/批阅；字段、分母、均值、分箱和CSV一致 | C07续包补quiz链；resources归003，全系统验收待执行 |
| R12/R27 | 原006五题型/批阅/幂等测试及010B真实partial→graded、旧快照保留；专用quiz亦通过 | 目标环境/教学验收待执行 |
| R16 | 后加入不补历史任务、退出不减冻结应交；均分仅graded | 教学验收待执行 |
| R33 | C07续包真实专用发布/提交/逐题统计/讲评→010B/旧ID/CSV通过 | 浏览器及当前head CI见文末；课堂/全系统验收仍待执行 |
| R34/R38 | C06双源ID/多标签/零样本、同集合进度；C07表格/CSV及原ID恢复有证据 | 012推荐非本包；003图文等缺口保留 |
| R22/R45 | 本记录、PR及个人交接明确范围/责任/阻塞/恢复点 | 全组工时风险及课堂材料待核验 |
| R46 | 单一APIC/DBD，复用analysis_run，无新表/旧SQL/队友算法/CI修改 | 真实非作者契约复核待执行 |
| R47 | PR #10继续draft，不自批、不合并/部署/发布 | 真实评审与当前head CI须分别核验 |
| NF-UI / NF-SEC / NF-DATA | 双浏览器真实链及窄屏；当前授权/创建者/范围；失败原子回滚、WAL并发批阅、备份副本原ID | 目标环境与完整生产恢复未执行 |
| NF-PERF | 待执行 | Linux4核8GB、50会话及真实worker；本地运行时间不作达标证据 |

全量本地回归：`.venv/Scripts/python.exe -m unittest discover -s tests -v`后端131项通过，204.533秒；前端`npm test`54项、lint/build通过。全量回归启动后补了CSV每周知识明细断言，该受影响单项另行通过1.149秒；其余后端逻辑未变。正式运行SHA/CI和干净浏览器证据随后独立登记，不把本机时长当NF-PERF。


## C07历史提交与CI（当前恢复见文末续包）

后端提交`3d1def696c76da24b02278afa65f8ec6af7bd20f`及页面提交`29ade52f8ef27eeb7f287dd7f41ab35aaa83b88e`均已推送origin/feature/spec-010b-knowledge-analysis。[PR #10](https://github.com/Gindama713/nchu-web-learning_platform/pull/10)为open/draft，目标develop `253a736a79a6b6778e8bde0e58673d1f4c7641d7`，reviews=[]；未合并、部署或发布。代码及页面独立部分可恢复，不把CI或AI自查当真实非作者批准。

正式双浏览器证据：[report.json](evidence/spec-010b/browsers/report.json)，tested_head=29ade52完整SHA，dirty_paths=[]。Chrome155.0.8059.40及Edge155.0.4283.45各10组全部通过，page_errors=[]；390px截图为[Chrome知识](evidence/spec-010b/browsers/chrome-knowledge-mobile.png)、[Chrome成绩](evidence/spec-010b/browsers/chrome-scores-mobile.png)、[Edge知识](evidence/spec-010b/browsers/msedge-knowledge-mobile.png)、[Edge成绩](evidence/spec-010b/browsers/msedge-scores-mobile.png)。初轮含工作区改动的报告不是正式源码证据；本目录只保存干净29ade52结果，新增内容均为合成受控数据，无口令/会话/数据库。

C07a [Actions38574944772](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38574944772) completed/success。C07b [Actions38576022315](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38576022315)也completed/success；已核对jobs：policy/lint/test/build/required全success，grader按develop阶段规则skipped，不代表真实worker通过。ci-test日志实际后端131项（109.162秒）及前端54项全通过；checkout tested merge=`040e8e0bfbc1190c298370db3bb7112f68b49e02`，head=29ade52，base=253a736。此merge为CI测试引用，不是实际合并。证据文档提交后的最终head须单独核对CI，不能以本代码run代替。读取运行中日志曾返回404 BlobNotFound，完成后重取成功并核对上述数目/SHA，无隐藏业务失败。

**下一恢复**：C07独立scores、页面、原ID恢复及同快照CSV已实施、验证并推送；不重做。先fetch并核验develop、008 PR #9和本PR最新head/CI。#9本轮结束核验仍open/draft、head=fafc69aecf723d06181e807bc1124aed2bd915de、未合入；不得复制其feature。待008合入develop后，在本010B共享分支merge origin/develop，按真实专用quiz发布→提交（含漏答/partial）→逐题统计/显式讲评→knowledge/scores→旧ID恢复/CSV补R33及联合证据，再更新完整矩阵。处理APIC/DBD/CHG-RB可能冲突时保留双方契约，不覆盖队友变更。

上述为C07当时交接，已由下述续包解除008专用链阻塞。003/004接缝、Linux4核8GB/50会话/真实worker、完整资源/电路生产恢复、教学账号及课堂/真实评审仍保留；父AC-01—05的局部链证据不等于010B全部验收。回退先备份事实和所有analysis_run，再恢复配套代码；旧代码无法处理新快照时明确不可用，不改写/删除历史或重算冒充原结果。

## 2026-10-15 C07续包：专用008→010B联测（当前交接）

初次fetch时#9未合入，因此在独立013分支实施并推送C08候选/算法/快照`16c1928`、`30d2948`并创建draft [PR #11](https://github.com/Gindama713/nchu-web-learning_platform/pull/11)。收口fetch发现#9已由外部于2026-10-14 23:49:35（Asia/Shanghai）实际合入，merge=`b4a376b860e891a969c9507d69b4cefba5c7f290`。按用户优先级返回本010B分支merge origin/develop，产生`39ac02c9d6461c4b768221404afc85464a0601d5`，无冲突。未将013或其他未合入feature带入本分支；原C07业务无需重做，续包仅追加真实联测与证据。

[专用联测](../tests/test_quiz_analytics_integration.py)通过真实001/005/006/008/010B HTTP完成：3人冻结、4题各10分，1人交客观正确/错误/漏答及待批简答，1人白卷、1人缺交。专用逐题客观正确率1/6（漏答计入提交分母）；knowledge实际作答n=2,c=1,mastery=0.5，多标签分项保留旧版本标签且不重复总体。scores应交3/提交2/缺交1/已批1/partial1，均百分比0；简答批8分后变已批2/partial0、均百分比22.5。显式review前仍无答案，之后原卷/错题开放；截止原key重放仍原201字节。旧knowledge/scores结果及CSV在批分、讲评、新版本后保持原值；带数据备份副本经迁移重放/完整性/外键后仍由真实HTTP按原ID恢复与导出。新增单项通过3.804秒，无业务缺陷或判分改动。

测试初轮误从注册响应顶层取id，改为真实登录会话user.id；曾比较含动态request_id的HTTP信封字节，改为契约规定的不变data对象及CSV字节，幂等提交仍严格比较原完整201字节。没有放宽业务规则或忽略失败。

双浏览器续包脚本为[scripts/verify_spec010b_quiz_integration.py](../scripts/verify_spec010b_quiz_integration.py)，只测本次专用quiz联测，不重跑C07独立链充作新增证据。正式干净源码SHA/结果、全量回归与PR最新CI在以下收口项登记。

本地全量后端147项通过（256.870秒；原010B131+新合入00815+本续包1），前端62项、lint/build、全仓ruff（含新浏览器脚本）、六文档链接/diff通过。初轮Chrome155.0.8059.40/Edge155.0.4283.45各6组通过，page_errors=[]，含专用统计16.7%、知识50%、quiz3/2/1/partial与0分、讲评UI、旧ID刷新/重登与CSV、新22.5%、390px截图；初轮工作区有脚本/测试改动，不作最终干净源码证据。浏览器最初遗漏“刷新逐题统计”，及查询后未等待新scores结果导致读到旧knowledge ID，脚本按真实页面等待修复后双浏览器通过，业务未改。正式证据待干净提交复跑登记。

本轮新增代码提交`5f60dda06454b187db04331d5a23ece8c08c540e`首次push因外部更新被拒；fetch确认远端`0d1ad349fe761cdbd99e53e05a89e34bfbf684ab`已追加专用scores联测并由外部以`7759d650e9b0a9b6c2a8070471f1040af603a22f`合入develop（PR #10已merged，2026-10-15 00:10:10 Asia/Shanghai）。随后merge远端原feature产生`6ddd6df`，保留双方测试/文档，README唯一冲突保留新专用联测入口及剩余验收；再merge实际develop产生`36e2f38c9ab9d70eacb6c9f1f71e7780dad33cea`，已成功推送同一feature，没有强推或自动合并。同步后两处专用联测重跑2项通过（6.130秒），运行时代码/页面/新脚本相对5f60dda没有差异。147项全量的256.870秒是同步前证据，不能把合并后额外测试计入该次数。

最终干净合并树的浏览器证据：[report.json](evidence/spec-010b/quiz-browsers/report.json)，tested_head=`d1063a47a11721aa0c25b95de562cffe0a194866`，dirty_paths=[]。Chrome150.0.7871.47及Edge155.0.4283.45各6组全部通过，page_errors=[]；390px截图为[Chrome知识](evidence/spec-010b/quiz-browsers/chrome-quiz-knowledge.png)、[Chrome成绩](evidence/spec-010b/quiz-browsers/chrome-quiz-scores.png)、[Edge知识](evidence/spec-010b/quiz-browsers/msedge-quiz-knowledge.png)、[Edge成绩](evidence/spec-010b/quiz-browsers/msedge-quiz-scores.png)。截图已目视核对，页面无整页水平溢出、宽表在容器内滚动。只保存本轮合成受控结果，无口令/CSRF/会话/学生答卷/数据库。此前`36e2f38`的独立原分支报告已由本次合并树复跑替换，不再作为当前文件的tested_head。

网络短暂transport/TLS失败后已恢复；正式证据提交`1d598b5895a87e98fcdccd31d889cc0a13b0332b`已推送，并核实无同head开放PR后新建draft [PR #12](https://github.com/Gindama713/nchu-web-learning_platform/pull/12)（旧PR #10已合入，不能更新成未合入续包）。本轮不再有网络阻塞。

证据head 1d598b5的[Actions38596864000](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38596864000)实际jobs均已完成，policy/lint/test/build/required全success，grader按develop规则skipped。已读取ci-test日志：后端148项（123.412秒）、前端62项；tested merge=`d96af20847cb2c5996201617307be8fb32e11d0a`，base=7759d65、head=1d598b5。此merge是CI测试引用，不是实际合并，148包含保留的双方专用联测；reviews=[]，不把自动验证记成真实非作者批准。本文后续纯文档提交的当前head CI须另核验，以PR当前检查及个人交接为准。

2026-10-15恢复收口时再次fetch：013 PR #11已由外部合入develop，实际merge=`bcda8c468e9054579639f3f66c709a54283494aa`，head=d7a0e78（外部另补真实专用quiz历史1/1回归及文档，保留本C08）。PR #12仍open/draft，本续包按共享分支流程merge最新develop，CHG-RB一处冲突保留013与010B两份记录，无运行时代码冲突。本次合并后的回归/最终head CI以PR #12当前结果及个人交接为准，不把上述148项直接升级成合并后次数。

同步提交`f1b7192bb6dee4ba7002c728278b90974f5417a5`已推送，[Actions38675507503](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38675507503)的policy/lint/test/build/required全部success，grader按develop规则skipped。实际ci-test日志后端167项（131.268秒）/前端62项，tested merge=`96437ff0309b49f90be0ffa26f806a1312e0cf05`，base=bcda8c4/head=f1b7192；仅CI测试引用，不是PR #12实际合并。本地合并后完整`unittest discover -s tests -v`亦167项通过（244.462秒）。新增19项C08测试包含外部quiz历史用例，与双方010B专用联测均保留。前端相对已测基线无变更；ruff、六文档链接及diff检查通过。最终纯文档提交的head检查仍另核验，个人交接第10.1与计划第6节记录最终状态。

下一恢复：专用008联测、原ID/CSV和干净双浏览器已补证，无需重复C07业务。先fetch核验PR #12当前head CI/实际评审，再按授权收口。完整010B仍有003/004、Linux4核8GB/50会话/真实worker、完整生产恢复/课堂缺口。C08已由外部合入，后续C09回013原feature，先同步最新develop，不能复制本010B未合入续包。C08/C07均不重做，不自动合并、部署或发布。
