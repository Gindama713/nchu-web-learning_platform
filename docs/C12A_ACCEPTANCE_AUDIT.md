# C12a 七个本人SPEC验收缺口与必要接缝

黄俊诚（24201716），2026-10-15，Asia/Shanghai。核对/自动执行人为本次授权下的Codex；不是非作者评审人或课堂验收人。本文保留C12a验收审计/010B修复，并记录C12b所属006/012 feature显示增量，不展开C12c整套报告。

依据：[PRD§11.5完整索引](PRD.md#acceptance-index)、§4/8/9/10.5/11.1—11.5与有效追加R；[README§8及附录A](../README.md)、[CHG-RB](CHG-RB.md)发布/恢复约束。沿用现行APIC/DBD，不修改规格、旧迁移、CI或队友业务。

## 当前结论与完整集合

2026-10-15 C12b增量优先：C12a-UI-02在006 feature由SPEC-006主修并引用008，已提交[后续PR #17](https://github.com/Gindama713/nchu-web-learning_platform/pull/17)；C12a-UI-03在原012 feature更新[PR #15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15)。三个NF-UI失败行经所属feature组件与真实HTTP/双浏览器复验改为本人适用范围“通过”，集成结果仍阻断，完整SPEC不关闭。代码没有互相复制到未合入分支；本010B分支只更新审计记录，不引入006/012实现。其余128行结果及原证据保持。

完整逐行记录见[验收矩阵](evidence/c12a/acceptance-matrix.md)，可机器读取的[完整字段JSON](evidence/c12a/acceptance-matrix.json)保留每行来源、输入/预期、实现、测试/人工步骤、证据层、补验、实际、结果、执行人/日期、PR/head/tested和附件。

| SPEC | AC | 业务R | 共通R | NF用例组 | 通过 | 失败 | 阻断 |
|---|---|---|---|---|---|---|---|
| 005 | 01—04 | 20/32/38 | 22/45/46/47 | 5 | 8 | 0 | 8 |
| 006 | 01—05 | 01/02/12/16/18/25/27/36/44 | 同上 | 5 | 14 | 0 | 9 |
| 008 | 01—04 | 01/02/12/16/18/25/27/33/36/37/44 | 同上 | 5 | 14 | 0 | 10 |
| 010B | **继承父SPEC-010/AC-01—05** | 12/15/16/27/33/34/38 | 同上 | 5 | 15 | 0 | 6 |
| 011 | 01—04 | 20/35，含未另编号的算法追加 | 同上 | 5 | 9 | 0 | 6 |
| 012 | 01—04 | 20/34/35，含未另编号的算法追加 | 同上 | 5 | 10 | 0 | 6 |
| 013 | 01—05（含§4.2追加05） | 14/25 | 同上 | 5 | 10 | 0 | 6 |
| 合计 | 31 | 37 | 28 | 35 | 80 | 0 | 51 |

131行无遗漏，结果只用待执行/通过/失败/阻断/不适用；本轮没有“不适用”及其批准。NF名称是既有用例组，未新造AC/R。**“通过”限该行明确的本人本地适用行为，不等于完整SPEC关闭**。矩阵另列“集成结果”：011/012独立feature上的业务通过仍全部保留develop跨链阻断。统计数不能解读为课程通过率；真实课程复核、目标性能和生产/课堂缺口单独保留。

## C12b修复、验证与集成边界（最新）

### 2026-10-16 C12b集成续核（12:44 Asia/Shanghai，最新）

本轮从干净010B feature `f1fad6563b4030f3d43b3f682e4d17865e4de3e4`接续；本地/远端一致。先fetch，origin/develop仍为`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`。独立读取四PR当前base/head、实际merged状态、精确head的Actions run元数据、全部6个jobs和ci-test原始日志，以及真实reviews、review_threads、issue comments。新快照追加于[正式门禁证据](evidence/c12a/c12b-code-head-ci.json)的`integration_recheck_followups[1]`（2026-10-16 12:44:33 Asia/Shanghai）；原start/c12b_final/integration_recheck及followups[0]保留。

| PR | 本轮接入head | 当前head的CI run / 原始日志 | 真实评审及合入 |
|---|---|---|---|
| [#14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14) | bbd9ecdb151cab0ff7a34e94261b5378ceabfb74 | [38681339662](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38681339662)，后端194项152.886秒 / 前端76项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15) | 9fefd17d99242efdd53847029d7d7cafbcadf59d | [38740733563](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38740733563)，后端190项146.828秒 / 前端79项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#16](https://github.com/Gindama713/nchu-web-learning_platform/pull/16) | f1fad6563b4030f3d43b3f682e4d17865e4de3e4 | [38771346788](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38771346788)，后端177项95.598秒 / 前端70项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#17](https://github.com/Gindama713/nchu-web-learning_platform/pull/17) | e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85 | [38739998112](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38739998112)，后端177项140.523秒 / 前端77项 | open/非draft，reviews/threads/comments=[]，未合入 |

四PR base均为上述develop；policy/lint/test/build/required全部success，grader按现行develop规则skipped。四PR均merged=false/merged_at=null、actual merge SHA=null；Git核验四个head均不是origin/develop祖先，当前feature包含该develop基线。#16的CI tested=`8120b7783d38edc396e9e7d9132891fb825ee88a`及其他CI引用均不是实际merge。无真实新评审问题或批准；未触发所属SPEC修复、合入后同步或集成补验。

本轮新增验证仅为上述远程门禁读取和本地文档/JSON一致性、矩阵保全及diff检查。131行矩阵及其Markdown、原集合检查文件均保持原样：80通过/0失败/51阻断，全部131行（包括006/008/012三个NF-UI）字典、原编号/结果/集成结果/head/tested/附件不变。三个NF-UI继续本人本地通过、集成阻断；最新门禁由本节和新增快照补充，原行中00:41登记及固定证据指针作为历史保留。复用下方006/012固定组件、真实handler、HTTP/双浏览器证据，未新增本地业务/handler/浏览器测试。真实非作者复核和课堂本轮均无新证据；完整SPEC未关闭。

仅追加本审计及正式门禁JSON两项文档证据，不制造代码或测试增量。新文档提交推送后须独立核验#16当前head的CI，写回PR说明及两份本地排除个人交接，避免把自身SHA写入自身。Context7文档已查询；本机gh命令不可用，远程读取实际使用GitHub连接器，未伪称gh执行成功。本地辅助检查首轮将零失败误断言为必须存在的计数键，修正该断言后重跑通过；属于检查脚本失败留痕，矩阵和业务测试未失败。

恢复条件：负责人真实复核并合入后，先fetch核对actual merge SHA位于origin/develop祖先链，再按项目流程同步最新develop，仅补006/008共用时间显示及012推荐依据截止的受影响集成验证并更新三个NF-UI；出现真实评审问题则回所属SPEC feature修复。尚未合入且无新问题继续保留阻断。不复制未合入feature实现、不代写队友、不自行合并/部署/发布或发协作消息；本轮不展开C12c。

### 2026-10-16 C12b集成续核（00:41 Asia/Shanghai）

本轮从干净010B feature `76a0deebaf117e8f783f4e19f96edc45f37c973a`接续。先fetch，origin/develop仍为`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`；Git确认当前feature包含该基线，四个PR head均不是develop祖先。随后独立读取四PR最新base/head/merged状态、精确head的Actions run元数据、全部6个jobs及ci-test原始日志、真实reviews/threads/comments；没有直接沿用前轮结论。追加快照见[正式证据](evidence/c12a/c12b-code-head-ci.json)的`integration_recheck_followups[0]`，原start/c12b_final/integration_recheck完整保留。

| PR | 本轮接入head | 当前head的CI run / 原始日志 | 真实评审及合入 |
|---|---|---|---|
| [#14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14) | bbd9ecdb151cab0ff7a34e94261b5378ceabfb74 | [38681339662](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38681339662)，后端194项152.886秒 / 前端76项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15) | 9fefd17d99242efdd53847029d7d7cafbcadf59d | [38740733563](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38740733563)，后端190项146.828秒 / 前端79项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#16](https://github.com/Gindama713/nchu-web-learning_platform/pull/16)（本轮证据提交前） | 76a0deebaf117e8f783f4e19f96edc45f37c973a | [38769957787](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38769957787)，后端177项142.932秒 / 前端70项 | open/非draft，reviews/threads/comments=[]，未合入 |
| [#17](https://github.com/Gindama713/nchu-web-learning_platform/pull/17) | e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85 | [38739998112](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38739998112)，后端177项140.523秒 / 前端77项 | open/非draft，reviews/threads/comments=[]，未合入 |

四PR base均为上述develop；policy/lint/test/build/required全部success，grader按develop规则skipped。四PR均merged=false/merged_at=null，actual merge SHA=null。#16日志tested=`ca42c0b35268c9893d2f3324690529f961b7d5ec`及其余三个CI测试引用均不是实际merge。无真实评审问题可修，无实际merge可核验或消费；未执行合入后同步develop或集成补验。

本轮新增验证仅为远程门禁读取及本地文档/JSON/矩阵一致性检查。006/008共用时间显示、012推荐依据截止的固定组件、真实handler、双浏览器/HTTP证据按下方原SHA复用，未重新执行。三个NF-UI仅更新集成核验及证据指针，本人本地仍通过、集成仍阻断；131行80通过/0失败/51阻断，其余128行和全部原结果/head/tested/附件不变。远程CI、既有本地验证、真实非作者复核及课堂分别登记；本轮无真实批准或课堂新证据，完整SPEC不关闭。

下一步仍由负责人完成真实复核/合入；fetch后核对actual merge位于origin/develop祖先链，再按项目流程同步，只补006/008/012受影响集成验证。新证据提交后的#16当前head CI须重新独立读取，结果写PR说明及两份本地排除个人交接，避免自引用循环。未自行合并、复制未合入feature代码、代写队友、部署/发布或发送协作消息；本轮不展开C12c。

### 2026-10-16 C12b集成续核（00:31 Asia/Shanghai）

本轮先fetch，origin/develop仍为`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`；当前010B feature已经包含该基线。独立读取四PR最新元数据、当前head对应Actions、全部6个jobs和ci-test原始日志，以及真实reviews、review_threads、issue comments；完整快照追加于[固定证据](evidence/c12a/c12b-code-head-ci.json)的`integration_recheck`，保留原历史快照。

| PR | 当前head | 当前head的CI run / 实际日志 | 真实评审与合入 |
|---|---|---|---|
| [#14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14) | bbd9ecdb151cab0ff7a34e94261b5378ceabfb74 | [38681339662](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38681339662)，后端194项152.886秒 / 前端76项 | open/非draft；reviews/threads/comments=[]；未合入 |
| [#15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15) | 9fefd17d99242efdd53847029d7d7cafbcadf59d | [38740733563](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38740733563)，后端190项146.828秒 / 前端79项 | open/非draft；reviews/threads/comments=[]；未合入 |
| [#16](https://github.com/Gindama713/nchu-web-learning_platform/pull/16)（本轮文档更新前） | dcf38ec73393a1c875d3479dae371fe12b4fe690 | [38741444389](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38741444389)，后端177项140.677秒 / 前端70项 | open/非draft；reviews/threads/comments=[]；未合入 |
| [#17](https://github.com/Gindama713/nchu-web-learning_platform/pull/17) | e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85 | [38739998112](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38739998112)，后端177项140.523秒 / 前端77项 | open/非draft；reviews/threads/comments=[]；未合入 |

四PR base均为上述develop；policy/lint/test/build/required均success，grader按develop规则skipped。四PR均`merged=false`、`merged_at=null`，actual merge SHA为空；Git核验四个head均不在origin/develop祖先链。API的`merge_commit_sha`只是CI合并测试引用，不记为真实merge。没有实际merge可做祖先确认，未执行合入后develop同步或集成测试；本轮没有真实评审问题可回feature修复，也没有真实批准。

006/008共用时间显示及012推荐依据截止的三个NF-UI行已补本次集成门禁核验、日期和后续补验条件；本人本地结果继续通过，集成结果继续阻断。131行仍80通过/0失败/51阻断，其余128行字典完全不变。原固定SHA的组件、真实handler及HTTP/双浏览器证据按下文复用，未重跑整套测试；本轮本地验证仅限文档/JSON/矩阵一致性和diff。远程CI重新查询与既有本地测试分开，真实非作者及课堂验收均未完成。

下一步由负责人完成真实复核/合入；再fetch核对actual merge属于origin/develop祖先，按项目流程同步develop，仅补006/008/012受影响集成验证。文档提交后的新#16 head需独立核验其CI/真实讨论，结果记PR及两份本地排除个人交接，避免将提交自身SHA写回自身。未复制未合入feature代码、未自行合并、未部署/发布，不展开C12c。

### 前轮修复与固定本地证据（保留原SHA）

最新fetch后origin/develop仍`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`。#14/#15/#16/#17均open/非draft，实际reviews/threads/comments=[]；没有真实评审阻断、批准或实际merge，不自造讨论关闭。接入#14 bbd9ecd、#15旧36a9cff、#16旧cd38efb的当前head Actions/jobs/ci-test重新独立读取，必需成功、grader按develop跳过，原实际后端194/190/177及前端76/77/70吻合历史；不是仅复述旧快照。#14未改动。006原#7已合入，只在原SPEC feature快进最新develop后开后续#17。012原#15仍open，继续原feature。

| 范围/主修 | 实际base / 最终实现及证据head | 本轮干净浏览器tested | actual merge / 消费条件 |
|---|---|---|---|
| UI-02，006主修/影响008，[#17](https://github.com/Gindama713/nchu-web-learning_platform/pull/17) | f9c49b19c59053be2b171e0b7f2a35d1e050e57e / e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85 | 4eadbcbcaf1df2cb8f1245c9fdfcbcfca4523072 | 无；008/其他feature只经负责人合入后的最新develop消费 |
| UI-03，012，[#15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15) | f9c49b19c59053be2b171e0b7f2a35d1e050e57e / 9fefd17d99242efdd53847029d7d7cafbcadf59d | 03a03c7611bd2d00e07a33d8f8bd5842bc36f9c9 | 无；没有把012/011复制到006或010B |

006固定[实施记录](https://github.com/Gindama713/nchu-web-learning_platform/blob/e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85/docs/SPEC-006_IMPLEMENTATION.md)、[原始报告](https://github.com/Gindama713/nchu-web-learning_platform/blob/e1c2bcdbe8e6a21b2eaa2e7fc039e25190c51c85/docs/evidence/spec-006/c12b-time/report.json)及8图/日志：26项受影响组件/HTTP替身，5项真实handler/SQLite14.788秒；干净4eadbcb，Chrome155.0.8059.41（UTC）/Edge155.0.4283.45（America/Los_Angeles）各4组，page_errors=[]。真实005知识、006考试及008专用发布/UI交卷，跨日/上海周界、午夜00、null讲评；开始前/截止新交409、原键截止及讲评后201字节完全一致、讲评前paper/attempt不含答案、定时/显式讲评后开放。DB submitted_at保持2026-10-18T16:00:00.000Z，GET data渲染前后不变。8张390px图自动无溢出，代表图目视；null/非法值在组件层，不伪造真实API异常时间。

012固定[实施记录](https://github.com/Gindama713/nchu-web-learning_platform/blob/9fefd17d99242efdd53847029d7d7cafbcadf59d/docs/SPEC-012_IMPLEMENTATION.md)、[原始报告](https://github.com/Gindama713/nchu-web-learning_platform/blob/9fefd17d99242efdd53847029d7d7cafbcadf59d/docs/evidence/spec-012/c12b-time/report.json)及2图/日志：8项组件/HTTP替身、2项既有真实handler/SQLite4.659秒（28天半开UTC边界、身份级保密入口及推荐故障不阻断提交）；干净03a03c7，两浏览器上述准确版本/不同时区各3组，page_errors=[]。依据截止UTC周日15:59:59/16:00显示上海周日23:59:59/周一00:00，原source_until/整个data不变；真实推荐→练习UI201、原键201字节重放样本仍1，DB created_at仍UTC。两张390px图已目视。

仅显示层修复，数据库、接口、CSV、原始快照、服务器判断与判分/保密/幂等规则不变。相关lint/build、ruff本脚本、六文档/diff通过；没有迁移/无关CI/公共框架重构。006/008共用代码仅006一处主修，本文件及矩阵只引用固定证据。原E006/E008/EQB/E012及C12a快照/CSV证据复用，原测试SHA/边界不变；不重做C10/C11/C09/C07，不重跑008→010B专用联测。账号bootstrap/TEST_NOW与组件替身、真实handler、socket HTTP/UI、人工/课堂证据分层；没有课堂新证据。

失败留痕：006预运行会话先登录后跳时钟而过期、GET动态信封误按字节比较、已登录late会话重复等待表单，均只修脚本后干净重跑；012首次fd64db7干净DOM/HTTP通过但Edge截图空白，调整完整卡片容纳于390×1200视口后03a03c7重跑目视通过；正式lint日志末尾空行由9fefd17修正，未改写已推送历史。正式源码/脚本/日志/截图在所属feature版本化，两份个人文件继续本地排除。

独立核验最终实现/证据head：[固定CI/真实评审快照](evidence/c12a/c12b-code-head-ci.json)。#17 e1c2bcd的[Actions38739998112](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38739998112)：policy/lint/test/build/required全success、grader依develop skipped，真实日志后端177项140.523秒/前端77项，CI tested=273081714a48eb9b85df134230d802ed6d4c4ed4。#15 9fefd17的[Actions38740733563](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38740733563)：同样必需全success/grader skipped，真实190项146.828秒/前端79项，CI tested=f71b4865bfde8daca143cf209b9fce1f24b225e5。base均为f9c49b1；这些tested是CI引用，不是actual merge；各PR最终head reviews/threads/comments仍[]。文档矩阵[集合检查](evidence/c12a/c12b-matrix-check.txt)确认131个原编号完整、仅三个NF-UI行变更、其余128行字典完全不变。本审计最终文档head另推送并独立核验CI/真实评审，结果写PR #16和本地交接，避免把自身提交SHA写入自身形成循环；不沿用旧cd38efb成功冒充新head。

剩余：上述PR未合入，三个NF-UI集成结果保留阻断；资源/备课/实验/评测等原依赖、I-01/02/03完整链、真实完整非作者复核、Linux4核8GB/50会话/worker、生产同点恢复/90天保留、Gitea与课堂均按原记录保留。下一恢复先fetch独立核对#14/#15/#16/#17最终head/CI/实际评审，真实问题回所属feature；若负责人合入，核对actual merge祖先后只消费最新develop，针对受影响行补集成登记。不自行合并、部署、发布或发协作消息；不展开C12c，不开发014/016。

## C12a接入快照与历史集成边界

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
| C12a-UI-02 | C12a登记006/008共用paper-view窗口及attempt-view提交/截止UTC显示缺口 | **C12b所属006 feature修复并复验通过**，#17待真实评审/合入，008只经develop消费；两个NF-UI集成结果仍阻断，见上方固定证据 |
| C12a-UI-03 | C12a登记012推荐依据截止UTC显示缺口 | **C12b原012 feature修复并复验通过**，原#15待真实评审/合入；NF-UI集成结果仍阻断 |

本轮未发现本人权限、判分、保密、幂等或持久化业务阻断。C12a历史3个失败矩阵行对应UI-02的006/008及UI-03的012；C12b三个本地行均通过，集成仍阻断，不误报成三个独立根因或已合入。没有以N/A消除未验范围。

验证过程失败留痕：首次脚本题型下拉定位超时；第二轮练习控件定位按实际radio修正；第三轮错误预期“下架删除历史样本”按现行APIC纠正，未改业务；第四轮DELETE204被旧helper当JSON解析，改本脚本helper；其后一次Edge本机socket ENOBUFS（并行handler期间）保留失败，不算通过。caf7d73干净重跑通过后发现UI-01，修复为79a133c；诊断改为脱敏异常后ruff报告宽泛捕获，2fa4a2b收窄异常并加入时区断言，重新ruff和干净双浏览器通过。正式JSON仅记录最终轮，早期调试不替代正式证据；诊断不输出密码、Cookie或CSRF。

## 2026-10-17 I-01与005图文有限续核

最新[I-01/005图文记录](SPEC-005_I01_RESOURCE_SEAMS.md)及[evidence](evidence/spec-005/i01/entry-state.json)优先于下方C12a历史依赖快照。009石佰合、017/010C罗浩铭均已actual merge且为develop祖先，不再以当时experiments404认定未开发；003也已合入。005→009同课知识ID/固定实验版本、真实017成功/失败/草稿/缺交及010C输入/计数/旧ID/CSV已在本轮有限消费范围核对，005自报进度不替代实验完成。017工作台和010C页面缺失，017窗口、撤权写入、重做及009UTC时间展示缺口见正式问题记录；未接管队友。

005现行HTML禁img/链接/属性，实际API和现成编辑/阅读页符合；003有效PNG在全部现有kind均415，未能创建真实图片业务对象，知识资源引用字段/同课/固定版本/event_id显示规则仍未定义。合法类型PDF字节对照不冒充图片验证；未复跑PR30题库源文件和导入整包。干净tested96f4f29，handler2通过+4项017契约expectedFailure，双浏览器各7组现成页面检查、12图逐张目视；完整I-01/005图文仍阻断。

原JSON/Markdown矩阵仅8行追加实际证据，保留原整行及head/tested/附件/原判定，其余123行不变：[保全核对](evidence/spec-005/i01/matrix-preservation.json)。本地80通过/51阻断，集成59通过/72阻断不改判；#27—#31均未合入，不能复制其矩阵增量或套用PR31的62/69。004/007无真实修复合入，沿用PR29/31固定失败与缺页，未重跑整包。R01及I-03的历史续包仅引用原PR，不复制未合入材料。

## I-01 / I-02 / I-03本人接缝及外部依赖（以下保留C12a历史快照）

| 链/缺口 | 当前本人证据 | 具体阻塞与恢复条件 |
|---|---|---|
| I-01 | 001→005、本人收藏/进度/发布与同课权限有E005/H12/B12 | 罗浩铭009/017/010C真实实验版本、接线保存/成功与失败事实未接入当前应用；experiments404。等待这些能力通过develop集成后仅验005知识引用/权限，不代写实验/统计 |
| I-02 | 012真实客观错题与进度推荐独立证据E012；不把评测成绩改作推荐客观题样本 | 石佰合018真实上传/队列/执行/报告/010D、罗浩铭009版本链缺失；health grader_ready=false；012自身也未合入。需原负责人契约和真实同课成绩/关联知识后再验本人入口，不接管worker |
| I-03 | E008→006错题→EQB/010B掌握度已验证；QA故障隔离仅E011独立feature | 罗浩铭004备课与007演示缺失，preparations404；011 #14未合入。姜苏豪014虽有独立模块，不因当前事实查询成功就声称其完整链已过；等待真实同课事件/名单/版本/权限链 |
| R01/005图文 | 本人知识白名单、题目身份保护已实现；B12当前资源路由404 | 石佰合003授权图片、题库源文件旧版权限及原子导入；罗浩铭004旁路。现行APIC知识禁img/链接/属性，DBD无知识资源引用；需真实契约与规定非作者复核，不放开任意URL |
| R37 | 原quiz ID/名单/窗口/讲评接口及保护有E008/EQB | 004真实同课关联、跨课/重复/非quiz拒绝、复制不自动发布、开始前元数据/非参与人/讲评旁路均阻断 |
| 共通/NF | 当前本人安全、受控恢复、双浏览器与版本化证据 | R22/R45全组检查点/工时/技术风险由019组织；R47真实完整复核；4核8GB Linux/50会话/worker与p95；生产同点恢复/90天保留；Gitea固定SHA与课堂检查。均未以自动测试关闭 |

I-01/02/03完整链结果均为**阻断**，不是不适用。I-04、生产部署/恢复/Gitea归档/课堂演示本轮未执行，用户未授权AI合并、部署、发布或发送协作消息。

## C12a正式复验与历史恢复点（C12b恢复见上方）

代码分段提交caf7d730b0d904716f083a014978da4795a0b494（新增接缝脚本）、79a133c（010B时区展示）、2fa4a2b04533bb8023d0e4a7f35de909c38a1e75（脱敏诊断lint及显示断言）、db83da52b8feeb903c61977f593aad764d34c16c（正式证据/矩阵）均推送原010B feature。新[PR #16](https://github.com/Gindama713/nchu-web-learning_platform/pull/16)已创建，open/非draft→develop；#10/#12保留实际已合入状态，不重开旧PR。

证据head db83da5的[Actions38697994792](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38697994792)已单独读取run/jobs及ci-test原始日志：policy/lint/test/build/required全部success，grader依develop规则skipped；后端177项97.469秒、前端70项。base=f9c49b19c59053be2b171e0b7f2a35d1e050e57e，tested=`7a5ef3d81747f3db030fad30a6017fb7e1ace73f`是CI合并测试引用，actual merge不存在。真实reviews=[]、review_threads=[]、comments=[]；固定[CI与评审快照](evidence/c12a/code-head-ci.json)已版本化，不将AI检查作为非作者复核。

本地7项真实handler通过8.950秒、前端70项、ruff/backend/tests/本脚本、lint/build、六文档链接/diff通过。B12干净源码SHA固定为2fa4a2b；正式附件提交不伪称该附件已经在自身SHA下执行。文档收口后的新head CI必须再次查询，不能沿用db83da5的run。最终head的base/head/tested/actual merge与真实reviews/threads/comments落在[PR #16说明](https://github.com/Gindama713/nchu-web-learning_platform/pull/16)及个人本地交接，避免把文档自身提交SHA写入自身造成循环，也不把#14/#15或旧#12 CI当作本续包结果。

网络留痕：db83da5首次push与随后fetch/push遭本机OpenSSL TLS wrong-version错误；使用仅该命令的schannel后远端读回成功并推送，未降低证书校验、持久修改Git设置或更改CI。此已解除，不再列成业务/环境验收阻断。

复现：根目录`.venv/Scripts/python.exe -m scripts.verify_c12a_seams --output logs/c12a-recheck`；需要当前已安装Chrome/Edge/浏览器可选依赖及空闲5000/5173。前端在frontend运行`npm test`、`npm run lint`、`npm run build`；前端时间测试为组件替身，B12为真实HTTP/UI。

下一轮先fetch/查本续包及#14/#15当前head/base/CI/review：真实评审阻断回所属feature修；若由负责人合入，仅消费最新develop并核对实际merge。C12b优先UI-02/03，各回所属SPEC，不重做C10/C11/C09/C07；依赖就绪后再补R01/R37/I链。C12c材料另开，不开发014/016、不接管队友或CI。

回退保留知识/题目版本/作答/错题/进度/analysis_run/schema一致性备份与增量；本轮无迁移，显示修复不改保存事实。恢复仅使用匹配代码/库，不删历史、不改旧SQL、不开保密旁路。受控SQLite副本不是完整生产恢复。两份个人AI记录继续info/exclude，正式证据全部版本化。
