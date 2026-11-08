# I-03有限包：007入口核对及008→006错题→010B掌握度→011检索

黄俊诚（24201716），2026-10-17，Asia/Shanghai。只完成本次两个相邻工作包的可执行范围；没有关闭全部I-03、UC-02、完整SPEC或课堂验收。未发现需修复本人006/008/010B/011业务的缺陷；仅新增联测、证据及原矩阵增量，未修改业务源码、迁移、APIC/DBD或CI。

## 基线、已合入事实及复用

初始工作区干净，位于PR30分支/head dbd32e65db1d6d371adcfe4b06889a24e7490e24。fetch后origin/develop仍为`dfb23271b470a93d557a2695fed0e04caf59d0d2`。#18/#19/#20/#21/#22/#23/#24/#26实际merge逐个通过develop祖先检查；007来自已合入#21，不能再称007后端未开发。另实读#9/#14/#16/#17的merged及actual merge并逐个核验develop祖先。见[接入事实](evidence/spec-010b/i03/entry-state.json)、[本人依赖祖先](evidence/spec-010b/i03/own-merge-ancestry.json)。

#27/#28/#29/#30均open、非draft、未实际合入；head分别7096b496/8111c539/b56141f2/dbd32e65，真实comments/reviews/review_threads均[]。按用户指令复用固定Actions38896062651/38904433916/38907219999/38909993594，没有重跑四个CI或将merge_commit_sha测试引用当actual merge。检查无同名分支后，从上述develop新建`feature/spec-010b-i03-subchain`，不改写四PR，不复制未合入实现/材料。

