# SPEC-005 / C01 实施与验证记录

责任人：黄俊诚（24201716）。日期：2026-10-13，Asia/Shanghai。依据：[PRD有效验收](PRD.md#accept-spec-005)、[APIC教学接口](APIC.md#3-教学管理接口-spec-002005)、[DBD](DBD.md)。

## 基线与范围

已fetch的origin/develop为`96601372d3ac6fb6c5391320e2d96ccb13815d66`。从此提交创建feature/spec-005-knowledge；没有接入其他feature或接管队友模块。只实施章节、知识、收藏和进度，提供010B当前发布集合/完成事实及011语料revision契约，不实施统计、索引或推荐算法。

PRD/README声明团队设计评审完成；2026-10-13读取框架[PR #1](https://github.com/Gindama713/nchu-web-learning_platform/pull/1)，API返回reviews=[]、comments=[]，不能作为005批准或CP-1教师通过证据。用户本会话明确要求继续实施，不等待评审相关证据；此执行指令不登记为非作者批准、CI成功或教师验收。后续合并和发布仍分别记录真实结果。

## 依赖与阻塞

下表缺失状态针对当前已合入的origin/develop。中断恢复后fetch发现队友候选分支`origin/feature/spec-001-002-jiang-suhao`（`c1229896096a4cb6cc62d9fb9a0d6300585c3db9`），尚未合入develop；已按3文件以内分批核对其shared/auth.py、shared/db.py、app.py、shared/api.py及001 SQL表名。005已对齐require_user/check_csrf及SQL文件stem/UTF-8校验和契约，只调整本模块消费层，不复制队友源码或从该feature启动新基线；实际登录集成仍须等待其合入。候选把app改为create_app，合入后需在工厂注册005 Blueprint，处理共享入口/首页/文档接缝并回归。

| 子能力 | 负责人 | 必需契约与已核验状态 | 对005的影响/恢复条件 |
|---|---|---|---|
| 001会话、CSRF、Origin | 姜苏豪 | develop尚未有auth/session；候选提供require_user/check_csrf | 运行请求503；合入候选后消费真实shared helpers，在事务内再次鉴权并联测 |
| 001课程与成员 | 姜苏豪 | user/course/course_member仅有DBD设计，无真实迁移/初始化 | 005只消费表，不能执行真实教师/学生流程；合入001及受控测试数据后恢复 |
| 公共迁移runner | 姜苏豪（001/019） | develop仅SELECT 1探针；候选已提供SQL runner | 005_knowledge.sql已按候选文件stem/校验和契约准备；合入后副本演练、重复执行/校验和/外键验证；不另建runner |
| 005真实登录后刷新/重登 | 黄俊诚消费上述能力 | 模块文件SQLite持久化可隔离测，真实登录链缺失 | 不能把测试夹具持久化写成AC-02真实重登通过 |
| R38聚合及011失效闭环 | 黄俊诚后续C06/C10 | 005提供真实完成事实和revision；聚合/索引未实现 | C06补null/日期同集合统计；C10补下架立即禁用旧索引和失败503 |

## 实现与可审阅接入

`backend/models/knowledge.py`承担固定字段验证、富文本白名单、同课权限复核及短事务。新增/排序锁内校验课程revision，完整ID集合先校验，再移至不冲突临时非负位置，最后写0至n−1及递增revision。数据库唯一约束是并发防线。数据库忙等待5秒后503，不无限重试。知识下架保留收藏/进度及引用；学生列表、详情及个人写入均检查当前发布状态。

`backend/apis/knowledge.py`提供APIC的10个005入口，已注册到当前app。knowledge_security消费真实shared helpers，缺失503，迁移缺失/校验失败503；显式适配器需事务内会话复核。输入user_id/role等未知字段拒绝；测试替身只在tests/test_knowledge.py的临时Flask实例中使用。ID/分页偏移拒绝SQLite整数范围之外的输入，异常JSON不返回HTML或内部路径。

`frontend/js/knowledge-view.js`及knowledge-client.js实现教师章节维护/原子排序、知识编辑/发布/下架/基础标记，学生检索/分页/详情/收藏/完成取消。章节排序先读取所有分页，并检查各页revision及总数一致，避免只提交第一页；冲突显示错误，不自动覆盖新顺序。写入前重新取得会话绑定CSRF；用户变化时拒绝写入并清除页面身份。请求失败不替换为伪成功数据。加载/失败/空结果/重试、移动端布局和键盘焦点已实现；正文只渲染服务端白名单HTML。

模块迁移由公共runner读取005_knowledge.sql，005不提供无鉴权初始化命令。runner必须在相同事务登记schema_migration，重复执行核对版本/校验和再跳过，失败全量回滚。实际公共runner尚未合入/对接，不能在生产执行本模块或承诺恢复演练通过。第一提交的spec-005-001只是未部署的Python迁移草案，最终对齐为005_knowledge；没有对真实库改名或绕过已应用校验和。

## 验收矩阵与真实验证

2026-10-13：Python 3.13.12，本机Windows。`python`指仓库`.venv/Scripts/python`。

| 编号 | 已执行隔离验证 | 真实集成/验收状态 |
|---|---|---|
| AC-01 | 关键词检索、空结果、分页末页及学生隐藏草稿通过 | 真实会话/课程联测阻断 |
| AC-02 | 收藏唯一/幂等、取消、跨用户隔离、关闭连接后新Store读取通过 | 真实登录/登出/重登阻断 |
| AC-03 | 完成/取消、UTC时间、重复完成保留时间、持久读取通过 | 真实学生页面及重登待联测 |
| AC-04 | 草稿/下架的列表、详情、收藏、进度均隐藏；重新发布恢复历史通过 | 真实会话撤销与课程成员链待联测 |
| R20（005部分） | 基础标记、实际字段变化递增revision、相同值不递增、富文本处理通过 | 011下架/索引失败联合场景在C10；其他模块由各负责人补证 |
| R32 | 改名、完整/重复/缺失/非法ID拒绝、过期revision、原子重排、新增与排序并发通过 | 真实课程/页面联测阻断 |
| R38（005部分） | 临时SQLite真实记录，发布集合依次2/3、1/2、2/2、0/0；下架保留完成记录通过 | 统计null/from-to完整输出在C06；未把夹具称真实业务验收 |
| R22/R45 | 责任/范围/依赖登记 | 全组排期/技术验证非本包；未执行/未核验 |
| R46 | 本文件只记实施/证据；字段仍在APIC/DBD单一归属 | 文档链接检查通过；跨模块后续核对 |
| R47 | 无非作者批准记录 | 未核验；不写假批准 |
| NF-SEC | 已测跨课404、可见越权403、管理员不代教师、停用401、成员撤销/角色不匹配404、未知字段及测试适配器CSRF拒绝 | 真实会话CSRF/Origin与失效链阻断；无假验收 |
| NF-DATA/UI/PERF | 模块外键/唯一约束及连接恢复已测 | 备份恢复、浏览器页面与50会话性能尚未执行；沙箱无本包实现 |

执行命令：`python -m unittest discover -s tests -v`，12测试通过（11个005隔离测试、1个框架测试）；`python -m ruff check backend tests scripts`通过；`python scripts/check_docs.py`通过。首次运行在Windows发现夹具连接未关闭导致9个tearDown错误，修复后上述结果通过；此失败不隐去。

最终本地验证：`python -m unittest discover -s tests -v`，19测试通过（18个005隔离测试、1个框架测试）；ruff通过；文档链接检查通过；前端`npm test`13测试通过（8个005客户端隔离测试、4个Vue交互隔离测试、1个框架测试），`npm run lint`及`npm run build`通过。新增适配层Origin/共享CSRF错误映射、事务内会话撤销拒绝写入、缺少事务校验拒绝503测试。Vue交互覆盖学生收藏/完成、切换登录人后清除数据且拒绝写入、教师编辑/下架、失败刷新清除旧结果；HTTP双替身不作为真实登录或浏览器业务验收。未升级依赖，npm ci沿用锁文件；本机Node 24.14.0/Python 3.13.12，目标CI为Node 22/Python 3.12，远端结果单独登记。

实际浏览器检查：Vite+Flask真实运行，默认课程知识页、重新加载及重试入口可用；`/auth/session`真实404，页面显示“暂时无法读取登录状态。请在登录服务可用后重试。”，没有生成课程/登录成功假象。窄侧栏截图确认失败提示布局可读。首次检查发现原生fetch绑定错误（Illegal invocation），已用闭包调用修复并加客户端回归测试。真实教师/学生列表、编辑、重登及桌面/移动完整流程仍因001缺失未执行，不能据此称NF-UI完整通过。

## 提交、PR与下一恢复点

- 后端第一部分：`8ed56b56d24b0e4de536d0bb7a7b7c01ade68a5c`，已推送origin/feature/spec-005-knowledge。
- 第二部分前端及边界回归：`e7189ad8e375319ba50af74b8b5ab440e1045b44`；第三部分接缝对齐：`0e38730b59a4224bf32fb55ee0ac3e2790201708`，均已推送同一feature。
- [草稿PR #4](https://github.com/Gindama713/nchu-web-learning_platform/pull/4)，feature→develop。当前基线仍为96601372，未合并develop、未发布；依赖及真实验收未关闭，不能转正式合并就绪。
- 代码提交0e38730的[Actions 38344996554](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38344996554)已核验：ci-policy/ci-lint/ci-test/ci-build/ci-required全部success；ci-grader在develop按现有规则skipped，不能写成真实引擎成功。CI使用Node22/Python3.12，和本机环境分开。后续文档提交触发的新head检查应单独查询，不能沿用旧head成功。
- 下一会话继续C01，同分支fetch最新origin/develop，先核对001及公共runner是否真实合入；只有就绪后才对接course_security和模块迁移。不要用FixtureSecurity接运行应用，也不要自行实现001或公共runner。
- 对接后在受控真实课程执行教师新增/改名/排序/发布→学生登录检索→收藏/完成→刷新/登出重登→撤销成员/下架隐藏→再次发布恢复历史，记录SHA及真实测试结果；完成副本迁移/重复执行/回滚边界验证。
- C06补R38聚合null及from/to同集合输出，C10补011索引失效联测；其他工作包未开始。
- 当前白名单支持文本、基础HTML和上下标公式；PRD的图文展示尚需与003授权资源契约对接图片来源，本轮未实现图片上传或外部URL展示，不能把图文范围记为全部完成。负责人：005黄俊诚对接、003石佰合提供授权资源入口；接入时先确认同课程与学生可见性，不能绕过资源权限。
