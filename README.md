# 计算机组成原理课程学习系统

本项目主题为中央处理器，班级242017，组号g24201710，组长24201718姜苏豪，组员24201716黄俊诚、24201723罗浩铭、24201737石佰合。按照任务书要求，采用Vue 3、Flask、SQLite和RESTful API，围绕CPU提供教学管理、知识学习、测评、实验与学情分析。数字逻辑作为前置知识。实验箱连线过程模拟和Logisim电路文件在线评测均为必做功能，不能以静态图片、视频或文件上传页面代替。

六份需求设计文档为 v0.6，团队评审已完成（据团队确认）。姜苏豪负责的身份/课程授权、考勤、考勤成绩关联、预警算法和受限图片识别第一轮代码已通过 PR #3 合入 `develop`；后续验收修正在独立功能分支进行。其他组员的测评、实验和评测事实表尚未集成；依赖未就绪的分析接口返回明确的 503。实验箱连线和 Logisim 在线评测仍是必做目标，当前整体系统不得视为已完成。

## 1 文档入口

| 任务书指定文件 | 本项目路径 | 内容 |
|---|---|---|
| PRD.md | [docs/PRD.md](docs/PRD.md) | 范围、模块规格、业务规则、验收标准 |
| README.md | 本文件（仓库根） | 运行、测试、部署和数据库约定 |
| APIC.md | [docs/APIC.md](docs/APIC.md) | 接口路径、参数、返回、错误、权限 |
| ADR.md | [docs/ADR.md](docs/ADR.md) | 架构选择、评测方案、托管决策 |
| CHG-RB.md | [docs/CHG-RB.md](docs/CHG-RB.md) | 变更、发布、回灌、备份与回滚 |
| DBD.md | [docs/DBD.md](docs/DBD.md) | 表、字段、关系、约束与生命周期 |

六份主文档中，README.md 置于仓库根，其余五份（PRD、APIC、ADR、CHG-RB、DBD）置于 docs 目录。实名分工、阶段计划、技术风险、完整验收索引和R01—R48纳入PRD第10—12节；Git与CI协作规范纳入本文件附录A。业务规格引用在这六份主文档之间跳转。

### 1.1 文档维护

后续统一维护本文件（仓库根 README.md）与 docs 目录下的五份主文档。分工、排期、追溯和完整验收见PRD第10—12节，Git/CI协作规范见本文件附录A。

六份主文档包含本阶段所需设计，可独立阅读。历史辅助资料暂未纳入此仓库。

## 2 建设范围与开发约束

先核对规格，再开发，再依据验收条目编写测试。业务规格以 PRD 中的 SPEC 编号为入口，接口和表结构分别引用 APIC、DBD；三个文档共同组成模块规格，不另造一套相互冲突的编号。规格改变必须在同一PR中说明原因并同步更新三处及PRD内的验收索引。

按用户确认，GitHub负责日常开发、PR与GitHub Actions，Gitea负责课堂提交。GitHub为唯一开发合并来源，Gitea以专用归档分支及固定tag保留同一提交历史和SHA；不得把同步归档变成绕过main保护的直推。操作规约见ADR-004和README附录A。任务书要求Gitea托管及PR评审，并未明确PR必须在Gitea内；GitHub评审证据随Gitea归档，课堂另有要求时登记调整。

开发与部署统一 SQLite，不改用 MySQL/PostgreSQL。统计及智能功能实际使用 NumPy/Pandas/scikit-learn 等轻量库，不得用固定数据冒充分析；不引入 PyTorch、TensorFlow。Docker 与 Nginx 对 Web 部署是可选项，但运行不可信电路的评测进程必须有资源和文件系统隔离。

## 3 计划目录

README 置于仓库根；docs/ 保留五份需求设计文档。backend/apis 按 SPEC 划分 HTTP 边界，backend/shared 放共享授权/事务/响应，backend/migrations 放校验和锁定的 SQLite 迁移；frontend/ 是 Vue 3 页面，tests/ 是后端测试，scripts/ 是文档检查，.github/workflows/ 是 PR 检查。上传目录由 `UPLOAD_ROOT` 指定；生产环境应设为源码目录之外的持久化目录，数据库、日志、密钥不提交版本库。公开合成测试数据可以进入 tests；隐藏评测数据不得进入公开仓库。

## 4 运行与配置契约

引擎选定Logisim-evolution 5.0.0，实验箱采用PRD定义的CPU-EDU-8 v1。前后端框架运行命令见第8节；Java/JAR校验和与评测 worker 的启动方式须在SPEC-018实现时补齐并实测。正式进入检查点2前须在目标环境复现完整业务命令。

