# SPEC-006 / C02a 实施与验证记录

责任人：黄俊诚（24201716）。日期：2026-10-13，Asia/Shanghai。依据：[PRD有效验收](PRD.md#accept-spec-006)、[APIC§4](APIC.md)、[DBD§4/8](DBD.md)。状态：开发中，仅完成C02a可独立实施部分；005知识真实联测、C02b编卷发布及C03/C04尚未完成，006未关闭。

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

下一恢复：优先个人会话计划第6节，继续006同分支fetch/核对PR与CI；C02b可继续实施本人编卷/固定版本/名单/保密发布及教师页面，不将夹具当真实试卷；005进入develop后merge同步并优先补真实知识标签和完整题库保存联测。003仍由队友负责。006未完成，C03/C04及008等其他包未启动；005独立分支仍保留图文/性能恢复点及草稿PR。涉及API/数据库/权限的真实两名非作者批准、CI、课堂/生产验收分别记录。
