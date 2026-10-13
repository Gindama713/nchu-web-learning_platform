# SPEC-005 / C01 实施与验证记录

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

[PR #4](https://github.com/Gindama713/nchu-web-learning_platform/pull/4)仍为draft，目标develop。005本身未合并、没有发布；不因旧head CI成功放行新head。文档后续提交的SHA与新CI在会话交接及PR中补录。

下一恢复：继续C01同分支fetch最新develop并核对PR最新head/CI。浏览器双端指定版本已补证；优先等003真实授权图片入口就绪并完成上述APIC/DBD对接，再实施图文及资源撤权联测。目标Linux4核8GB/50会话/worker性能仍未执行，需队友worker及目标环境；不以本机WSL探测冒充通过。001及公共runner已接入，不重做或重复当缺失阻塞。不启动C02、不接管003、不合并005或发布；PR保留draft，真实非作者批准/课堂验收另记。C06补R38正式聚合、C10补索引失效；其他本人工作包未开始。
