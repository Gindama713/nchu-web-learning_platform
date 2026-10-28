# SPEC-008 / C05a—C05b 随堂测、逐题统计与显式讲评

> 2026-10-16 C12c材料导航：当前合入、真实评审、两个矩阵版本及交付状态见[个人交付索引](C12C_DELIVERY_HUANG_JUNCHENG.md)和[本轮远程快照](evidence/c12c/entry-state.json)。下文各节保留原日期、SHA及当时事实；旧“未合入/待实现/最新”措辞按其历史范围阅读，不覆盖索引中的当前状态。完整SPEC仍未凭材料整理关闭。

## 2026-10-28 C05a/C05b新基线验收补证（当前增量）

本节优先于下方历史增量。基线为fetch后origin/develop `8e32fb41ab9453f8b4b4f8e7be86153a183b88dc`，从该提交新建`feature/spec-008-acceptance-evidence`；代码/测试干净tested `55167f6f1b04c91606e6e53fa5e7ca339b9cfcbe`，正式浏览器报告`working_tree_dirty=false`。只补008 C05自有链路的验证脚本、测试和证据，未改业务、迁移、鉴权、CI、001/006共享实现、003/004/005或队友模块；PR45保持open，未合并、未cherry-pick、未把其分支内容带入本包。

### 本轮结论与补强

- 定向后端48项通过（`tests.test_quizzes`15、`tests.test_quiz_analytics_integration`1、`tests.test_attempts`16、`tests.test_papers`16，113.238秒）；前端135项、lint/build通过；全仓ruff及`scripts/check_docs.py`通过。均为本机结果，不是远程CI或教师验收。
- Chrome 155.0.8059.86与Edge 156.0.4314.50各10组真实HTTP/UI通过（共20组），`page_errors=[]`；使用真实001账号/课程/成员、真实005知识API、真实006题库/编卷/作答、真实008 quiz API和临时SQLite。服务器`TEST_NOW`只控制开始/截止/讲评窗口，网络故障只abort真实已提交响应；没有用替身业务数据冒充联调。[浏览器报告](evidence/spec-008/acceptance-20261028/browser-results.json)记录tested_head、双浏览器版本、各自开始/结束时间及服务器窗口。
- 新增断言补齐：讲评入口无头/仅Origin/仅CSRF/异源+有效CSRF四组均403，只有同课教师带合法CSRF/Origin及空body或`{}`可成功；普通定时quiz在14:00调用review仍保留16:00`review_at`且答案不提前，16:00实际到点后才释放；截止未讲评时paper/attempt/错题均无`answer`/`explanation`，同question两个版本均不能练习（正常未开放409 `PRACTICE_UNAVAILABLE`，异常已开放数据被409 `QUESTION_RESERVED`拦截）；浏览器侧增加发布/开始前元数据无`items`、讲评前三个读取入口无`answer`/`explanation`、讲评后固定版本答案/解析释放、重复review保留首次时刻，以及元数据和作答态390px无横向溢出。
- 截图：[Chrome统计](evidence/spec-008/acceptance-20261028/chrome-teacher-statistics.png)、[Chrome待批](evidence/spec-008/acceptance-20261028/chrome-student-pending.png)、[Chrome讲评](evidence/spec-008/acceptance-20261028/chrome-student-reviewed.png)，Edge同名`msedge-`三张；均为390px受控课程页面。

### 覆盖对照

