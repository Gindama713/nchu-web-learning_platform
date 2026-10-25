# SPEC-008/R37：004备课关联随堂测定向联调

> 2026-10-19当前收口：#27—#35及#38修复已合入develop；原004/007/017接口缺陷复验通过，仍缺页面/全组环境另列。131行现为本地81通过/50阻断、集成81通过/50阻断，见[合入后复验与剩余工作](SPEC-010B_POSTMERGE_ACCEPTANCE.md)。以下旧日期、SHA、计数和“待合入/失败”均为当时记录，不覆盖本条当前结论；完整SPEC及课堂未关闭。

黄俊诚（24201716），2026-10-16，Asia/Shanghai。执行人为黄俊诚授权下的Codex；不代表非作者批准或教师验收。本包只补004→008的R37缺口，不关闭I-03，也不展开下一包003→006/008的完整R01资源保护接缝。

当前结论：真实004、008接口可联通，核心关联与保护子集通过；**完整R37仍阻断**，原因是下述两项004契约失败及备课页面缺口。没有发现需修改本人008/006业务代码的缺陷，未改004/003/007、迁移、APIC、DBD或CI。

## 基线与已有覆盖

工作区从材料分支干净接入，fetch后origin/develop为`dfb23271b470a93d557a2695fed0e04caf59d0d2`。从该版本新建`feature/spec-008-preparation-integration`，没有复制未合入feature代码。已记录的#18/#19/#20/#21/#22/#23/#24/#26八个actual merge逐个对origin/develop祖先核验通过。003/#19、004/#20、007/#21已经合入；不将“未重新验证”写成“未开发”。

