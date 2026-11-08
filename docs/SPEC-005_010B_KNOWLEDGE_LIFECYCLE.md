# 005变更后010B当前集合与历史快照的有限消费核对

黄俊诚（24201716），2026-10-18 Asia/Shanghai。本轮先审计原131行矩阵、既有测试/固定证据及PR，最终只选择一个尚未明确覆盖的C工作包；A/011和B/012复用固定覆盖。新增一个真实API用例、运行/独立复算脚本、页面证据及8行矩阵增量。没有修改业务源码、算法、接口/数据契约、迁移、CI或队友实现，不提升完整模块/跨链结论。

## 入口、actual merge与固定CI

初始工作区干净，位于PR34固定head `73358de0df2a20415875bbe160b4dd57c6f64157`。首批仅本地计划§6/7、交接§3/10.1和PR34固定head的消费报告；第三份未合入，不复制到本分支。fetch后 `origin/develop=dfb23271b470a93d557a2695fed0e04caf59d0d2`，从该已核验基线建立本人 `feature/spec-005-consumer-lifecycle`。

[实际入口快照](evidence/knowledge-lifecycle/entry-state.json)保存#27—#34精确head及真实comments/reviews/review_threads。八PR均原head/open/非draft/merged=false，反馈均[]；沿用固定CI38896062651、38904433916、38907219999、38909993594、38994482166、38996421357、38998602097、39090096665，未重跑或改写旧PR。PR34最后一run已由上轮独立核验后端314/前端119，本轮只复用该固定结论。PR API的merge_commit_sha在merged=false时只是临时测试引用，actual merge仍为null。

005/011/012/010B/006的#4/#14/#15/#16/#17均实际merged；分别核对实际merge `17fd54e6dd428c1446127a4338ddf6b51a85e656`、`336806072638a4ab0a973b3e7b01b517f73aa9d6`、`0a2b84c7ecf05df9f29c4142cd36c28266b3eb4d`、`aa373606f47d4e5c4533e6d48d263c7781bddf26`、`32ec16bf3a281d6f4d9be8f1c19410239d73145c`属于origin/develop祖先，exit均0后消费。不将actual merge当成真实非作者批准。

## 剩余缺口审计与选择

原矩阵和[C12a历史审计](C12A_ACCEPTANCE_AUDIT.md)中的“011未注册/尚未合入”“等待C06/C10”等是历史描述；当前已合入事实以上方祖先核验为准。保持历史原文与原行判定，不能按旧文字重复造缺口，也不能把局部证据提升为完整SPEC。

原矩阵剩余登记逐SPEC核对如下，均为历史登记统计，不等于本轮重判全部模块。005本地8/集成8行阻断，006为9/10，008为10/11，010B为6/6，011为6/15，012为6/16，013为6/6，共51/72。七SPEC均各有R22/R45/R47及NF-PERF/DATA/ISOLATION六行共通缺口，须全组材料、真实复核、目标环境或生产/课堂证据，不能靠新增消费用例关闭。额外业务登记为005/R20与NF-UI、006/R01/R02/R44、008/R01/R02/R37/R44；其中“011未合入”等按实际祖先事实识别为历史，003图片引用契约与004/007/017旧缺陷按下方实名条目继续保留。011/012已存在的固定覆盖和#27/#30/#31/#32的未合入补证分开登记，不复制其矩阵判定；本轮不重跑其整包，也不将旧历史文字自动清空。