| 运行单元 | 启动前条件 | 预期行为 | 完成证据 |
|---|---|---|---|
| 前端 | 安装锁文件指定依赖，配置同源 /api 代理 | 开发可访问，生产输出静态资源 | 安装、开发启动、构建的真实命令及日志 |
| Flask API | 配置数据库与文件路径，执行 `db-upgrade` 迁移及管理员初始化 | /api/v1/health 显示 `db_ready=true`，整体仍因 grader 降级 | 启动入口、端口、健康检查记录 |
| 评测 worker | 固定 Java/JAR 校验和，隔离环境可用 | 从 SQLite 领取任务并写回结果 | 独立启动入口、标准电路实测报告 |
| 完整系统 | 前两项就绪且 worker 可用 | 完成连线保存、提交 .circ、获取判分 | 新环境端到端运行录像或记录 |

配置项：APP_ENV、SECRET_KEY、DATABASE_PATH、UPLOAD_ROOT、GRADER_WORK_ROOT、LOGISIM_JAR_PATH、JAVA_PATH、GRADER_TIMEOUT_SECONDS（初始 10 秒）、GRADER_MEMORY_MB（初始 512 MiB）。SECRET_KEY 不得有公开生产默认值；示例配置只能放占位符。数据库及文件路径必须是服务端配置，不能取自用户请求。对外部署关闭调试模式，HTTPS 同源服务前端和 API。

初始化必须使用迁移创建空库，再用 `admin-create` 交互命令创建首位管理员；随后由管理员授权教师、创建课程，学生自行注册并由教师加入课程。课程知识、实验与题库的可重复演示数据装载仍由相应模块实现；不在文档或源码写死真实密码，也不以假数据替代评分事实。

## 5 测试与质量门禁

测试分为接口/数据库约束测试、前端交互测试、真实 Logisim 集成测试、浏览器端到端测试。每项关联 SPEC 与 AC 编号。检查点 2 之前落实测试入口与命令；检查点 5 必须在干净环境按本说明完成安装、测试、构建和启动。

GitHub PR 到 main 必须自动执行测试、构建、lint；门禁还覆盖真实评测冒烟和规格完整性检查，具体见 README附录A。缺少源码或测试时不能用“无测试即成功”、空命令或跳过 job 冒充绿色 CI。框架及已实现业务检查现已落地；main/release 的真实评测检查会明确失败，直到 SPEC-018 实测通过。main/develop 分支保护已配置并经 API 读取核对，拒绝直推等负向演练及未来 release 规则仍待验证。

两条关键端到端验收：学生打开实验箱→连接端子→观察逻辑输出→保存并重开→提交记录→教师查看；学生提交 .circ→后端校验并入队→隔离运行固定引擎→按测试判分→查看报告→教师按班级统计。错误电路、越权访问、超时、评测服务不可用均必须有测试。

## 6 数据库与部署约定

SQLite 每连接开启外键约束，采用短写事务、有限忙等待；数据库和用户上传目录持久化，临时评测目录按任务隔离。不能在执行 Java 仿真期间持有数据库写事务。数据结构及迁移规则见 DBD。

生产发布从 main 的已验收版本生成不可变产物，记录提交 SHA、依赖锁文件、数据库版本、Logisim JAR 哈希和测试结果。Web 服务与 worker 分离启动；先迁移副本演练，再备份、迁移正式库、启动服务并冒烟。部署失败停止开放写入，按 CHG-RB 恢复。前端静态部署成功但评测 worker 不可用，不能判定整体部署成功。

运行手册后续还须补充评测 worker 的启动/停止、备份位置、日志位置及故障定位步骤；不得将尚未实现的业务命令当成已验证操作。

## 7 检查与提交

六份需求设计文档仍保留；本开发分支增加前后端框架、测试和 CI。README 在仓库根、其余五份在 docs，课程检查仍按 Gitea 要求归档。班级242017、组号g24201710及GitHub开发地址已登记。实验模型与引擎已设计选定，运行兼容性尚未实测。

任务书安排：第 3 周分组，第 4 周需求分析，第 5—7 周系统设计，第 8—11 周编码测试，第 12 周系统检查及超星提交。阶段检查未通过不得进入下一阶段；不把组员教程的相对“9 周实例”替换为课程周次。

最终还需测试用例与报告、部署说明、用户手册、系统源码及设计文件。原任务书图片规定组长文件名为“XX班_第X组_成员名单.txt”“XX班_第X组_大作业报告.docx”“XX班_第X组_大作业源码及设计文件.zip”，组员文件名为“学号_姓名_设计报告.docx”。其中班级、组号、姓名必须替换为真实值；最终报告格式附件未随当前资料提供。


## 8 本地运行与验证

