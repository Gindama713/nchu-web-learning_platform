# SPEC-011 检索问答实施记录

负责人：黄俊诚（24201716）。范围为C10，依据[PRD§4.3](PRD.md#qa-recommendation-acceptance)、[011有效验收](PRD.md#accept-spec-011)、[APIC](APIC.md)第5.2节及[DBD](DBD.md)第3/5节。只返回知识检索片段与出处，不接生成模型、向量库或新调度平台；不开展C11。

## 接入基线与评审边界

2026-10-15 fetch后origin/develop=`cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb`，从该基线新建`feature/spec-011-qa`。远程没有同名011分支。PR #13仍open/非draft、head=`a6870326e31be2018d9fb135ef29b099d82aa6d4`；真实reviews、review_threads、issue comments均空。当前head的[Actions38678908036](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38678908036)已重新查询，policy/lint/test/build/required均success，grader按develop规则skipped。没有实际评审缺陷或本轮阻断项；保留013评审状态，不复制其未合入代码，不重复C08/C09、C07或010B专用联测。

## C10a 算法、索引与持久化

`qa-tfidf-v1`查询与语料共用NFKC（包括HTML字符实体）、英文小写、去标签和空白合并。固定PC/ALU/ACC/IR别名用英文词边界（字母/数字/下划线不可紧邻，中文可紧邻），长缩写优先。每个当前已发布知识按title/content/example组成一篇文档，scikit-learn字符1—3gram、min_df=1、平滑IDF、L2归一化。未舍入余弦相似度≥0.10后按原值降序、知识ID升序取top_k；响应数值round到6位，页面补足6位显示。摘录仅去HTML的正文前200字符。

语料revision为按ID排序的当前已发布知识id/title/content/example/content_revision的规范JSON SHA-256；空语料也有稳定revision。内容或发布集合变化在下次请求的快照及最终写事务校验中立即使旧缓存失效，不依赖定时任务或005进程内通知。各应用实例持有可丢弃完整索引对象；进程重启/备份恢复从事实重建，不反序列化pickle或信任数据库ready标记直接返回旧内容。

读取快照后释放事务，在写锁外构建/搜索。短BEGIN IMMEDIATE内重新核验会话、课程访问及当前revision；变动则最多重新读取/构建3次，持续变动返回503 INDEX_UNAVAILABLE。完整提交qa_index与qa_query后才原子替换缓存。构建/搜索失败丢弃该课缓存，当前revision落failed/INDEX_UNAVAILABLE，返回503且不含旧片段；下一次请求可重建恢复。持久化任一步失败整体回滚，不发布半成品。其他进程同样受最终数据库revision门控。

新增`011_qa.sql`，不改旧迁移。qa_index一课一行记录revision/算法/built_at/status/error_code；qa_query仅保存会话本人、课程、最多500字符原问题、命中ID、对应未舍入相似度、revision及算法版本。无查询历史读取端点，不能凭用户输入查询他人记录；未授权/非法请求和失败重建不写成功查询记录。复用001/005会话、Origin、CSRF及课程访问；接口按APIC的L可查，管理员同样只检索已发布语料。`Cache-Control: no-store`。

Context7已查询当前scikit-learn TF-IDF/归一化、Vue watcher异步失效及Playwright Python浏览器验证文档；没有升级依赖。业务实现、证据与正式记录版本化，两份个人记录继续info/exclude。

## 分段验证与待续

C10a：`python -m unittest tests.test_qa -v`，15项通过（11.746秒）；5项算法组件测试、10项真实001/005 Flask HTTP-handler/SQLite集成测试，账户仅bootstrap，课程/学生注册/成员/章节/知识更新及下架均走真实业务接口。包括并发查询、第二线程实际005更新/撤权、构建失败夹具、qa_index/qa_query触发器故障回滚及受控SQLite备份恢复；不等同真实网络socket、浏览器或生产恢复。首轮夹具同线程嵌套请求失败已改成独立线程，旧失败不记通过。页面/组件、真实双浏览器、全量回归及PR/当前head CI将在后续节登记，尚不能据此关闭完整SPEC。

回退：保留知识/用户/会话/查询及配套schema的一致性备份和增量；用匹配代码与数据库恢复，索引缓存可丢弃重建。不得删除历史查询来掩盖失败、不改旧SQL或共享分支。两名实际非作者复核、目标Linux4核8GB/50会话性能、生产恢复及课堂证据须单独登记，不由本地自动测试代替。

## C10b 页面与第一次集成验证

问答页接入现有Vue课程页面，沿用005色彩、排版与出处阅读方式；查询仅发question/top_k，写前刷新真实会话/CSRF。显示真实知识ID、去标签片段、6位相似度、语料revision和算法版本；通过005详情读取最新正文。loading/no_match/empty_corpus/失败/显式重试及无权限后重新加载分别处理。修改问题/课程、切换身份或销毁组件会废弃未完成响应，失败清除此前片段。片段始终作为文本渲染，详情仅渲染005已清洗的无属性HTML。

7项新组件测试通过，第一次整套前端70项通过，lint/build通过。`scripts/verify_spec011_qa.py`在Chrome155.0.8059.41/Edge155.0.4283.45各9组通过，page_errors=[]，包含真实socket HTTP、005发布/改文/下架、PC/ACC别名、零向量、查询记录、成员撤权及390px；两种构建失败为明确注入的故障夹具，网络、页面与其他进度操作仍是真实请求。该轮tested_head=66b7ad2加尚未提交的页面/脚本，不能称干净head；提交同步后的干净复验结果另记。

开发期间用户告知组长已合入013。重新fetch/查询确认[PR #13](https://github.com/Gindama713/nchu-web-learning_platform/pull/13)已merged，实际merge=`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`，最终head=`4710a56399d3c3eaf5a97ceaba142fa403263e07`。真实批准为Gindama713（2026-10-15T04:06:52Z），review_threads=[]；当前head的Actions38679487882 policy/lint/test/build/required成功、grader skipped。4710a56相对a687032只有013记录/浏览器证据更新，未发现业务代码增量。将通过merge消费已合入develop并验证接入，不重复实现013，不把一名批准补写成两名。

## 同步后验证与当前恢复点

同步前011树全量后端182项通过282.075秒、前端70项，保留为旧基线结果。011页面提交`0aada21`后，以merge `c3a4b52c7f6ca4421cf9549ebf8a876ac24869a0`消费已合入的origin/develop f9c49b1，无冲突；只消费013成果，没有改写其代码。同步后17项011专题通过22.344秒，新增真实索引失败期间006公开练习提交201及连续真实005更新三次后503/恢复；阈值边界仍明确属于算法组件夹具。

最终实现提交`36854081b1ba991a89bacbf7d797ab0620619ae3`已推送；本地完整后端194项通过344.743秒、前端76项通过，ruff（含本轮浏览器脚本）/lint/build/六文档链接/diff通过。[完整后端原始日志](evidence/spec-011/c10-backend-tests.txt)、[前端原始日志](evidence/spec-011/c10-frontend-tests.txt)已版本化。全量自动回归包含develop既有013/010B等用例，没有重复开发或另起其专用联测。

干净3685408（dirty_paths=[]）的Chrome155.0.8059.41、Edge155.0.4283.45各9组通过，page_errors=[]；[报告、JSON及6图](evidence/spec-011/browsers/REPORT.md)包含真实发布/改文/下架、旧revision禁用、故障503/恢复、实际作答201、延迟响应清除、撤权及390px。已目视核对截图；第一次未提交页面的浏览器结果只作为历史，不替代本次干净证据。

实现head的[Actions38680739233](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38680739233)已单独核验policy/lint/test/build/required全部success，grader按develop规则skipped；真实ci-test日志194项146.416秒、前端76。head=3685408、base=f9c49b1、tested merge=`46426f684cf97dbb0f6d535039a5d6be37db9338`，它是CI测试引用，不是实际合并。[CI固定快照](evidence/spec-011/c10-code-ci.json)和[日志摘录](evidence/spec-011/c10-code-ci-test-summary.txt)保留对应SHA。

[PR #14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14)目标develop；最初草稿用于等待当前树完整验证，本地已就绪后转待评审。收口证据/本记录提交后，最终文档head的CI须重新核验，不能套用3685408的run；当前head检查与真实review以该PR为准，最终核验结果写回PR说明和本地计划第6节/个人交接第10.1节。最后读取时reviews=[]、review_threads=[]，尚无011实际非作者复核。个人计划的两名复核目标与GitHub required approvals=0分别记录，不把课程复核目标虚称平台合并门禁。

本轮C10实现及适用本地业务验证已完成，正式SPEC未关闭：R47真实复核、目标Linux4核8GB/50会话性能、生产恢复和课堂证据仍缺。下一恢复先fetch并核验#14当前base/head/CI/review；按实际缺陷修复，不重复C10/C09/C07/010B专用联测。C11推荐未开始，须另按任务卡推进。未自行合并、部署或发布，也未接管队友业务。

## 适用验收与证据性质

| 范围 | 本轮实现及验证 | 证据/限制 |
|---|---|---|
| AC-01 | “PC 有什么作用”命中真实已发布程序计数器，显示片段/出处 | 001/005实际业务数据；真实socket HTTP与双浏览器，见[报告](evidence/spec-011/browsers/REPORT.md) |
| AC-02 | 未知字符/零向量返回no_match；无已发布知识返回empty_corpus；空词表无成功命中 | 真实HTTP/UI空结果；空词表另由算法组件测试证明 |
| AC-03 | 真实正文更新、下架、再发布改变revision，未发布草稿不进入语料；构建中更新则重新取快照 | 真实005 HTTP及第二线程handler/独立SQLite连接；不是直接灌语料表 |
| AC-04 | 算法版本、当前revision及对应未舍入分数持久化；页面按6位显示，标为知识片段 | 数据库实际记录断言、真实出处正文和浏览器截图；未接生成模型 |
| R20（011部分） | 失败503 INDEX_UNAVAILABLE、清除旧缓存；重建及query记录原子提交/替换 | 构建失败为明确mock夹具；qa_index/qa_query触发器故障验证真实事务回滚；真实网络/UI观察；不代做014预警/012推荐 |
| R35（011部分） | NFKC/HTML实体/小写/空白，四别名及英文边界，1—3gram/平滑IDF/L2，原始0.10边界、未舍入排序、同分ID、top_k/200字符 | [17项专题原始日志](evidence/spec-011/c10-focused-tests.txt)；double阈值边界为算法组件夹具，另有真实HTTP相同语料排序 |
| R35异常隔离 | 三次真实并发改文后有限503/恢复；失败不阻断真实006练习提交201及005进度 | handler与真实socket HTTP各有验证，不只声称其他模块应当可用 |
| NF-SEC/UI/DATA适用部分 | 当前会话/CSRF/Origin/撤权/跨课/输入及纯文本片段；过期响应丢弃；双浏览器390px；迁移重放/校验及受控备份重建 | 本地自动验证；不扩展为生产恢复、50会话性能或课堂结论 |
| R22/R45 | 本人分工/依赖、固定算法输入/预期/实际和证据登记齐全；未扩大到其他人的模块 | 共通项目检查点仍由019组织，不能以C10代码代替全组门禁 |
| R46 | QA接口仍以APIC第5节、算法以PRD§4.3为单一业务定义；DBD补齐qa_query.algorithm_version/原始分数含义 | 新迁移和共享入口影响在PR说明，权限/API/数据库须实际复核 |
| R47 | [011 PR #14](https://github.com/Gindama713/nchu-web-learning_platform/pull/14)待实际非作者评审 | 不用作者自测或013的一份批准代替011的两名非作者复核；尚未通过 |

正式原始证据只包含受控合成账号和必要结果，不包含密码、Cookie、CSRF、数据库文件或真实学生答卷。查询原文只在受控数据库保留，不导出到浏览器报告。