| 候选 | 已有固定覆盖及性质 | 本轮决定 |
|---|---|---|
| A：011语料revision、片段、出处 | [011实施](SPEC-011_IMPLEMENTATION.md)、`tests/test_qa.py`的`test_real_update_unpublish_empty_revision_zero_and_draft_isolation`及记录/缓存/失败用例，真实标题+正文修改、下架、隐藏期间改文、重新发布；[干净浏览器报告](evidence/spec-011/browsers/report.json) tested36854081b1ba991a89bacbf7d797ab0620619ae3，两浏览器各9组。阈值/重建故障夹具与成功真实请求分开；原片段/来源和revision已有证据 | 复用，不重跑C10算法/故障整包；不新增011矩阵覆盖 |
| B：012候选、基础/完成状态、入口 | [012实施](SPEC-012_IMPLEMENTATION.md)、`test_recommendations.py`的real_cold_foundations_progress_unpublish_empty、latest_eligible及重新核验用例；[浏览器报告](evidence/spec-012/browsers/browser-results.json) testede8da2410c87c1cf2173fad36aaf92fcacdf46e38，两浏览器各7组，真实基础标记/完成/上下架、来源、最新合格版本入口及实际练习；练习资格/固定标签亦已有C11证据 | 复用，不重做公式、边界或PR33整包；不新增012矩阵覆盖 |
| C：010B当前集合、历史标签、进度、旧ID/CSV | [010B实施](SPEC-010B_IMPLEMENTATION.md)、`test_knowledge_analytics.py`已有R38无样本上下架、4答3对固定标签及旧ID；C07已有CSV、刷新恢复及原快照；PR34固定head已有题目版本变化/混合来源/两周，未合入材料不搬入 | 仅补已有非零客观样本经过005改名/改文、全部下架/隐藏改文/逐步恢复后的当前投影和原快照/CSV连续核对；不重跑PR34 |

依据为PRD§11.5的005/010B有效编号及R34/R38、APIC§3.1/5.1、DBD知识/完成事实和不可变analysis_run。不存在005知识正文历史版本契约；旧快照保留的是查询当时输入/标题，未新增版本机制、跳转或事实关联。

## C：原事实、当前投影与旧快照

[新增用例](../tests/test_knowledge_lifecycle.py)通过真实001注册/登录/课程/成员、005知识/进度、006版本/练习及010B查询/导出接口运行。初始admin/teacher SQL bootstrap、随机口令与TEST_NOW为受控夹具；成功业务无mock、无直接灌业务表、无故障注入。不把handler准备/修改/作答说成UI点击。

同课两点K1/K2，K1完成。公开单选v1标签[1,2]、答案A，学生答B错；追加v2标签[2]、答案B，再答B对。原practice两行、两版本/标签、learning_progress含completed_at保持；总体始终2答1对50%，K1为1答0对，K2为2答1对，不把多标签之和当总体分母。

| 005阶段 | 当前明细K | 完成/发布及进度 | 历史总体 |
|---|---|---|---|
| 原始；随后K1改标题/正文/基础标记 | [1,2]，新查询标题随当前005改变 | 1/2=.5 | 2答1对=.5 |
| 下架已完成K1 | [2] | 0/1=0 | 2答1对=.5 |
| 全部下架；隐藏期间再次改K1标题/正文 | [] | 0/0=null | 2答1对=.5，items为空 |
| 仅恢复K1 | [1]，显示恢复名 | 1/1=1，保留原完成时间 | 2答1对=.5，当前K1仍1答0对 |
| 恢复K2 | [1,2] | 1/2=.5 | 2答1对=.5 |

再以排除两次作答的日期区间查询，样本0，当前K仍[1,2]且进度1/2；不按from/to过滤知识集合/完成事实。学生本人和教师选学生逐阶段核对一致。

每阶段恢复原学生/教师analysis_run_id、比较完整响应、原analysis_run整行（含input_snapshot_json/result_json等）和原CSV字节；原名及旧固定标签[1,2]/[2]保留。新增查询使用新ID，不替换原ID。原事实、版本、当前集合、进度、所有快照、审计和FK检查分别保存在[handler证据](evidence/knowledge-lifecycle/handlers/lifecycle.json)。[独立复算](evidence/knowledge-lifecycle/reconciliation.json)仅从原表重新连接practice→固定版本标签、投影当前published集合及进度，不调用业务算法；handler/Chrome/Edge三份场景的8阶段均通过。