从仓库根目录开始。目标环境为 Python 3.12+、Node 22+。虚拟环境、node_modules、数据库和上传文件不进 Git。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.lock
.\.venv\Scripts\python -m pip install ruff==0.17.0
$env:DATABASE_PATH = 'instance/app.db'
.\.venv\Scripts\python -m flask --app backend.app db-upgrade
.\.venv\Scripts\python -m flask --app backend.app admin-create
.\.venv\Scripts\python -m flask --app backend.app run --host 127.0.0.1 --port 5000
```

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`。Vite 把 `/api` 代理到 Flask。开发环境默认 `APP_ORIGIN=http://127.0.0.1:5173`，若改变前端地址必须同步设置 `APP_ORIGIN`；生产环境必须设置至少 32 字符的随机 `SECRET_KEY`、HTTPS `APP_ORIGIN`、外置 `DATABASE_PATH` 和 `UPLOAD_ROOT`。`GET /api/v1/health` 在迁移后显示 `db_ready=true`，仍返回 503、`grader_ready=false`，如实表示真实评测 worker 尚未实现。

本地检查：

```powershell
python -m unittest discover -s tests -v
python -m ruff check backend tests scripts
python scripts/check_docs.py
cd frontend
npm test
npm run lint
npm run build
```

当前后端在 Python 3.12 运行并通过测试；课程完整运行基线仍需在 Python 3.12、Java 21、Logisim-evolution 5.0.0 的目标环境验证。`db-upgrade` 可重复执行并验证迁移 SHA，`admin-create` 提示输入学号、姓名和隐藏密码；管理员改密可用 `PATCH /api/v1/users/me`，请求须含旧密码。评测 worker、备份与完整生产部署命令待对应模块实现。

### 8.1 本分支完成范围与集成边界

| 负责项 | 当前可运行能力 | 尚需集成或实测 |
|---|---|---|
| SPEC-001/002 | SQLite 持久身份与课程成员授权、CSRF/审计、冻结名单签到、请假审批及更正 | 章节/知识点由负责组员的教学内容模块接入；浏览器端到端验收 |
| SPEC-010A | Pandas 考勤成绩配对、C01—C04 测试、不可变快照与同快照 CSV | 组员测评的 `paper/paper_item/attempt` 真实迁移和数据；缺表时 503 |
| SPEC-014 | 规则与固定参数 KMeans、批次保存、处理记录和合成测试 | 组员题库、实验、评测事实表；缺表时 503，不伪造预警 |
| SPEC-016 | PNG/JPEG 边界校验、固定字典模板、人工确认及成绩隔离；合成图测试 | PRD 固定 SHA 的 F01—F05 原图未在当前资料中找到，TV-03 尚不能宣称通过；模板 SHA/定位版本仍为 provisional |
| SPEC-019 | GitHub PR 门禁、依赖锁定及 main/develop 分支保护已落地 | SPEC-017/018 真实 Logisim 冒烟、目标环境检查、release 保护及远端拒绝场景演练仍为发布阻断项 |


### 8.2 完整系统实施契约（待实现）

以下保留需求设计阶段的运维与安全契约；表内尚未落地的命令不是本次框架的运行说明。

| 顺序 | 工作目录/计划命令 | 行为 |
|---|---|---|
| 1 | backend：python -m venv .venv；激活后python -m pip install -r requirements.lock | 安装锁定后端依赖；首次实现必须提供锁文件 |
| 2 | `python -m flask --app backend.app db-upgrade` | 创建/迁移SQLite，重复执行无副作用；已在本分支实现 |
| 3 | backend：python -m flask --app app admin create | 交互录入初始管理员及密码，不接受公开默认密码、不回显密码 |
| 4 | backend：python -m flask --app app seed-demo | 仅development/test允许；幂等创建匿名课程/实验/样例，不覆盖成绩 |
| 5 | backend：python -m flask --app app run --host 127.0.0.1 --port 5000 | 开发API；生产禁止使用此服务器 |
| 6 | backend：python -m grader.worker | 单worker，检查JAR哈希及沙箱可用后领取任务 |
| 7 | frontend：npm ci；npm run dev -- --host 127.0.0.1 --port 5173 | /api代理到127.0.0.1:5000，浏览器只访问5173同源入口 |
| 8 | 根目录：python -m pytest tests；frontend：npm run test -- --run、npm run lint、npm run build；根目录：python -m ruff check backend tests | 测试/lint/构建，命令依赖由首次实现提供，不允许空测试成功 |
| 9 | backend：python -m flask --app app backup create --destination <备份目录>；backup verify --manifest <清单> | 维护模式一致备份SQLite及引用文件，校验可恢复性 |

生产计划：Gunicorn单Web进程监听127.0.0.1:8000，Nginx可作为同源HTTPS入口，前端静态目录frontend/dist，/api转发8000；worker由单独systemd服务管理，沙箱不可读主库。计划启动命令gunicorn --workers 1 --bind 127.0.0.1:8000 app:app；服务停止使用systemctl stop cpu-grader/cpu-web，先暂停新提交并处理活动任务。部署时必须提供经过验证的服务配置，当前未创建。