依据：[PRD§11.2 I-03及§3.1 UC-02](PRD.md)、[006](PRD.md#accept-spec-006)、[007](PRD.md#accept-spec-007)、[008](PRD.md#accept-spec-008)、[010B](PRD.md#accept-spec-010b)、[011](PRD.md#accept-spec-011)，APIC§4/4.3/4.4/5.1/5.2及DBD§4/5；以下证据只覆盖所列子集。

已核对并复用：`tests/test_demo.py`已有六种预设、同课读取/学生禁推进、revision冲突、关闭及简单CPU步骤；`tests/test_quiz_analytics_integration.py`和[010B专用quiz记录](SPEC-010B_IMPLEMENTATION.md)已有真实专用发布、待批/漏答/缺交、分母差异、旧ID/CSV；[011记录](SPEC-011_IMPLEMENTATION.md)固定干净36854081b1ba991a89bacbf7d797ab0620619ae3已有算法、全输入边界、索引失败/并发及故障隔离。原006五题型、幂等、并发、008逐题统计及R01/R37整包均不重做。R01继续引用[PR30](https://github.com/Gindama713/nchu-web-learning_platform/pull/30)固定head；R37继续引用[PR29固定版本](https://github.com/Gindama713/nchu-web-learning_platform/blob/b56141f2e060d1ec5464d58d52f6f735c445d56c/docs/SPEC-008_R37_INTEGRATION.md)，未将两PR文件复制到本分支。

## A：007实际能力和界面边界

已合入`backend/apis/demo.py`有真实创建、按课分页/active筛选、详情、step/reset/pause/run及close接口，六预设定义存在。新增受测范围为真实CPU会话：同课列表仅含本课对象、教师推进一次后学生重复读到同一实际状态、旧revision写409；学生创建/推进/关闭403，跨课列表/详情及非成员详情404，真实撤销学生成员后列表/详情404。SQLite保留原会话、推进审计及外键事实。

APIC定义的跨模块字段只有可选`experiment_version_id`，需同课已发布且模式符合契约；没有demo的knowledge_id、quiz_id或备课关联字段。本包没有调用实验关联或重跑六场景/R06/R07核心语义整套，不能从简单CPU步骤推出其符合完整CPU基线。

当前`frontend/js/main.js`未导入或挂载demo组件。双浏览器记录教师/学生实际heading清单，能调用真实demo列表/详情，但页面无课堂演示入口；不能执行“从007页面进入本人知识/随堂测”。没有定义的demo→知识/quiz关联不新增。现有知识、随堂测、错题和问答面板各自可用，不冒充007页面链。

| 本包问题号（不是新增验收编号） | 有效验收/最小复现及实际 | 负责人/结论 |
|---|---|---|
| I03-007-01 | SPEC-007/R02、AC-01/03页面部分：登录同课教师或学生，主页面heading没有课堂演示；main.js无demo挂载，后端列表200有真实会话。无法从演示页面选择/刷新及跳转 | 罗浩铭；界面阻断，绝不登记007浏览器通过 |
| I03-007-02 | SPEC-007/AC-03及APIC§4详情应返回当前revision：创建CPU会话201/revision0，教师step200/revision1，学生GET `/demo-sessions/{id}?after_revision=99`实际200/revision99，数据库仍revision1、state仍第1步 | 罗浩铭；真实契约失败。`get_session`尾部将revision替换为after_revision，单独expectedFailure保留，不算通过 |

最小复现的逐请求响应、预期/实际及数据库见[007权限](evidence/spec-010b/i03/handlers/test_demo_actual_entry_permissions_and_current_revision_observation.json)、[007失败](evidence/spec-010b/i03/handlers/test_contract_future_cursor_must_return_actual_revision.json)。未接管007或发送协作消息；只有负责人真实修复并actual merge祖先核验后才补受影响项。

## B：同一批真实答卷到错题、掌握度及检索

经真实001创建课程/成员，005创建章节、两个已发布知识点K1程序计数器/K2算术逻辑单元及一个草稿，006创建4题各10分、原版本标签分别[K1,K2]/[K1]/[K2]/[K1]，008专用发布保密quiz并冻结4人。发布后将第1题更新为另一版本（答案A→B，标签[K1,K2]→[K1]），原paper_item不变。

| 冻结学生 | 原版本第1/2/3客观题 | 第4简答 | 原始结果 |
|---|---|---|---|
| S1 | 错B / 对A / 漏答 | 实际作答、待批 | partial，score=null；后真实批8分，总18/40 |
| S2 | 对A / 错B / 对A | 漏答 | graded，20/40 |
| S3 | 整份空白提交 | 漏答 | graded，真实0/40 |
| S4 | 缺交 | 缺交 | 没有attempt，不填假0分 |

实际核对：

1. 4条paper_participant、3份attempt、12条answer；5条实际客观作答加1条待批简答。两条wrong_question仅来自S1原第1题/S2原第2题；空白及缺交不入错题。S1错题固定原question/version、双标签、last_attempt_type=paper、原attempt_id、wrong_count=1；knowledge_id筛选仍使用原版本。SQL事实和每个analysis输入sample_id、correct、固定版本标签逐条对应，不把多标签累计成总体7次作答。
2. 截止而未review时，三份原答卷、原卷items及错题响应均无标准answer/explanation。页面错题与答卷只显示原作答/待批；实际教师review后，错题及答卷释放原答案A及原解析，未变成新版B。学生review403，他人答卷404。
3. quiz应交4/提交3/缺交1，客观正确率3/9=1/3，漏答计入逐题提交分母。010B总体实际客观n=5,c=3,mastery=0.6；K1为4/2，K2为3/2；S1个人n=2,c=1，已完成K1/已发布2点=0.5；空白及缺交学生n=0,mastery=null。简答待批、漏答、缺交均不混掌握度。
4. 同一批原始事实的scores快照A为4/3/1、已批2/partial1、mean_percentage=25；真实批8分后新查询为已批3/partial0、31.67。原knowledge/scores的analysis_run_id读取data完全相等，原CSV字节不变；原JSON/输入、筛选、分母、审计均保留。知识K2下架后，新knowledge的items只剩K1、总体历史样本仍5；旧双标签及旧快照仍原值。这里只验证受控快照，不新增备份/生产恢复整包。
5. 从真实错题的原标签读取同课005详情，再用该真实标题请求011；匹配含原knowledge_id，片段来自已发布正文，草稿不被检索。逐条核对qa_query的user/course、matched_ids、原始相似度与响应6位值、index_revision；没有调用生成式模型。现有知识面板手动选择知识，再在现有问答面板查询、点击真实出处正文，未新增或伪造“错题标签一键跳转”。
6. K2真实下架后，005出处404，新qa不含K2且revision更新；浏览器点击已缓存的K2出处实际404，清除旧matches/source。真实001撤权后，原卷/答卷/知识/本人analysis快照404，错题列表空、历史DB仍在；qa404清空并禁用查询。教师班级冻结分母仍4，旧JSON/CSV仍可按教师本人ID读取。

## 正式证据、夹具与复现

干净tested为`4498fd97ff30fb9a1e92146528d960c6975ed48a`，[handler报告](evidence/spec-010b/i03/handlers/report.json)和[浏览器报告](evidence/spec-010b/i03/browsers/report.json)的dirty_paths均[]；后续只补证据/文档，不能声称在附件自身SHA执行。最终head CI独立核验结果只写PR和两份本地排除交接。

- handler：[原日志](evidence/spec-010b/i03/handlers/handlers.txt)，3项8.165秒，**2通过、1项007契约expectedFailure**。原始子链接口/各阶段事实见[完整子链](evidence/spec-010b/i03/handlers/test_fixed_wrong_version_four_students_mastery_snapshot_and_qa_revocation.json)。绿色CI不能消除该失败。
- 真实socket及现有UI：Chrome155.0.8059.41、Edge155.0.4283.45各7组受测检查通过，page_errors=[]。这7组包含007 API探测和明确的缺页登记，不是7组007 UI。逐请求状态及实际脱敏JSON/CSV响应见[Chrome请求](evidence/spec-010b/i03/browsers/chrome-requests.json)、[Edge请求](evidence/spec-010b/i03/browsers/msedge-requests.json)，原始答卷/标签/快照/审计/外键各阶段见[Chrome事实](evidence/spec-010b/i03/browsers/chrome-facts.json)、[Edge事实](evidence/spec-010b/i03/browsers/msedge-facts.json)。
- 夹具独立登记：只bootstrap最初admin/teacher，控制TEST_NOW；handler学生注册、课程/成员及所有成功业务走真实API。浏览器既有running helper的初始学生/课程/成员经真实handler，后续全部业务及页面走真实socket；监听从helper准备结束后开始，初始helper请求没有冒充socket请求。没有直接插业务表、成功mock、故障注入或阈值double；SQL仅账号bootstrap及事实读取。仅有007已知契约失败使用expectedFailure。
- 首轮子链脚本因handler recorder尚未接受Idempotency-Key的headers参数而TypeError，未到提交，见[未完成首轮事实](evidence/spec-010b/i03/preflight/handler-incomplete-before-header-fix.json)、[失败说明](evidence/spec-010b/i03/preflight/failures.json)。修复助手参数后通过；首轮ruff仅导入顺序问题已改。预检、2096d7d阶段报告留在本地logs，与最终4498fd9正式附件分开。

390px共12图已逐张目视：原错题/解析、60%/5个实际样本、出处正文及失败清空符合实际响应；无整页横向溢出，统计宽表在容器内滚动。

| 浏览器 | 未讲评错题 | review后 | 原掌握度快照 | 检索出处 | 下架清空 | 撤权清空 |
|---|---|---|---|---|---|---|
| Chrome | [图](evidence/spec-010b/i03/browsers/chrome-wrong-protected.png) | [图](evidence/spec-010b/i03/browsers/chrome-wrong-reviewed.png) | [图](evidence/spec-010b/i03/browsers/chrome-original-knowledge.png) | [图](evidence/spec-010b/i03/browsers/chrome-qa-source.png) | [图](evidence/spec-010b/i03/browsers/chrome-unpublished-cleared.png) | [图](evidence/spec-010b/i03/browsers/chrome-revoked-cleared.png) |
| Edge | [图](evidence/spec-010b/i03/browsers/msedge-wrong-protected.png) | [图](evidence/spec-010b/i03/browsers/msedge-wrong-reviewed.png) | [图](evidence/spec-010b/i03/browsers/msedge-original-knowledge.png) | [图](evidence/spec-010b/i03/browsers/msedge-qa-source.png) | [图](evidence/spec-010b/i03/browsers/msedge-unpublished-cleared.png) | [图](evidence/spec-010b/i03/browsers/msedge-revoked-cleared.png) |

```text
.venv/Scripts/python.exe -m scripts.verify_i03_handlers --output logs/i03/recheck-handlers
.venv/Scripts/python.exe -m scripts.verify_i03_browsers --output logs/i03/recheck-browsers
```

需要空闲5000/5173、既有浏览器依赖和Chrome/Edge；结束关闭本次服务、浏览器及临时DB。Context7已查询Git、Flask、Playwright、Ruff及GitHub REST具体用法；首次Flask解析网络失败，重试成功，没有更改业务或依赖。

## 原矩阵及继续保留的阻断

仅补[原JSON矩阵](evidence/c12a/acceptance-matrix.json)和[原Markdown矩阵](evidence/c12a/acceptance-matrix.md)实际覆盖的13行。每行保留原整行/Markdown行、head_SHA、本轮tested_SHA、原附件与判定，新增I03历史及tested/附件；其余118行逐字典/Markdown行不变。没有新建第二矩阵或007矩阵行。011 AC-01/03/04的集成登记只改为本次有限本人检索子链通过；本地仍80通过/0失败/51阻断，集成62通过/69阻断。这个“三行”与未合入#27的三个NF-UI不是同一批行，未复制或重判#27。

006/008 R02仍阻断，只更正“007列表未就绪”的旧描述为API已合入实测、007页面缺失及revision缺陷。其余完整链/R44不改判。旧C12a表格是当时快照，不能再用其中历史404断言当前003/004/007接口不存在。

罗浩铭的R37-004-01错误码、R37-004-02缺window_state及004备课UI继续阻断；#29两项expectedFailure仍不是通过，本次没有收到实际修复并合入，故未重复R37或两个C12b脚本。完整R01继续缺004备课页面。005图文、012推荐、013组卷、014预警、完整R47、目标性能环境、生产恢复/90天保留、教师格式及课堂验收均未展开。初始页面自动挂载既有其他面板不构成其新增验收。

必要联测按所属本人010B后续feature分段提交，最终证据不含数据库/上传文件/口令/会话。回退仅撤销本包新联测/脚本/附件及13行增量；不改旧迁移、真实业务历史或既有证据。未直推共享、强推、删分支、代合并、部署/发布、归档或发送协作消息。最终head/PR/独立CI见本包PR和两份本地排除交接。