## 正式执行与双浏览器

handler：[报告](evidence/knowledge-lifecycle/handlers/report.json)/[原日志](evidence/knowledge-lifecycle/handlers/tests.txt)，干净tested `6c08ae069a976d4bbe507eb2feec975f869183a7`，1项3.689秒、0失败/0错误/0expectedFailure。之后仅调整浏览器验证脚本，未改变该测试或业务源码。

浏览器：[报告](evidence/knowledge-lifecycle/browsers/report.json)，干净tested `6894204a285c33f65582df314cb3c1c83cd35ba0`，Chrome155.0.8059.41与Edge155.0.4283.62各10项检查，page_errors=[]。两套场景业务仍由真实handler准备；现成统计页面通过真实socket恢复当前/原ID、显示、下载CSV、刷新恢复。每个当前教师CSV与对应真实API字节相等，最终原教师CSV等于初始字节；学生原ID刷新后仍保留原名。请求响应见[Chrome原事实](evidence/knowledge-lifecycle/browsers/chrome/lifecycle.json)/[socket](evidence/knowledge-lifecycle/browsers/chrome/socket.json)、[Edge原事实](evidence/knowledge-lifecycle/browsers/msedge/lifecycle.json)/[socket](evidence/knowledge-lifecycle/browsers/msedge/socket.json)。正式socket仅初始未登录session为401，其余记录200，无DB_BUSY。

10张390px截图均逐张目视：标题、样本2/正确1/50%、空K仍保留历史总体且进度“无数据”、恢复后完成状态、原ID与原名正确，无整页横向溢出；明细和周表沿用现成横向滚动，截图只显示当前可见列，完整字段以响应/CSV核对。恢复快照后的筛选输入框不声称等于保存筛选，页面下方“原筛选/学生#3”与原data才是本次显示依据。

| 页面阶段 | Chrome | Edge |
|---|---|---|
| 原始 | [图](evidence/knowledge-lifecycle/browsers/chrome/original.png) | [图](evidence/knowledge-lifecycle/browsers/msedge/original.png) |
| 改名/改文 | [图](evidence/knowledge-lifecycle/browsers/chrome/renamed.png) | [图](evidence/knowledge-lifecycle/browsers/msedge/renamed.png) |
| 全部下架 | [图](evidence/knowledge-lifecycle/browsers/chrome/all-hidden.png) | [图](evidence/knowledge-lifecycle/browsers/msedge/all-hidden.png) |
| 恢复两点 | [图](evidence/knowledge-lifecycle/browsers/chrome/both-restored.png) | [图](evidence/knowledge-lifecycle/browsers/msedge/both-restored.png) |
| 刷新恢复原ID | [图](evidence/knowledge-lifecycle/browsers/chrome/old-after-refresh.png) | [图](evidence/knowledge-lifecycle/browsers/msedge/old-after-refresh.png) |

预检失败如实保留：[历史时钟失败](evidence/knowledge-lifecycle/preflight/historical-clock-report.json)使用10月13日TEST_NOW而浏览器按实际日期处理Cookie；浏览器改用当前UTC受控时钟并重新真实登录。首轮Ruff导入排序已修正。新增多线程本地WSGI夹具后，[首次干净轮失败](evidence/knowledge-lifecycle/preflight/first-clean-threaded-report.json)、[刷新等待失败](evidence/knowledge-lifecycle/preflight/threaded-refresh-report.json)、[延长等待仍失败](evidence/knowledge-lifecycle/preflight/threaded-ready-report.json)；[真实socket](evidence/knowledge-lifecycle/preflight/threaded-socket.json)证实页面并发初始化期间503 DB_BUSY，并非仅等待时长。运行器改为仓库既有浏览器脚本的单线程本地服务器，保留脱敏诊断，正式轮通过。此处是本机测试环境条件，不作为并发/性能通过证据，不修改共享DB/鉴权或替换响应。

