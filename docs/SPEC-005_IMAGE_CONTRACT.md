# SPEC-005 图文知识：资源契约与独立准备

黄俊诚（24201716，Nelpine），2026-10-20，Asia/Shanghai。状态：**契约提案及现有边界验证，图文实现仍有003依赖**。本包不修改003业务、共享鉴权、生产迁移或HTML白名单，不发送协作消息，不代合并/发布。

## 当前核验

初始工作区干净，`feature/spec-010b-postmerge-acceptance` head为`7a99ca215595411b8b25b669283dd412cb82e595`。fetch后`origin/develop=2973bef7bfadb429fe8b17cfadf2d3a2685c796a`，与用户快照相同；从该develop新建`feature/spec-005-knowledge-images`，保留原005和010B分支，没有带入尚未合入的PR40材料。

[PR40](https://github.com/Gindama713/nchu-web-learning_platform/pull/40)重新查询为open、非draft、merged=false、merged_at=null，head/base仍为上述SHA，实际reviews=[]；[CI39280808424](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/39280808424)为completed/success。旧PR正文中的“queued”是过期记录，本轮本地交接已纠正；未把merge_commit_sha测试合并引用当actual merge，也未改写/发送PR评论。入口快照随本包证据保存。

依据为PRD§4/§11.5的005、003和R39，APIC§3/§3.1，DBD§3，以及实际005/003代码；没有以“存在预览MIME”推断上传已支持图片。

- `backend/apis/resources.py`的KIND_MEDIA：slides为PDF/PPT，guide仅PDF，video为MP4/WebM，question_bank仅JSON；四种均无PNG/JPEG。VIEWABLE_PREFIXES虽含image/png、image/jpeg，无法从现行合法上传生成对应资源。
- Resource有course_id、当前visibility/archived，ResourceVersion固定file_id；版本模型未返回media_type/图片宽高。普通资源创建默认students，不能直接沿用为尚未发布知识的私有图片上传。
- `backend/models/knowledge.py`只保存title/content/example/published/is_foundational及revision；DB没有knowledge图片关系，未知images/resource_version_ids为400。SafeHTML删除img/a等标签及全部属性；`frontend/js/knowledge-view.js`只有文字编辑及服务端清洗HTML显示，没有图片选择/上传/访问事件。
- 现有content会按当前会话/课程/资源权限拒绝旧URL；文件不存在/archived返回404。但它没有knowledge上下文授权，不能直接作为知识下架后的取图入口。当前先授权、再另起事件写事务，也不能声称已覆盖授权与撤权并发的串行要求。
- 现行UQ(user_id,event_id)及顺序请求可防重试/Range重复。`event_id=not-a-uuid`实际200并入库，违反APIC已有UUID约束；这是003当前缺陷。并发同键和撤权竞态本轮未运行，代码审查发现的风险保持“待验证”，不写成已复现失败。

## 可审阅的契约方案

拟议业务、API和数据定义分别统一放在[PRD§4](PRD.md#modules-acceptance)、[APIC§3.2](APIC.md#32-spec-005图文增量提案2026-10-20待复核实施)、[DBD§3.1](DBD.md#31-知识图片关系增量提案2026-10-20待复核实施)。三处明确待复核/实施，不覆盖当前§3.1禁图契约。本文件只记录分工、依赖及真实结果，不另造规范或验收矩阵。

教师拟议写入示例（当前提交该images字段仍400）：

```json
{
  "title": "程序计数器",
  "content": "<p>PC 指向下一条指令。</p>",
  "example": "<p>执行后 PC<sub>next</sub> 的变化。</p>",
  "published": false,
  "images": [
    {"resource_version_id": 101, "placement": "content", "alt": "PC与指令存储器示意", "caption": "固定资源版本1"},
    {"resource_version_id": 102, "placement": "example", "alt": "执行前后PC值", "caption": ""}
  ]
}
```

101/102仅为格式例子，不是真实验收数据。固定ID属于本课、当前权限、PNG/JPEG字节及20张上限等校验均由服务端执行；不把alt/caption解释成HTML，不把数组变成任意src。

## 黄俊诚的改动清单与先后关系

本轮已经完成契约和独立准备：核对现状；新增6项真实handler/SQLite边界检查及专用执行器；可解码PNG/JPEG探针；保留非法UUID原响应；同步主文档及005/steering摘要。005现有文本编辑、保存、展示和HTML安全边界保持，未发布无资源服务时可调用的图片入口，也未用预置image数据库行冒充真实上传集成。

依赖满足后的本人实现清单：

1. 在`backend/models/knowledge.py`及独立005追加迁移实现knowledge_image与严格数组校验；同课/固定版本/草稿与发布可见性检查、原子替换和revision。只消费003提供的资源元数据与事务内服务，不写上传/存储/资源事件业务。
2. 在`backend/apis/knowledge.py`增加知识上下文图片内容入口，原有列表不抓图；详情只投影当前允许的元数据。复用001事务内会话授权和003内容服务，错误不泄露他课/私有资源信息。
3. 在`frontend/js/knowledge-client.js`、`knowledge-view.js`及本人知识样式中增加本课guide图片固定版本选择、正文后/例题后排序、alt/caption编辑与整体保存。图片经同源鉴权请求→Blob→短期object URL显示；清理旧图、重读权限、失败保留UUID按APIC处理。原服务端清洗HTML仍仅用于文字块。
4. 补本人模型/真实API/前端交互和Chrome/Edge受影响图文链，使用003真实上传所得ID；保存重登、旧版不变、发布/下架、撤权/归档、非法/跨课/越权、重试/并发及失败回滚。替身只能验证组件，不算真实图文验收。

第1项的关系迁移须在003宽高元数据迁移之后协调命名；第2项依赖003可复用服务；第3项依赖资源列表/历史版本的media_type与尺寸以及本人保存/详情接口。当前不提前接入未生效契约，避免默认公开图片或把半个权限链交给用户。

## 石佰合需要提供的能力与验收条件

按现分工由石佰合处理；本轮只提出可审阅清单，未修改其模块或向其发消息。

1. 在`backend/apis/resources.py`支持guide PNG/JPEG真实上传和新增版本、图片限额/字节与完整解码检查、首次默认teacher_only；原文档/视频/题库规则继续有效。在资源列表和版本元数据提供精确MIME、宽高，原版本字节和SHA保留。
2. 提供同一调用方connection内的资源内容/事件服务，统一版本/current权限/归档/文件检查、UUID校验、顺序和并发去重、冲突409、错误不记数及私有no-store缓存头。修复本轮`not-a-uuid`实际200缺陷；不在005再实现一份事件服务。
3. 追加本人资源迁移和必要不可变约束，提供显式归档/恢复行为及旧URL复核；保留现有备课发布引用保护。知识引用不阻止紧急撤权，关联保留并降级占位，不能删旧文件来解除关联。
4. 提供包含上述API/模型/追加迁移的可审阅feature与真实测试；经规定CI/两名非作者复核后合入develop。图片与版本必须经真实API产生，不插表/伪装PDF或借016的file_id；不要求提供真实账号、文件私链或密钥。

解除依赖的可判定条件：合法PNG和JPEG各能上传v1/v2并返回真实固定ID/MIME/尺寸，v1字节与SHA在v2后不变；错误MIME/伪装/空截断/超限被拒且无部分资源；本课学生无上传权、跨课及teacher_only/归档/撤权旧URL404，失败零事件；UUID非法400，同逻辑访问及Range顺序/并发只1事件、异对象/intent409，HEAD/304/416不新增，权限改变后旧ID不可重放。共享服务、缓存与撤权串行的测试证据一并给出，黄俊诚再接入005双重权限，不把PDF对照替代图片证据。

## 本轮验证和证据层次

专用命令（必须使用新的输出目录，执行器拒绝覆盖旧证据）：

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_knowledge_image_contract --output logs/knowledge-images/new-run
```

正式干净tested为`3505978e68efa514c019fcb8c79d907bc898fc21`，dirty_paths=[]；**6项现有边界检查通过、0测试失败/错误，执行器耗时14.436秒；另有1项UUID契约探针真实失败，图文能力blocked**。本机Windows、Python3.13.12；非目标环境性能证据。[正式报告](evidence/spec-005/images-20261020/handlers/report.json)、[原日志](evidence/spec-005/images-20261020/handlers/checks.txt)、[入口快照](evidence/spec-005/images-20261020/entry-state.json)。后续本包文档/证据提交不是这次运行的tested。

执行器分别输出`boundary_checks`、`observations`和`image_readiness`；退出0只代表受测现有边界检查通过，**不代表003契约全部满足或图片可用**。UUID实际失败在[原请求/响应及事件表](evidence/spec-005/images-20261020/handlers/test_pdf_control_retries_range_conflicts_and_non_content_responses.json)中保留expected=400、actual=200和contract_failure；合法UUID及Range只有1条事件，非法UUID又实际新增1条，共2条，不能把总数2误判为重试去重失败。PNG/JPEG为当前类型契约的合法415及图文依赖blocked，不混成图片正向通过。[首次未提交探针报告](evidence/spec-005/images-20261020/preflight/report.json)、[首次UUID原响应](evidence/spec-005/images-20261020/preflight/test_pdf_control_retries_range_conflicts_and_non_content_responses.json)保留；后续只补真实跨课成员、角色标识及失败创建计数断言，没有修003来消除该失败。一次文档补丁上下文不匹配在写入前拒绝，随后按实际行修正；不是业务失败。

6项的覆盖：[PNG/JPEG](evidence/spec-005/images-20261020/handlers/test_png_jpeg_uploads_and_new_versions_are_currently_blocked.json)各四kind上传及各一次新增版本共10次均415、无多余file/resource/version；[005保存/持久化](evidence/spec-005/images-20261020/handlers/test_markup_persists_without_images_urls_or_attributes_after_relogin.json)移除图片/外部URL/data URL/属性，保留上下标，经真实登出/重登及新app读取持久正文，相同PATCH不增revision；[未知字段/权限](evidence/spec-005/images-20261020/handlers/test_unknown_image_fields_fail_atomically_and_roles_remain_enforced.json)整批拒绝、学生/真实另一课程成员/撤权/下架访问受限，失败创建无新增知识；[PDF版本/当前权限](evidence/spec-005/images-20261020/handlers/test_pdf_control_fixed_versions_current_permissions_and_revocation.json)含跨课章节上传404无部分文件；Range同UUID一次事件及跨版本/intent冲突、HEAD/304/416零新事件；[缺文件/归档](evidence/spec-005/images-20261020/handlers/test_pdf_control_missing_file_and_archived_resource_fail_closed.json)404。归档为显式SQL状态注入、缺文件为故障注入，因为当前无归档HTTP动作；不把它们称为真实归档UI。所有账户以外的成功对象通过真实API创建。

Ruff检查仅新增测试/执行器通过；16份变更Markdown按最多3份一批检查本地链接通过。正式证据按3份一批复算上传拒绝、无部分写入、HTML、事件原表、权限/失效、PR40状态及SQLite完整性/外键。backend/frontend/CI及原矩阵相对develop无差异；附件文本统一LF生成[SHA256清单](evidence/spec-005/images-20261020/sha256.json)，不是对运行结果的二次判分。

没有运行全仓后端/前端整包，没有新增浏览器图文正向执行、目标性能、生产恢复或课堂证据。已有验收矩阵不改判；PR40尚未合入，其81/50是该PR的固定收口状态，不从本分支重新计算或复制其增量。历史失败与旧附件不覆盖。

## 交接及回退

下一步先由真实复核确认PRD/APIC/DBD提案及003最小能力；取得含003增量的最新develop后，在本人SPEC feature实现并定向验证上述清单。两名非作者复核是共享API/数据库/权限变更的合入条件，不阻止本轮准备、验证及feature保存。

本包回退仅撤新增探针/执行器、提案和导航；没有生产schema或业务数据变更。未来关系迁移回退须保留新关系/旧版本/事件/学习事实并部署兼容代码，不能清表或改旧迁移。仍未授权共享直推、强推、代合并、发布、归档或协作消息。
