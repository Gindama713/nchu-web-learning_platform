# SPEC-013 智能组卷实施记录

> 2026-10-19当前收口：#27—#35及#38修复已合入develop；原004/007/017接口缺陷复验通过，仍缺页面/全组环境另列。131行现为本地81通过/50阻断、集成81通过/50阻断，见[合入后复验与剩余工作](SPEC-010B_POSTMERGE_ACCEPTANCE.md)。以下旧日期、SHA、计数和“待合入/失败”均为当时记录，不覆盖本条当前结论；完整SPEC及课堂未关闭。

> 2026-10-16 C12c材料导航：当前合入、真实评审、两个矩阵版本及交付状态见[个人交付索引](C12C_DELIVERY_HUANG_JUNCHENG.md)和[本轮远程快照](evidence/c12c/entry-state.json)。下文各节保留原日期、SHA及当时事实；旧“未合入/待实现/最新”措辞按其历史范围阅读，不覆盖索引中的当前状态。完整SPEC仍未凭材料整理关闭。

## 2026-10-15 PR #13 当前集成评审

PR #12 已以 `cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb` 合入 develop。本 C09 续包吸收该基线，保留其专用测验联测和统计页面加载修复；下方关于“#12 未合入”的段落是当时记录。合并树受影响后端30项、前端69项、lint/build/文档检查通过，干净`641d6aeb2cb116478de0b0c5599de7606272b9b3`的[Chrome/Edge证据](evidence/spec-013/c09-browsers/REPORT.md)各5组通过。C09 的教师生成、草稿保存和快照重放已在本分支实现，但 003/004 接缝、目标环境性能、完整生产恢复及课堂验收仍待完成；完整回归与 CI 以 PR #13 最终 SHA 核验。

最新C09状态见文末“当前交接与下一恢复”；此前C08记录保留原SHA、范围和当时事实。

## C08历史：2026-10-15 与已合入模块的集成评审

组长审查后，PR #9 的008与PR #10 的010B已分别合入develop（merge commits `b4a376b860e891a969c9507d69b4cefba5c7f290`、`7759d650e9b0a9b6c2a8070471f1040af603a22f`）。本013分支合并最新develop；README一处文本冲突按8.5统计、8.6组卷顺序保留两边内容，并修正DBD中“013快照表仍待接入”的过时描述。新增真实专用quiz发布、提交客观正确答案后，C08冻结候选历史得到该固定版本c/n=1/1的回归。原C08测试和浏览器/CI证据仅对应旧SHA，合并后的完整回归及CI以PR #11最新提交核验。

C08仍只交付内部算法和不可变快照，尚无generated-papers教师HTTP入口、草稿paper/item持久事务、replay_of权限或页面；这些属于C09。003/004接缝、目标环境性能、完整恢复和课堂验收仍未完成。下文“#9/#10未合入”是当时记录。

负责人：黄俊诚（24201716）。本轮执行 C08，API、草稿 paper/item 同事务保存、replay_of 权限和教师页面留在 C09；不自动发布。

## C08a 候选与历史输入

