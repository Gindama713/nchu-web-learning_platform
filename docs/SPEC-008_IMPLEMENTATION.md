# SPEC-008 / C05a 专用测验发布与限时作答

责任人：黄俊诚（24201716）。记录日期：2026-10-14，Asia/Shanghai。依据：[PRD完整验收](PRD.md#accept-spec-008)、[APIC§4/9/11](APIC.md)、[DBD§4/7/9](DBD.md)。C05a已实施；C05b逐题统计与显式讲评未实施，008与006完整验收均未关闭。

## 当前恢复点

复用`feature/spec-008-quiz`，原起点为005/006已合入的develop `5718fabf73c39f49ce8231d30620cfe08dd2283a`；本轮fetch后快进到`253a736`，纳入组长PR #8的014漏答筛选修复，不接管014。C05a代码、测试、规格实施说明随本分支提交；实际提交、推送、PR和CI证据在本记录后续补录，不能由本地通过推断远程批准或合并。

下一恢复：先fetch并复核本分支/PR实际head与develop，继续C05b `GET /quizzes/{id}/statistics`、`POST /quizzes/{id}/review`及页面。复用原paper、paper_item、paper_participant、attempt、answer和身份级保密保护；一致读快照统计，零分母null、漏答计入提交分母、简答正确率null、多选比例可超过1。review只允许已published且服务器now≥end_at，在短写事务中把原paper.review_at从null设为now后释放保护。普通paper入口的定时讲评保持原契约。

合并后005/006真实知识双浏览器闭环、003源文件/旧版授权与原子导入、004备课关联/保护联测、目标Linux4核8GB/50会话/worker、完整备份恢复及第二名非作者评审仍待补。C05b后补当前head的真实Chrome/Edge闭环，不把旧006夹具截图当本轮证据。

## C05a实现与约束

- `POST /courses/{id}/quizzes`严格接受paper_id/start_at/end_at及可选confidentiality_note；只发布本课draft quiz，跨课或不存在404、非quiz/重复发布409，未知字段/非法ID/时区与精度/顺序400。通过原paper.publish(quiz=True)执行保密资格、全部版本并发占用和有效学生名单冻结；review_at初始null，不新增quiz表或迁移。
- 专用发布返回201、id=paper_id、paper_id和按服务器时间计算的status=upcoming/open/closed，另含原paper元数据。`GET /courses/{id}/quizzes`是原paper列表的kind=quiz投影，status筛选使用draft/published，window_state才表示时间窗口；分页、当前成员及冻结名单权限复用原服务，元数据不含题干/答案。所有响应no-store。
- quiz发布提醒复用公共notify与notification。在同一发布事务中只向冻结名单学生写入target_type=quiz、target_id=paper.id、event_key=quiz.published:{paper_id}，按(user_id,event_key)去重；普通paper发布quiz也采用此事件。通知只是导航，读取仍经原权限/名单/窗口复核。名单、发布时间、审计或通知任一步失败则全部回滚；转入者不追加历史名单/提醒。
- paper/quiz提交仍走唯一paper_attempt作用域：新受理仅start≤服务器now<end，成功键可在截止后字节一致重放；先复核当前权限，异内容/异卷冲突、换键不能重复交卷。人工批分仅改变最新GET结果，不改首次成功快照；简答pending时总分null，漏答0分和五题型规则复用006。
- 新增独立随堂测区域，复用PaperView的quizOnly模式进行固定版本编卷、列表/筛选/分页、专用发布及原AttemptView作答/历史/批阅。专用发布只填写开始/截止时间；普通试卷仍填写定时讲评。quiz提交采用原quiz别名，丢响应保留原内容和原键重试；倒计时是本机估计，不决定服务端受理或阻止成功键重放。读取失败/身份变化清除旧数据，后台继续执行权限与答案保护。
- 截止且未讲评仍去掉paper/attempt/错题标准答案与解析，并阻止同question其他版本开放练习或用于其他卷。C05a仅验证保护不提前释放；显式review后的释放与统计留待C05b。

## 验证与追溯

执行人：黄俊诚任务下的Codex自动执行，2026-10-14（Asia/Shanghai）。使用临时隔离SQLite与真实create_app、公共迁移、001注册/登录/课程/成员、005章节/知识和006题库/编卷/判分/批阅；仅初始管理员/教师账号bootstrap，知识helper虽然沿用knowledge_fixture命名，实际调用已合入005 API，不是知识表/HTTP替身。服务器时钟通过现有TEST_NOW精确控制；通知失败用受控SQLite触发器注入，前端单元测试使用HTTP/渲染替身，不称浏览器验收。

新增[后端测试](../tests/test_quizzes.py)7项通过（14.550秒）；前端全量50项通过（新增4项），[专用客户端](../frontend/js/quiz-client.test.js)、[发布页面](../frontend/js/paper-view.test.js)及[作答页面](../frontend/js/attempt-view.test.js)分别覆盖专用路径、无自动讲评、会话拒写和本机倒计时归零后的原键重试。全量后端114项通过（173.823秒），前端50项、全仓ruff、前端lint/build、六文档链接与diff检查通过；本轮未执行真实浏览器、003/004联测或目标性能验收。

| 有效编号 | 结果与具体入口 | 剩余证据 |
|---|---|---|
| AC-01 / R12 | 通过（C05a子集）；`test_exact_start_end_shared_replay_and_manual_scores_do_not_rewrite_snapshot`、`test_new_submission_at_end_is_rejected_without_consuming_key` | 真实浏览器闭环及完整UC-02待C05b |
| AC-02 / R18 | 通过（原提交共用）；上面的exact_start_end测试证明跨paper/quiz同一答卷、截止后字节重放、异内容拒绝、批阅后原快照不变 | C05b review后再回归 |
| AC-03 / R33 | 待执行 | C05b逐题统计及分母 |
| AC-04 / R36 | 通过（截止未讲评保护子集）；`test_closed_unreviewed_quiz_protects_all_versions_and_wrong_question_entry` | 显式review后开放及010B成绩分析待执行 |
| R01 | 阻断（003/004部分） | 题库源文件旧版授权、原子导入、备课旁路联测 |
| R02 | 通过（C05a列表/原答卷历史与批阅入口子集）；publication与exact_start_end测试、前端发布/作答组件测试 | 演示与完整UC-02待执行 |
| R16 | 通过（冻结名单子集）；`test_publication_same_paper_null_review_and_frozen_notification_recipients` | C05b缺交统计验证原分母 |
| R25 | 通过（专用公开历史拒绝/全版本占用子集）；closed_unreviewed、public_identity与concurrent_publication测试；006共享保护回归 | C05b释放、004真实联合及专用发布/开放练习竞态补证 |
| R27 | 通过（原判分/批阅子集）；exact_start_end测试及006全量回归 | C05b统计/完整五题型闭环 |
| R37 | 阻断（004未就绪） | 本人提供原quiz ID/元数据/名单/窗口入口，队友备课不得复制状态/提前泄题 |
| R44 | 待执行（完整流程） | C05b故障分支、完整UC-02及跨模块映射 |
| R22 / R45 | 待执行（全组） | 分工与依赖已登记，全组工时/风险证据由原负责人提供 |
| R46 | 通过（本包契约归并子集） | APIC/DBD保留原事实归属和单一定义；003/004接缝待核对 |
| R47 | 待执行 | 涉及权限/工作流/API需两名真实非作者复核；AI检查不作批准 |
| NF-SEC | 通过（本包权限/CSRF/跨课/名单/保密子集）；strict_fields、publication及closed_unreviewed测试 | 教学账号/完整跨模块验收待补 |
| NF-DATA | 通过（同事务回滚与并发去重子集）；`test_public_identity_rejected_and_notification_failure_rolls_back_publication`、`test_concurrent_publication_keeps_one_event_roster_and_notification` | 完整资源/电路备份恢复及生产演练待执行 |
| NF-UI | 待执行（真实双浏览器） | 单元组件替身和lint/build不替代Chrome/Edge当前head证据 |
| NF-PERF | 阻断 | 目标环境/50会话/真实worker未就绪，本机测试秒数不是性能证据 |

复现命令（仓库根；npm命令在frontend目录）：

```powershell
.venv/Scripts/python.exe -m unittest tests.test_quizzes -v
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe scripts/check_docs.py
git diff --check
# frontend: npm test; npm run lint; npm run build
```

没有修改旧迁移、判分规则、队友模块或CI。回退须保存本轮发布、通知、答卷、审计和幂等增量并使用配套代码/一致性备份恢复点；不可删历史paper/attempt或把review_at提前改成截止来绕过保护。没有部署、生产迁移、合并或发布。

## 提交、PR与CI证据

C05a代码/测试/契约记录提交`ce6dbfeb7cd1ce7312f9ab73a23cfe28566c06c6`已推送origin/feature/spec-008-quiz；[PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9)为open/draft，目标develop，实际base为`253a736a79a6b6778e8bde0e58673d1f4c7641d7`。没有008真实非作者批准或实际合并；005/006既有合并及课程评审缺口不因本PR变化。

代码[Actions38564909856](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38564909856)已查询run、全部jobs和ci-test日志：completed/success，ci-policy/ci-lint/ci-test/ci-build/ci-required全部success，ci-grader按develop规则skipped。实际日志后端114项（62.390秒）、前端50项，tested merge=`7a378cf6132ce662b92d7b0b66aa7f413d8cb1e7`，head=ce6dbfe、base=253a736；该merge是CI临时测试引用，不是PR实际合并。随后仅补本节证据的文档提交须独立核对最新head CI，不沿用代码run作最终head批准。最新恢复仍为C05b；完整008/006、真实浏览器/跨模块/目标环境和两名非作者评审未关闭。