开发仅本机HTTP允许SESSION_COOKIE_SECURE=false；production必须true、HTTPS且启动拒绝弱SECRET_KEY/调试配置。两环境均保留HttpOnly、SameSite=Lax、CSRF与Origin校验；前端代理避免跨端口Cookie/跨域分歧。Cookie名称固定，Path=/，无Domain属性。

生产数据默认/srv/cpu-learning/data/app.db，上传/srv/cpu-learning/uploads，临时评测/srv/cpu-learning/grader-work，日志/var/log/cpu-learning，备份/var/backups/cpu-learning（皆非源码目录）。Web和worker分别用最小权限账户，沙箱仅挂当前任务输入；环境文件不进Git。开发对应目录可配置到源码外的本机数据目录。

运维顺序：校验依赖/引擎→维护模式→备份及迁移→启动API/worker→检查/api/v1/health→受控验收账号/独立验收课程执行正确与错误电路冒烟→关闭验收例外→开放普通用户写入。维护模式默认拒绝普通写入，验收例外及worker领取范围严格按CHG-RB第4节；CI冒烟与目标部署冒烟分别留证。故障用request_id/run_id关联脱敏日志；引擎不可用先暂停提交，不能改成学生0分。恢复依CHG-RB，不直接覆盖正在写入的数据库。

