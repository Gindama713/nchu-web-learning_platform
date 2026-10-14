# SPEC-006 / C02a—C04 实施与验证记录

## 2026-10-14 集成评审更新（优先于下方历史记录）

组长复核 PR #7 时，SPEC-005 已通过 PR #4 合入 `develop`（merge commit `17fd54e6dd428c1446127a4338ddf6b51a85e656`）；原分支与新基线在入口、文档及测试夹具上有六处文本冲突。本次合并保留两模块入口，并把原先手建 `chapter/knowledge_point` 的题库测试改为经真实教师知识 API 创建标签；缺少标签现在按实际契约返回 400，而知识依赖表不存在才返回 503。原 C02a—C04 历史测试与浏览器证据仍对应各自旧 SHA，不能当作本次合并后的双浏览器验收。合并后的 CI/评审/最终 SHA 以 PR #7 为准。

此集成只解除 005 真实知识 API 接缝的代码阻断。003/004 资源与备课接缝、C05 专用 quiz、目标 Linux/性能/完整恢复及课堂验收仍未完成；SPEC-006 整体不标记通过。下文“005 未合入”“PR 为草稿”等均是当时的历史状态。

责任人：黄俊诚（24201716）。当前记录日期：2026-10-14，Asia/Shanghai。依据：[PRD有效验收](PRD.md#accept-spec-006)、[APIC§4/11](APIC.md)、[DBD§4/7/8/9](DBD.md)。当前状态：C02a—C04独立部分已实施；005知识真实联测、003/004接缝及目标环境仍阻断，C05专用quiz发布/讲评未实施，006未关闭。

## C04当前恢复与证据（优先读取）

继续`feature/spec-006-exercises`，本轮起点HEAD/远端`015d1b2f65ee49fc7ec214880b2bfca256ce121a`，fetch核对origin/develop仍`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`；工作区原本干净。没有复制005代码。代码/最终证据提交、PR及CI按本节末尾真实记录核验，旧C03b证据保持其原tested_head。[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)仍为006→develop草稿，2026-10-14查询reviews=[]，未合并、部署、生产迁移或发布。

下一恢复：C04独立实现与回归已完成，待两名真实非作者复核；先推动005/006按团队门禁合入develop并补真实知识联测。下一业务包C05（SPEC-008）必须从包含006的已核验origin/develop建立`feature/spec-008-quiz`，不从未合入006偷带代码。003源文件永久teacher_only/旧版本下载/原子导入由石佰合资源能力与本人006接缝在C12补，004由罗浩铭接入同一保护服务；当前不接管队友模块。SPEC-014由姜苏豪对接practice_attempt.answered=1筛选（见下方），目标Linux/50会话/worker仍待原负责人/目标环境。005恢复点仍在其原分支，当前006没有005实施记录文件。

### C04行为、迁移与页面

- `006d_practice_wrong.sql`通过公共校验和runner新增真实practice_attempt/wrong_question，不改旧迁移。按原answer回填最近实际客观错误，排除漏答/简答；错题UQ(student_id,question_id)、错误来源触发器和历史保留约束。固定版本、原始作答、整数0/10000分、answered/correct及created_at保留；wrong_count从原answer/practice事实派生，正确重练resolved=true，新错误恢复false，不删除作答或更换最近错误来源为成功来源。
- `POST /questions/{id}/practice-attempts`校验当前同课学生、固定公开客观版本、CSRF/Origin、完整字段和UUID，复用原五题型规范化/客观评分，返回201、固定version_id、correct、0/100及explanation。单题可多次提交；空答保留为answered=false、0分且不计错题。路径/版本不匹配404，私有/简答409 PRACTICE_UNAVAILABLE，语法/类型400，异常已开放的受保护question任何版本409 QUESTION_RESERVED。BEGIN IMMEDIATE内作答、错题、审计、幂等快照同事务；paper原答卷事务消费原answer错误事实，不重做幂等或更改原响应。
- 公共ledger增加practice_attempt作用域参数，保留paper_attempt原默认行为和快照。数值1/1.0、排序多选及未答规范化；同键同内容精确重放原201/JSON字节，异目标/内容409，24小时过期可新受理，不把原重放增计错误。当前身份/成员、版本公开与question全版本保护在重放前复核，旧含解析快照也不能绕过新增保护。
- `GET /users/me/wrong-questions`仅学生本人，分页/knowledge_id严格校验，固定错误来源版本及标签筛选，退出课程隐藏、重新加入/重新登录历史保留。每项含来源、wrong_count/resolved、固定版本题干/选项及can_practice；answer_visible由question保密占用先决检查和来源paper实际review/原名单或practice固定公开资格派生。受保护时false、无answer/explanation、不能重练；不依赖最新版或截止释放。公开题库、paper/attempt详情及列表、题目开放/发布继续使用原同一question身份保护服务。
- `PracticeView/PracticeClient`提供公开练习/错题、固定版本的四客观题作答、分页、已加载知识标签筛选、正确已掌握/新错恢复；暂不能重练的考试来源显示等待讲评/开放。无结果前不显示练习解析，丢响应锁住原内容/键并可重试；当前身份/角色变化丢弃迟到响应，权限/保护拒绝和读取失败清空旧内容。保留既有视觉样式，390px无横向溢出。
- `tests/test_warning_facts.py`只移除对已由006真实迁移创建的practice_attempt夹具、按实际字段插入原4条已作答记录并补公开标志；原5样本/1正确等断言不变，没有修改SPEC-014统计业务。实际014适配器虽然created_at兼容，仍未按answered=1排除漏答；后续原负责人须接入并补漏答样本回归，现有已作答适配器测试通过不能冒充该项完成。010B后续直接消费answered及原版本事实。

### C04验证与失败记录

执行人：黄俊诚任务下Codex自动执行；日期2026-10-14（Asia/Shanghai）。Windows Python3.13.12/Node24.14.0。后端全量86（原72+本包14）、前端34（原27+本包7），ruff、前端lint/build、六文档链接/diff检查通过。后端入口：[test_practices.py](../tests/test_practices.py)；前端入口：[practice-client.test.js](../frontend/js/practice-client.test.js)、[practice-view.test.js](../frontend/js/practice-view.test.js)。后端成功题目只以明确知识schema/标签夹具隔离005；其余权限/课程/题目/试卷/答卷/评分/错题/审计/快照/迁移为实际SQLite/HTTP，前端单元组件HTTP替身不代表真实集成。

用例覆盖：四题型严格值/十进制容差/多选全等、旧版新私有版本、null/[]不计错题、简答不练习/不计错题、同题去重、跨paper/practice历史错误计数、正确重练/新错恢复、最近错误固定标签分页筛选/重登；同键同内容/数值等值/异目标异内容/独立作用域/过期键、双真实会话同内容一次和异内容仅一成功；当前学生/他人/教师/管理员/退出课程/停用/CSRF/Origin；错题更新/审计/快照故障全部回滚且不占键，paper错题投影失败也回滚答卷/答案；旧C03数据实际runner回填/重放、错误来源和历史保留约束、带数据一致性备份副本integrity_check=ok/foreign_key_check=[]和HTTP错题读取/原键重放。保护回归含定时review精确边界、保密quiz截止review=null、新旧全部版本、异常开放和旧含解析快照重放；quiz实际review路由留待C05，不把受控数据库边界变更称为该路由完成。

失败记录：初轮保护测试构造kind=quiz时漏设confidential=true，默认普通quiz可合法公开练习，导致预期409实际201；修正测试为显式保密quiz后通过，未放宽保护。首次全量83项因旧预警测试重复CREATE practice_attempt失败，改装载真实表并按其既有created_at时间契约保存练习事实，原断言通过。新增严格UUID用例时测试helper把空字符串通过`key or uuid4()`替换成合法键，导致预期400实际201；改为仅None生成键，原空键用例及全量86通过。未删除失败用例、降低门禁或修改队友统计。首次暂存检查另报两处新回归文件尾空行，已追加style提交清除并重新通过暂存diff检查，没有改写已推送历史。

浏览器复现：[verify_spec006_practices.py](../scripts/verify_spec006_practices.py)，Chrome155.0.8059.40/Edge155.0.4283.45，共22组（无夹具4/仅知识夹具18），page_errors=[]。正式[无夹具](evidence/spec-006/practices-empty/browser-results.json)与[仅知识夹具](evidence/spec-006/practices-knowledge-fixture/browser-results.json)按代码提交后同一tested_head执行，截图见[错题重练](evidence/spec-006/practices-knowledge-fixture/chrome-wrong-repractice.png)、[保护状态](evidence/spec-006/practices-knowledge-fixture/msedge-protected-wrong.png)；最终tested_head/时间见本节末尾。实际HTTP成功后故意丢响应，页面锁答/导航、原键201字节重试；教师另会话改新版为私有后旧版正确重练、再错恢复，四题型实际作答，实际paper UI错答入错题、截止前解析保护和服务器定时讲评后显示、重新登录保留6份练习/2个错题/6条练习审计通过。临时库/服务/新建浏览器退出均关闭，报告不保存密码/Cookie/token；旧C02b/C03b证据不改写为C04结果。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend目录：npm test；npm run lint；npm run build
.venv/Scripts/python.exe -m scripts.verify_spec006_practices --output docs/evidence/spec-006/practices-empty
.venv/Scripts/python.exe -m scripts.verify_spec006_practices --knowledge-fixture --output docs/evidence/spec-006/practices-knowledge-fixture
```

C04代码提交`37cd0d716d02e65decb6303f9c7b8a1b4bbf4083`及仅文件尾空行修正`408c29a8171b3ab86f8eb6f4114f6543aeaf0b0e`已推送006 feature；正式两个浏览器报告tested_head均为后者。无夹具时段2026-10-14 18:08:20—18:08:29、仅知识夹具18:08:31—18:08:47（Asia/Shanghai），仅为验证执行时间，不是生产性能证据；22组通过，page_errors=[]，上述390px截图已目视检查。代码[Actions38547456600](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38547456600)已查询run/全部jobs，completed/success，policy/lint/test/build/required全部success、grader按develop规则skipped。ci-test实际日志Python3.12.15后端86、Node22前端34通过；tested merge=`7d7ed5b937f615969e2cfae27f7f338b1e20967d`，将head408c29a测试合入base ca8ae47，未实际合并PR。最终证据文档head另独立核验CI，不沿用本条或旧C03b成功。

### SPEC-006完整有效验收核对（C04后的状态）

| 有效编号 | 结果及本包实际覆盖 | 剩余/阻塞 |
|---|---|---|
| AC-01 | 通过（原卷/固定练习版本客观判分子集；知识夹具） | 005真实标签及完整UC-02 |
| AC-02 | 通过（公开历史、新私有版本保密拒绝、各006入口全版本解析保护子集） | 003/004入口、005真实UC-02 |
| AC-03 | 通过（实际客观错误自动入本、去重/筛选/重练/恢复/重登子集） | 005真实UC-02；不视为整模块验收 |
| AC-04 | 通过（漏答0、简答pending/null/人工评分原回归；简答排除错题） | 005真实UC-02 |
| AC-05 | 通过（paper/quiz原快照及practice原键去重/冲突/并发子集） | 完整真实UC-02/C05 |
| R01 | 阻断（006内部标准答案保护通过） | 003源文件/旧下载/题库导入及004接缝 |
| R02 | 通过（试卷/答卷/错题列表进入、分页和页面子集） | 演示等他人模块由原负责人 |
| R12 | 通过（固定练习版本及原作答状态子集） | 完整真实UC-02 |
| R16 | 通过（原名单/当前授权不漂移原回归） | 005与完整真实UC-02 |
| R18 | 通过（整卷截止后/quiz同作用域原字节回归，练习独立作用域） | C05专用发布/讲评真实流程 |
| R22 | 待执行 | 全项目检查点证据 |
| R25 | 通过（公开历史、全部版本占用、并发开放/保密发布原回归） | C05及003/004实际入口 |
| R27 | 通过（原五题型/人工评分全量回归；练习严格值/0或100） | 完整真实UC-02 |
| R36 | 通过（截止/null/定时讲评、异常开放、练习/错题/快照全部版本保护子集） | C05实际review API/004/003 |
| R44 | 阻断（006独立页面/权限/失败流程通过） | UC-02跨资源/备课/知识完整角色流程 |
| R45 | 待执行 | 全项目评审/材料检查 |
| R46 | 通过（本包API/DBD/实施/测试契约登记子集） | 全模块正式交付证据 |
| R47 | 阻断 | 当前reviews=[]，需两名真实非作者 |
| NF-SEC/NF-DATA/NF-UI | 通过（本包权限/全版本保护/并发回滚/副本HTTP恢复/双浏览器390px子集） | 真实知识/资源联测、生产迁移/完整恢复 |
| NF-PERF | 阻断 | 4核8GB Linux/50会话/worker未测 |

## C03b历史恢复与证据（由上方C04恢复覆盖）

继续`feature/spec-006-exercises`，本轮fetch的origin/develop仍`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`，起点HEAD/远端`8cf56e89ce26472531c17ab59d74f1ddba7210e1`的[Actions38509534637](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38509534637)重新核验completed/success。代码分段提交`1b2ed20`（批阅事务）、`880257b`（页面/浏览器脚本）、`7c7daf7e9f8d9ba602f91ee078e5e696daef6b0f`（失败重试/恢复回归）均推送006 feature；最新CI按下方记录及[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)实际head核验。PR继续草稿、目标develop，重新查询reviews=[]；未合并、部署、生产发布或取得两名真实非作者批准。005记录从其原分支读取，未复制005代码。

下一步C04：在同一006分支复用`backend/models/attempt.py`、`backend/apis/attempts.py`和`006c_attempts.sql`中的完整answer事实接入公开客观练习、错题及重练；仅实际作答客观错答计入错题，不把漏答或人工简答伪造成客观错误；按question身份统一复核全部版本保护。学生原提交成功快照保持不变，后续最新成绩走GET。005正式合入develop后merge同步，补真实标签→编卷→发布→交卷→批阅联测；003/004联测、C05专用quiz发布/讲评、Linux/50会话及worker仍按原负责人/续包处理。

### C03b实现与验证

- `PATCH /attempts/{id}/manual-scores`复用真实当前任课教师、CSRF/Origin及BEGIN IMMEDIATE；不新增表或修改已应用迁移。整批严格语法/精度400，非本卷/非已作答简答/超配分422，旧revision409；均不留下部分评分或新增审计。允许部分批阅、零分及更正；所有原作答不变，评分人/前后整数分/评语保留在审计，answer、汇总、revision+1、审计同事务。仍有pending时总分null，全部批完变graded。
- `AttemptView`接入课程试卷内五题型作答、本人历史/结果、教师课程/试卷/评分状态筛选及分页、待批阅和更正；从列表进入，无需猜ID。网络失败锁住原作答并保留原键重试，收到成功快照后另GET最新结果；旧revision冲突禁用批阅，重新加载后重填。当前身份/角色变化清空旧内容并丢弃迟到响应；失败读取清空旧结果，所有文本经Vue文本节点显示。
- 执行人：黄俊诚任务下的Codex自动执行，日期2026-10-14（Asia/Shanghai）；双浏览器最终执行时段12:33:34—12:34:20，仅为本次测试时间。Windows Python3.13.12/Node24.14.0：后端全量72（原63+本包9）通过；前端27（原18+本包9）通过；全仓ruff、前端lint/build、文档链接和diff检查通过。入口：[test_manual_scores.py](../tests/test_manual_scores.py)、[attempt-client.test.js](../frontend/js/attempt-client.test.js)、[attempt-view.test.js](../frontend/js/attempt-view.test.js)。仅SPEC-005知识schema/标签为明确夹具；身份/课程/名单/题目/试卷/答卷/评分/审计/幂等/迁移均为真实实现，前端单元用例为组件HTTP替身，不冒充005联测。
- 新后端用例覆盖：部分→全批→更正的整数汇总和完整审计；400/422全批不变；revision冲突；当前教师/学生/外课/管理员/CSRF/Origin/撤权/停用；第二答案/汇总/审计三点故障全回滚；两个实际SQLite会话同revision仅一个成功；批阅后本人最新GET与截止后原201字节重放；带评分/审计/快照备份副本迁移重放、integrity_check=ok、foreign_key_check=[]及HTTP恢复。
- 双浏览器复现：[verify_spec006_attempts.py](../scripts/verify_spec006_attempts.py)。[无依赖夹具报告](evidence/spec-006/attempts-empty/browser-results.json)与[仅知识夹具报告](evidence/spec-006/attempts-knowledge-fixture/browser-results.json)分开；最终报告tested_head为`7c7daf7e9f8d9ba602f91ee078e5e696daef6b0f`。Chrome155.0.8059.40/Edge155.0.4283.45，共26组（无夹具6、仅知识夹具20），page_errors=[]；真实HTTP提交后故意丢弃响应、原键原字节重放、两个教师真实登录会话旧revision冲突/重载、部分/全批/更正、重新登录最新成绩、截止与实际讲评边界均通过。390px无横向溢出；[学生作答](evidence/spec-006/attempts-knowledge-fixture/chrome-student-answer.png)、[教师更正](evidence/spec-006/attempts-knowledge-fixture/msedge-teacher-correction.png)截图已目视检查。受控临时库及测试窗口不代表生产数据/教师验收；脚本退出关闭新建浏览器、服务及临时库，不保存密码/Cookie/token。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend目录：npm test；npm run lint；npm run build
.venv/Scripts/python.exe -m scripts.verify_spec006_attempts --output docs/evidence/spec-006/attempts-empty
.venv/Scripts/python.exe -m scripts.verify_spec006_attempts --knowledge-fixture --output docs/evidence/spec-006/attempts-knowledge-fixture
```

失败记录：首轮新测试模块直接导入TestCase类造成重复收集旧测试，改为模块引用后全量72项；浏览器脚本初次lint有未使用导入，删除后通过。首轮知识夹具浏览器在冲突重载后的全批断言失败：Playwright对旧已勾控件的check直接返回，重载后新表单未勾选，页面正确拒绝空批次，数据库未被覆盖；显式等待加载结束再操作后通过。诊断截图API曾误把full_page传给Locator.screenshot而TypeError，移除不支持参数后定位完成；失败报告保留本地logs，最终正式passed报告重新执行于上述代码head。另补页面读失败清空/重试回归、客户端可精确表示的评分范围及结果选项文本。未改评分口径、删除失败用例或降低门禁。

| 有效验收 | C03b本包结果（未关闭整项） | 剩余依赖/执行 |
|---|---|---|
| AC-01/04、R12/R27 | 通过（固定原题作答、pending/null、部分/全批/更正、revision和非法整批子集；知识为夹具） | 005真实标签完整UC-02联测 |
| AC-05、R18 | 通过（实际提交响应丢失/重试、批阅后原快照不变子集） | C05专用测验流程及005联测 |
| R02 | 通过（试卷作答、本人历史、教师答卷筛选/分页与批阅入口子集） | 其他模块对应入口由原负责人验证 |
| AC-02、R25/R36 | 通过（新结果页截止前后、讲评时点和身份保护子集） | C04所有练习/错题入口、C05显式讲评、003/004联测 |
| AC-03、R01/R44 | 待执行/阻断；未实现练习错题及完整资源/备课接缝 | C04、003/004、C12 |
| R22/R45/R46/R47 | R46本包契约/文档通过；R22/R45待执行，R47阻断 | 全项目证据与两名真实非作者批准 |
| NF-SEC/NF-DATA/NF-UI | 通过（本包权限、失败/并发、评分备份副本HTTP恢复与双浏览器子集） | 005真实联测、生产迁移/完整资源恢复 |
| NF-PERF | 阻断；未测目标Linux/50会话/worker | 目标环境及原负责人 |

最新代码CI：[Actions38511987512](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38511987512)，head=`7c7daf7e9f8d9ba602f91ee078e5e696daef6b0f`；已查询run及全部jobs确认completed/success，policy/lint/test/build/required全success，grader按develop规则skipped；ci-test日志Python3.12后端72、Node22前端27通过，实际tested merge SHA为`e5254aa983564aafe9aeae3cf770ded6b438c7cd`，base为`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`，未实际合并PR。最终证据文档提交的CI须按最终head单独检查，不沿用旧C03a或代码head。

## C03a历史恢复与证据（由上方C03b恢复覆盖）

继续`feature/spec-006-exercises`，本轮fetch核对origin/develop仍`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`，原HEAD/远端为`7b7c0ffe83a2b68f58329329a2acc7e83595564a`；原head的Actions38410442151重新查询确认completed/success。[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)仍草稿、目标develop，reviews=[]；005实施记录仅从其原分支读取，未复制005代码。C03a新增提交及最新CI按本节下方和PR实际head核验；未合并、部署、生产发布或取得真实两名非作者批准。

下一步C03b：复用`backend/models/attempt.py`、`backend/apis/attempts.py`和`006c_attempts.sql`，实现简答整批批阅/更正、revision冲突、审计及学生作答/历史/结果和教师待批阅页面。不能在重放时返回最新分数；最新状态走GET。C04仍须按原answer事实接入客观错题和重练，不得漏答计为实际错答；005正式合入后同步并补真实标签→发布→交卷联测。C05专用发布/讲评、003/004/worker及目标性能保持原负责人/后续包边界。

### C03a行为与迁移

- `006c_attempts.sql`由公共runner按版本/校验和接入真实attempt/answer及公共idempotency_record。原名单复合外键、每人每卷唯一、整数分值、partial/graded汇总和保留触发器；answer须为本卷固定版本且分数不超配分，原作答不可改。未修改旧迁移或队友业务。两处既有队友测评测试仅改真实表装载、补原名单及显式字段，原断言不变。
- 五题型严格校验，未知/重复/非本卷（含题目新版）版本及非法值整批400。省略/null/multiple=[]/short空白写完整未答行，0分；判断仅布尔，数值仅有限JSON数值，多选集合全等才满分。数值用足够精度十进制绝对差比较容差，0.3对0.2±0.1满分，0.30000000000000004不满分。简答仅去首尾空白，非空作答pending、score/correct=null；漏答简答0分且correct=null。整数配分精确累计，原题新版本不参与判分。
- `POST /papers/{id}/attempts`及`POST /quizzes/{id}/attempts`共用paper_attempt。当前会话/成员/原名单和基础语法先检查；带连字符UUID规范化、全卷未答/条目/多选/等值数值规范化后比对指纹。成功键先重放原201/JSON字节（含首次request_id），新请求才检查start≤now<end及每人每卷一次。异内容/异目标409，换键不能重交；24小时到期可复用键接受别卷，但不绕过本卷唯一约束。
- BEGIN IMMEDIATE内写答卷、全部答案、汇总、审计及响应快照；任一点失败全部回滚、不占成功键。真实并发同键同内容只一份答卷/审计并返回同一响应，同键异内容或异键均只有一个201。沿用公共5秒busy_timeout和503 DB_BUSY，不改001事务/限流业务。
- `GET /attempts/{id}`及课程分页答卷列表供读取最新状态，教师看本课、学生仅本人并检查当前授权/原名单，退出或停用不能重放或读取；转入不补历史名单。所有响应no-store，学生review_at未到或null时无标准answer/explanation，到实际讲评后仍复核question身份保护。quiz alias只接受kind=quiz，不等于C05发布/统计/讲评已完成。

### C03a验证及验收性质

执行人：黄俊诚任务下的Codex自动执行，本轮记录日期2026-10-14（Asia/Shanghai；用例内固定服务器时刻主要为2026-10-13，不是实际执行时间）。Windows Python3.13.12/Node24.14.0；全量后端63项（原44+本包19）、前端18项及全仓ruff、前端lint/build、文档链接/diff检查通过。后端测试入口：[test_attempts.py](../tests/test_attempts.py)，RealAttemptApiTest两项完全无知识夹具；KnowledgeFixtureAttemptTest十七项仅知识schema/标签为明确005夹具，身份/CSRF/课程/名单/试卷/评分/幂等/迁移均真实HTTP及SQLite连接。不是005真实联测、人工批阅或教师验收。C03a无页面修改，未新跑浏览器；下方C02b浏览器证据保持原tested_head，不冒充本轮截图。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m unittest tests.test_attempts.KnowledgeFixtureAttemptTest.test_database_constraints_retention_and_populated_backup -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend目录：npm test；npm run lint；npm run build
```

| 有效验收 | 本包结果（未关闭整项） | 剩余执行 |
|---|---|---|
| AC-01 | 通过（C03a固定旧版/四客观题评分子集，知识为夹具） | 005真实联测及UC-02 |
| AC-02、R25、R36 | 通过（提交/详情/列表/重放脱敏与null/定时讲评、异常受保护身份拒读子集） | C04全入口、C05实际review、003/004联测 |
| AC-03 | 待执行；原始answered/score/版本事实已保存 | C04错题及重练 |
| AC-04、R27 | 通过（五题型全批校验、漏答0、简答pending/null子集） | C03b人工评分/revision/更正及页面 |
| AC-05、R18 | 通过（受理幂等子集；截止后精确重放、别名、指纹/过期/唯一及并发） | 005真实联测及UC-02/C05完整测验 |
| R02、R12、R16 | 通过（最新答卷分页/详情、真实窗口/当前授权及冻结名单子集） | C03b页面、C04固定版本练习、完整应交/缺交流程 |
| R01、R44 | 阻断；003/004和完整UC-02尚未接齐 | 原负责人及C03b—C05/C12 |
| R22/R45/R46/R47 | R46本轮文档范围通过；R22/R45待执行，R47阻断 | 全项目记录及两名真实非作者批准 |
| NF-SEC/NF-DATA | 通过（本包真实权限/CSRF/失败回滚/并发/5秒锁拒绝与带数据备份副本HTTP读取/幂等重放子集） | 005真实联测及生产迁移/完整备份恢复演练 |
| NF-UI/NF-PERF | 待执行/阻断；旧页面回归18项，不是新作答UI/性能验收 | C03b页面与目标Linux/50会话/worker |

关键恢复验证：带答卷/答案/成功快照的一致性备份副本执行迁移重放，integrity_check=ok、foreign_key_check=[]，切换受控API到副本后GET内容和原键POST成功字节一致。人工分数更新后的旧响应测试仅在测试库模拟C03b后续写入，证明重放快照不随revision变化；不宣称manual-scores已实施。故障注入分别在第二个answer、audit_event和idempotency_record插入时触发ABORT，确认所有三表及提交审计0行后，同键可成功重试。

失败与修复：首轮ruff发现SQL集合内隐式字符串拼接、导入排序和并发测试闭包未绑定循环变量，补括号/排序/默认参数后全仓通过；首批17测试通过后增加真实锁超时与过期键跨卷复用用例，并补备份副本HTTP恢复检查。未删除失败用例、变更评分口径或降低门禁。

代码提交`557261f7bb68ec88f10d5f495a1772ce2d7fa509`已推送006 feature；对应[Actions38413864567](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38413864567)已查询run及全部jobs，head_sha精确匹配、completed/success，policy/lint/test/build/required全success，grader按develop规则skipped。ci-test日志确认Python3.12后端63/Node22前端18通过，实际checkout的tested merge SHA为`7f85302d49a7230285f87c6c6b04dac702003427`（将该head测试合入base `ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`）；这是Actions合并测试，未实际合并PR。最终文档head须另按PR和个人交接核验，不能沿用代码head或原7b7c0ff成功；最新CI与真实评审状态保存在[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)。

## C02b历史恢复与证据（由上方C03a恢复覆盖）

继续`feature/spec-006-exercises`，本轮fetch核对origin/develop仍`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`，未复制005 feature业务。后端提交`4a49abb6931df46fd9ae1b8f46e04f84051e8248`、页面/浏览器脚本提交`67358dca1f05ec78f0251458e855e6585794756d`已推送；[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)继续草稿、目标develop。新的文档head与CI在PR和个人交接按完整SHA核对；不沿用C02a旧CI。当前没有真实非作者批准，未合并、部署或生产发布。

下一步C03a：整卷受理、固定版本自动判分和共享paper_attempt幂等，随后C03b人工批阅/revision与页面。复用`backend/models/paper.py`、`paper_item`固定版本/整数配分、`paper_participant`原名单和当前课程权限；不从最新题库重读答案，不新增quiz独立答卷表。005正式进入develop后再merge同步，优先补真实标签保存→编卷→发布联测。C04统一练习/错题保护、C05专用quiz发布/null讲评和003资源保护仍待做；不接管003、004或worker。

页面提交67358dc对应[CI38409660193](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38409660193)已查询run及jobs，status=completed/conclusion=success；policy/lint/test/build/required全success、grader按develop规则skipped。PR实时metadata确认draft=true、merged=false、base=develop；reviews为空，不视为非作者批准。最终证据文档提交的CI须另按其完整head核对，最新状态见PR和个人交接。

### C02b行为与实际接口

- `006b_papers.sql`经公共runner接入真实paper/paper_item/paper_participant。同question两版本也不能重复入卷；复合外键保证固定版本属正确题目，同课检查和配分正整数约束；新增索引、发布内容/条目冻结、名单留存与不可删试卷。未修改已应用的006_question_versions迁移。
- `POST /courses/{id}/papers`严格接收非空items，按请求顺序固定版本与position。JSON数值分值须正、有限、最多两位小数，转换为整数百分之一分后累计，拒绝布尔/字符串/超精度/溢出；不静默舍入。后续题目新版本不影响本卷。
- `POST /papers/{id}/publish`普通发布支持homework/exam/quiz并要求start<end≤review，时间有时区且最多毫秒；保密说明1—1000字符。真实当前有效学生名单、状态、时间、说明和审计同事务，重复发布409。quiz普通发布采用定时讲评；共享服务的quiz模式供C05接入null讲评，当前没有专用quiz路由。
- 发布与练习公开均在BEGIN IMMEDIATE内按question身份复核。普通卷不能共享尚受保护的保密卷题目，保密卷不能共享任何尚受保护卷的题目；review_at=null或未到均保护，不以截止替代。ever_public、全部公开版本、任何已到start_at的published卷都阻止保密资格恢复，不依赖异步标记。已到讲评但曾经开放的题目只能用于不要求保密的卷。
- paper详情/分页列表复用真实001权限，教师查本课全部，学生仅published且在原名单并仍有当前课程权限。开始前只返回元数据；截止后讲评前仍无answer/explanation；实际到review_at才返回原固定答案，并再次检查身份保护。转入不补名单，退课失去访问但名单留存。所有响应no-store。
- Vue试卷页提供课程/类型/状态筛选、分页、加载/空/失败重试、题目版本选择/调序/配分、草稿和窗口发布。写入前刷新真实会话/CSRF；身份改变清空旧内容并丢弃迟到响应，学生无教师控件。发布后冻结，当前没有草稿修改接口，需另建草稿。

### C02b验证性质与适用验收

Windows Python3.13.12/Node24.14.0全量后端44项、前端18项通过，全仓ruff、前端lint/build、文档链接/diff检查通过。新增[test_papers.py](../tests/test_papers.py)共13项：RealPaperApiTest两项使用真实空库/001/迁移且不创建依赖夹具，验证权限、缺知识失败、迁移重放/校验和与一致性备份；KnowledgeFixturePaperTest十一项仅知识schema/标签为显式夹具，paper和001均真实实现。包含旧版引用、非法配分/重复身份/跨课全部拒绝、发布回滚、当前权限和冻结名单、窗口边界、公开历史、两种并发竞争和带数据备份。null讲评用例直接调用共享服务，不能宣称C05专用接口已实施。

原test_questions.py的试卷替身已移除，保护用例改用真实迁移表；异常已开放历史数据仍是刻意绕过资格检查的坏数据场景。test_identity_attendance.py/test_warning_facts.py仅适配新表的测试装载，原业务和断言不改，attempt等未实现表仍为队友测试自己的夹具。前端新增[客户端测试](../frontend/js/paper-client.test.js)三项和[组件测试](../frontend/js/paper-view.test.js)四项，HTTP替身只验证交互与状态隔离。

| 验收 | C02b结果与证据 | 完整收口仍需 |
|---|---|---|
| AC-01 | 待执行；固定原答案/版本通过，为C03评分基础 | C03真实按冻结答案判分 |
| AC-02、R25、R36 | 阻断；真实paper/001+知识夹具的保密资格/身份保护/讲评及并发用例通过 | 005真实联测、C04全入口、C05专用quiz与003/004接缝 |
| R02、R12 | 待执行；真实paper列表/开始前脱敏子集通过 | 答卷/批阅/作答/练习完整流程 |
| R16 | 阻断；真实001成员变化不改真实paper原名单用例通过，知识为夹具 | 005与C03应交/缺交事实联测、UC-02 |
| R27 | 待执行；整数配分与超精度原子拒绝通过 | 判分/简答/revision |
| AC-03/04/05、R18 | 待执行；C02b没有作答/批阅/错题 | C03/C04 |
| R01 | 阻断；003未接入，不代写 | 003/C04源文件权限与导入 |
| R44 | 待执行；本包发布/权限/时间异常通过，完整UC-02未贯通 | C03—C05/C12 |
| R22/R45/R46/R47 | R22/R45待执行；R46本轮文档范围通过；R47阻断，无两名非作者批准 | 团队评审/检查点及完整证据 |
| NF-SEC/NF-DATA/NF-UI | 本轮权限/CSRF/冻结/并发/备份及双浏览器通过，成功题目使用明确知识夹具 | 005真实数据联测、生产迁移/完整恢复演练 |
| NF-PERF | 阻断；没有4核8GB Linux/50会话/worker证据 | 目标环境及队友worker |

正式浏览器执行人：黄俊诚任务下的Codex自动执行。tested_head为页面提交67358dc完整SHA；Chrome154.0.8037.98、Edge155.0.4283.45，均headless、新浏览器上下文、真实HTTP/Vue及公共迁移。无知识夹具场景2026-10-13 22:00:30—22:00:38（Asia/Shanghai）两浏览器各4组；知识夹具场景22:00:40—22:00:51各7组，总22组，page_errors=[]。教师/学生390px截图已目视检查。前者是实际基线空库与503证据，后者使用明确知识夹具而非005真实联测；两者均无paper替身，不保存密码/Cookie/token，脚本关闭服务器、新浏览器及受控库。这些时段仅为测试时间，不填推测总工时。

- [无知识夹具报告](evidence/spec-006/papers-empty/browser-results.json)，截图：[Chrome空编卷](evidence/spec-006/papers-empty/chrome-teacher-empty.png)、[Edge空编卷](evidence/spec-006/papers-empty/msedge-teacher-empty.png)。
- [仅知识夹具报告](evidence/spec-006/papers-knowledge-fixture/browser-results.json)，截图：[Chrome教师发布](evidence/spec-006/papers-knowledge-fixture/chrome-teacher-published.png)、[Edge教师发布](evidence/spec-006/papers-knowledge-fixture/msedge-teacher-published.png)、[Chrome学生保护](evidence/spec-006/papers-knowledge-fixture/chrome-student-protected.png)、[Edge学生保护](evidence/spec-006/papers-knowledge-fixture/msedge-student-protected.png)。
- [复现脚本](../scripts/verify_spec006_papers.py)：`python -m scripts.verify_spec006_papers`；知识夹具单独用`--knowledge-fixture --output logs/spec-006-papers-fixture`。全量验证命令沿用下方C02a记录。

失败与修复留痕：最初新增paper迁移使两处队友自建paper夹具冲突，仅改测试装载后原断言通过；首次共享quiz服务测试的审计使用另一连接导致锁冲突，改为公共write/get_db同事务；时间跳跃使测试会话过期，改为通过真实登录刷新测试身份。首次前端测试替身缺少完整items读模型，补齐替身字段后通过。浏览器发现下拉框标签名称包含选项文本而超时，给控件补显式aria-label后Chrome/Edge通过。旧失败报告仅在logs，不混入正式passed报告。

## C02a历史记录（截至f875bcd；以下旧状态由上方C02b恢复覆盖）

## 基线与边界

用户明确调整原“暂不启动C02”的安排，允许先推进不依赖队友的部分。新建`feature/spec-006-exercises`，起点为fetch核验的origin/develop `ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`。没有从尚未合入的005 feature起步或复制其业务代码，没有实现003上传/导入、005知识、worker或其他队友业务。

005 feature的文档修正和恢复说明另已推送`4f810ab`及`bd7ec0f5bf798e10ef530de9be517acd031f1c4e`；其PR #4仍草稿。bd7ec0f对应[CI 38402216414](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38402216414)及policy/lint/test/build/required全部success，grader skipped，非005完整验收。005实施记录保存在005分支，不随当前006分支出现。

006消费实际001会话、CSRF/Origin、课程成员授权、事务锁和公共SQL runner。共享接入仅增加questions Blueprint及Vue组件注册、样式导入和Vue编译器别名；沿用既有页面和依赖锁。SPEC-014的`test_warning_facts.py`仅移除自建题目替身表、改为向新迁移表填测试行，原业务代码和断言未改。

## 本轮行为

- 五题型写模型：选择题2—8项、key唯一、答案匹配；判断严格JSON布尔；数值答案/容差严格有限数值、容差非负；非数值容差0；简答参考答案非空且不开放单题练习。非法/重复ID、未知字段及空PATCH拒绝400。
- `POST /courses/{id}/questions`创建身份及版本1；`PATCH /questions/{id}`完整校验合并字段后追加版本；GET按最新版本提供分页及题型/难度/知识筛选。稳定id和version_id分开，旧内容/答案/标签不被覆盖；数据库拒绝旧版本/关联UPDATE/DELETE。并发PATCH串行生成连续版本，不丢历史。
- 题目、版本、标签、ever_public及审计同事务；非法同课标签或插入失败不留下半份题目。公开历史只能0→1，改为私有不恢复保密资格。学生列表只含最新公开版本，始终去掉answer/explanation。
- `ensure_practice_unreserved`按question身份检查published保密卷及review_at，所有版本受同一保护，null或尚未到讲评时间均禁止开放，实际到review_at才释放。C02b/C04须复用并补齐发布/练习/错题等其他入口；当前没有这些业务入口。
- 教师页面提供五题型表单、知识多选、版本编辑、分页筛选与加载/空/错误/重试；数值输入转有限JSON数值，空白不转成0；身份变化拒绝写入并清空旧编辑内容；正文/解析以文本显示，不执行HTML。

## 依赖与失败边界

| 依赖 | 负责人/后续包 | 当前处理 | 恢复条件 |
|---|---|---|---|
| 001身份、课程、迁移 | 姜苏豪提供，黄俊诚消费 | 已在develop；真实登录/成员/CSRF/撤权/停用及迁移测试通过 | 保留真实共享实现，敏感变更按两名非作者复核 |
| 005知识父表和标签查询 | 黄俊诚005 feature，真实合入依赖团队复核 | develop尚未包含005；创建/编辑不能省略非空同课标签，缺表503 DEPENDENCY_UNAVAILABLE；知识接口缺失时UI禁用新增 | 005正式进入develop后merge同步006，真实创建/编辑/跨课标签/撤权联测 |
| paper/paper_item保护与发布 | 黄俊诚C02b | 缺表时开放练习及非空学生公开题读取503；不把缺少保护当成不受保护 | C02b建立真实试卷能力并联测保密发布/并发公开/实际讲评边界 |
| 003资源导入与源文件权限 | 石佰合提供，黄俊诚消费 | 未接管；本轮没有上传/导入实现 | C04与003按R01真实联测 |

迁移`006_question_versions.sql`仅创建question/question_version/question_knowledge及索引/保留触发器。公共runner允许先声明knowledge_point外键；当前父表未接入时仅空题库读和依赖拒绝可运行。未关闭外键或建立运行替身。模型按SQL文本SHA-256核对迁移记录；缺失/校验失败503 MAINTENANCE。生产迁移/完整备份演练未执行。

## 验收映射与测试性质

以下登记完整006编号；C02a局部基础通过不代表整项通过。`tests/test_questions.py`的RealQuestionApiTest使用实际create_app、001/API、公共迁移及受控库，没有知识/试卷替身，成功写入仍被真实依赖阻断。FixtureVersionTest另建最小知识/试卷schema夹具，只验证版本事务与保护SQL，不作005或发布联测证据。初始管理员/教师bootstrap，课程、成员与学生注册走真实001 API。

| 有效验收 | 本轮证据/结果 | 剩余执行位置 |
|---|---|---|
| AC-01 | 待执行；旧版保留为基础，尚无按冻结答案判分 | C02b/C03 |
| AC-02 | 阻断；夹具验证学生脱敏、保密保护、ever_public保留通过，真实空列表通过 | 005联测、C02b发布保密资格及C04入口保护 |
| AC-03 | 待执行；未实现错题 | C04 |
| AC-04 | 待执行；简答写模型通过，未实现人工批阅 | C03 |
| AC-05 | 待执行；未实现交卷幂等 | C03 |
| R01 | 阻断；003资源导入/源文件权限尚未就绪 | 003/C04 |
| R02 | 待执行；本轮题库列表不替代试卷/答卷入口 | C02b/C03/C04 |
| R12 | 待执行；题目版本基础通过，未实现窗口/作答 | C02b/C03/C04 |
| R16 | 待执行；未发布试卷冻结名单 | C02b |
| R18 | 待执行；未实现交卷幂等 | C03 |
| R25 | 阻断；ever_public不可清除、同身份各版本保护的夹具用例通过，缺保护明确503 | 真实试卷保密发布/并发联测待C02b |
| R27 | 待执行；[模型测试](../tests/test_question_validation.py)四组严格五题型校验通过，判分/配分/批阅尚未实现 | C02b/C03 |
| R36 | 阻断；夹具用例核对review_at=null及等于服务器时刻边界通过 | C02b/C04真实所有入口联测 |
| R44 | 待执行；本轮真实身份/课程异常分支通过，完整UC-02未贯通 | C02b—C04/C12 |
| R22/R45 | 待执行；责任与续包登记，无全组工时/验收结论 | 团队检查点 |
| R46 | 通过（本轮文档范围）；APIC/DBD单一定义、迁移归属、文档链接检查 | 后续继续核对各新入口 |
| R47 | 阻断；没有真实非作者批准，敏感权限/API/数据库须两名 | PR实际评审 |
| NF-SEC | 本轮真实401/403/404/503、CSRF/Origin、撤权/停用、非法输入用例通过；成功题目写入/脱敏非空数据仍为夹具 | 005与C02b真实联测、完整模块权限回归 |
| NF-DATA | 公共迁移重放/校验和拒绝、空库一致性备份及完整性/外键检查通过；版本保留/失败回滚夹具通过 | 含真实知识/试卷的备份恢复及生产演练 |
| NF-UI | Chrome真实HTTP/UI四组通过；表单/版本编辑仅组件HTTP替身通过 | 005接入后的实际表单保存、指定双浏览器完整回归 |
| NF-PERF | 阻断；目标4核8GB Linux/50会话/真实worker未测试 | 目标环境和worker就绪后 |

具体入口：[test_questions.py](../tests/test_questions.py)含三项RealQuestionApiTest及五项FixtureVersionTest；[question-client.test.js](../frontend/js/question-client.test.js)五项客户端/输入测试；[question-view.test.js](../frontend/js/question-view.test.js)四项组件交互。组件HTTP替身不返回真实教学结论。

## 本地验证与失败记录

Windows Python3.13.12、Node24.14.0；全量后端31项（develop原19+本轮12）、前端11项（原2+本轮9）通过，`ruff check backend tests scripts`、前端lint/build、文档链接和diff检查通过。CI的Python3.12/Node22结果另按实际新head核验。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
# frontend目录：npm test；npm run lint；npm run build
.venv/Scripts/python.exe -m scripts.verify_spec006_questions --output docs/evidence/spec-006/questions
```

失败与修复：首次新迁移使预警测试自建question表冲突，适配其测试夹具后原断言通过；新增停用用例直接停用负责教师被001合法移交规则409拒绝，改用已撤课学生验证停用；首次ruff报告app导入格式和浏览器脚本过宽异常捕获，分别整理导入及收窄脱敏异常边界后通过。没有修改队友业务来让测试通过。

真实浏览器：[复现脚本](../scripts/verify_spec006_questions.py)、[可选依赖](../backend/requirements-browser.txt)。执行人：黄俊诚任务下的Codex自动执行；时间2026-10-13 21:26:20—21:26:24（Asia/Shanghai，仅此测试时段）。使用已安装headless Chrome154.0.8037.98和真实HTTP/Vue；仅bootstrap管理员/教师，课程/学生/成员通过真实API准备，完全不建立知识/试卷夹具。四组检查：教师登录空题库且知识缺失禁用新增、实际HTTP创建503且无半份题目、390px无横向溢出、学生登录空题库且无教师控件。所有page_errors为空。结果见[browser-results.json](evidence/spec-006/questions/browser-results.json)，截图[教师依赖提示](evidence/spec-006/questions/chrome-teacher-blocked.png)及[学生空题库](evidence/spec-006/questions/chrome-student-empty.png)已目视检查。脚本结束关闭新建浏览器、Vite/API服务器及临时库，无密码/Cookie/token存档。

## 提交与下一恢复

| 部分 | SHA | 状态 |
|---|---|---|
| 后端模型/版本/迁移/API与测试 | d582039 | 已推送006 feature |
| 教师页面/客户端测试/真实浏览器脚本 | df4f1b5b04d7e03a831740c6cf8ecf138430400d | 已推送；浏览器原始报告的tested_head |
| 首轮正式契约与证据 | cfd868b1f58a8deae199e9f05e1e046e5e83a6e5 | 已推送；CI38405502738通过 |

[PR #7](https://github.com/Gindama713/nchu-web-learning_platform/pull/7)保持草稿，目标develop；未合并006/005、未发布。上述cfd868b对应[CI38405502738](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38405502738)已完成success，jobs核对policy/lint/test/build/required全success、grader skipped；查询reviews为空，没有真实非作者批准。后续提交的新head CI在个人交接与PR中按实际结果核对，不沿用此旧head成功。

当前下一恢复见本文件上方“C02b当前恢复与证据”及个人会话计划第6节。此处保留C02a提交/测试历史，不沿用“C02b待做”或旧head CI作为当前状态。