复现仅本包：

```text
.venv/Scripts/python.exe -m scripts.verify_knowledge_lifecycle --output logs/knowledge-lifecycle/handlers
.venv/Scripts/python.exe -m scripts.verify_knowledge_lifecycle --browsers --output logs/knowledge-lifecycle/browsers
.venv/Scripts/python.exe -m scripts.reconcile_knowledge_lifecycle logs/knowledge-lifecycle/handlers/lifecycle.json logs/knowledge-lifecycle/browsers/chrome/lifecycle.json logs/knowledge-lifecycle/browsers/msedge/lifecycle.json --output logs/knowledge-lifecycle/reconciliation.json
```

脚本使用既有依赖、空闲5000/5173及已安装Chrome/Edge；不安装/升级依赖。结束已关闭本次浏览器/服务器并清理临时库。没有提交数据库、Cookie或口令，保留合成业务请求/响应、原SHA和CSV。

## 原矩阵、旧阻断及收尾边界

[JSON](evidence/c12a/acceptance-matrix.json)/[Markdown](evidence/c12a/acceptance-matrix.md)仅8行追加`005消费增量`与报告索引，具体为005 AC-03/04/R38、010父AC-01/04（010B）、010B R34/R38/NF-UI；只覆盖本报告明确的010B消费部分。原行所有字段/判定/head/tested/附件及历史原文保留，其他123行不变，见[原整行与Markdown保全](evidence/knowledge-lifecycle/matrix-preservation.json)。131行仍本地80通过51阻断、集成59通过72阻断；未套用未合入#27/#31判定，未提升完整模块。

004/007/017没有新的actual merge修复；不重跑旧受阻项、不复制未合入测试，expectedFailure不是通过。继续登记原实名负责人及最小复现（固定PR原证据复用，本轮未声称新复现）：

- 石佰合，[#29](https://github.com/Gindama713/nchu-web-learning_platform/pull/29)：R37-004-01，引用未发布quiz后发布备课，预期409 QUIZ_NOT_PUBLISHED，实际404 NOT_FOUND；R37-004-02，学生读取备课quizzes元数据缺window_state（008接口正常）；备课UI亦缺。对应004/R37及原APIC，两项expectedFailure保留。
- 罗浩铭，[#31](https://github.com/Gindama713/nchu-web-learning_platform/pull/31)：I03-007-01，教师/学生main无demo组件，无法执行007页→知识/quiz（007/R02、AC-01/03）；I03-007-02，CPU step令DB revision=1后GET after_revision=99返回revision99（007/AC-03及APIC§4），一项expectedFailure保留。
- 罗浩铭，[#32](https://github.com/Gindama713/nchu-web-learning_platform/pull/32)：I01-017-01缺工作台/009事件接收者（R02）；02开始前可新建201、截止仍提交200（AC-05/R16）；03撤成员后GET404但旧PUT/validate/submit仍200写库（AC-07）；04提交后新建仍返回原submitted attempt不能重做（AC-10）。原四项expectedFailure保留。I01-010C-01缺统计页、石佰合I01-009-01历史时间UTC及003图片/005引用契约继续原记录，未代修或发消息。

本轮只有一个C有限包，无业务消费缺陷修复；两个脚本环境/诊断修正已分段提交。A/B复用；未重跑I-01/I-03/R37、两个C12b、PR33/34整包或算法/竞态/幂等专题；未展开018、生产、Linux4核8GB/50会话/worker、恢复/90天、R47完整真实复核或课堂。完整跨链/模块仍未关闭。

最终证据head推送并建新PR后，独立核验精确run、全部jobs及测试原日志；结果仅更新新PR和两份本地排除交接，不再为写自身SHA循环提交。不直推共享、强推、删分支、代合并、部署、归档或发送协作消息。回退仅撤销本包测试/脚本/证据和8行新增字段，不改旧事实、迁移或历史判定。
