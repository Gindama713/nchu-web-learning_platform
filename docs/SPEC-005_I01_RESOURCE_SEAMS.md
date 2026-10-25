# 005后续：I-01实际能力与图文资源契约核对

> 2026-10-19当前收口：#27—#35及#38修复已合入develop；原004/007/017接口缺陷复验通过，仍缺页面/全组环境另列。131行现为本地81通过/50阻断、集成81通过/50阻断，见[合入后复验与剩余工作](SPEC-010B_POSTMERGE_ACCEPTANCE.md)。以下旧日期、SHA、计数和“待合入/失败”均为当时记录，不覆盖本条当前结论；完整SPEC及课堂未关闭。

黄俊诚（24201716），2026-10-17，Asia/Shanghai。本包完成用户指定A/B的可执行接缝；**完整I-01、完整SPEC-005及图文能力仍未关闭**。没有修改业务源码、共享APIC/DBD、迁移、CI或队友模块；新增真实联测、执行器、证据及原矩阵增量。未发现需要修复本人005消费代码的缺陷。

## 已合入事实与本轮范围

fetch后develop仍为`dfb23271b470a93d557a2695fed0e04caf59d0d2`，工作区初始干净。#27—#31 head仍分别7096b496/8111c539/b56141f2/dbd32e65/40bba87e，全部open/非draft/未实际合入，真实comments/reviews/review_threads均[]；沿用固定CI38896062651/38904433916/38907219999/38909993594/38994482166。没有把其merge测试引用当actual merge，没有复制未合入实现/报告或改写旧PR。PR31报告按40bba87e固定head阅读。见[入口核验](evidence/spec-005/i01/entry-state.json)。

005 #4、003 #19、009 #18、017 #22、010C #23的GitHub actual merge均已核实为origin/develop祖先，不能继续沿用旧404判断模块未开发。见[actual merge及祖先结果](evidence/spec-005/i01/merged-dependencies.json)。检查无同名分支后从该develop建立`feature/spec-005-i01-resource-seams`；没有使用#28工作区或复制它的材料。