| 核对项 | 本轮真实证据 |
|---|---|
| 专用发布仅draft quiz、跨课/非quiz/重复拒绝、review_at初始null、同事务冻结名单与通知去重、并发发布一份 | `test_publication_same_paper_null_review_and_frozen_notification_recipients`、`test_strict_fields_permissions_filters_and_cross_course`、`test_public_identity_rejected_and_notification_failure_rolls_back_publication`、`test_concurrent_publication_keeps_one_event_roster_and_notification`；浏览器发布零统计与名单2/通知原quiz |
| 开始前仅元数据、start≤服务器now<end、截止拒新提交但成功键原201字节重放、转入不补名单、退出保留历史分母/答卷 | `test_exact_start_end_shared_replay_and_manual_scores_do_not_rewrite_snapshot`、`test_new_submission_at_end_is_rejected_without_consuming_key`、`test_current_access_and_frozen_roster_precede_replay`、`test_window_boundaries_replay_exact_snapshot_after_deadline_and_review`；浏览器prestart无题目/无items、丢响应截止后原键重放 |
| expected/submitted/missing、answered/unanswered、graded/pending、correct_count/correct_rate、mean_score、零计数选项、零分母null、漏答计错、简答率null、多选比例>1、待批不混已批均分、冻结名单分母 | `test_statistics_five_types_omissions_options_pending_and_frozen_population`、`test_statistics_only_short_no_objective_denominator_and_empty_roster`、`test_statistics_read_snapshot_survives_concurrent_manual_score`、`test_statistics_mean_does_not_overflow_for_valid_large_scores`、`test_real_dedicated_quiz_partial_missing_omitted_review_grade_old_ids_and_backup`；浏览器应交2/已交1/缺交1、漏答计入、简答null、多选200%、零计数与7.01批分 |
| 显式讲评仅截止后、同课教师、CSRF/Origin、空body或`{}`、仅null设服务器now、重复/并发保留首次时刻且一次审计 | `test_review_exact_end_durable_repeat_and_all_answer_entries_release`、`test_review_permissions_strict_payload_and_ordinary_schedule_retained`、`test_review_failure_rolls_back_and_parallel_retries_audit_once`；浏览器UI讲评+直接API重复同时间、审计1条 |
| 讲评前paper/attempt/错题及同question全部版本无答案/解析、不能练习；实际review_at后释放；普通定时quiz不提前/延后 | `test_closed_unreviewed_quiz_protects_all_versions_and_wrong_question_entry`、`test_review_exact_end_durable_repeat_and_all_answer_entries_release`、`test_review_permissions_strict_payload_and_ordinary_schedule_retained`；浏览器讲评前后API字段断言及页面答案/解析显示 |
| 390px无横向溢出、Chrome+Edge、TEST_NOW仅控窗口 | 双浏览器各10组、`page_errors=[]`、元数据/作答/统计/待批/讲评截图及`documentElement.scrollWidth<=innerWidth`断言；报告记录服务器窗口06:57—06:58 UTC，实际运行06:56:03—06:56:33 UTC |

### 保留未关闭

两名真实非作者复核（判分/答案保护/讲评属敏感改动）；R01（003题库资源/004备课）与R44跨模块仍阻断；003/004实际接缝、007演示/实验/电路完整UC-02、NF-PERF目标Linux4核8GB/50会话/真实worker、生产迁移/恢复及课堂教师验收均未执行；未取得教师验收结论，不把本地通过写成课程通过。

## 2026-10-16 R37定向接缝（当前增量）

004/#20、003/#19、007/#21已合入develop，不再沿用下方C05历史的“004未就绪”作为当前判断。详见[004→008正式联调报告](SPEC-008_R37_INTEGRATION.md)。从核验后的develop dfb23271建立本人008后续feature，干净tested `7204a14054611ab6b68f4ebfae3fd1c6115d575d`；真实handler 8项中6通过、2项004契约预期失败（17.525秒），Chrome155.0.8059.41/Edge155.0.4283.45各5组通过、page_errors=[]、6图目视。

真实知识/题目/quiz/备课关联、跨课/非quiz/重复拒绝、复制不复制/发布quiz、发布后HTTP/UPDATE冻结、冻结名单过滤、开始前保护、讲评前后答案及撤权、通知失败回滚已覆盖。无成功响应mock，账号bootstrap/TEST_NOW与失败注入单列，DB关联/状态/名单/答卷均有快照；未发现需修改本人008/006业务的缺陷。

