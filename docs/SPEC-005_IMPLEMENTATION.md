# SPEC-005 / C01 实施与验证记录

> 2026-10-19当前收口：#27—#35及#38修复已合入develop；原004/007/017接口缺陷复验通过，仍缺页面/全组环境另列。131行现为本地81通过/50阻断、集成81通过/50阻断，见[合入后复验与剩余工作](SPEC-010B_POSTMERGE_ACCEPTANCE.md)。以下旧日期、SHA、计数和“待合入/失败”均为当时记录，不覆盖本条当前结论；完整SPEC及课堂未关闭。

> 2026-10-16 C12c材料导航：当前合入、真实评审、两个矩阵版本及交付状态见[个人交付索引](C12C_DELIVERY_HUANG_JUNCHENG.md)和[本轮远程快照](evidence/c12c/entry-state.json)。下文各节保留原日期、SHA及当时事实；旧“未合入/待实现/最新”措辞按其历史范围阅读，不覆盖索引中的当前状态。完整SPEC仍未凭材料整理关闭。

2026-10-17后续核对：[I-01实际能力及005/003图文契约](SPEC-005_I01_RESOURCE_SEAMS.md)补同批真实知识/实验版本/连线成功失败草稿缺交到010C消费、独立知识进度及旧ID/CSV。干净tested96f4f29，handler2通过+4项017契约expectedFailure，Chrome/Edge各7组现成页面检查及12图；017/010C缺页、017窗口/撤权写入/重做及009时间展示缺口均按当前PRD实名记录。005现行契约明确禁img/链接/属性，实际清洗一致；003真实有效PNG在四种kind均415，知识引用契约未定义，图文仍未完成。未改业务源码、APIC/DBD或队友实现，不将下方C01历史待办/旧依赖状态当作当前事实。

2026-10-14 C06追加恢复：005/R38正式聚合已在独立010B feature实现，真实API验证2/3→1/2、2/2、0/0=null、日期不改当前发布集合及旧快照不变；见[SPEC-010B实施记录](SPEC-010B_IMPLEMENTATION.md)。本记录下方保留C01当时证据/恢复点，不再以旧“C06待补”描述本轮聚合状态。003图文、011索引、生产/课堂及完整目标性能仍未关闭；下一开发从010B记录恢复C07页面/成绩/CSV，008未合入时不复制其feature。

