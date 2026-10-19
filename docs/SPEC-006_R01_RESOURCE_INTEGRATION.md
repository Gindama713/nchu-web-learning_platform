# SPEC-006/008 R01：003资源保护接缝定向联调

黄俊诚（24201716），2026-10-16，Asia/Shanghai。Codex在本人授权范围执行，仅补003→006/008资源保护接缝，不关闭全部I-03、UC-02或完整SPEC。本包没有发现需修复的本人006/008业务缺陷；未修改003/004业务、迁移、API契约、DBD或CI。

## 接入与已有覆盖

干净工作区fetch后，origin/develop仍为`dfb23271b470a93d557a2695fed0e04caf59d0d2`；8个既有actual merge（#18/#19/#20/#21/#22/#23/#24/#26）逐个通过develop祖先检查。从该提交新建此前不存在的`feature/spec-006-resource-integration`。#27/#28/#29仍open/head未变，实际评论、reviews、review_threads均空，merged=false、merged_at=null；复用固定Actions38896062651/38904433916/38907219999，不重跑CI。其merge_commit_sha是测试引用，actual merge不存在。详见[接入快照](evidence/spec-006/r01/entry-state.json)。没有复制三PR未合入实现或材料。

依据：[PRD有效R01](PRD.md#r01)、[006有效索引](PRD.md#accept-spec-006)、[008有效索引](PRD.md#accept-spec-008)，APIC§3资源/导入/备课及§4版本与讲评保护，DBD§3 question_import及§4 question/version/paper。

已有`tests/test_resources.py`的ResourceImportTest覆盖合法导入、非法单条、同键同import_id和权限，但未贯通导入题目到保密quiz、备课及多版本源下载，原幂等断言未比较完整响应字节。原`tests/test_quizzes.py`覆盖全版本身份/未讲评保护，`tests/test_preparations.py`未覆盖真实题库源文件；#29的R37有限证据独立保留，未复制或重跑。本包新增[四项定向测试](../tests/test_resource_question_integration.py)及两个专用执行器，仅补上述缺口。

## 正式证据与实际覆盖

实现及正式干净tested为`270dd8e2dbf17cfb4104a2dbe1afb9696c173169`；handler/browser两份正式报告的dirty_paths均为[]。后续附件提交不冒充在自身SHA执行；最终head CI独立核对后只写PR及两份本地排除交接，避免SHA循环。

- **真实handler/SQLite**：[摘要](evidence/spec-006/r01/handlers.json)、[原日志](evidence/spec-006/r01/handlers.txt)，4项全部通过，9.737秒，0 expectedFailure。逐请求状态/实际响应、逐阶段DB事实另见[导入原子与幂等](evidence/spec-006/r01/test_r01_import_invalid_atomic_and_original_key_bytes.json)、[源文件全部版本](evidence/spec-006/r01/test_r01_all_source_versions_and_preparation_rejected.json)、[后段故障回滚](evidence/spec-006/r01/test_r01_import_write_fault_rolls_back_and_key_retries.json)、[导入到测验及备课](evidence/spec-006/r01/test_r01_imported_quiz_old_question_version_and_unreviewed_answers.json)。
- **真实socket HTTP及现有UI**：[双浏览器报告](evidence/spec-006/r01/browsers.json)，Chrome155.0.8059.41、Edge155.0.4283.45各4组通过，page_errors=[]。教师实际资源页面上传坏v1、修订好v2并点击导入；学生实际资源/quiz页面补验。每浏览器DB为1题/1导入批次/1答卷/1冻结参与人，foreign_key_check=[]。
- **夹具**：测试基础设施只bootstrap初始admin/teacher并控制TEST_NOW；学生注册、课程/成员使用真实001 API。handler知识/资源/题目版本/测验/备课及成功业务均走真实handler；浏览器helper仅账号/初始课程成员经handler，其后上传、导入、知识、测验、备课、提交、讲评均走socket HTTP。独立故障触发器在`resource.question_import`审计前ABORT，验证已创建题目/版本/标签、批次和成功幂等键均回滚，移除触发器后原键真实成功。没有成功mock或直接插业务表绕过发布。SQL仅用于bootstrap、事实读取和该故障注入。

实际断言范围：

1. 真实multipart上传JSON题库；第2条非法返回400 VALIDATION_ERROR及题目[1]，question/version/knowledge/import/idempotency/audit均无部分写入。上传合法修订版后，原失败键可成功；同成功键返回原201完整字节且数据库不变，换version同键409，无新题或批次。学生导入403、非成员404。
2. handler建立同一题库源3个版本，教师旧版实际下载字节等于上传内容。学生资源列表、kind筛选、标题检索均排除该源；版本列表404；三个版本的GET download/view、HEAD及Range均404，不增加resource_event。强改question_bank为students返回422且DB不变。浏览器验证坏v1/好v2两个版本的真实教师字节和学生404。受测`/uploads/{storage_key}`及`/api/v1/files/{storage_key}`均404，仅证明这些候选路径没有旁路，不据此推断任意未知URL。
3. 每个源版本可供教师存draft备课，但发布404 NOT_FOUND，状态/关联/审计不变；学生草稿详情404、列表不出现。无题库源经备课暴露。这里APIC未规定该场景具体错误码，不把404归为R37未发布quiz错误码缺陷。
4. 从实际导入返回的question_version_id创建保密quiz，再经006 PATCH生成同question新版本。008专用发布冻结名单、review_at=null；真实004发布仅含该quiz的备课。学生备课只返回关联元数据，开始前paper无items；私有题目直接备课发布拒绝。同question新版本仍不能开放练习（409 QUESTION_RESERVED）。
5. 开始后真实交错答案，截止未讲评paper/attempt/wrong-question/题目列表/备课列表详情均无标准answer/explanation；现有quiz UI有题干和原作答、无参考答案/解析。真实review后才在paper及原答卷UI开放原导入版本的答案/解析，DB仍只有一批导入和一份答卷。

390px共8图逐张目视：没有横向溢出，资源页不显示题库源，开始前无题干，截止未讲评无参考答案/解析，review后才显示：

| 浏览器 | 资源列表 | 开始前 | 截止未讲评 | review后 |
|---|---|---|---|---|
| Chrome | [图](evidence/spec-006/r01/chrome-student-resources.png) | [图](evidence/spec-006/r01/chrome-prestart.png) | [图](evidence/spec-006/r01/chrome-unreviewed.png) | [图](evidence/spec-006/r01/chrome-reviewed.png) |
| Edge | [图](evidence/spec-006/r01/msedge-student-resources.png) | [图](evidence/spec-006/r01/msedge-prestart.png) | [图](evidence/spec-006/r01/msedge-unreviewed.png) | [图](evidence/spec-006/r01/msedge-reviewed.png) |

## 未完成边界、矩阵与失败留痕

**R01资源/导入及现有quiz入口的受测子集通过；完整R01仍阻断于004备课UI，完整I-03未执行。** 当前frontend/js/main.js未接入备课组件，不能证明“学生从备课页面点击”的UI链；浏览器消费真实preparation响应的原quiz ID，再在现有quiz列表打开，不冒充备课跳转。

R37仍由罗浩铭负责：**R37-004-01（SPEC-004/008 R37）**关联draft quiz发布应409 QUIZ_NOT_PUBLISHED、实际404 NOT_FOUND；**R37-004-02（SPEC-004/008 R37）**学生quizzes元数据缺window_state。最小复现、实际响应及`backend/apis/preparations.py`位置继续见[#29](https://github.com/Gindama713/nchu-web-learning_platform/pull/29)的固定head `b56141f2e060d1ec5464d58d52f6f735c445d56c`及`docs/SPEC-008_R37_INTEGRATION.md`。本分支基于develop，该未合入文件不复制；本轮socket再次观察缺window_state，未重跑R37整包，不能将#29的两项expectedFailure判通过。本包未发现新的003/004本体缺陷；003负责人石佰合、004负责人罗浩铭，未代修或发协作消息。

仅补[原JSON矩阵](evidence/c12a/acceptance-matrix.json)及[原Markdown矩阵](evidence/c12a/acceptance-matrix.md)的SPEC-006/R01、SPEC-008/R01两行；原整行存入R01_历史记录，原head_SHA/本轮tested_SHA/附件字段保留，新增本包tested和附件。其余129行不变，包括本分支R37原历史行；R37当前事实按#29固定版本引用，不把旧404说成当前接口不存在。131行仍本地80通过/0失败/51阻断，集成59通过/72阻断；#27三个NF-UI分版本补验未复制或重判。005图文、完整R44、R47、其他链、目标环境和课堂均未关闭。

辅助失败全部保留：[handler预检摘要](evidence/spec-006/r01/preflight-handler-failure.json)、[栈/日志](evidence/spec-006/r01/preflight-handler-failure.txt)为记录器将HEAD空body当JSON解析；已用silent解析修正。[浏览器预检1](evidence/spec-006/r01/preflight-browser-failure1.json)为select嵌套选项文本导致精确label定位超时；[预检2](evidence/spec-006/r01/preflight-browser-failure2.json)为上传版本刷新重建列表后版本历史折叠，脚本未重新展开。均为脚本定位/诊断修复，未更改业务。另首次探测本地AGENTS.md、gh和猜测资源客户端文件名未命中，已使用用户给定规则、GitHub连接器及实际文件继续；未据此判业务缺失。正式通过记录与这些预检失败分开，未覆盖失败文件。

## 复现与回退

```text
.venv/Scripts/python.exe -m scripts.verify_r01_handlers --output logs/r01/recheck-handlers
.venv/Scripts/python.exe -m scripts.verify_r01_browsers --output logs/r01/recheck-browsers
.venv/Scripts/python.exe -m ruff check tests/test_resource_question_integration.py scripts/verify_r01_handlers.py scripts/verify_r01_browsers.py
```

浏览器依赖requirements-browser.txt、现有Chrome/Edge与空闲5000/5173；复用旧启动/login helper，结束关闭本次服务器/浏览器/临时DB及上传目录，不执行两个C12b脚本或原整包main。正式两脚本在干净tested各执行一次；无业务修复，因此不追加无关整包本地回归。正常PR CI仍按既有流程自动执行。

回退仅撤销本包新增定向测试/执行器/证据及两行增量，不改已合入源码、旧SQL、既有历史与数据库事实。未直推共享、强推、删分支、代合并、部署/发布或发送协作消息；两份个人交接继续本地排除。PR最终head、独立CI run/全部jobs/测试原日志核验结果只落PR及个人交接。