依据：[PRD I-01/UC-03及有效005验收](PRD.md#accept-spec-005)、[009验收](PRD.md#accept-spec-009)、[017验收](PRD.md#accept-spec-017)、[010C验收](PRD.md#accept-spec-010c)、APIC§3.1/5.1/6/9、DBD§3/5/6。实名责任以PRD§10.1为准：005及010B黄俊诚，003/009石佰合，017/010C罗浩铭。

复用已有覆盖而不重跑整包：`test_knowledge.py`已有HTML清洗、自报进度/下架和章节排序；`test_knowledge_integration.py`已有真实001接入；`test_experiments.py`已有真实版本/名单/同课引用/分页；`test_wiring.py`已有真实保存/结构/功能和不可变提交；`test_wiring_analytics.py`是构造输入的算法测试，不能冒充真实学生事实。现有009组件测试只验证派发入口事件，不证明017工作台已经打开。既有003主要用PDF/JSON，不能据此声称PNG上传通过。原005主体及R38完整既有结果仍见[SPEC-005记录](SPEC-005_IMPLEMENTATION.md)和[SPEC-010B记录](SPEC-010B_IMPLEMENTATION.md)。

本轮新增的是同一批真实005→009关联→017提交→010C消费、同集合进度与实验分母区别，以及005现行禁图/禁链接和003真实PNG上传能力核对。无契约的自动知识→实验跳转、知识完成联动实验完成、固定知识正文版本、知识内嵌资源关系均未设计或新增。

## A：实际事实与有限消费

所有成功业务对象经001/005/009/017实际API创建。005创建本课章节、两点已发布知识及一点草稿；另一真实课程的知识引用被009创建版本拒绝400，学生跨课005详情/实验列表404、学生编辑知识/实验版本403、教师自报学生进度403。学生由实际实验列表的latest_version.id选择v1，读到原知识ID及指导；草稿005详情404。

实验v1发布冻结4名真实注册学生，固定窗口11:00—12:10上海时间，原请求为`start_at=2026-10-17T03:00:00Z,end_at=2026-10-17T04:10:00Z`。后端受控TEST_NOW初始04:00Z。实验版本及knowledge_ids关联由真实表保留，v2不会改写v1。**实验版本固定知识ID，不固定知识正文历史revision**；APIC/DBD未定义知识正文快照，因此没有把该关系说成固定知识内容版本。009的definition_sha256当前覆盖其定义字段，未声称覆盖知识关联或知识正文。

| 原冻结学生 | 实际操作和原记录 | v1结果 |
|---|---|---|
| S1 | 从列表选v1，六条真实connect动作保存revision1/latest_seq6；GET恢复原state；旧revision保存409；validate真实成功后submit | submitted/completed=true，功能断言全部通过 |
| S2 | A/B输入接反但结构合法，真实保存并提交 | submitted/completed=false，实际功能结果含失败 |
| S3 | 新建草稿，在revision0重复validate两次，无submit | draft/completed=false；重复REQUIRED_OPEN不重复算错误尝试 |
| S4 | 没有创建attempt，也没有提交 | 无attempt；不伪造0分或失败提交 |

教师实际读取原attempt和actions。第一次010C查询在04:11Z，筛选`from=2026-10-17T00:00:00Z,to=2026-10-17T04:11:00Z`，按已发布版本end_at选任务，返回assigned_count=4、completed_student_count=1、completion_rate=0.25、attempt_count=2、error_counts={REQUIRED_OPEN:1}。attempt_count仅已提交次数，草稿不混入；完成按功能全过，不按结构合法或005自报完成替代。原输入快照保留3个attempt及验证事件，逐项核对其ID、学生、固定实验版本、状态、completed和提交时间。

005侧S1只标记第1点完成，010B仅消费005进度事实：completed_knowledge_count=1、published_knowledge_count=2、progress=0.5，实际客观题sample_size=0、mastery=null。两个实验提交不会产生掌握度样本或第二条知识完成记录。下架该已完成点后，005旧详情404，新的同集合进度为0/1=0，历史learning_progress保留。

原统计A保存后，教师真实新建v2、改其关联为第2点并发布04:11—04:15Z窗口，冻结同4人；学生由更新后的列表选择v2并产生第4条真实attempt（S3功能成功），未改v1草稿或两个旧提交。04:16Z新查询B的assigned_count=8（4人×2版本）、completed_student_count=2、completion_rate=0.25、attempt_count=3。旧analysis_run_id=2读取data逐项相同，旧CSV三次教师导出字节相同，原输入/结果及原提交快照保留；新结果使用新的analysis ID。学生读教师ID404、调用导出403；真实001撤销S1成员后，005进度/详情/个人快照、009列表/旧版本、017旧详情均404，教师原统计及CSV仍不变，原冻结名单不减少。

完整实际请求及阶段事实见[主接缝记录](evidence/spec-005/i01/handlers/test_published_knowledge_fixed_experiment_facts_and_teacher_consumption.json)。这只验证本包消费范围，没有重跑010C完整算法或EXP-02/03、CPU引擎、M9整包。

## 队友缺陷、入口与最小复现

以下是本包问题号，不新增PRD验收编号；已登记负责人，不代修、不发送协作消息。

| 问题号及有效条目 | 实际最小复现、证据及文件 | 负责人/判定 |
|---|---|---|
| I01-017-01；017/AC-01/05/07、R02；009/AC-02 | 真实009列表选v1→查看指导→点击“进入实验箱连线”，派发cpu-experiment-open及真实version_id，但无接收者/工作台、没有wiring-attempts请求。`frontend/js/main.js`无017挂载；`frontend/js/experiment-view.js` openEntry只有事件。双浏览器记录headings和[截图](evidence/spec-005/i01/browsers/chrome-experiment-entry-blocked.png) | 罗浩铭；017页面阻断。009实际列表/指导/事件观察通过不等于连线页面链通过 |
| I01-017-02；017/R16、UC-03、APIC§9 | 已发布但start=05:00Z，now04:00Z时POST wiring-attempts应拒绝409，实际201；另在有效窗口建/保存revision1，now04:11Z超过end04:10Z，POST submit应409，实际200/completed=true。`backend/apis/wiring.py` create_attempt/submit_attempt未复核窗口。见[未开始](evidence/spec-005/i01/handlers/test_contract_017_future_window_rejects_new_attempt.json)、[截止](evidence/spec-005/i01/handlers/test_contract_017_closed_window_rejects_submit.json) | 罗浩铭；两个真实契约失败，分别expectedFailure |
| I01-017-03；017权限共通、R16、APIC§9 | 窗口内保存revision1→DELETE本人成员204→旧GET404，但旧PUT revision1返回200/revision2，validate revision2返回200，submit revision2返回200/completed=true，原库实际被写。save_attempt/validate_attempt/submit_attempt只有本人校验，缺课程成员复核。见[逐请求及原表](evidence/spec-005/i01/handlers/test_contract_017_revoked_member_rejects_old_mutations.json) | 罗浩铭；真实契约失败，expectedFailure；不能用GET拒绝代表写入也拒绝 |
| I01-017-04；017/AC-07/10、UC-03 | 窗口内已成功提交后再次POST同版本wiring-attempts，应有新attempt供重做；实际200返回原submitted attempt，同id/revision1，无法新建重做。create_attempt existing分支见`backend/apis/wiring.py`。见[原始记录](evidence/spec-005/i01/handlers/test_contract_017_redo_creates_new_attempt_after_submission.json) | 罗浩铭；真实契约失败，expectedFailure；未验证同人重交完成去重，不能套用算法测试冒充接口通过 |
| I01-010C-01；010C继承010/AC-01/04的页面消费 | `frontend/js/analytics-view.js`仅knowledge/scores且拒绝恢复wiring快照；main.js只有考勤统计及010B页面，没有010C页面。真实010C GET/旧ID/CSV已有本包handler证据；无现成页面可核对其展示/恢复/导出 | 罗浩铭；UI阻断，未新增或接管010C页面 |
| I01-009-01；PRD§8 NF-UI时间 | 009历史版本行原样显示start_at/end_at的UTC Z字符串，截图如2026-10-17T00:44:50.000Z，未转上海展示；响应字段为UTC本身合法。位置`frontend/js/experiment-view.js`版本列表。见双浏览器experiment-entry-blocked截图 | 石佰合；本次目视登记既有页面缺口，未代修，不将其他受测检查泛称009完整UI通过 |

## B：图文与003资源现行契约

APIC§3.1只允许p/br/b/strong/i/em/u/ul/ol/li/pre/code/blockquote/sub/sup/h2/h3，去除全部属性及其他标签；图片、链接和主动内容明确暂不支持。实际005正文/例题保存把img删除、a去标签但保留文字，onclick/style/class/href/target均不保留，sup/sub继续显示。真实`resource_version_ids`未知写字段400。实现位置`backend/models/knowledge.py` SafeHTML；编辑器明确显示移除图片/链接/属性的提示，没有图片上传或资源选择器；阅读页没有img/a节点，也未因该正文发出资源内容请求。

APIC/DBD定义003自身的固定resource_version及当前授权content端点，但**没有005知识资源引用字段/表、同课绑定、固定资源版本或知识撤权显示规则**；已有preparation_resource是004关系，不能挪作005授权。003的intent/event_id已有定义：明确打开生成逻辑UUID，重试/Range复用；只有200/206成功内容记一次，旧版本也按当前资源权限读取。不能把该资源访问契约擅自扩成知识内img src规则。

实际PNG fixture经教师对slides、guide、video、question_bank四种现有kind上传全部415 UNSUPPORTED_MEDIA；数据库没有成功图片对象。`backend/apis/resources.py` KIND_MEDIA只列PDF/PPT、视频和JSON，虽VIEWABLE_PREFIXES允许PNG/JPEG，但没有可创建这种图片的现有上传kind。问题I01-003-01（003/AC-01/02的图片能力缺口、005图文依赖；石佰合负责003，黄俊诚负责005消费）：现行上传输入未定义图片分类/MIME，不能把415直接判成违反现有上传契约，更不能伪造图片预览/下载、旧图片版本/撤权通过。JPEG上传未实际执行，也未宣称通过。

为区分当前003可用与图片缺口，单独经真实API/UI创建合法类型的PDF字节对照v1/v2：原版view两次字节一致、同event_id仅一事件，新版download另一事件；teacher_only后学生原URL/versions404、教师旧版仍可读。浏览器从资源历史v1按钮真实下载、字节等于原PDF对照，收紧后列表为空。**这只是文档类型/旧版本/当前授权对照，不是图片渲染证据，也不复跑PR30题库源文件/原子导入包。** fixture是短PDF类型探针字节，未拿它证明完整PDF渲染器正确性。见[handler实际响应](evidence/spec-005/i01/handlers/test_markup_resource_upload_policy_and_current_permissions.json)及双浏览器socket记录。

后续最小待定边界：003需确定图片kind及允许MIME/尺寸与真实上传；005需团队确定知识内表示形式、同课/学生可见校验、固定resource_version_id、逻辑打开event_id/Range重试、资源撤权/成员撤权/下架后的重读与占位显示。001继续提供当前课程授权，003提供资源版本与内容鉴权，005仅消费已定义引用。需要先形成明确契约及适用真实复核，当前未修改APIC/DBD、未新增数据库关系，未开放任意URL或file_object下载入口。

## 正式证据、夹具与复现

干净tested为`96f4f2989765359e01949f4003dde4d32c0c4814`，handler/browser报告dirty_paths均[]；正式附件随后提交，不声称在附件自身SHA执行。最终head独立CI只更新PR及两份本地排除交接，避免SHA循环提交。[独立原始事实复算](evidence/spec-005/i01/reconciliation.json)核对actions/seq、提交state的SHA、功能结果与completed、冻结人×版本集合、010C计数/错误去重及旧CSV；PNG各chunk CRC与解压扫描行也已验证。

- [handler报告](evidence/spec-005/i01/handlers/report.json)及[原日志](evidence/spec-005/i01/handlers/handlers.txt)：6项18.680秒，**2通过、4项017契约expectedFailure**。每项保存实际脱敏请求响应和最终原表；4项不是通过。其失败trace分别落在目标契约断言，没有用fixture/其他异常冒充已知失败。
- [浏览器报告](evidence/spec-005/i01/browsers/report.json)：Chrome155.0.8059.41、Edge155.0.4283.45各7组受测检查，page_errors=[]；其中含PNG真实拒绝及017缺页观察，不是7组完整I-01/图片/017 UI通过。实际socket请求分别见[Chrome](evidence/spec-005/i01/browsers/chrome-requests.json)、[Edge](evidence/spec-005/i01/browsers/msedge-requests.json)，原库/审计/外键见[Chrome事实](evidence/spec-005/i01/browsers/chrome-facts.json)、[Edge事实](evidence/spec-005/i01/browsers/msedge-facts.json)。
- 夹具分别登记：只SQL bootstrap最初admin/teacher、TEST_NOW及合法面板定义输入；学生注册/课程/成员/知识/实验/上传/提交全走真实API。handler用Flask实际处理器；浏览器准备阶段走同一套实际handler，原请求单列[Chrome bootstrap](evidence/spec-005/i01/browsers/chrome-bootstrap.json)/[Edge bootstrap](evidence/spec-005/i01/browsers/msedge-bootstrap.json)，没有冒充socket。其后全部页面及APIRequestContext为真实socket；after_request只观察响应，不替换返回。无成功mock、业务表直接插入、故障注入、仿真成功double；SQL其余仅原始事实读取。
- 首轮脚本未完成：事实采集误按所有表的id排序（wiring_action非该模型）及时间夹具前移两小时使会话过期，随后查询日期先缺时区、再超当前时间，均修正脚本/夹具；没有改业务接受非法筛选。浏览器观察器最初晚于首请求注册被Flask拒绝，后在初始化前注册；相对locator、select标签及knowledge/qa重复class导致定位失败，日志临时目录清理顺序也已修正。保留[handler查询失败报告](evidence/spec-005/i01/preflight/handler-date-query-failure.json)、[浏览器定位失败报告](evidence/spec-005/i01/preflight/browser-selector-failure.json)及[过程说明](evidence/spec-005/i01/preflight/failures.json)；正式轮只认干净tested，不混用预检截图。

12张390px截图逐张目视：HTML清洗、进度、自报说明、PNG415、009真实列表/引用名/事件提示及撤权清空与响应一致，无整页横向溢出。关联知识只是文字列表，未冒充可点击跳转；没有017工作台截图或010C页面通过。

最初2dd3135轮的PNG夹具IDAT CRC错误；虽415发生于MIME类型检查，仍不作为有效图片的正式证据。已单独提交96f4f29修正CRC并核验1×1灰度/alpha的实际解压扫描行，随后在干净96f4f29重新运行本包全部6项handler及双浏览器、重新目视12图。原[2dd handler报告](evidence/spec-005/i01/preflight/initial-2dd-handler-report.json)/[2dd浏览器报告](evidence/spec-005/i01/preflight/initial-2dd-browser-report.json)降为预检留存，正式附件均来自新轮。

| 浏览器 | PNG上传415 | 编辑规则 | 清洗后阅读/进度 | 实验入口阻断 | 资源撤权重读 | 成员撤权 |
|---|---|---|---|---|---|---|
| Chrome | [图](evidence/spec-005/i01/browsers/chrome-png-upload-415.png) | [图](evidence/spec-005/i01/browsers/chrome-markup-editor-policy.png) | [图](evidence/spec-005/i01/browsers/chrome-sanitized-reading-progress.png) | [图](evidence/spec-005/i01/browsers/chrome-experiment-entry-blocked.png) | [图](evidence/spec-005/i01/browsers/chrome-resource-permission-reread.png) | [图](evidence/spec-005/i01/browsers/chrome-revoked-entry-cleared.png) |
| Edge | [图](evidence/spec-005/i01/browsers/msedge-png-upload-415.png) | [图](evidence/spec-005/i01/browsers/msedge-markup-editor-policy.png) | [图](evidence/spec-005/i01/browsers/msedge-sanitized-reading-progress.png) | [图](evidence/spec-005/i01/browsers/msedge-experiment-entry-blocked.png) | [图](evidence/spec-005/i01/browsers/msedge-resource-permission-reread.png) | [图](evidence/spec-005/i01/browsers/msedge-revoked-entry-cleared.png) |

```text
.venv/Scripts/python.exe -m scripts.verify_i01_handlers --output logs/i01/recheck-handlers
.venv/Scripts/python.exe -m scripts.verify_i01_browsers --output logs/i01/recheck-browsers
```

需要既有依赖、Chrome/Edge及空闲5000/5173；结束关闭本次服务/浏览器并清理临时库和上传。Context7已解析查询Git、Flask、Playwright及Ruff具体用法；本机无gh，GitHub实际读取和建更PR使用已连接工具。没有安装或升级依赖。

## 原矩阵增量与继续保留事项

仅补[原JSON矩阵](evidence/c12a/acceptance-matrix.json)和[原Markdown矩阵](evidence/c12a/acceptance-matrix.md)实际覆盖的8行：005/AC-01/03/04、R20、R38、NF-SEC、NF-UI及010B/R38。保留原整行/Markdown行、原编号/判定/head/tested及附件，追加I01历史/tested/证据；其余123行不变。131行仍本地80通过/0失败/51阻断、集成59通过/72阻断；不改判，不新增队友矩阵行或第二矩阵。#27—#31未合入的矩阵增量不复制；尤其本分支统计仍是develop的59/72，不套用PR31的62/69。

004/007没有新实际修复合入：I03-007-01缺演示页、I03-007-02未来cursor虚报revision；R37-004-01错误码、R37-004-02缺window_state及004备课UI继续按PR31/29固定head证据保留。007一项及#29两项expectedFailure不是通过；本分支未复制它们测试，不能以本PR CI没有它们消除旧失败。未重跑I-03、R37整包或两个C12b脚本。

完整R47、目标4核8GB/50会话/worker环境、生产恢复/90天保留、课堂/真实账号验收仍未执行。012推荐、013组卷、018评测及其他完整模块不展开。初始主页面自动挂载其他模块不构成新增覆盖。后续仅在负责人真实修复且actual merge为develop祖先后，补相应受影响项。

回退仅撤销本包联测/脚本/附件及8行矩阵增量；无业务迁移、旧版本或历史事实改写。本轮不直推共享、不强推、不删分支、不代合并、不部署/发布、不归档、不发协作消息。最终head/PR/独立CI及本地收尾状态见本包PR与两份本地排除交接。