完整R37仍阻断：罗浩铭004的R37-004-01（未发布quiz应409 QUIZ_NOT_PUBLISHED，实为404 NOT_FOUND）、R37-004-02（备课测验元数据缺window_state）及当前缺备课UI。两项以expectedFailure明确保留，CI成功不等于契约通过。实际仅通过现有008页面消费备课返回的原quiz ID，不冒充备课页面跳转，不代写队友。只补原矩阵SPEC-008/R37行，其余130行不变；历史404/判定/附件/head/tested保留。003完整R01下一包处理，不关闭UC-02/I-03。

#27/#28 head/状态未变、无实际merge/反馈，复用各自固定CI；不改写#27、不把本包混入#28，不执行两个C12b脚本或008整套专用链。下方C05及C12b记录为原版本历史；新最终head CI只写本包PR及两份本地排除交接。此段记录的是该分支形成时的状态，后续合并状态以仓库记录为准。

## 2026-10-15 C12b共用显示增量（最新）

C12a-UI-02共用PaperView/AttemptView由SPEC-006主修，详见[006 C12b记录](SPEC-006_IMPLEMENTATION.md)及[真实HTTP/双浏览器报告](evidence/spec-006/c12b-time/report.json)。006 feature干净tested=4eadbcbcaf1df2cb8f1245c9fdfcbcfca4523072；008不建立重复代码修复、不从未合入feature复制，后续只消费最新develop。仅窗口/讲评/截止/提交显示Asia/Shanghai，UTC数据及服务器截止、答案保护、原成功幂等快照不改。组件替身与5项真实handler、Chrome/Edge真实HTTP/UI分层；原C05/EQB等证据按原SHA复用，没有重跑008→010B专用链。新PR/真实评审/CI/合入独立核验；完整008、003/004/007接缝、目标性能/生产恢复/Gitea/课堂仍未关闭。下方“当前恢复”保留C05历史，以上增量优先。