完整追加验收及现行契约位置见[PRD第12节](docs/PRD.md#supplemental-acceptance)。文档一致性核对与未来运行验收分别记录。

### 8.3 SPEC-005课程知识（主体接入，验收仍有缺口）

登录后知识组件提供教师章节新增/改名/排序、知识编辑/发布/下架/基础标记，以及学生检索/详情/收藏/完成状态。后端沿用001会话和公共SQL runner；`db-upgrade`包含005_knowledge迁移。受控API链及Chrome/Edge检查已通过，授权图片、目标环境性能和课堂验收仍待补。契约、证据和恢复步骤见[SPEC-005实施记录](docs/SPEC-005_IMPLEMENTATION.md)。

### 8.4 SPEC-006题库、测评与公开练习（C02a—C04）

教师可创建五题型题目及不可变版本、编卷发布并冻结名单；学生可按固定版本交卷、查看讲评、做公开客观练习和重练错题。简答支持教师整批评分、更正及审计；保密题在实际讲评前禁止通过练习或旧版本泄露答案。当前分支已合入005知识模块并注册题目、试卷、作答、练习页面；题目必须关联真实同课知识。新测试通过实际知识 API 准备标签并验证联动；旧浏览器报告仍只证明其原测试提交，不能冒充本次合并后的浏览器验收。集成证据见[SPEC-006实施记录](docs/SPEC-006_IMPLEMENTATION.md)。

运行与迁移沿用第8节，006_question_versions、006b_papers、006c_attempts、006d_practice_wrong按公共runner顺序接入。C05专用测验发布/显式讲评已由SPEC-008实现；003资源与004备课接缝、目标环境性能及课堂验收仍未完成，SPEC-006不标记为整体通过。可用`python -m unittest discover -s tests -q`和`npm test`复核当前代码；可选Chrome/Edge脚本位于`scripts/verify_spec006_*.py`，仅在两浏览器及相应依赖已安装时执行。


### 8.5 SPEC-010B知识与分类成绩分析（C06—C07）

登录后在“知识与分类成绩分析”选择课程和维度。知识页显示掌握度、错题表及本人完成进度；教师留空学生编号查看班级掌握度，填写学生编号查看该生。分类成绩选择作业/考试/随堂测，可按试卷编号查看单卷原分均值；跨卷查看百分比均值及分布，缺交和待批不当0分。日期按本机时区输入，留空为最近28天，最长366天；知识按作答日期筛选，成绩按试卷开始时间选择任务。

“查询统计”保存新快照。记录“原快照编号”后，可在同一账号、同一课程用“恢复原快照”读取原结果；刷新或重登会尝试恢复该账号上次快照，浏览器仅本地保存课程和快照编号。教师可点“导出当前快照 CSV”，下载与页面相同ID的数据；更正成绩不会改变旧快照。修改筛选、读取/导出失败会清空当前结果；快照已清理或当前无权访问时，须显式重新查询，不会自动用最新数据冒充原结果。表格支持横向滚动和键盘聚焦，空样本显示无数据。

运行沿用第8节，无新增迁移。独立API测试为`python -m unittest tests.test_knowledge_analytics tests.test_score_analytics -v`；008已合入后的专用联合为`python -m unittest tests.test_quiz_analytics_integration -v`。可选真实Chrome/Edge回归分别为`python -m scripts.verify_spec010b_analytics`及`python -m scripts.verify_spec010b_quiz_integration`（需已安装两浏览器、`backend/requirements-browser.txt`依赖及前端依赖，5000/5173端口空闲）。专用quiz逐题统计包含提交漏答、knowledge只计实际客观作答，分母不同属于规定口径；批分后新scores变化，原ID/CSV保持原值。测试使用临时受控课程，不写教学库；报告和剩余验收见[SPEC-010B实施记录](docs/SPEC-010B_IMPLEMENTATION.md)。目标环境性能、完整生产恢复及课堂验收仍未关闭。

### 8.6 SPEC-013草稿组卷与快照重放（C08/C09）

C08提供内部候选冻结、确定性回溯和不可变generation_snapshot；C09接入`POST /courses/{id}/generated-papers`及教师“课程试卷/随堂测→智能组卷”。首次填写新标题、题量、总分、难度配额和必选知识点，可选随机种子/历史截止/保密；成功仅保存草稿，显示固定版本和精确配分。“查看草稿与发布设置”继续006/008原流程，发布前仍检查题目资格和冻结名单。通过“从此快照重放”或原快照编号仅填写新标题，使用原约束/seed/全部候选历史，不读取新题库重新选题；原卷不变。

沿用第8节公共`db-upgrade`，追加013_generation_snapshot和013b_generated_papers迁移，不修改已应用SQL。求解不持写锁，权限/当前资格复核及snapshot+draft/item+审计保存同一短事务。400修正参数、422调整题量/配额/覆盖、503 SEARCH_LIMIT缩小约束；失败不返回成功ID，保存错误全回滚。网络丢响应时先刷新列表检查是否已保存再重试。专题验证：`python -m unittest tests.test_generated_papers tests.test_generation_input tests.test_generation_solver tests.test_generation_snapshot -v`；真实浏览器：`python scripts/verify_spec013_browsers.py --output logs/spec-013-browsers`（已安装Chrome/Edge、browser依赖及前端依赖，5000/5173空闲）。实施、真实证据及未完成验收见[SPEC-013实施记录](docs/SPEC-013_IMPLEMENTATION.md)。

### 8.7 SPEC-012个人学习推荐（C11）

学生登录后在“个人学习推荐”选择课程和数量（1—20，默认5），用“刷新推荐”读取最近28天本人客观作答与当前完成状态。每项显示推荐理由、样本数、掌握度、6位排序分数及知识出处；无作答时只推荐教师标记且未完成的基础知识。分数用于排序，不代表预测概率；完成且样本≥5、掌握度≥80%的项被过滤。空课程、无基础候选和全部掌握均显示原因、截止时间和算法版本。

“阅读知识”读取当前005正文/例题；“去练习”重新检查推荐资格后在已有“公开练习与个人错题”区打开对应固定版本。无合格开放客观练习时可先阅读。练习仍按006保护、判分、幂等重试规则提交；推荐失败清除旧结果，可显式刷新恢复，练习区继续可用。专题验证：`python -m unittest tests.test_recommendations -v`；真实浏览器：`python scripts/verify_spec012_browsers.py --output logs/spec-012-browsers`，环境同8.6。不新增迁移或推荐缓存；正式证据与未完成验收见[SPEC-012实施记录](docs/SPEC-012_IMPLEMENTATION.md)。

<a id="submission-check"></a>
## 9 本次提交状态与自查

需求设计团队评审已完成（据团队确认）。教师检查、应用实现、技术验证、CI执行与部署验收分别记录，不能由团队文档评审推定通过。

| 检查项目 | 当前结论 |
|---|---|
| 六份指定文档 | 齐全，文件名与课程要求一致 |
| 需求、范围与验收 | PRD正文及第10—12节完整收录分工、排期、AC、R01—R48与计划用例 |
| 接口、架构与数据 | APIC/ADR/DBD相互引用，包含权限、失败、版本与事务规则 |
| 运行、测试、部署 | 姜苏豪负责模块的开发命令与测试已提供；完整业务闭环和生产部署尚待组内集成 |
| 变更与回滚 | CHG-RB记录文档修订并规定软件发布与恢复流程，未宣称已演练 |
| 独立阅读 | 必要内容已归入六份文档，原审查材料与独立样本清单不作为本次阅读前提 |
| 团队评审 | 已完成 |
| 课堂提交 | README 置于仓库根、五份文档置于 docs，按课程要求通过Gitea提交 |

GitHub开发仓库：[nchu-web-learning_platform](https://github.com/Gindama713/nchu-web-learning_platform)。Gitea具体目录可按仓库安排，README 与 docs 目录的相对链接需保持一致；开发与课堂归档流程见附录A。

项目已进入功能集成阶段，软件验收及最终小组报告、个人报告、源码设计包仍按课程后续阶段要求准备。识别样例的尺寸、内容、预期、容差及固定SHA已在PRD第4.5节说明；PNG是后续软件测试输入，不是本次六份设计文档的阅读依赖。


<a id="git-workflow"></a>
## 附录A Git分支与CI协作规范

以下为已评审工程设计。工作流已加入仓库；main/develop 分支保护于2026-10-13配置并通过 API 读回核对，负向阻断演练与 release 保护尚待执行。关联SPEC-019，实际设置记录见CHG-RB，软件发布回滚细则亦见CHG-RB。

### A.1 分支和权限

| 分支 | 起点 | 合入目标 | 规则 |
|---|---|---|---|
| main | 仓库基线 | 不用于日常开发 | 稳定发布主线；只接release/hotfix PR；所有人禁止直推、强推、删除，管理员不得绕过 |
| develop | main | 创建release候选 | 日常集成；接feature PR与release/hotfix修复回灌PR；禁止直推、强推、删除 |
| feature/spec-编号-主题 | 最新远端develop | develop | 一项规格或已编号子规格一个主责任人；文档先行，3—5天为建议周期，超期先拆合理独立任务而非合入坏代码 |
| release/v主.次.修订 | 已集成develop | main；再回灌develop | 冻结后只修阻断缺陷、测试及发布文档，不夹带新功能 |
| hotfix/spec-编号-主题 | 最新main | main；再回灌develop及仍活动的release | 线上紧急修复，仍需PR和CI，不能因紧急绕过门禁 |

文档和测试通常在对应feature内完成，提交type区分用途，无须为每个文件增加分支类型。发布修复若多人协作，使用从release切出的release-fix/spec-编号-主题分支并PR回原release；release本身也启用PR和禁止强推。组长姜苏豪负责合并和发布，黄俊诚为代理；不设置必须等待组员批准的合并条件，作者也必须提交PR并通过同样的自动检查。

“每天同步”和“频繁提交”是协作建议，不设置每天3—6次等机械指标。每个提交聚焦一件可解释的事；组长也须有独立业务开发和统计模块贡献。

### A.2 规格驱动的日常流程

1. 确定SPEC及AC，检查依赖、接口和数据库；从已fetch的远端develop建立命名feature。
2. 先核对PRD/APIC/DBD相关规格再写代码；规格变更在PR中记录原因、版本、受影响接口与验收，不虚构批准人。
3. 开发与测试分成可审查提交，提交信息为type(spec-编号): 具体改动，例如“feat(spec-017): 支持端子连接与位宽校验”。公共变更可用ci/db scope，但正文Refs必须列出SPEC-019及相关业务Spec。
4. 个人独占且无人基于其开发的分支允许rebase同步，确需改写远端时仅使用带明确预期远端提交的force-with-lease。已共享分支用merge同步，不强推。禁止对main/develop/release改写历史。
5. 作者解决冲突，检查工作区及暂存区差异、残留冲突标记，重新执行受影响测试。冲突解决写入PR说明，不能只保留其中一人的代码。
6. feature PR目标为develop，描述关联Spec、改动原因、接口/数据影响、AC对照、真实测试结果及回滚方式；无证据的项目填“未执行”，不能全部勾选通过。
7. 必需检查全部通过、已有讨论解决后，由合并负责人使用Create a merge commit合入；不把组员审批设为必需条件。触及权限、数据库、判分、工作流、APIC时在PR描述中列明风险、测试与回退方式，仍须通过同一CI门禁。
8. 合并后验证develop健康并补追溯矩阵；确认不再有依赖后删除feature。release/hotfix只有main与回灌PR均完成后才删除。

远端develop、本地origin/develop和本地develop不是同一个引用。origin/develop是上次通信取得的远程跟踪状态，fetch后才用于判断最新基线；不能凭分支名字认定已经同步。

### A.3 GitHub保护规则

必须启用“合并前需要PR”“解决全部已有讨论”“必需状态检查”“合并前与目标分支保持最新”；必需批准人数为0。main/develop禁止强推和删除，并使管理员受相同规则约束。只允许merge commit策略，不同时要求linear history，以免与合并节点策略冲突。自动删除分支不应在main合并后立即删掉尚待回灌的release。

main来源限定release/*或hotfix/*；develop来源允许feature/*、release/*、hotfix/*以及backport/*回灌。来源限制由ci-policy检查，不能仅靠PR作者填写标题。工作流修改可能影响自己的CI门禁，因此该类PR须在合并前单独核对工作流差异和预期检查结果；此项为发布负责人操作责任，当前未实现独立于PR代码的技术强制。

CODEOWNERS可作为自愿审阅提示，不设为合并阻断条件；真实GitHub用户名在需要启用时再补入。它不替代自动测试，也不保证未实现的两人审批规则。[官方CODEOWNERS说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

GitHub仓库可见性/账号方案影响保护能力。建仓验收须确认实际能启用所需规则；如果不可用，不允许声称“CI强制阻断已生效”，应调整合适方案并记录。所有状态检查名称固定且唯一，并尽可能绑定GitHub Actions来源；依赖检查必须在最新提交上完成。[官方分支保护说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

### A.4 Actions设计与必需检查

工作流配置位于.github/workflows/，当前已有框架检查YAML；真实评测冒烟、完整规格检查和合并后回归仍须随对应实现补齐。PR的base为main/develop/release/*时触发，包含首次打开、更新提交、重新打开和准备评审；后续须在合并至main/develop后再运行回归。分支过滤针对目标分支，不误写成只有源分支叫main才运行。main PR不通过路径过滤跳过必需检查。

当前落地的ci-policy仅检查来源分支与六份主文档的本地链接；ci-test包括已实现的姜苏豪模块测试，ci-build构建前端。下表其余业务检查为发布前必须补齐的验收目标，不能把当前局部CI视为已通过完整软件门禁。

| 固定检查名 | 执行内容 | 失败判定与证据 |
|---|---|---|
| ci-policy | 分支来源、Spec引用、六文档链接及必要契约同步检查 | 缺Spec/错base/不合规发布来源即失败；输出具体问题 |
| ci-lint | Vue/JS及Python lint，文档格式/链接校验 | 错误非零退出；不得用忽略失败转换绿色 |
| ci-test | 后端鉴权与SQLite约束、前端交互、业务/接口测试 | 用例失败或应有测试却发现0项即失败；保存测试清单和结果 |
| ci-build | 按锁文件安装，前端生产构建，后端依赖及导入/启动检查 | 任一步失败即失败；保存构建日志及产物身份 |
| ci-grader | 固定JAR真实运行ALU/REG/CPU的公开测试电路，覆盖错误和零用例 | 只有mock不足；时序/子电路不执行、零用例或误判即失败 |
| ci-required | 总门禁，检查上述每个job确实success及必要产物存在 | skipped/cancelled/neutral/missing/failed均不能作为本项目成功；聚合检查自身总会执行 |

main与release的软件门禁必须包括上述六项；develop按附录A.9阶段矩阵执行，ci-required再验证前置状态，防止某个job被条件跳过后平台显示可合并。不得continue-on-error、空测试占位或吞掉退出码。缺源码/工具/测试要显式失败，不以“文档阶段”为由发布软件。平台对某些skipped状态的处理与项目真实执行要求不同，因此必须验证聚合逻辑。[官方状态检查说明](https://docs.github.com/en/pull-requests/reference/status-checks)

测试使用PR与最新目标分支的合并测试结果，记录base SHA、head SHA及实际tested SHA；目标更新后必须刷新并重跑。GitHub合并测试SHA可能不同于最终merge SHA，不能混称同一个；main合并后对最终merge SHA再执行回归/冒烟，只有成功才发布软件tag和产物。已合入main后回归异常立即冻结发布并通过修复PR恢复，不能宣称CI保证绝对无缺陷。[官方必需检查排查](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)

CI运行只读仓库权限、无生产密钥，第三方Action固定版本/提交，PR不通过高权限pull_request_target执行不可信代码。CI电路全为合成公开样例；学生上传电路走业务worker，不以提交到GitHub工作流的方式评测。公开CI产物不得包含学生资料和隐藏测试。

### A.5 文档基线与软件基线

CP-1是文档基线，检查六文档、实名分工、Spec覆盖和链接；没有应用时不伪造ci-test/build/grader成功。CP-1可以在develop的文档提交上建立checkpoint-1-docs tag并同步Gitea，main不因交作业而接收未经完整门禁的软件。

建仓初期develop使用文档阶段门禁：ci-policy和文档lint；这不是软件门禁通过。开始编码时，develop按实际落地单元依次增加前后端测试、构建、lint，评测引擎接入后增加ci-grader；每次门禁升级以SPEC-019的PR和配置读回留痕，只能增加，不能因失败降低。main从首个软件发布PR起必须具备附录A.4完整六项门禁，无文档例外。这样既能提交先行规格，又不会要求空仓库伪造应用测试。

首次建仓只产生仓库基础引用，不能称该初始提交为可发布软件；保护规则生效后所有实际变更走PR。本项目main首次软件发布始于通过完整门禁的版本。文档提交和软件发布的边界在检查报告中明确记录。

### A.6 发布及回灌

从验收范围完整的develop创建release/v0.1.0等，冻结范围并记录基线SHA。所有修复再次测试，提交release→main PR，按完整CI门禁合并，不等待组员审批。合并后回归通过，将不可变附注版本tag指向main实际merge SHA，发布清单记录该SHA与产物哈希。

通过release→develop PR回灌冻结期修复；若main已有hotfix或发布提交有额外差异，核对差异并通过独立回灌PR补齐。验收是“develop包含发布修复”，而不是“develop必须完全等于main”。未回灌不得删除release。hotfix从main开始，同样有main PR和develop/活动release回灌PR。

回滚也从目标共享分支建立修复分支，添加revert提交并PR，禁止在本地main/develop直接revert后push。不得移动已交付tag；修正使用新tag。

### A.7 Gitea课堂提交操作规约

1. 在GitHub完成相应检查点的PR及CI，准备已提交的阶段报告。由报告记录实际证据，不编造“通过”。
2. 建立唯一checkpoint tag指向选定提交；报告可引用预先约定的tag名，避免要求报告把自身提交SHA写进自身形成循环。最终SHA记在Gitea提交说明或发布记录中。
3. 将该Git对象历史、submission/checkpoint-N归档分支及tag传到Gitea。只同步指定引用，不使用会删除/覆盖远端引用的无差别mirror/force操作；普通成员不直接写Gitea main/develop。
4. 从Gitea读取归档tag/分支SHA与GitHub源SHA逐字核对，抽查六文档、源码/测试（相应阶段）及个人作者记录。传输不改变作者身份，不把全组内容压为组长一次提交。
5. 课堂提交链接指向固定tag，并附GitHub PR/CI记录及必要日志。Gitea归档失败或SHA不一致不能勾选已提交，修复后再次核验；不重建merge commit来“看起来相同”。

课堂资料以Gitea为可访问交付位置，GitHub是唯一开发入口。若Gitea已有独立提交造成分叉，停止同步并保存两边引用，先确认来源；不强推覆盖。此流程并不自动复制GitHub Issue/PR对话，它们的课程证据需写入检查报告。

### A.8 规范生效的实测清单

SPEC-019验收必须记录：普通成员及管理员直推main被拒绝；失败测试、失败构建、失败lint分别阻断PR；跳过ci-grader不会获得ci-required成功；feature直接指向main被策略拒绝；目标更新后旧检查不能继续放行；修复PR正常通过；发布修复回灌；Gitea归档tag SHA一致。组员审批已按组长要求从必需门禁移除，故不再把“新提交撤销旧批准”列为本项目当前验收项。

可用临时演练PR测试这些阻断，失败提交不合入main。保存截图/日志、操作者、日期、规则配置及对应SHA。2026-10-13已通过 GitHub API 核对 main/develop 保护配置及 PR #5 的真实 CI 成功；直推拒绝、故意失败检查、目标分支更新、release 回灌与 Gitea SHA 核对仍未演练，不能把配置读取当作负向测试已通过。


### A.9 分支×阶段的唯一门禁矩阵

阶段由受保护配置和实际代码范围确定，不能由PR作者标签自由降级。文档阶段不创建虚假应用检查；一旦升级不得因失败退回。

| 目标与阶段 | 允许来源 | ci-required必须核验实际成功的集合 |
|---|---|---|
| develop，CP-1纯文档 | feature/* | ci-policy、ci-lint（此时只检查文档） |
| develop，开始应用开发 | feature/*、release/*、hotfix/*、backport/* | ci-policy、ci-lint、ci-test、ci-build |
| develop，评测集成之后 | 同上 | ci-policy、ci-lint、ci-test、ci-build、ci-grader |
| release/*，软件冻结 | release-fix/*、hotfix/*、backport/* | 上述完整五项 |
| main，任何软件PR | release/*、hotfix/* | 上述完整五项 |

ci-required自身也是每阶段必需检查，必须总执行并验证该阶段每项真实success，missing/skipped/cancelled不得放行。develop从首次带应用源码的PR起启用应用门禁；仅实现的单元参与测试，但该单元0测试失败。涉及评测实现的首个PR即启用ci-grader，不推迟到发布。应用门禁升级与相应源码同PR记录；分支保护的新增required checks由管理员配置、API读回并留证，不要求组员审批。main/release不接受渐进式门禁。

release-fix/*仅从目标release建立且只回该release。backport/*从接收修复的develop/活动release建立，只移植已通过PR与CI合入的发布/热修复提交，PR必须引用来源SHA及原PR；不得借回灌带新功能。普通feature只回develop。main的revert走hotfix，其他共享分支的revert按其允许来源提交。分支前缀规则及目标在ci-policy验证。

CP-1可在通过文档门禁的develop提交上打文档tag；main的初始化不是软件发布。六项完整软件检查没有文档例外，也不声称每个develop文档PR都执行尚不存在的引擎。
