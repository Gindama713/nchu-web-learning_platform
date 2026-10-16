# SPEC-012 个性化推荐实施记录

> 2026-10-16 C12c材料导航：当前合入、真实评审、两个矩阵版本及交付状态见[个人交付索引](C12C_DELIVERY_HUANG_JUNCHENG.md)和[本轮远程快照](evidence/c12c/entry-state.json)。下文各节保留原日期、SHA及当时事实；旧“未合入/待实现/最新”措辞按其历史范围阅读，不覆盖索引中的当前状态。完整SPEC仍未凭材料整理关闭。

## 2026-10-15 C12b时间显示增量（最新）

C12a-UI-03“依据截止”已改为明确Asia/Shanghai/h23，UTC周日15:59:59显示周日23:59:59、16:00显示周一00:00。空值为“—”，非法/无时区日期为“时间异常”，不按客户端时区猜测。改动仅RecommendationView内显示与回归；source_until、28天半开UTC窗口、排序/理由/入口资格、原始事实/快照不变，无迁移或公共框架重构。没有复制未合入010B/011或006 C12b显示修复，006/008共用缺口只由006 PR #17主修，012后续仅经已合入develop消费。

继续原feature/spec-012-recommendation及open/非draft [PR #15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15)。base仍`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`；本轮接入重新fetch且独立读取#14/#15/#16的CI/reviews/threads/comments，必需成功、grader按develop跳过，实际评审/讨论均为空，无actual merge。代码fd64db75593adf18b938c5ed6b16fd61ffa7cd65、截图修正03a03c7611bd2d00e07a33d8f8bd5842bc36f9c9已分段推送；最终证据head的CI与真实评审独立核验后记录于PR及C12a正式记录，不沿用旧head。

仅做受影响验证：[8项组件/HTTP替身](evidence/spec-012/c12b-time/components.txt)，新增2项覆盖跨日/周界/明确时区、空/异常/无时区与原UTC对象不变；[2项既有真实handler/SQLite](evidence/spec-012/c12b-time/handler-tests.txt)通过4.659秒，覆盖真实28天半开边界及身份级保密入口/推荐故障不阻断原提交。lint/build、ruff本脚本、六文档/diff通过。原C11算法/权限/故障/全部reason/课堂缺口仍按原固定证据复用，不重跑C11完整专题或C10/C09/C07/008→010B专用链。

[正式真实HTTP/浏览器报告](evidence/spec-012/c12b-time/report.json)固定干净tested=`03a03c7611bd2d00e07a33d8f8bd5842bc36f9c9`，dirty_paths=[]，Chrome155.0.8059.41（UTC）/Edge155.0.4283.45（America/Los_Angeles）各3组，page_errors=[]。真实005知识/基础标记、006公开题及推荐练习入口；API source_until保持`2026-10-18T15:59:59.000Z`/`2026-10-18T16:00:00.000Z`，渲染前后GET data完全一致；真实UI练习201、原键201字节重放样本仍1、DB created_at仍UTC。账号bootstrap与TEST_NOW为受控夹具，非课堂账号/生产测量；空/异常时间只在组件替身验证，不伪造真实API非法值。

同目录两张390px截图均目视确认截止/时区可读且页面无横向溢出。首次fd64db7干净浏览器DOM/HTTP通过，但Edge局部截图空白，改为截图前让完整卡片容纳于390×1200视口，03a03c7重新干净验证并取证；不将空图称为目视通过。复现：`.venv/Scripts/python.exe -m scripts.verify_c12b_recommendation_time --output logs/c12b/recommendation-recheck`。课堂/真实非作者复核、develop集成、Linux4核8GB/50会话、生产同点恢复/90天保留、Gitea及队友I-02依赖仍阻断，完整012未关闭。未自行合并、部署、发布或发送消息。

负责人：黄俊诚（24201716），范围为C11。依据[PRD§4.3](PRD.md#qa-recommendation-acceptance)、[012有效验收](PRD.md#accept-spec-012)、[APIC§5.1/5.2](APIC.md)及[DBD§3/4](DBD.md)。

## 接入基线与边界

2026-10-15 fetch后从origin/develop `f9c49b19c59053be2b171e0b7f2a35d1e050e57e`独立建立feature/spec-012-recommendation。实时读取011 PR #14仍open/非draft，head `bbd9ecdb151cab0ff7a34e94261b5378ceabfb74`、base develop/f9c49b1；reviews、review_threads、会话评论均为空。同head两次Actions38681339662/38681315802均completed/success。保留其评审状态，没有复制未合入011，也没有自行合并。

仅消费已合入001/005/006/008/010B事实。不依赖看板HTTP、不接大模型/向量库/调度平台，不建推荐缓存或新事实表，不开展014/016、C12整包或队友模块。

## C11a 事实、算法与API

`GET /courses/{id}/recommendations`仅会话学生本人；严格接受单个limit，默认5、范围1—20，未知/重复参数400。成功及失败均no-store。复用010B `knowledge_analysis.extract/metrics`，以同一读事务提取当前发布集合、本人进度和真实客观作答；窗口沿用APIC左闭右开 `[source_until−28天,source_until)`，时间统一UTC毫秒。漏答、简答排除，practice/answer不同source去重，固定版本多标签分别计点；没有把标签样本数之和当总体答题数。

recommend-v1用精确有理数计算未舍入排序分数和0.8边界；全候选n之和为0才冷启动。基础且未完成项score=1、mastery=null、ID升序；非冷启动剔除已完成且n≥5且m≥0.8，其他按固定公式/原始分数降序及ID升序截limit。reason与空结果优先级严格沿用PRD；序列化score至6位精度，页面固定显示6位，不称预测概率。

每个question先取当前最新版本，再过滤同课、未归档、客观、显式开放、本知识点标签及006身份级保密保护；从合格版本取最小ID，无则null。旧公开版本不替代最新私有/简答/已换标签版本。推荐只返回契约字段，不带题干、标准答案或解析；实际入口仍重新调用现行006鉴权/练习服务。

计算在读事务外，返回前重新授权并按同一截止重提取事实比对；知识/基础标记/进度/练习资格变化后重算，最多3轮，持续变动503 RECOMMENDATION_UNAVAILABLE。数据库读取或计算失败503，不保存半份结果，不阻断原有作答链。只增加推荐blueprint及app必要注册，没有修改001鉴权/006判分/010B口径或迁移。

首次分段验证：13项通过（3项算法组件夹具、10项真实handler/SQLite，14.744秒）。含真实005基础标记/进度/下架、006固定版本练习及幂等、多标签、n=5/m=.8、28天边界、008真实发布/partial提交/漏答/简答/批阅、权限和重核验、失败期间实际练习/整卷201、受控备份恢复。异常保密旧数据与计算故障明确为夹具，不称自然生产故障。页面及真实socket HTTP/双浏览器验证待C11b补齐。

## C11b 学生页面与分段验证

学生“个人学习推荐”提供课程/数量、显式刷新、所有reason中文说明、样本/掌握度/6位排序分数、截止/算法及知识出处。无合格练习显示说明；来源使用005当前详情及其既有净化正文/例题。打开来源或练习前重新请求当前推荐并检查对应项；练习事件只携带课程/知识/固定版本指针，原006组件从当前公开列表寻找该版本，找不到则拒绝替代。原组件继续负责提交/保密/幂等重试，未知提交结果尚未确认时不切换到其他推荐练习。

刷新、数量/课程/身份变化使旧结果失效；异步迟到响应不能恢复旧推荐，权限/读取失败清除来源和结果，显式重试恢复。推荐失败不会卸载练习组件。共享入口仅main组件注册/事件连接与PracticeView的可选entry，不改既有提交/判分规则。

页面首次验证：前端77项、lint/build通过；未提交树的Chrome/Edge各7组真实socket HTTP/UI通过，覆盖真实005基础/进度/下架、006空答和幂等重放/真实五次作答、最新合格练习版本、来源净化、n=5/m=.8过滤、全部掌握、无练习、服务端计算故障503期间实际练习201及恢复、服务端延迟真实响应丢弃、撤权404/课程移除/恢复、账号停用和390px。第一次脚本定位错误及未等待练习加载已修正，正式证据将使用提交后的干净head重跑；这些调试运行不作为最终基线。完整后端回归仍在运行，当前不能称最终CI成功。

## 当前验证与证据

实现/分段提交：`b1368e7`后端、`f508192`页面/入口与验证脚本、`e8da2410c87c1cf2173fad36aaf92fcacdf46e38`脚本诊断lint收口，均推送本人012 feature。起点远端状态单独保存于[接入快照](evidence/spec-012/c11-start-remote.json)，不能拿011 CI代替012。

本地完整后端190项通过241.741秒、前端77项通过，13项012专题14.753秒（3算法组件、10真实handler/SQLite）。[后端完整日志](evidence/spec-012/c11-backend-tests.txt)、[前端日志](evidence/spec-012/c11-frontend-tests.txt)、[专题日志](evidence/spec-012/c11-topic-tests.txt)均保留实际输出。后端全量回归包含develop已有测试，没有重开C09/C07/010B专用联测。ruff（backend/tests及本轮浏览器脚本）、前端lint/build、六文档链接及diff检查通过；浏览器诊断代码曾有多余noqa，已在e8da241修复并重新检查，不将旧失败隐去。

干净e8da241（dirty_paths=[]）的Chrome155.0.8059.41、Edge155.0.4283.45各7组通过，page_errors=[]；[报告/原始JSON及6图](evidence/spec-012/browsers/REPORT.md)已版本化并目视。真实HTTP503及作答201、撤权404均有实际服务响应；故障/延迟由明确服务端夹具注入，不能称生产故障自然复现。原始分数舍入前排序、大计数近同分等使用算法组件夹具，不能称真实课堂大样本。

## 适用验收逐项登记

| 验收 | 当前证据/结论 |
|---|---|
| AC-01 | 真实本人1次错答、多标签、0样本、充分样本的公式/顺序；3算法组件和真实practice/008 partial题目事实核对；浏览器真实作答改变推荐 |
| AC-02 | 每项reason按foundational/insufficient_sample/weakness/incomplete优先级，样本/掌握度/6位分数、真实知识出处与可用入口；组件及双浏览器 |
| AC-03 / R20适用 | 无已发布知识优先、无基础标记、基础项已完成、基础标记及完成状态真实变化；不造基础候选、不扩展预警/识别/QA验收 |
| AC-04 | n=4与n=5/m=.8、完成与掌握组合、原始分数及同分ID排序、limit1/5/20与非法输入；真实n5及已完成过滤/全部掌握 |
| R34 | 复用010B事实，不重复累计总体；固定版本多标签各点计样本；practice/answer相同数字ID仍不同样本，幂等重放不增样本，漏答/简答排除，空items元信息完整 |
| R35 / 算法追加 | 冷启动仅所有候选n总和=0；n=0/1错误/充分掌握/全部完成/空课；28天左闭右开边界（下界前/下界/上界前/上界/上界后），未舍入排序/ID及快照一致性；故障期间实际练习和整卷201 |
| R22 / R45 | 本人C11/既有事实依赖独立留证，分段提交与浏览器重放脚本；全组计划工时、固定引擎/016等由019/原负责人登记，本轮不代验 |
| R46 | PRD算法/reason为唯一有效定义；APIC5.1统计及5.2实现接入口，DBD不新增表、不改旧SQL；本记录/README只说明实现与证据 |
| R47 | 待真实非作者复核，不以自动化测试或AI自查代替课程复核；个人计划两名目标与GitHub required approvals=0分别记录 |
| NF-SEC / UI | 当前会话学生/跨课/他人参数/撤权/停用、权限在计算后复查；来源净化沿用005，推荐不含标准答案，异常保密夹具无入口；加载/空/失败/显式恢复/迟到响应/双浏览器/390px |
| NF-DATA | 本地SQLite一致性备份、integrity_check及公共迁移重放后推荐一致；不新增推荐存储，事实缺失503；生产恢复演练未完成 |
| NF-PERF / ISOLATION | 本地回归耗时仅为测试耗时，未完成目标Linux4核8GB/50会话实测；不引入执行沙箱/新平台，保留原隔离边界，不代验018 |

## 下一恢复点与回退

[PR #15](https://github.com/Gindama713/nchu-web-learning_platform/pull/15)已创建，open/非draft→develop。证据head `d6617280888a148506b005a9bd1c51a04f681977`的[Actions38694148590](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38694148590)实际policy/lint/test/build/required全部success，grader按develop规则skipped；读取真实ci-test日志确认190项185.343秒及前端77项。base=`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`、tested merge=`108f8fbef3b566a85bcfeb3d02b4dd37016b6300`是CI测试引用，非实际合并。[固定CI快照](evidence/spec-012/c11-code-ci.json)及[日志摘录](evidence/spec-012/c11-code-ci-test-summary.txt)对应此head，不沿用011结果。

最后读取真实reviews=[]、review_threads=[]、comments=[]，尚缺012实际非作者复核。最终收口文档提交的新head仍须独立核验，其最新Checks/真实评审以PR为准，核验结果同步PR说明和本地计划第6节/个人交接10.1；不能把本段d661728的run冒充后续head结果。本轮C11实现及适用本地验证已就绪，完整SPEC仍待真实复核/合入、目标性能、生产恢复及课堂证据。禁止自行合并、部署或发布。

下一轮先fetch核验develop/012 PR的当前base/head、必需jobs与真实review/thread，再按所属SPEC实际问题修复；保留011 PR #14的独立评审状态。不重复C10/C09/C07/010B专用联测，不扩展C12整包。回退使用匹配代码及知识/作答/进度/schema一致性备份；不删除历史事实、不覆盖旧迁移，没有推荐缓存需要清理。