[#27](https://github.com/Gindama713/nchu-web-learning_platform/pull/27)仍open，head `7096b496504f62181f60987062b1397bdb96a937`；[#28](https://github.com/Gindama713/nchu-web-learning_platform/pull/28)仍open，head `8111c5395d8b7cf33205065c77490593e07ed045`。两PR merged=false、merged_at=null，comments/reviews/review_threads均为空；状态/head未变，复用既有固定Actions38896062651/38904433916证据，不重跑CI或两个C12b脚本。`merge_commit_sha`是CI测试引用，不是actual merge。详见[接入快照](evidence/spec-008/r37/entry-state.json)。本包不改#27/#28。

依据：[PRD SPEC-008有效验收](PRD.md#accept-spec-008)、[R37原条款](PRD.md#r37)、APIC§3备课随堂测关联/§4.4、DBD§3 preparation_quiz/§4发布及冻结关系。

原`tests/test_preparations.py`只直接SQL创建空quiz草稿来验证404，没有真实006编卷/008专用发布、名单/讲评闭环；原`tests/test_quizzes.py`覆盖008名单、窗口、发布和review，但没有调用preparations接口。因此补[定向测试](../tests/test_preparation_quiz_integration.py)，原E008/EQB的全版本保护、并发及其他既有结果按固定证据复用，不重跑整套专用链。

## 正式执行与证据分层

代码提交及正式干净tested均为`7204a14054611ab6b68f4ebfae3fd1c6115d575d`，两份正式JSON的dirty_paths均为[]。证据提交不改变实际tested。最终PR head及独立CI只写PR和两份本地排除交接，避免提交自身SHA循环。

- **真实handler/SQLite**：[handlers.json](evidence/spec-008/r37/handlers.json)、[原始日志](evidence/spec-008/r37/handlers.txt)。8项，6通过、2项明确的004契约预期失败，17.525秒；无意外失败。逐请求保存实际状态/响应，逐测试保存preparation_quiz、paper状态/时间、冻结名单、答卷、审计及foreign_key_check。预期失败不是验收通过。
- **真实socket HTTP及现有008 UI**：[browsers.json](evidence/spec-008/r37/browsers.json)。Chrome155.0.8059.41、Edge155.0.4283.45各5组通过，page_errors=[]；每浏览器2份备课关联原同一paper，paper总数1、名单1、答卷1，外键检查为空。
- **故障夹具**：初始admin/teacher bootstrap、TEST_NOW；冻结UPDATE仅尝试并回滚；preparation通知失败触发器用于事务回滚。成功业务对象均由实际001/005/006/008/004接口创建，不直接插业务表绕过发布，无成功响应mock。浏览器辅助启动器的账号/课程/初始名单调用实际handler，知识/题目/quiz/备课及后续成员变更走socket HTTP。
- **UI缺口**：当前`frontend/js/main.js`没有备课组件/路由，未实现或伪造队友页面。008页面使用从真实备课响应取得的原quiz ID，在已有随堂测列表打开；这不冒充“从备课页面点击跳转”的验证。真实课堂/教师/目标环境均未执行。

390px截图已逐张目视，无横向溢出，开始前无题干，截止未讲评无参考答案，讲评后才显示答案/解析：

| 浏览器 | 开始前 | 截止未讲评 | 讲评后 |
|---|---|---|---|
| Chrome | [图](evidence/spec-008/r37/chrome-prestart.png) | [图](evidence/spec-008/r37/chrome-unreviewed.png) | [图](evidence/spec-008/r37/chrome-reviewed.png) |
| Edge | [图](evidence/spec-008/r37/msedge-prestart.png) | [图](evidence/spec-008/r37/msedge-unreviewed.png) | [图](evidence/spec-008/r37/msedge-reviewed.png) |

## 实际覆盖与剩余阻断

本节是本次执行说明，唯一验收矩阵仍是[原JSON](evidence/c12a/acceptance-matrix.json)及[原Markdown](evidence/c12a/acceptance-matrix.md)。仅补SPEC-008/R37一行，保留原行历史、编号、判定、head/tested、附件；其余130行不变。本分支131行仍本地80通过/0失败/51阻断、集成59通过/72阻断；#27三个NF-UI集成通过的分版本事实仍按其固定head引用，不复制或重判。

实测已覆盖：

1. 真实知识→题目→quiz草稿→备课草稿；同课quiz可关联。跨课quiz、同课非quiz创建/PATCH均404，重复ID均400；拒绝前后关联、状态及审计不变。
2. draft及published备课copy保留原quiz ID、创建新draft；paper总数及状态/窗口/名单保持，未复制或自动发布quiz。关联未发布quiz阻止备课发布，失败不写发布审计，具体错误码有下述契约缺陷。
3. 008专用发布冻结名单并保持review_at=null，再发布备课；发布后PATCH quiz_ids返回409，关联保持；数据库UPDATE冻结触发器拒绝修改。这里只证明实际执行的HTTP和UPDATE边界，不推断未测试的其他SQL写入。
4. 测验发布后转入学生能读published备课，但详情及列表的quiz_ids/quizzes均过滤为空；原参与学生可见原ID。开始前paper详情无items，备课关联元数据无题干/答案，具体元数据结构有下述缺字段失败。
5. 开始后真实交卷，截止后未讲评的paper/attempt/wrong-question均不泄answer/explanation；开放同题练习409。提前review409；到截止真实review提交后才开放原答案。备课自身始终只提供元数据。
6. 同课学生不能publish/copy，非成员404，失效/缺会话401；撤销学生课程访问后备课列表/详情、paper、attempt均404，冻结名单仍保留。通知写入故障使备课发布整体回滚，恢复后真实发布成功。

**R37-004-01（SPEC-008/R37、SPEC-004/R37，负责人罗浩铭）**：APIC§3规定关联draft quiz时发布备课应`409 QUIZ_NOT_PUBLISHED`；实际为`404 NOT_FOUND`，message=`Related paper not found in this course`，details.ids=[1]。最小复现：真实同课知识/题目创建quiz草稿，POST preparations传quiz_ids，再POST preparation/publish空JSON。文件`backend/apis/preparations.py`的`_validate_links`把published筛选并入`_assert_same_course`，将状态失败当作不存在；原备课测试也按404断言。拦截本身有效，错误契约失败。复现测试`test_r37_004_01_unpublished_quiz_requires_contract_409`，实际响应及失败栈完整保留于handler报告。

**R37-004-02（SPEC-008/R37、SPEC-004/R37，负责人罗浩铭）**：APIC§3要求学生关联元数据`{id,title,window_state,start_at,end_at}`；真实学生GET preparation的quizzes项只有`{id,title,start_at,end_at}`。最小复现：008专用发布quiz后发布备课，以原冻结学生GET详情/列表。文件`backend/apis/preparations.py`的`_serialize`直接投影paper四列，未派生window_state。原008 GET paper/quiz的window_state正常；未借此修改008业务。复现测试`test_r37_004_02_prestart_metadata_requires_window_state`，socket双浏览器也复现该缺字段。当前没有泄题，但具体契约未满足。

两项测试使用`@expectedFailure`显式登记已复现的队友缺陷，正常CI会显示expected failures=2；CI绿色不能把两项改判通过。负责人修复后，测试应出现unexpected success，届时需核对新actual merge及受影响验证再移除标记，不继续固化错误行为。备课页面缺口继续由004负责人处理；未发送协作消息。

原B12 Q9 preparations 404仍为原版本历史，不能用作当前接口不存在的依据。R01仅覆盖本包备课入口的答案保护，003源文件/旧版本/原子导入尚待下一包；R36/R16/R44的相关子集在本报告登记，不重判这些原矩阵行，更不关闭完整UC-02/I-03。

## 复现、失败留痕与回退

```text
.venv/Scripts/python.exe -m scripts.verify_r37_handlers --output <临时输出目录>
.venv/Scripts/python.exe -m scripts.verify_r37_browsers --output <临时输出目录>
.venv/Scripts/python.exe -m ruff check tests/test_preparation_quiz_integration.py scripts/verify_r37_handlers.py scripts/verify_r37_browsers.py
```

浏览器需可选requirements-browser.txt、已安装Chrome/Edge及空闲5000/5173；自动关闭本次服务器/浏览器/临时库。复用旧脚本启动/登录helper，不执行两个既有C12b脚本或原008全套main。

首轮浏览器预检在收到预期404后，脚本错误地假定所有JSON都有data字段，抛出KeyError；[原失败报告](evidence/spec-008/r37/preflight-failure.json)保留。改为读取错误信封后，预检和正式干净双浏览器运行通过；此为测试脚本修复，不是业务修复。首次目录定位把数组传给PowerShell Filter及猜测不存在的004实施文件名也失败，已改为目录名筛选/实际文件定位；未据此判模块不存在。原历史业务/辅助失败与旧矩阵证据均未删除。

回退只撤销本包新增联测、证据及R37增量记录，不改已合入业务、旧迁移、数据库事实或原历史证据。没有部署/发布、直推共享、强推、删分支或代合并。两份个人交接继续本地排除；最终当前head CI需独立读取run、全部jobs及测试原日志后再写PR和交接。