从核验的 origin/develop `253a736a79a6b6778e8bde0e58673d1f4c7641d7` 创建 `feature/spec-013-paper-generation`。2026-10-14 fetch 与 GitHub 元数据核验：008 [PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9) open、非 draft、未合入，head `fafc69aecf723d06181e807bc1124aed2bd915de`；010B [PR #10](https://github.com/Gindama713/nchu-web-learning_platform/pull/10) open/draft、未合入，head `a750f8024f2f58fa72097bff521bdf1a75fe75d7`。保留 008→010B 专用联测阻塞，未复制两个 feature。

`backend/models/generation_input.py` 在独立 SQLite 读事务内冻结本课未归档 question 最新 version、标签、全部候选、参数、截止及 seed，读取完释放事务。候选身份先按 version_id 升序分配 NumPy PCG64 原始随机键，再按实际正确率（整数比值精确比较）、无样本排后、已保存键、version_id 排序。负 seed 映射为无符号 64 位，仅用于首次生成键；原 signed 64 位 seed 保存。键保存为 16 位十六进制字符串，避免 JSON/浏览器整数精度损失。重放加载保存键，不运行 RNG；算法版本 `paper-backtrack-v1`。

历史按固定 question_version 统计本课真实 paper answer 与 practice_attempt；只计截止前 answered=1 的已评分客观事实，partial 答卷中的已评分客观题有效，漏答/简答排除。正确为原配分满分或 practice.correct=1，样本为事实数量；无样本 rate=null，简答 n=0/rate=null。不把旧版本历史迁到新版本，不读取 wrong_question 投影作为事实。history_until 不晚于 source_until。

保密冻结排除 ever_public=1、任一版本 practice_available=1 或 published paper 已到 start_at 的全部题目身份；新私有版本不能恢复资格。发布时的当前占用/公开资格复核仍沿用 006，并由 C09 接入，候选快照不能替代发布检查。

C08a 本地验证：`.venv/Scripts/python.exe -m unittest tests.test_generation_input -v`，5 项通过（16.210 秒）；受影响 ruff 与 git diff --check 通过。使用真实 001/005/006 HTTP 创建题目、知识、发布及作答；归档状态和 501 候选属于明确 SQL 边界夹具，不能冒充教师 HTTP 归档验收。测试初轮遗漏真实幂等键、误用不存在的归档接口，已改为带 UUID 的真实作答与明确归档夹具并重跑通过。

## C08b 求解、整数配分与持久快照

求解使用冻结顺序、先选后跳过的确定性回溯；按question身份去重，按剩余难度配额的独立身份数量及剩余可选知识覆盖剪枝。每节点进入时计数，包含根、剪枝及终点，最多100000次；穷尽树返回422 INFEASIBLE_CONSTRAINTS，还需要第100001次访问返回503 SEARCH_LIMIT。不使用运行耗时作预算，不返回partial选题。求解在数据库写事务外执行。

总分先严格换算整数百分之一分，按选中顺序divmod均分，余数给前若干题；每题至少1，总和与输入精确一致。生成的Solution含有序版本、整数配分、覆盖及实际节点数。保存前再次检查数量/独立question/配额/覆盖/顺序/配分，不能保存部分或不合规结果。

`013_generation_snapshot.sql`由原公共runner接入：不可变表存全候选、历史、参数、seed、算法版本、source_until、SHA-256与selected_ids；同课程版本及选中候选插入触发器防错误引用。旧SQL不变，引用版本沿用006全局保留。内部save要求调用方已有事务，不自行commit；load校验输入哈希与并行历史，replay仅从保存输入复算，并对照原selected_ids。paper新列/外键、API权限与draft事务由C09追加，C08不会建草稿或发布。

C08b专题验证：`python -m unittest tests.test_generation_solver tests.test_generation_snapshot -v`，13项通过（6.548秒）；全仓ruff通过。包含200组独立穷举对照、实际100000节点、500候选/100选题、同题两版、无样本排序、精确余数、WAL真实第二请求在读取期间新增版本/作答、存储回滚/不可变/版本同课程触发器、带数据备份副本完整性/外键与原快照复算。预算用例初轮22候选在88639节点已证明无解（422正确）；改为33候选后确实耗尽100000节点并验证503，未放宽算法或改写断言掩盖结果。

## 验收证据与未完成项

| 编号 | C08证据与结果 | 剩余范围 |
|---|---|---|
| AC-01 | solver正常约束/多标签/配额/精确总分，通过 | C09真实教师操作与draft/item |
| AC-02 | 同question两版不重复；freeze最新版本，通过 | C09生成卷固定版本外键 |
| AC-03 | 配额/覆盖/题量不可行422，预算503区分，通过 | HTTP错误状态/教师失败页 |
| AC-04 | 保存输入/排序键/seed复算，RNG被禁仍一致，通过 | replay_of HTTP权限与持久卷 |
| AC-05 / R14 | 新题/版本/真实作答后保存快照及备份副本选题配分一致，200组穷举/实际预算，通过 | 教师新增题后端到端replay_of |
| R25 | 公开身份所有版本排除候选，通过 | C09当前资格复核与006/008发布联合 |
| R22/R45/R46/R47 | 版本保留、存储回滚/备份组件证据，通过；完整共通验收待执行 | 完整权限/生产恢复/性能/真实评审与课堂证据 |

用例由AI于2026-10-14—15在本地受控数据库执行，预期与实际断言一致；所有用户/数据为合成，无真实学生资料。算法夹具不能冒充HTTP、目标Linux4核8GB/50会话、worker、课堂或非作者评审。前端未改，本轮不要求C08浏览器截图。正式运行/用户说明见README§8.6；生产迁移未执行。

2026-10-15全量回归：`.venv/Scripts/python.exe -m unittest discover -s tests -v`，后端125项通过（190.409秒，C08新增18）；`npm test`前端46项通过，`npm run lint`/`npm run build`通过；全仓`ruff check backend tests`、六文档链接和`git diff --check`通过。序列化重算补强禁用secrets seed RNG后单项另通过（0.008秒）。本013分支来自develop，未包含010B/008 feature，故125/46不能与010B分支131/54当作同一套代码的数量比较。

回退：先保存题目版本、作答、审计与全部generation_snapshot的一致性备份/增量，恢复配套代码和数据库恢复点；不DROP快照/历史表，不修改已应用迁移。旧代码不认识新快照时明确不可用，不重算冒充原结果。

## C08历史交接与恢复记录

C08a `16c1928`、C08b `30d2948130e1fbc42dbc8e6ddc8327ede355a356`已推送本feature，并创建open/draft [PR #11](https://github.com/Gindama713/nchu-web-learning_platform/pull/11)。初次基线253a736时#9未合入；随后#9由外部以b4a376b合入，#10亦由外部以`7759d650e9b0a9b6c2a8070471f1040af603a22f`合入develop。本轮按用户优先级返回010B原feature补专用HTTP及干净Chrome/Edge各6组联测，新测试/证据在独立draft [PR #12](https://github.com/Gindama713/nchu-web-learning_platform/pull/12)，解除专用008链阻塞，不带入本013。

本013分支已merge最新成功fetch的origin/develop 7759d65，产生`6a0094e`，README唯一冲突保留010B§8.5及013§8.6、APIC/DBD/PRD/CHG-RB自动合并保留双方契约；同步提交已推送。现有008/010B来自已合入develop，不复制其未合入feature；C08源码与旧SQL均未因同步改写。网络曾短暂TLS失败，恢复后推送成功；此项不再是阻塞。PR #11/#12 reviews=[]，当前head CI分别核验，不沿用旧feature CI。

同步develop后全量本地回归165项通过（245.257秒），前端62项、ruff/lint/build/六文档链接/diff通过。`6a0094e22d7eac9a54be2d4f04de2c78a8ff273e`的[Actions38596794698](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38596794698)实际jobs均已完成：policy/lint/test/build/required全success，grader按develop规则skipped。已读取ci-test日志：后端165项（84.502秒）、前端62项，tested merge=`351e40a1d80205a40eda072827232834020746f0`，base=7759d65、head=6a0094e；此merge只是CI测试引用，不是实际合并。本文后续纯文档提交的当前head检查仍需单独核验，以PR当前检查及个人交接为准，不将本run偷换成之后head。

SPEC-013完整验收未关闭，无generated-papers API、教师页面或C09真实HTTP重放链。下一恢复先fetch核验develop与PR #11/#12及当前head CI，再继续C09本013分支；若目标更新则merge最新develop。追加paper.seed/algorithm_version/generation_snapshot_id FK及发布冻结治理；首次/replay_of二选一，冻结→无写锁求解→重新授权/资格核验→短事务保存snapshot+draft paper/item+审计。重放只接新title，读取旧快照，不读新题库；发布仍用006/008现行保护，不自动发布，不接管队友模块。003/004、Linux4核8GB/50会话/真实worker、完整生产恢复/课堂/实际评审仍待补。本轮未自行合并、部署或发布。

## 当前交接与下一恢复（C09，2026-10-15）

本轮按C09任务卡继续原`feature/spec-013-paper-generation`。fetch核验develop=`bcda8c468e9054579639f3f66c709a54283494aa`；#11已合并，原head=`d7a0e78`，#12仍open/draft、head=`b3f494e89f0428574c8bfa31d8366e1e47a2ff57`、reviews=[]。本地先同步远端013原分支，再merge origin/develop（fast-forward到bcda8c4），保留C08及外部专用quiz历史回归；没有复制#12增量或重复010B联测。#11不更新，创建新的013续包PR至develop；不自行合并、部署或发布。

C09a提交`3925d50320ae6fc8c78e60b0a29d40e7bbe8d228`已推送：generated-papers教师POST入口严格区分首次参数与仅title/replay_of；复用C08冻结及求解，求解不持写事务。取得短写锁后再次检查会话、有效课程教师成员、全部候选版本同课及所选题当前归档/公开/保密占用资格，保存generation_snapshot、draft paper、paper_item和paper.generate审计，任何一步失败全部回滚。seed/algorithm_version早已存在于006b，新增013b只追加generation_snapshot_id FK/索引与来源冻结触发器，不改已应用迁移。重放从原快照复算并核对原selected_ids，每次新建同输入哈希快照及独立草稿，原卷不变；当前资格检查仅查询所选身份和引用，不提取新候选/作答，不替换选题。

C09b提交`e3d92e8`已推送：教师“课程试卷/随堂测→智能组卷”参数、固定版本/配分结果、失败修正提示和原快照重放入口。重放隐藏全部约束，只接受新标题；浏览器以已校验十进制无损发送64位JSON seed，响应seed_text供精确展示。结果仅为draft，查看后仍由教师进入006普通发布或008专用发布；未自动发布。失败移除旧结果、保留参数；身份变化/卸载丢弃迟到响应，权限失败阻断旧表单。网络丢响应不宣称服务端未保存，提示先刷新列表核对。

### C09验收映射与验证性质

| 编号 | 本轮证据 | 状态与限制 |
|---|---|---|
| AC-01/AC-02 | tests/test_generated_papers.py真实001/005/006/013 HTTP：固定版本、334/334/333精确总分、仅draft无名单；C08去重及穷举保留 | 本地通过；不扩大为课堂验收 |
| AC-03/R14 | 真实空题库422、33候选/11标签100000节点HTTP 503 SEARCH_LIMIT，无快照/卷/条目/审计残留；规模题目为明确SQL夹具，知识通过真实API | 本地通过；不是目标环境性能证据 |
| AC-04/AC-05/R14 | 首次后新增题、版本及真实practice作答；禁止freeze/RNG仍HTTP重放相同有序版本/精确配分；备份副本完整性/FK及真实HTTP重放 | 本地通过；原输入哈希相同，原卷不变 |
| R25 | 冻结后公开竞态拒绝；保密重放遇公开历史409；普通发布再次拒绝公开题、quiz专用发布/名单/null讲评/全身份占用继续保护 | 本地通过；沿用006/008，不接管003/004 |
| 权限/事务 | 学生/无关人/管理员/跨课/无快照/非法组合/CSRF拒绝；计算期间真实第二连接撤成员/会话，保存前拒绝；paper/item/audit三个位置触发器故障均整体回滚 | 本地通过；撤教师成员为明确SQL状态夹具，负责教师DELETE本身正确返回409 |
| R22/R45/R46/R47及NF | 分工/依赖与两段提交可追溯；C08十九项与专用quiz历史保留 | 真实C09非作者评审、课堂、Linux4核8GB/50会话/worker、完整生产恢复仍待执行，不关闭完整SPEC |

专题命令：`.venv/Scripts/python.exe -m unittest tests.test_generated_papers tests.test_generation_input tests.test_generation_snapshot tests.test_generation_solver -v`，29项通过46.366秒（C09新增10项、C08原19项）；全仓ruff通过。首轮测试的负责人DELETE预期及知识SQL缺必填字段已纠正：成员撤权标明SQL夹具、知识通过真实API创建，重跑通过，没有放宽业务保护。前端`npm test`68项通过，lint/build通过，六文档链接/diff通过。全量本地后端176项通过293.361秒、前端68项通过；日志见docs/evidence/spec-013/。后端源码对应3925d50、前端对应e3d92e8，后续仅浏览器脚本/文档/证据变化，不将旧010B分支167项当作本013树。

真实浏览器预跑：Chrome155.0.8059.41与Edge155.0.4283.45各5组通过、page_errors=[]；覆盖首次精确seed/配分、新题/版本/作答后重放、390px无横向溢出、真实422保留参数/清旧结果、组卷quiz接原专用显式发布。运行时存在未提交UI/脚本，因此该轮只作为预跑，不当作干净SHA正式证据。首轮Chrome完成后出现Windows临时目录清理PermissionError；补充保留原始异常诊断及UTC时区后重跑两浏览器通过。正式证据将对提交后干净树重跑并记录tested_head/dirty_paths，不复用010B截图。浏览器仅初始管理员/教师账号SQL引导，其余课程/知识/题目/作答/生成/发布全部真实HTTP，无伪造API响应；是合成本地数据，不是课堂或生产数据。

下一恢复：先读本节与个人会话计划第6节，fetch核验develop、010B #12和新的013续包PR当前head/CI/真实评审。C09实现已落地，不重做C08/C07/010B联测；本轮干净浏览器和全量本地回归已完成，下一步优先核验续包PR当前head CI/真实评审，按实际评审修正；无新缺陷时按后续任务卡推进C10，不重复实现C09。若develop变化仅按同分支merge同步并复验受影响点，不复制未合入feature。队友003资源/004备课、图文/授权图片、目标性能、worker、完整生产恢复及实际两名非作者复核/课堂证据仍独立记录，不代写。

回退：先备份当前题目版本、作答、paper/item、generation_snapshot及审计一致状态/增量，再使用匹配代码和数据库恢复点。013b是追加迁移，不能改旧checksum、DROP历史或清空快照外键来“回滚”；本轮临时库迁移/备份验证不能替代生产恢复演练。

### C09正式收口证据

干净`fd89dab00baedaf0d743c8cfe51f03a86f1e4444`两浏览器正式重跑通过：Chrome155.0.8059.41、Edge155.0.4283.45各5组，dirty_paths=[]、page_errors=[]，390px截图已目视核对；报告/原始JSON/6张截图在[正式浏览器证据](evidence/spec-013/c09-browsers/REPORT.md)。早期干净3b25284轮Edge并未通过：原始诊断为启动阶段等待/列表选择失败，随后Windows临时库清理还可能PermissionError遮盖原错。fd89dab仅修正测试登录先等待初始session响应、明确使用试卷“重新加载”恢复并等待目标模块；未改共享鉴权/队友业务、不伪造响应，最终通过轮单独登记，不能把失败轮改写为通过。

新续包[PR #13](https://github.com/Gindama713/nchu-web-learning_platform/pull/13) open/draft→develop。3b25284的[Actions38677497071](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38677497071)已核验policy/lint/test/build/required全success，grader按develop规则skipped；读取真实ci-test日志为176项147.207秒、前端68项，tested merge=`1dce877f7c82183c8e024fb63edda3d5d02f8ab4`、base=`bcda8c468e9054579639f3f66c709a54283494aa`/head=`3b252840d506cf721d95d502ee5ae8c099c570a5`。这是CI测试引用，不是实际merge；脚本/证据后续head CI须另核验。

本轮后续fetch观察#12由外部更新为head=`ab91dc1b666c1382d170fba189d1dc3e7654bf26`、open/非draft、reviews=[]，仍未合入；保留此评审状态且不复制增量。develop仍bcda8c4，C09源码/十九项C08与专用quiz历史均保留。C09实际非作者批准尚无，敏感API/数据库仍需课程规定的真实复核；003/004、目标性能/worker、完整生产恢复及课堂证据仍未关闭。

### 最后核验与评审恢复点

`fd89dab00baedaf0d743c8cfe51f03a86f1e4444`的[Actions38677844614](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38677844614)已核验policy/lint/test/build/required全success、grader按develop规则skipped。真实ci-test日志176项131.484秒/前端68，tested merge=`5adaae934bdb918dc2d0f99f1542adb532929aad`、base=`bcda8c468e9054579639f3f66c709a54283494aa`/head=fd89dab；不是实际merge。正式证据提交`cdec71e8a9995a8b93ec965ae1a9bfb5951814ff`和本段最终文档不改业务源码；它们的检查不能冒充fd89dab运行，按PR #13当前head状态及个人交接另核验。

C09实现、本地全量及干净双浏览器已就绪，交付新PR #13真实非作者评审；本段提交后仅更新PR评审状态/说明和本地两份交接，不再追加业务改动。下一恢复先查#13当前head的CI（缺失/运行中不能记成功）及实际review；需要两名真实非作者复核的API/数据库改动仍未满足，不能自行合并。课堂与全模块依赖仍按上表保留，未授权或执行教学环境部署/发布。两份个人文件为本地排除，不随PR提交，恢复时优先计划第6节/个人10.1，再读本节。

### 收口期间外部develop更新

最后fetch发现#12已由外部于2026-10-15 11:45:05（Asia/Shanghai）合入develop，merge=`cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb`，最后head ab91dc1。本013随后merge origin/develop，唯一冲突在本文末；保留对方C08/010B真实历史及本方全部C09记录，README/CHG-RB自动合并。纳入已合入的010B测试/证据及analytics-view在课程加载前禁用筛选的修复，不复制未合入feature、不接管其业务，也不重做专用联测。此前“#12未合入”均为当时核验事实。新同步树的完整后端/前端、C09浏览器及当前PR CI须分别登记；旧176/68和fd89dab截图保留原SHA，不能冒充新同步树。

### 同步后最终验证与下一步（当前结论）

同步提交`d14054d4edc56dcd6635a9e3de6fc042f3e10ca6`已推送：全量本地后端177项通过288.776秒，前端69项、全仓ruff/lint/build/六文档链接/diff通过，原始日志在docs/evidence/spec-013/c09-synced-*.txt。比原176/68多出的用例来自外部已合入#12；旧统计保留原SHA，不改写为本次次数。这里的全量自动回归包含已合入的专用quiz历史及统计测试，未重新开发或另起010B手工/浏览器联测。

干净d14054d（dirty_paths=[]）C09 Chrome155.0.8059.41、Edge155.0.4283.45各5组通过，page_errors=[]，六图/JSON及390px验证见[同步后C09证据](evidence/spec-013/c09-browsers-synced/REPORT.md)。原fd89dab报告及全部C08/010B历史保留。

同步代码的[Actions38678429264](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38678429264)已核验policy/lint/test/build/required全success、grader按develop规则skipped；真实ci-test日志177项129.855秒/前端69，tested merge=`91a376436b4634176cbcb72c45eede2b6bc84731`、base=`cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb`、head=d14054d。这是CI测试引用，不是013实际合并；随后仅提交本段和证据，最终文档head的CI按PR当前状态及两份个人交接核验，不把旧run冒充新head。

新[PR #13](https://github.com/Gindama713/nchu-web-learning_platform/pull/13)已open/非draft，C09实现和本地证据就绪待真实评审，目前reviews=[]；#12已由组长外部合并，#11亦早已合并。本轮没有合入共享分支、部署或发布到教学环境；临时合成库中的显式发布仅为006/008验收。下一恢复先查#13当前CI/head/base及实际review，必要时只修评审缺陷；不要重复C08/C07/C09或010B专用联测。无缺陷后按另行任务卡进入C10。003/004、图文/授权图片、目标Linux4核8GB/50会话/worker、完整生产恢复、两名真实非作者复核及课堂证据仍未完成，完整013未关闭。
