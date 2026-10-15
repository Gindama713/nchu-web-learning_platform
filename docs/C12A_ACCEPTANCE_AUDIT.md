# C12a 七个本人SPEC验收缺口与必要接缝

黄俊诚（24201716），2026-10-15，Asia/Shanghai。核对/自动执行人为本次授权下的Codex；不是非作者评审人或课堂验收人。本轮仅验收审计、已合入教学链补验和010B必要显示修复，不展开C12c整套报告。

依据：[PRD§11.5完整索引](PRD.md#acceptance-index)、§4/8/9/10.5/11.1—11.5与有效追加R；[README§8及附录A](../README.md)、[CHG-RB](CHG-RB.md)发布/恢复约束。沿用现行APIC/DBD，不修改规格、旧迁移、CI或队友业务。

## 当前结论与完整集合

完整逐行记录见[验收矩阵](evidence/c12a/acceptance-matrix.md)，可机器读取的[完整字段JSON](evidence/c12a/acceptance-matrix.json)保留每行来源、输入/预期、实现、测试/人工步骤、证据层、补验、实际、结果、执行人/日期、PR/head/tested和附件。

| SPEC | AC | 业务R | 共通R | NF用例组 | 通过 | 失败 | 阻断 |
|---|---|---|---|---|---|---|---|
| 005 | 01—04 | 20/32/38 | 22/45/46/47 | 5 | 8 | 0 | 8 |
| 006 | 01—05 | 01/02/12/16/18/25/27/36/44 | 同上 | 5 | 13 | 1 | 9 |
| 008 | 01—04 | 01/02/12/16/18/25/27/33/36/37/44 | 同上 | 5 | 13 | 1 | 10 |
| 010B | **继承父SPEC-010/AC-01—05** | 12/15/16/27/33/34/38 | 同上 | 5 | 15 | 0 | 6 |
| 011 | 01—04 | 20/35，含未另编号的算法追加 | 同上 | 5 | 9 | 0 | 6 |
| 012 | 01—04 | 20/34/35，含未另编号的算法追加 | 同上 | 5 | 9 | 1 | 6 |
| 013 | 01—05（含§4.2追加05） | 14/25 | 同上 | 5 | 10 | 0 | 6 |
| 合计 | 31 | 37 | 28 | 35 | 77 | 3 | 51 |

131行无遗漏，结果只用待执行/通过/失败/阻断/不适用；本轮没有“不适用”及其批准。NF名称是既有用例组，未新造AC/R。**“通过”限该行明确的本人本地适用行为，不等于完整SPEC关闭**。矩阵另列“集成结果”：011/012独立feature上的业务通过仍全部保留develop跨链阻断。统计数不能解读为课程通过率；真实课程复核、目标性能和生产/课堂缺口单独保留。

## 最新远端与集成边界

开始工作区干净，位于012 feature。fetch成功后develop仍为`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`。实时读取PR元数据、实际reviews、review threads、issue comments和当前head Actions/jobs/ci-test原始日志，保存[接入快照](evidence/c12a/start-remote.json)及[日志摘录](evidence/c12a/open-pr-ci-summary.txt)。

| PR | 当前head | base | 实际状态/CI | 实际评审/讨论 |
|---|---|---|---|---|
| [#14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14) | bbd9ecdb151cab0ff7a34e94261b5378ceabfb74 | develop/f9c49b1 | open/非draft，未合入；run38681339662 policy/lint/test/build/required全部success，grader依develop规则skipped；实际194项152.886秒/前端76 | reviews=[]，review_threads=[]，comments=[] |
| [#15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15) | 36a9cff64425221a146bbfbf301f212a34db48f8 | develop/f9c49b1 | open/非draft，未合入；run38694647828同样必需成功/grader skipped；实际190项160.029秒/前端77 | reviews=[]，review_threads=[]，comments=[] |

没有真实评审提出的本人阻断，故不伪造修复、批准或讨论关闭。#14 tested=`805b1afa2ca40b6955fcae9becaa62acf9c7ac95`，#15 tested=`60757090901320e2b095fb3226dae4f9449c298d`均为**CI合并测试引用，actual merge均不存在**。未把这些代码复制到010B或develop。

再次读取已合入PR，实际merge如下，均可在当前develop祖先链找到。对应PR各有Gindama713一份真实批准，原文/日期在接入快照；不写成两份或完整课程规格复核。

| 归属 | PR/head | 实际merge SHA |
|---|---|---|
| 005 | #4 / fc67f0c649ae904039f210875de5e388926805a9 | 17fd54e6dd428c1446127a4338ddf6b51a85e656 |
| 006 | #7 / 335a1239ae93f46f089b524687e82549693b836a | 5718fabf73c39f49ce8231d30620cfe08dd2283a |
| 008 | #9 / fafc69aecf723d06181e807bc1124aed2bd915de | b4a376b860e891a969c9507d69b4cefba5c7f290 |
| 010B | #10 / 0d1ad349fe761cdbd99e53e05a89e34bfbf684ab | 7759d650e9b0a9b6c2a8070471f1040af603a22f |
| 013 C08 | #11 / d7a0e7819eabbab68899381e322ce6df97b9f4ad | bcda8c468e9054579639f3f66c709a54283494aa |
| 010B续包 | #12 / ab91dc1b666c1382d170fba189d1dc3e7654bf26 | cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb |
| 013 C09 | #13 / 4710a56399d3c3eaf5a97ceaba142fa403263e07 | f9c49b19c59053be2b171e0b7f2a35d1e050e57e |

本轮继续既有`feature/spec-010b-knowledge-analysis`，先快进本地至远端ab91dc1，再快进至已核验develop f9c49b1；没有未合入跨SPEC代码。以010B为本次上游教学事实→统计的联调保存点，矩阵同时登记本人全部责任范围。后续006/008/012专属修复仍回各自feature，不放入本分支。

## 证据目录与复用判断

复用不是把旧CI宣称为当前head结果。旧附件保留原tested_head、环境和用途；[复用清单一](evidence/c12a/reuse-one.json)、[二](evidence/c12a/reuse-two.json)、[三](evidence/c12a/reuse-three.json)登记原报告SHA-256、固定ref、真实浏览器版本及相关文件差异。

| 代号 | 原始证据与输入/预期/实际 | 有效范围及限制 |
|---|---|---|
| E005 | [005记录](SPEC-005_IMPLEMENTATION.md)与[原浏览器JSON](evidence/spec-005/browsers/browser-results.json)，bdfa25c；检索、公式/例题、收藏/完成重登、发布及章节排序 | 对比当前知识模型仅尾空行；适用证据保留。图片/链接契约仍未就绪，不把文字/HTML白名单升级为图文通过 |
| E006 | [006记录](SPEC-006_IMPLEMENTATION.md)及[原C04 JSON](evidence/spec-006/practices-knowledge-fixture/browser-results.json)，408c29a；固定版本、错题/幂等/解析保护 | 原浏览器成功知识为当时明确夹具，不能替代真实005接缝。practice相关实现与当前base无差异；新真实标签/五题型编辑与旧版本→错题→统计由B12补齐 |
| E008 | [008记录](SPEC-008_IMPLEMENTATION.md)、[原JSON](evidence/spec-008/browsers/browser-results.json)，917ea08；专用发布/名单/五题型/待批/缺交/分母/显式讲评 | quiz模型/API无改变；paper页面新增013入口，后续E013已覆盖该接入口；不重跑独立C05。003/004旁路和007演示不在通过范围 |
| EKB | [010B记录](SPEC-010B_IMPLEMENTATION.md)、[原C07 JSON](evidence/spec-010b/browsers/report.json)，29ade52；四作答3正确、分箱、旧ID/CSV、撤权 | 数值/同快照语义可复用；课程加载时序由#12修复，时间显示由UI12修复，相关显示由新证据取代旧截图 |
| EQB | [专用联测JSON](evidence/spec-010b/quiz-browsers/report.json)，d1063a4；实际应交3/已交2/缺交1，quiz客观1/6与knowledge1/2，批分后22.5%，旧JSON/CSV不变 | 原始Chrome为**150.0.7871.47**、Edge155.0.4283.45，各6组；部分历史摘要写155，按原JSON纠正。该时点至base范围内知识/成绩模型与统计页面无差异；本轮仅显示时区增量，不重跑专用联测 |
| E013 | [013记录](SPEC-013_IMPLEMENTATION.md)、[当前合入时JSON](evidence/spec-013/c09-browsers/browser-results.json)，641d6ae；精确334/334/333、同题去重、重放、422、专用quiz草稿发布 | 原始Chrome150.0.7871.47/Edge155.0.4283.45各5组，相关生成模型/页面至base无差异。算法18/19项、真实handler、100000节点故障/规模夹具按原记录分层，不重做C09 |
| E011 | [#14固定011记录](https://github.com/Gindama713/nchu-web-learning_platform/blob/bbd9ecdb151cab0ff7a34e94261b5378ceabfb74/docs/SPEC-011_IMPLEMENTATION.md)；[固定浏览器报告](https://github.com/Gindama713/nchu-web-learning_platform/blob/bbd9ecdb151cab0ff7a34e94261b5378ceabfb74/docs/evidence/spec-011/browsers/report.json)，tested3685408，各9组 | 17专题含5算法组件/12实际handler；真实socket/UI与故障夹具另记。QA失败期间实际006作答201已留证，仅独立feature有效；当前develop未注册QA，不宣称I-03完整通过 |
| E012 | [#15固定012记录](https://github.com/Gindama713/nchu-web-learning_platform/blob/36a9cff64425221a146bbfbf301f212a34db48f8/docs/SPEC-012_IMPLEMENTATION.md)；[固定浏览器报告](https://github.com/Gindama713/nchu-web-learning_platform/blob/36a9cff64425221a146bbfbf301f212a34db48f8/docs/evidence/spec-012/browsers/browser-results.json)，testede8da241，各7组 | 13专题含3算法/10实际handler；冷启动、28天、原分数、固定版本/入口保护及故障503不阻断201。仅012独立feature，不推断I-02评测事实已接入 |
| H12 | [本轮7项handler日志](evidence/c12a/handler-tests.txt) | 真实001/005及practice/knowledge handler、SQLite，8.950秒；不是socket/UI、课堂或性能数据。helper名称含Fixture但当前代码实际调用005 API |
| B12 | [本轮干净双浏览器JSON](evidence/c12a/report.json)、四张同目录390px截图；[脚本](../scripts/verify_c12a_seams.py) | tested2fa4a2b04533bb8023d0e4a7f35de909c38a1e75，dirty_paths=[]，Chrome155.0.8059.41/Edge155.0.4283.45各9组，page_errors=[]；仅账号bootstrap/TEST_NOW及明确故障触发器，业务成功均真实网络请求 |
| UI12 | [组件测试](../frontend/js/analytics-view.test.js)、[本轮前端70项日志](evidence/c12a/frontend-tests.txt) | 上海跨日时间、周区间、原快照不变；组件HTTP替身与真实B12分开。lint/build/ruff/六文档/diff通过；新head CI另核验 |
| REMOTE | [接入快照](evidence/c12a/start-remote.json)、[原始日志摘录](evidence/c12a/open-pr-ci-summary.txt) | 真实PR、批准和讨论状态，不能代替教师/课堂或两名课程复核 |

## 本轮新增联调输入、预期与实际

所有B12步骤在两个全新浏览器上下文、临时迁移库、本机真实Vite/Flask socket执行；结束关闭自建服务/浏览器，数据库和会话秘密不入Git。脚本调用既有runner的`running(False)`，**不灌知识表**；章节与两个知识点均经真实HTTP创建。初始账号仍是受控合成数据，不能称课堂账号。

| 步骤 | 输入/预期 | 实际/结果 |
|---|---|---|
| Q1 | 005真实已发布知识标签；教师在题库页保存单选/多选/判断/数值/简答 | 五次实际201，5题保存并可见；通过 |
| Q2 | 公开判断v1后在页面保存私有v2并改变答案；原v1不可覆盖 | 实际PATCH200/v2，旧固定版本继续存在；通过 |
| Q3 | 学生固定v1错答，同键重放，再从错题页正确重练/再次错答 | 两次201字节一致只算一次；wrong_count1→resolved→2，仍按v1判分；通过 |
| Q4 | 收藏/完成1个点；共2发布点，3次实际客观作答1正确、1个零样本点 | 实际总体3、1/3；进度1/2，零样本null；页面33.33%/50.00%；通过 |
| Q5 | 下架已完成点，再发布；旧快照只读 | 新进度0/1=0、items仅剩零样本点；总体历史作答仍3/1（APIC明文要求）；旧ID字节结构不变，再发布恢复；通过 |
| Q6 | 真实撤课程成员后读旧ID/知识/错题，重新加入并重登；他人快照/学生CSV | 404且旧页面内容清除；重登后收藏/完成/2次错题历史保留；非创建教师404/学生导出403；通过 |
| Q7 | 明确SQLite保存故障触发器，不替换业务响应；页面新查询失败后显式重试 | 真实HTTP503、旧统计不再显示；移除夹具后显式查询恢复33.33%；通过（故障为夹具，不称自然生产故障） |
| Q8 | 一致性backup到隔离副本，完整性/FK/runner重放，再HTTP读原ID/错题 | integrity_check=ok、foreign_key_check=[]，同会话/原统计不变、wrong_count2；通过；不称生产资源恢复 |
| Q9 | 当前base真实resources/preparations/experiments/recommendations与health；两页390px | 四GET404；app route map无QA/资源/备课/实验；health503、grader_ready=false。照片目视无文档横向溢出；依赖阻断如实保留 |

没有重跑008→010B专用联测或013专题套件；这些链路的成功/失败、固定版本/保密、批阅revision、截止原键、名单分母、原ID/CSV证据已在原用例和PR固定附件中登记。新的7项handler仅补本轮关注的真实005/006输入、权限和R38一致性。

## 缺陷、失败与必要修复

| 编号 | 判定与范围 | 处理 |
|---|---|---|
| C12a-UI-01 | 010B快照截止/生成/筛选/周区间直接显示UTC，违背PRD§8上海展示；实际截图复现 | 已在010B feature修复，显式Intl Asia/Shanghai、跨日h23；不改UTC存储/API/CSV或快照。组件8项、前端70项及干净B12通过 |
| C12a-UI-02 | 006/008共用paper-view窗口及attempt-view提交/截止仍直接显示UTC；静态代码核对，有Z可辨认，不改变服务器受理/保护 | **NF-UI失败，非业务阻断**；登记C12b，按006/008所属feature修复和受影响页面复验，不将其他SPEC显示改动混入本010B续包 |
| C12a-UI-03 | 012独立feature推荐依据截止仍直接显示UTC | **NF-UI失败，非业务阻断**；留012 feature C12b处理，不因#15算法/UI业务通过抹去此缺口 |

本轮未发现本人权限、判分、保密、幂等或持久化业务阻断。3个失败矩阵行对应UI-02的006/008及UI-03的012，不误报成三个独立根因。没有以N/A消除未验范围。

验证过程失败留痕：首次脚本题型下拉定位超时；第二轮练习控件定位按实际radio修正；第三轮错误预期“下架删除历史样本”按现行APIC纠正，未改业务；第四轮DELETE204被旧helper当JSON解析，改本脚本helper；其后一次Edge本机socket ENOBUFS（并行handler期间）保留失败，不算通过。caf7d73干净重跑通过后发现UI-01，修复为79a133c；诊断改为脱敏异常后ruff报告宽泛捕获，2fa4a2b收窄异常并加入时区断言，重新ruff和干净双浏览器通过。正式JSON仅记录最终轮，早期调试不替代正式证据；诊断不输出密码、Cookie或CSRF。

## I-01 / I-02 / I-03本人接缝及外部依赖

| 链/缺口 | 当前本人证据 | 具体阻塞与恢复条件 |
|---|---|---|
| I-01 | 001→005、本人收藏/进度/发布与同课权限有E005/H12/B12 | 罗浩铭009/017/010C真实实验版本、接线保存/成功与失败事实未接入当前应用；experiments404。等待这些能力通过develop集成后仅验005知识引用/权限，不代写实验/统计 |
| I-02 | 012真实客观错题与进度推荐独立证据E012；不把评测成绩改作推荐客观题样本 | 石佰合018真实上传/队列/执行/报告/010D、罗浩铭009版本链缺失；health grader_ready=false；012自身也未合入。需原负责人契约和真实同课成绩/关联知识后再验本人入口，不接管worker |
| I-03 | E008→006错题→EQB/010B掌握度已验证；QA故障隔离仅E011独立feature | 罗浩铭004备课与007演示缺失，preparations404；011 #14未合入。姜苏豪014虽有独立模块，不因当前事实查询成功就声称其完整链已过；等待真实同课事件/名单/版本/权限链 |
| R01/005图文 | 本人知识白名单、题目身份保护已实现；B12当前资源路由404 | 石佰合003授权图片、题库源文件旧版权限及原子导入；罗浩铭004旁路。现行APIC知识禁img/链接/属性，DBD无知识资源引用；需真实契约与规定非作者复核，不放开任意URL |
| R37 | 原quiz ID/名单/窗口/讲评接口及保护有E008/EQB | 004真实同课关联、跨课/重复/非quiz拒绝、复制不自动发布、开始前元数据/非参与人/讲评旁路均阻断 |
| 共通/NF | 当前本人安全、受控恢复、双浏览器与版本化证据 | R22/R45全组检查点/工时/技术风险由019组织；R47真实完整复核；4核8GB Linux/50会话/worker与p95；生产同点恢复/90天保留；Gitea固定SHA与课堂检查。均未以自动测试关闭 |

I-01/02/03完整链结果均为**阻断**，不是不适用。I-04、生产部署/恢复/Gitea归档/课堂演示本轮未执行，用户未授权AI合并、部署、发布或发送协作消息。

## 正式复验与下一恢复

代码分段提交caf7d730b0d904716f083a014978da4795a0b494（新增接缝脚本）、79a133c（010B时区展示）、2fa4a2b04533bb8023d0e4a7f35de909c38a1e75（脱敏诊断lint及显示断言）均推送原010B feature。后续正式证据/矩阵文档单独提交，创建新的feature→develop续包PR；#10/#12保留实际已合入状态，不重开旧PR。

本地7项真实handler通过8.950秒、前端70项、ruff/backend/tests/本脚本、lint/build、六文档链接/diff通过。B12干净源码SHA固定为2fa4a2b；正式附件提交不伪称该附件已经在自身SHA下执行。新PR的base/head、CI测试ref（tested）、实际merge各自登记；文档收口后的最新head CI必须再次查询。最终head检查与真实reviews/threads/comments落在续包PR说明及个人本地交接，不能把#14/#15或旧#12 CI当作本续包结果。

复现：根目录`.venv/Scripts/python.exe -m scripts.verify_c12a_seams --output logs/c12a-recheck`；需要当前已安装Chrome/Edge/浏览器可选依赖及空闲5000/5173。前端在frontend运行`npm test`、`npm run lint`、`npm run build`；前端时间测试为组件替身，B12为真实HTTP/UI。

下一轮先fetch/查本续包及#14/#15当前head/base/CI/review：真实评审阻断回所属feature修；若由负责人合入，仅消费最新develop并核对实际merge。C12b优先UI-02/03，各回所属SPEC，不重做C10/C11/C09/C07；依赖就绪后再补R01/R37/I链。C12c材料另开，不开发014/016、不接管队友或CI。

回退保留知识/题目版本/作答/错题/进度/analysis_run/schema一致性备份与增量；本轮无迁移，显示修复不改保存事实。恢复仅使用匹配代码/库，不删历史、不改旧SQL、不开保密旁路。受控SQLite副本不是完整生产恢复。两份个人AI记录继续info/exclude，正式证据全部版本化。