责任人：黄俊诚（24201716）。记录日期：2026-10-14，Asia/Shanghai。依据：[PRD完整验收](PRD.md#accept-spec-008)、[APIC§4/9/11](APIC.md)、[DBD§4/7/9](DBD.md)。C05a/C05b本人功能已实施；完整008/006验收、跨模块依赖及非作者评审未关闭。最新C05b记录优先于下方C05a历史证据。

## 当前恢复点

复用`feature/spec-008-quiz`，原起点为005/006已合入的develop `5718fabf73c39f49ce8231d30620cfe08dd2283a`；本轮fetch后快进到`253a736`，纳入组长PR #8的014漏答筛选修复，不接管014。C05a代码、测试、规格实施说明随本分支提交；实际提交、推送、PR和CI证据在本记录后续补录，不能由本地通过推断远程批准或合并。

下一恢复：C05b统计/显式review及页面已实现，继续本分支补真实两名非作者复核、003/004与目标环境依赖；先fetch核对PR #9最新head/CI，不自动合并。下一开发包C06从核验且包含008所需事实的origin/develop起步；008尚未合入时按个人计划推进不依赖008的知识统计基础，不能把008 feature作为010B起点。010B成绩分析/不可变快照及CSV在C06/C07补，不因008逐题统计已实现而记AC-04成绩分析全部完成。

本轮Chrome/Edge已使用合入005/006的基线走通知、编卷、限时作答、批阅、统计与显式讲评；原始证据按本轮tested_head单独登记，不提升旧006所有页面的验收状态。003源文件/旧版授权与原子导入、004备课关联/保护联测、目标Linux4核8GB/50会话/worker、完整备份恢复及真实评审仍待补。

## C05b实现及验证（最新）

- [quiz模型](../backend/models/quiz.py)在一个读事务内从原名单、唯一答卷及固定版本聚合完整QuizStatistics，按原题目/选项顺序返回；partial也属于有效提交。缺交=冻结应交−提交，漏答参与正确率分母，简答correct_count/correct_rate为null，未定分不混均分，无提交/无客观题/无定分的对应指标null。选项零计数仍返回，多选总比例可超过1。SQLite AVG避免多个合法大配分导致整数SUM溢出。不输出学生身份，不新增事实表或010B快照。
- [quiz接口](../backend/apis/quizzes.py)统计仅当前同课教师可读；讲评复用CSRF/Origin、BEGIN IMMEDIATE及锁内会话/教师复核，仅截止后从null设服务器now，quiz.review审计同事务，故障回滚。空body或{}可调用，业务字段/非法JSON/查询参数拒绝；重复与并发返回原时刻且不重复审计，原普通定时quiz不提前或延后。
- [原试卷页面](../frontend/js/paper-view.js)增加教师逐题统计、冻结缺交、均分/待批/选项比例和显式讲评操作，显示null为“—”，刷新读取最新批分。讲评后重读原paper，学生原详情/答卷/错题按原身份级保护返回固定版本答案。页面失败、课程/身份变化与迟到响应会清除旧数据，学生没有教师操作入口。
- 不改006判分、答卷、原幂等成功快照、旧迁移、003/004、014或CI。原paper/quiz同键截止重放、未知/越权、冻结分母、全部版本保护在本轮回归；正常讲评备份副本已核对完整性/外键并经真实会话读回，不称生产完整资源恢复。

新增8项后端C05b真实API测试（本文件测试集合由7增至15）和4项前端测试（总54）；[后端入口](../tests/test_quizzes.py)、[页面入口](../frontend/js/paper-view.test.js)、[客户端入口](../frontend/js/quiz-client.test.js)。首次完整后端120项通过（201.462秒）；新增发布/开放竞态后14项quiz通过（31.740秒），合法大配分回归单项通过（1.566秒）；最终完整后端122项通过（172.002秒）。前端54、全仓ruff、lint/build、六文档链接及diff检查全部通过；这些是本机验证，不是远程CI/非作者批准。

[双浏览器脚本](../scripts/verify_spec008_quizzes.py)以临时库、公共迁移、真实001/005/006/008 HTTP及Vue页面运行，只有初始admin/teacher bootstrap；学生注册、课程/名单、知识标签、题库、编卷、专用发布、提交、批阅、统计和review全部走真实API。TEST_NOW控制开始/截止，网络故障仅abort真实已提交响应/统计请求，不替换成功业务数据。Chrome 155.0.8059.40、Edge 155.0.4283.45各8组受控闭环通过，page_errors=[]；390px的统计、待批答卷及讲评结果截图已目视确认无横向溢出。首次预运行带未提交变更，只作预验证；代码提交后正式重跑并保存对应SHA，不能将预运行的旧HEAD写为新代码证据。

| 完整有效编号 | 本轮证据/入口 | 剩余限制 |
|---|---|---|
| AC-01 / AC-02 / R18 | exact_start_end/new_submission测试及浏览器真实交卷响应丢失→截止→原键字节一致重放；唯一attempt | 课堂真实账号/生产未执行 |
| AC-03 / R33 | statistics_five_types/only_short/read_snapshot/large_scores；浏览器零提交、漏答、缺交、简答null、待批、均分、多选200%及最新批分 | 不替代010B快照及CSV |
| AC-04 / R36 | review_exact_end与closed_unreviewed；讲评前paper/attempt/错题及全部版本继续保护；显式review后原固定答案开放/其他版本可开放；定时quiz保持原时间 | AC-04成绩纳入分析由C06/C07补；003/004旁路仍阻断 |
| R02 / R12 / R27 | 原列表、五题型、历史及人工批阅回归；浏览器不猜ID操作、漏数值0分、待批总分null及7.01批分 | 演示为007负责人，完整跨模块UC-02待联测 |
| R16 | publication/five_types/empty_roster；转入不补名单、退出仍保留提交/应交分母，空名单0/0 | 课堂账号验收未执行 |
| R25 | public_identity/concurrent_publication及quiz_publication_and_practice_opening竞态；全版本占用/释放 | 004真实联合待补 |
| R01 / R37 | 本人原quiz ID、名单、窗口与解析接口已就绪 | 003源文件旧版授权/原子导入、004关联发布/保护由原负责人联测 |
| R44 | 开始前、截止、幂等、非法输入/权限、失败回滚及真实网络故障恢复均有入口 | 007演示、实验/电路及003/004的完整UC-02故障分支仍待原负责人 |
| R22 / R45 | 本人范围、依赖和实施登记 | 全组工时/风险证据未核验 |
| R46 | APIC固定输出/单一事实定义、DBD原表/事务、CHG-RB同步 | 跨模块接缝待实际联测 |
| R47 | PR #9仍无真实非作者批准 | 权限/API/讲评需两名真实非作者复核；AI检查不是批准 |
| NF-SEC | permissions/strict_payload、会话退出401、学生403/外课404、CSRF拒绝及原锁内鉴权回归 | 教学账号/生产未执行 |
| NF-DATA | review故障回滚、并发审计一次、WAL真实第二请求批分后同次统计保留旧快照、备份完整性/外键及真实HTTP读取 | WAL只为并发测试条件，未改运行配置；完整资源/电路恢复及生产演练未执行 |
| NF-UI | 当前基线Chrome/Edge各8组真实HTTP/UI及390px截图，正式提交SHA下方补录 | 本机headless受控数据，非课堂/所有006页面完整验收 |
| NF-PERF | 未执行 | Linux4核8GB/50会话/真实worker仍阻断，本机测试秒数不是性能证据 |

### C05b正式浏览器及代码提交

代码/测试/契约/复现脚本提交`917ea08736a001220922f130d090ff35eeb7e5da`已推送origin/feature/spec-008-quiz；继续[PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9)，目标develop 253a736，open/draft、未合并。代码CI [Actions38568683749](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38568683749)已查询run、全部jobs及ci-test日志：completed/success，policy/lint/test/build/required全部success，grader按develop规则skipped；实际后端122项（101.798秒）、前端54项。tested merge=`e6adf1740343347bd80f8b776900d5611eea4fcb`，head=917ea08，base=253a736；此为CI临时merge引用，不是实际合并。正式证据文档的后续提交另核对最新head CI，不沿用代码run当最终head批准；本轮查询reviews=[]，没有008两名非作者批准。

2026-10-14 21:03:37—21:04:04（Asia/Shanghai）在干净工作区正式运行双浏览器，tested_head=`917ea08736a001220922f130d090ff35eeb7e5da`、working_tree_dirty=false；Chrome 155.0.8059.40、Edge 155.0.4283.45各8组通过（共16组）、page_errors=[]。原始报告：[browser-results.json](evidence/spec-008/browsers/browser-results.json)。截图：[Chrome待批](evidence/spec-008/browsers/chrome-student-pending.png)、[Chrome统计](evidence/spec-008/browsers/chrome-teacher-statistics.png)、[Chrome讲评](evidence/spec-008/browsers/chrome-student-reviewed.png)、[Edge待批](evidence/spec-008/browsers/msedge-student-pending.png)、[Edge统计](evidence/spec-008/browsers/msedge-teacher-statistics.png)、[Edge讲评](evidence/spec-008/browsers/msedge-student-reviewed.png)。全部为390px受控课程页面；证据后续文档提交不改变tested_head，不能由此宣称所有006页面、课堂/生产或目标性能验收完成。

复现：`.venv/Scripts/python.exe -m scripts.verify_spec008_quizzes --output docs/evidence/spec-008/browsers`（需要可选requirements-browser.txt、Chrome/Edge及空闲5000/5173；自动关闭所建浏览器/服务器和临时库）。失败记录：首次测试使用同线程嵌套Flask请求导致共用连接500，改独立线程真实请求后快照用例通过；退出预期状态改为真实204；浏览器首次对两个相同B选项文本用单元素断言失败，修正计数后通过。无业务响应替身、无隐去失败、无依赖升级。

## C05a实现与约束

- `POST /courses/{id}/quizzes`严格接受paper_id/start_at/end_at及可选confidentiality_note；只发布本课draft quiz，跨课或不存在404、非quiz/重复发布409，未知字段/非法ID/时区与精度/顺序400。通过原paper.publish(quiz=True)执行保密资格、全部版本并发占用和有效学生名单冻结；review_at初始null，不新增quiz表或迁移。
- 专用发布返回201、id=paper_id、paper_id和按服务器时间计算的status=upcoming/open/closed，另含原paper元数据。`GET /courses/{id}/quizzes`是原paper列表的kind=quiz投影，status筛选使用draft/published，window_state才表示时间窗口；分页、当前成员及冻结名单权限复用原服务，元数据不含题干/答案。所有响应no-store。
- quiz发布提醒复用公共notify与notification。在同一发布事务中只向冻结名单学生写入target_type=quiz、target_id=paper.id、event_key=quiz.published:{paper_id}，按(user_id,event_key)去重；普通paper发布quiz也采用此事件。通知只是导航，读取仍经原权限/名单/窗口复核。名单、发布时间、审计或通知任一步失败则全部回滚；转入者不追加历史名单/提醒。
- paper/quiz提交仍走唯一paper_attempt作用域：新受理仅start≤服务器now<end，成功键可在截止后字节一致重放；先复核当前权限，异内容/异卷冲突、换键不能重复交卷。人工批分仅改变最新GET结果，不改首次成功快照；简答pending时总分null，漏答0分和五题型规则复用006。
- 新增独立随堂测区域，复用PaperView的quizOnly模式进行固定版本编卷、列表/筛选/分页、专用发布及原AttemptView作答/历史/批阅。专用发布只填写开始/截止时间；普通试卷仍填写定时讲评。quiz提交采用原quiz别名，丢响应保留原内容和原键重试；倒计时是本机估计，不决定服务端受理或阻止成功键重放。读取失败/身份变化清除旧数据，后台继续执行权限与答案保护。
- 截止且未讲评仍去掉paper/attempt/错题标准答案与解析，并阻止同question其他版本开放练习或用于其他卷。C05a仅验证保护不提前释放；显式review后的释放与统计留待C05b。

## 验证与追溯

执行人：黄俊诚任务下的Codex自动执行，2026-10-14（Asia/Shanghai）。使用临时隔离SQLite与真实create_app、公共迁移、001注册/登录/课程/成员、005章节/知识和006题库/编卷/判分/批阅；仅初始管理员/教师账号bootstrap，知识helper虽然沿用knowledge_fixture命名，实际调用已合入005 API，不是知识表/HTTP替身。服务器时钟通过现有TEST_NOW精确控制；通知失败用受控SQLite触发器注入，前端单元测试使用HTTP/渲染替身，不称浏览器验收。

新增[后端测试](../tests/test_quizzes.py)7项通过（14.550秒）；前端全量50项通过（新增4项），[专用客户端](../frontend/js/quiz-client.test.js)、[发布页面](../frontend/js/paper-view.test.js)及[作答页面](../frontend/js/attempt-view.test.js)分别覆盖专用路径、无自动讲评、会话拒写和本机倒计时归零后的原键重试。全量后端114项通过（173.823秒），前端50项、全仓ruff、前端lint/build、六文档链接与diff检查通过；本轮未执行真实浏览器、003/004联测或目标性能验收。

| 有效编号 | 结果与具体入口 | 剩余证据 |
|---|---|---|
| AC-01 / R12 | 通过（C05a子集）；`test_exact_start_end_shared_replay_and_manual_scores_do_not_rewrite_snapshot`、`test_new_submission_at_end_is_rejected_without_consuming_key` | 真实浏览器闭环及完整UC-02待C05b |
| AC-02 / R18 | 通过（原提交共用）；上面的exact_start_end测试证明跨paper/quiz同一答卷、截止后字节重放、异内容拒绝、批阅后原快照不变 | C05b review后再回归 |
| AC-03 / R33 | 待执行 | C05b逐题统计及分母 |
| AC-04 / R36 | 通过（截止未讲评保护子集）；`test_closed_unreviewed_quiz_protects_all_versions_and_wrong_question_entry` | 显式review后开放及010B成绩分析待执行 |
| R01 | 阻断（003/004部分） | 题库源文件旧版授权、原子导入、备课旁路联测 |
| R02 | 通过（C05a列表/原答卷历史与批阅入口子集）；publication与exact_start_end测试、前端发布/作答组件测试 | 演示与完整UC-02待执行 |
| R16 | 通过（冻结名单子集）；`test_publication_same_paper_null_review_and_frozen_notification_recipients` | C05b缺交统计验证原分母 |
| R25 | 通过（专用公开历史拒绝/全版本占用子集）；closed_unreviewed、public_identity与concurrent_publication测试；006共享保护回归 | C05b释放、004真实联合及专用发布/开放练习竞态补证 |
| R27 | 通过（原判分/批阅子集）；exact_start_end测试及006全量回归 | C05b统计/完整五题型闭环 |
| R37 | 阻断（004未就绪） | 本人提供原quiz ID/元数据/名单/窗口入口，队友备课不得复制状态/提前泄题 |
| R44 | 待执行（完整流程） | C05b故障分支、完整UC-02及跨模块映射 |
| R22 / R45 | 待执行（全组） | 分工与依赖已登记，全组工时/风险证据由原负责人提供 |
| R46 | 通过（本包契约归并子集） | APIC/DBD保留原事实归属和单一定义；003/004接缝待核对 |
| R47 | 待执行 | 涉及权限/工作流/API需两名真实非作者复核；AI检查不作批准 |
| NF-SEC | 通过（本包权限/CSRF/跨课/名单/保密子集）；strict_fields、publication及closed_unreviewed测试 | 教学账号/完整跨模块验收待补 |
| NF-DATA | 通过（同事务回滚与并发去重子集）；`test_public_identity_rejected_and_notification_failure_rolls_back_publication`、`test_concurrent_publication_keeps_one_event_roster_and_notification` | 完整资源/电路备份恢复及生产演练待执行 |
| NF-UI | 待执行（真实双浏览器） | 单元组件替身和lint/build不替代Chrome/Edge当前head证据 |
| NF-PERF | 阻断 | 目标环境/50会话/真实worker未就绪，本机测试秒数不是性能证据 |

复现命令（仓库根；npm命令在frontend目录）：

```powershell
.venv/Scripts/python.exe -m unittest tests.test_quizzes -v
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend: npm test; npm run lint; npm run build
```

没有修改旧迁移、判分规则、队友模块或CI。回退须保存本轮发布、通知、答卷、审计和幂等增量并使用配套代码/一致性备份恢复点；不可删历史paper/attempt或把review_at提前改成截止来绕过保护。没有部署、生产迁移、合并或发布。

## 提交、PR与CI证据

C05a代码/测试/契约记录提交`ce6dbfeb7cd1ce7312f9ab73a23cfe28566c06c6`已推送origin/feature/spec-008-quiz；[PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9)为open/draft，目标develop，实际base为`253a736a79a6b6778e8bde0e58673d1f4c7641d7`。没有008真实非作者批准或实际合并；005/006既有合并及课程评审缺口不因本PR变化。

代码[Actions38564909856](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38564909856)已查询run、全部jobs和ci-test日志：completed/success，ci-policy/ci-lint/ci-test/ci-build/ci-required全部success，ci-grader按develop规则skipped。实际日志后端114项（62.390秒）、前端50项，tested merge=`7a378cf6132ce662b92d7b0b66aa7f413d8cb1e7`，head=ce6dbfe、base=253a736；该merge是CI临时测试引用，不是PR实际合并。随后仅补本节证据的文档提交须独立核对最新head CI，不沿用代码run作最终head批准。最新恢复仍为C05b；完整008/006、真实浏览器/跨模块/目标环境和两名非作者评审未关闭。