责任人：黄俊诚（24201716）。日期：2026-10-13，Asia/Shanghai。依据：[PRD有效验收](PRD.md#accept-spec-005)、[APIC](APIC.md)、[DBD](DBD.md)。状态：005主体实现及真实API链已有CI通过证据，本轮补齐指定版本Chrome/Edge受控浏览器验证；图文资源接入及完整性能目标仍有缺口，PR保持草稿，未关闭SPEC。最新head的CI须按PR实际结果核对。

## 基线与责任边界

初始fetch基线为origin/develop `96601372d3ac6fb6c5391320e2d96ccb13815d66`，从此创建feature/spec-005-knowledge。先独立实施005，没有复制队友feature代码。后续fetch发现001已进入origin/develop `f242d2b8f370cff35cf8f4a76f9a5d3fad20f136`，按GitFlow merge同步到005，合并提交为`f90937ee2578811af878905359eb219d50e68b96`。

同步保留队友create_app、登录/课程/考勤等页面及历史，只增加005 Blueprint和知识组件注册；入口相对新develop为backend/app.py两行、frontend/js/main.js四行，Vite一行启用已采用template的Vue编译器。移除005重复通用异常处理，避免把公共鉴权403转换为500。未接管001/002/010A/014/016逻辑，未自行改CI门禁；工作流和锁文件变化来自同步的develop。

PRD/README声明团队设计评审完成。框架PR #1返回reviews=[]、comments=[]，不作005批准或CP-1教师通过证据。用户本会话要求继续实施、不等待评审证据；此指令不记录为非作者批准或教师验收。005不自动合并或发布。

## 依赖契约与当前缺口

| 子能力 | 负责人 | 当前状态/接入 | 仍需完成 |
|---|---|---|---|
| 001会话/CSRF/Origin | 姜苏豪提供，黄俊诚消费 | 已同步真实require_user/check_csrf；005业务事务取得锁后再验证会话 | Windows真实链及受控浏览器已验证；真实教学账号验收未执行 |
| 001课程/成员 | 姜苏豪 | 通过真实课程创建/成员API产生受控测试课程；越权、撤权、停用已通过CI | 课堂及实际教学账号验收未执行 |
| 公共SQL runner | 姜苏豪（001/019）提供，黄俊诚消费 | 已接入005_knowledge.sql；公共migrate、重复执行、校验和拒绝及备份恢复通过CI | 生产迁移、完整资源备份集和部署演练未执行 |
| 003授权图片资源 | 石佰合提供，黄俊诚接入 | 当前只支持文字/基础HTML/上下标，不支持图片或外部URL | 确认同课程、学生可见的资源图片入口后接入；不代写上传/资源权限 |
| R38统计/011索引联合 | 黄俊诚后续C06/C10 | 005提供当前发布集合、真实完成事实、content_revision/is_foundational | C06补统计null/日期同集合，C10补下架失效及重建失败；本轮不实施其他工作包 |

初始阶段001/runner缺失时005返回503，页面实际auth/session 404显示失败/重试；001合入后的真实API链已解除这一阻塞，不能继续沿用旧缺失结论。FixtureSecurity和HTTP双替身只用于隔离测试，未注册到运行应用。

本轮用户确认队友部分仍未完成。图片阻塞涉及实现及现行契约：APIC§3.1明确禁止knowledge图片/链接及全部属性，DBD的knowledge_point未定义资源引用关系；003入口`GET /resource-versions/{id}/content`要求`intent=view`和逻辑访问`event_id`，只预览受支持的PNG/JPEG等类型并按资源当前权限判权。因此不能仅放开`img src`或使用file_object/公开文件URL。恢复前需石佰合提供真实同课、学生可见的PNG/JPEG版本及权限收紧用例，团队确认知识引用/同课校验、事件ID重试复用和资源撤权时的显示规则，再按两名非作者复核要求同步必要APIC/DBD定义。此处是对接待办，未联系队友、未批准新契约或实现003。

## 实现与数据约束

- 章节：新增/改名；完整ID集合+chapters_revision验证后原子重排，先移动至不冲突非负临时位置再写0至n−1，新增/排序递增revision。
- 知识：教师编辑/发布/下架/基础标记，学生检索/详情；实际持久字段变化递增content_revision，相同值不递增。富文本白名单和字段语义以APIC为单一定义，图文缺口不改写成已完成。
- 收藏/完成：身份来自真实会话，唯一约束保证幂等；下架保留历史，学生各入口隐藏；重复完成保留completed_at，取消后为null。
- 005 SQL只创建chapter/knowledge_point/bookmark/learning_progress和查询索引；版本为005_knowledge，SHA-256按公共runner的read_text(encoding="utf-8").encode()计算。knowledge_migration.py只提供SQL身份和测试辅助，不是第二套runner。初始spec-005-001草案未部署，未重命名真实数据库版本。
- Vue：教师章节/知识维护、发布/下架、基础标记；学生检索/分页/详情/收藏/完成取消；加载/空/错误/重试。排序读取全部分页并核对revision/总数，避免第一页截断；写请求重新取CSRF，登录人变化即拒绝写入并清除旧页面数据。

## 全部有效验收矩阵

| 编号 | 已执行证据 | 未完成/限制 |
|---|---|---|
| AC-01 | 隔离关键词/分页/空结果、真实登录检索通过本地/CI；Chrome/Edge真实检索“程序计数器”、上下标公式、例题及空结果检查通过 | 授权图片图文接入待补 |
| AC-02 | 收藏唯一/幂等/取消/本人隔离、真实登出→401→重登保留通过本地/CI；受控浏览器刷新和重登后状态保留 | 受控课程测试，非课堂验收 |
| AC-03 | 完成/取消/重复完成/持久读取通过；真实进度API与重登通过CI | 自报完成不代表掌握度或成绩 |
| AC-04 | 列表/详情/收藏/进度隐藏草稿/下架；再次发布恢复历史；真实撤权/停用通过CI | 生产/课堂验收未执行 |
| R20（005部分） | 基础标记、revision变更/不变、HTML处理通过 | C10补011下架/索引失败联合；其他模块由各负责人补证 |
| R32 | 缺失/重复/跨课/非法ID拒绝、并发新增和重排、改名/过期revision/原子性通过；真实API及受控浏览器新增/改名/重排通过 | 真实教学课程验收未执行 |
| R38（005部分） | SQLite事实及发布集合2/3→1/2、2/2、0/0，下架保留历史通过 | C06补正式聚合null/from-to输出，不称统计已实现 |
| R22/R45 | 责任/依赖/工作包登记 | 全组工时/技术验证非本包；未核验 |
| R46 | APIC/DBD归属清楚、SQL单一迁移定义；文档链接检查通过 | 接003时继续核对有效定义 |
| R47 | 无005非作者批准记录 | 未核验；不填假批准 |
| NF-SEC | 真实Cookie会话、CSRF/Origin、未知字段、可见越权403、跨课404、撤权404、停用401通过CI；事务内会话复核隔离测试通过 | 非真实教学账号/生产测试 |
| NF-DATA | 真实公共runner重放、校验和拒绝；SQLite一致性备份、恢复库完整性/外键及原会话读取收藏通过CI | 完整资源/电路备份集及生产恢复演练未执行 |
| NF-UI | Chrome 154.0.8037.98 / Edge 155.0.4283.45各8组真实HTTP/UI检查通过；含教师编辑/发布、学生重登持久化、公式/转义、390px、空结果和注入断网后的加载/失败/重试 | 本机headless受控数据，非真实教学账号/课堂/生产验收；图片缺口另列 |
| NF-PERF | 已核对本机环境：WSL Ubuntu为8核、约7942MiB内存；Docker守护进程未运行，真实评测worker未实现 | PRD§8的4核8GB Linux/50会话/单worker联合目标未执行，不以Windows浏览器时长或WSL环境探测替代性能验收；沙箱非005实现 |

### 测试入口与复核定位

以下索引对应上表已有证据，不新增验收编号或提升验收状态。`test_knowledge.py`使用隔离库及鉴权替身；`test_knowledge_integration.py`使用真实001会话、课程API与公共迁移。前端`.test.js`使用HTTP替身，只证明组件/客户端行为；真实浏览器证据以原始JSON的`tested_head`和`checks`为准。2026-10-13本轮仅整理索引，未重跑业务测试。

| 验收项 | 具体测试入口/原始结果定位 |
|---|---|
| AC-01 | [test_knowledge.py](../tests/test_knowledge.py)的`test_ac01_search_pagination_and_visibility`；[真实联测](../tests/test_knowledge_integration.py)的`test_real_login_course_publish_bookmark_progress_and_relogin`；浏览器`search_formula_example_xss_escape_student_controls`及`empty_search_clears_detail`；图片仍阻断 |
| AC-02 | `test_knowledge.py`的`test_ac02_bookmark_idempotency_reopen_and_user_isolation`；上述真实登录联测；浏览器`bookmark_progress_refresh_logout_relogin` |
| AC-03 | `test_knowledge.py`的`test_ac03_progress_is_durable_idempotent_and_resettable`；上述真实登录联测；浏览器`bookmark_progress_refresh_logout_relogin`及`unpublish_hides_republish_preserves_cancel_states` |
| AC-04 | `test_knowledge.py`的`test_ac04_unpublish_all_student_entry_points_and_keep_history`；上述真实登录联测；浏览器`draft_hidden_publish_real_api`及`unpublish_hides_republish_preserves_cancel_states` |
| R20（005部分） | `test_knowledge.py`的`test_r20_revision_and_safe_markup`；浏览器`search_formula_example_xss_escape_student_controls`；011索引联合待C10 |
| R32 | `test_knowledge.py`的`test_r32_atomic_complete_order_revision_and_rename`、`test_r32_concurrent_add_vs_order_cannot_lose_new_chapter`及`test_http_teacher_flow_cross_course_and_strict_input`；[knowledge-client.test.js](../frontend/js/knowledge-client.test.js)的跨页完整集合、revision变化/重复ID拒绝及重排冲突用例；浏览器`teacher_add_rename_atomic_reorder` |
| R38（005事实） | `test_knowledge.py`的`test_r38_current_published_set_and_retained_facts`；仅核对当前集合和真实完成事实，正式统计null/from-to仍待C06 |
| NF-SEC | `test_knowledge.py`的`test_permission_revocation_global_role_and_admin_no_teacher_privilege`、`test_http_closed_security_csrf_and_validation`、`test_session_revoked_between_dispatch_and_transaction_prevents_write`；真实联测`test_real_csrf_origin_course_revocation_and_deactivation`；[knowledge-view.test.js](../frontend/js/knowledge-view.test.js)的身份变化清空与拒绝写入用例 |
| NF-DATA | `test_knowledge.py`的`test_migration_preconditions_rollback_checksum_and_no_silent_init`、`test_failed_write_rolls_back_every_change`、`test_migration_ddl_and_bookkeeping_share_rollback_boundary`；真实联测`test_actual_runner_replay_backup_restore_and_checksum_rejection`；生产和完整资源备份仍待补 |
| NF-UI | [browser-results.json](evidence/spec-005/browsers/browser-results.json)的chrome/msedge各8项`checks`、版本、`page_errors`和截图；[复现脚本](../scripts/verify_spec005_browsers.py)的`verify_browser`。其中`390px_no_horizontal_overflow`核对窄屏，`injected_network_loading_failure_retry`核对加载/失败/重试 |
| NF-PERF | 目标环境/真实worker尚未就绪，没有性能测试入口或通过证据；不以浏览器耗时替代 |
| R22/R45/R46/R47 | 分工/依赖及契约登记见本记录和PRD；代码批准以PR真实reviews为准，自动测试不证明团队批准 |

## 真实测试与失败记录

同步前：Windows Python3.13.12/Node24.14.0，后端19隔离测试、前端13测试、ruff/lint/build/文档检查通过。首次夹具未关闭SQLite连接导致9个tearDown错误，修复后通过；浏览器发现fetch绑定Illegal invocation，修复并加回归测试。

同步后：Windows本机全量后端39测试（包含3个真实001集成测试）通过，前端14测试（增加队友API包装测试）及lint/build、全仓ruff、文档链接/diff检查通过。公共锁定依赖安装曾因镜像断流和官方PyPI代理连接失败中断；提前运行真实联测因pandas未安装而ImportError。依赖重试安装同一requirements.lock后成功，随后39测试通过；未改版本或公共配置，不隐去先前环境失败。

实际浏览器：Codex IAB受控库，教师真实登录→新增ALU章节→改名→上移原子排序→新增基础知识草稿/正文/例题→发布；学生真实登录→检索程序计数器→收藏/完成→刷新重新读取→退出/重登→两状态保留。390×844响应式布局无横向溢出，视口已重置。IAB版本无法从受限DOM读取，未宣称指定Chrome/Edge双浏览器兼容性验收通过。所有账号/数据只在隔离验收库，数据库与密码/令牌未提交；运行应用没有FixtureSecurity。

截图证据：[学生重登后的收藏/完成](evidence/spec-005/student-relogin.jpg)、[390px学生详情布局](evidence/spec-005/student-mobile.jpg)。

CI：同步提交f90937的[Actions 38365996636](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38365996636)已查询jobs和测试日志，policy/lint/test/build/required全部success。Python3.12后端39测试通过，Node22前端14测试通过。其中tests/test_knowledge_integration.py三项真实受控库集成测试全部ok：公共迁移/备份恢复/校验和、CSRF/Origin/课程撤权/停用、登录/发布/收藏进度/登出重登。它们使用实际create_app、会话Cookie、公共runner及API，只有初始管理员/教师账号在受控库bootstrap，没有模拟鉴权、课程或迁移。ci-grader在develop按现有规则skipped，不视为真实Logisim通过。

### 本轮指定版本浏览器补证（2026-10-13）

fetch后origin/develop为`ca8ae47f6ad987d1af11c4212a116c4fb7ece5bc`（队友PR #5考勤/识别修复），通过merge commit `273168e7dfbd9e35da1bdb009c6dbe9e870a517c`无冲突同步，未改写队友历史。本机同步后后端40测试、前端14测试及ruff/lint/build/文档链接/diff检查通过。

新增[可重复验收脚本](../scripts/verify_spec005_browsers.py)和[可选浏览器依赖](../backend/requirements-browser.txt)，代码提交`bdfa25c2cfde83c6d0a128af859422dae5b2dae2`。脚本自动使用临时库、公共迁移、真实HTTP及Vue页面；仅初始管理员/教师bootstrap，学生注册/课程/成员与005操作走真实接口；不读取现有业务库或用户浏览器配置，不保存密码、Cookie或token。要求本机安装Chrome和Edge，空闲5000/5173端口及既有前后端依赖。

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-browser.txt
.venv/Scripts/python.exe scripts/verify_spec005_browsers.py
# 默认报告写入被忽略的logs/spec-005-browsers；正式留证可指定另一个目录：
.venv/Scripts/python.exe scripts/verify_spec005_browsers.py --output docs/evidence/spec-005/browsers
```

执行人：黄俊诚任务下的Codex自动执行；2026-10-13 19:50:09—19:50:28（Asia/Shanghai，仅此测试实测时段，非整个开发工时）。Windows 11 10.0.26200 / Python 3.13.12 / Node 24.14.0 / Playwright 1.63.0，headless Chrome 154.0.8037.98、Edge 155.0.4283.45；tested_head为上述bdfa25c完整SHA。两个浏览器分别完成8组检查（共16组），结果通过，page_errors=[]，桌面1440×1000及390×844截图已目视检查：

- 教师章节新增/改名/排序、草稿学生404、发布可见。
- 学生关键词检索、sub/sup公式及例题；恶意img/script/onclick被移除，`<CPU>`转义文本正确渲染，脚本文本仅作为普通文字，未执行。
- 收藏/完成在刷新及退出重登后保留；下架后读取404且清空，重新发布恢复历史，可取消收藏/完成。
- 390px页面无横向溢出；空检索清空旧详情；注入网络挂起/断网时加载提示及按钮禁用、错误/重试可见，恢复网络后真实API重载成功。仅网络故障项是注入条件，没有替换成功响应或模拟鉴权。

原始结果：[browser-results.json](evidence/spec-005/browsers/browser-results.json)。截图：[Chrome桌面](evidence/spec-005/browsers/chrome-desktop.jpg)、[Chrome窄屏](evidence/spec-005/browsers/chrome-mobile.jpg)、[Edge桌面](evidence/spec-005/browsers/msedge-desktop.jpg)、[Edge窄屏](evidence/spec-005/browsers/msedge-mobile.jpg)。脚本结束自动关闭新建浏览器、服务器及临时库。浏览器测试为本地可选验证，未加入或改变队友CI工作流。

环境失败记录：Context7前两次Playwright查询失败，第三次成功；阿里云镜像Playwright下载停滞，停止该安装后改用官方PyPI成功安装同一1.63.0版本，未改业务依赖锁。初次新增脚本ruff失败（导入/UTC及安全错误报告边界），修正后全仓检查通过。两个浏览器初次运行及在代码提交后正式留证运行均通过，无业务代码修复。

## 提交、PR与恢复点

| 部分 | SHA | 远端状态 |
|---|---|---|
| 后端独立实现 | 8ed56b56d24b0e4de536d0bb7a7b7c01ade68a5c | 已推送005 feature |
| Vue页面及边界 | e7189ad8e375319ba50af74b8b5ab440e1045b44 | 已推送 |
| 001消费/SQL契约 | 0e38730b59a4224bf32fb55ee0ac3e2790201708 | 已推送；旧CI 38344996554通过 |
| 第一轮交接证据 | 001c903e58a78052ac47ccfe7a106348fddfbcd4 | 已推送 |
| 同步已合入001并接入 | f90937ee2578811af878905359eb219d50e68b96 | 已推送；CI 38365996636通过 |
| 同步队友PR #5 | 273168e7dfbd9e35da1bdb009c6dbe9e870a517c | 005 feature同步；本地40/14测试通过 |
| 可重复双浏览器验收 | bdfa25c2cfde83c6d0a128af859422dae5b2dae2 | 指定Chrome/Edge各8组通过，原始报告对应此tested_head |
| 双浏览器正式证据 | 5bb364117c3b6c35e7afd64ad46d9a379278a524 | 已推送；对应CI 38393278642通过，浏览器tested_head仍为bdfa25c |

[PR #4](https://github.com/Gindama713/nchu-web-learning_platform/pull/4)仍为draft，目标develop。005本身未合并、没有发布；不因旧head CI成功放行新head。文档后续提交的SHA与新CI在会话交接及PR中补录。

2026-10-13 19:59（Asia/Shanghai）恢复核对：fetch后develop仍为`ca8ae47`，本地/远端005 feature及PR head均为上述`5bb3641`，develop已包含于feature，无需再次merge。重新查询[Actions 38393278642](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38393278642)及jobs，policy/lint/test/build/required全部success、grader skipped；PR为open/draft、未合并，reviews为空。队友未完成的依赖仍保留。本轮随后修正README过期浏览器说明并补测试入口索引，没有改变业务或APIC/DBD契约；新文档head的CI另行核验。

下一恢复：继续C01同分支fetch最新develop并核对PR最新head/CI。浏览器双端指定版本已补证；优先等003真实授权图片入口就绪并完成上述APIC/DBD对接，再实施图文及资源撤权联测。目标Linux4核8GB/50会话/worker性能仍未执行，需队友worker及目标环境；不以本机WSL探测冒充通过。001及公共runner已接入，不重做或重复当缺失阻塞。不接管003、不合并005或发布；PR保留draft，真实非作者批准/课堂验收另记。C06补R38正式聚合、C10补索引失效。

用户本轮已明确调整计划：允许先推进C02中不依赖队友的部分。006从核验的origin/develop建立独立feature，先做C02a题目模型校验和不可变版本；不复制未合入005代码。Question的knowledge_ids仍须非空并引用真实同课知识，因此005未合入时相关创建/编辑和知识标签联测须明确阻断，不能去掉标签约束或用夹具冒充真实接入。此调整不解除005缺口或合并门禁。
