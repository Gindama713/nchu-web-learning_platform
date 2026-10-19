# 黄俊诚 C12c 正式材料与交付清单

黄俊诚，24201716，242017班，g24201710组。材料日期：2026-10-16，Asia/Shanghai。本文供本人、组长和课程检查人员查找交付物。C12c完成当前可独立整理的材料；外部复核、系统验收和提交仍按实际证据保留。整理及文档检查由黄俊诚授权的Codex执行，不能据此填写教师通过或人工复核。

## 依据与版本范围

课程依据为仓库根目录《Web高级编程》课程项目大作业任务说明（24级，下发学生）.docx的“过程监督”“交付说明”及两张命名图片；已实际读取文字并查看图片。[README§7](../README.md#7-检查与提交)和[PRD§10.5](PRD.md#105-提交材料责任)登记同一交付要求。独立的最终报告格式附件未提供，因此个人报告是内容可审阅的准备稿，不能声称已经按教师模板定稿。

本材料分支 `feature/spec-010b-c12c-materials` 从已fetch的develop `dfb23271b470a93d557a2695fed0e04caf59d0d2`建立。没有带入尚未合入的[PR #27](https://github.com/Gindama713/nchu-web-learning_platform/pull/27)文件。C12c以010B统计及本人七SPEC为关联范围，不接管019全组门禁或队友业务。

远程状态及11个历史PR的head、actual merge、真实review记录见[本轮接入快照](evidence/c12c/entry-state.json)。实际merge均由Git祖先核验确认属于该develop；不能由merge推断批准，不能用CI临时merge充作actual merge。快照时间为2026-10-16 20:05:38 Asia/Shanghai，之后的最终C12c head及CI只在对应PR和两份本地排除交接登记，避免循环提交自身SHA。

## 正式交付清单

| 材料 | 已有依据与本轮交付 | 当前完成范围 | 剩余依赖与责任 |
|---|---|---|---|
| 六份需求设计文档 | [README](../README.md)、[PRD](PRD.md)、[APIC](APIC.md)、[ADR](ADR.md)、[CHG-RB](CHG-RB.md)、[DBD](DBD.md) | 沿用有效规格；本轮仅补材料入口和变更追溯 | 各原作者维护；Gitea/课堂由实际负责人留证 |
| 七SPEC测试用例与报告 | [个人测试报告](TEST_REPORT_HUANG_JUNCHENG.md)、原实施说明及固定证据 | 汇总测试范围、环境、证据层和失败留痕；引用完整131行矩阵 | 原51个本地阻断及未关闭集成项不改判；外部输入就绪后受影响补验 |
| 阶段检查报告 | [个人检查点报告](checkpoints/HUANG_JUNCHENG_C12C.md) | 按课程目录登记CP-2基础、CP-3统计、CP-4难点和CP-5缺口 | 教师实际检查、全组链路和Gitea证明仍待负责人提供 |
| 本人运行与用户说明 | [本人模块使用说明](USER_GUIDE_HUANG_JUNCHENG.md)、README§8 | 补角色步骤、判断结果和失败恢复；启动命令沿用README | 完整部署/worker/备份为原负责人职责，未实测部分不宣称可用 |
| 个人设计报告 | [Markdown内容源](reports/24201716_黄俊诚_设计报告.md)、[Word准备稿](reports/24201716_黄俊诚_设计报告.docx) | 说明七SPEC设计、010B统计、算法难点、测试和贡献追溯 | 缺教师最终格式附件；补真实复核、课堂及归档结果后再定稿 |
| 小组报告与源码设计ZIP | README§7、PRD§10.5及已有源码 | 本轮提供本人可引用材料，不制作小组最终发布包 | 组长汇总，真实班级/组号及教师命名习惯核对；本轮不归档/发布 |

## 验收数字的两个来源

本轮不建立第二套验收矩阵。[本分支现有131行JSON](evidence/c12a/acceptance-matrix.json)及[逐项Markdown](evidence/c12a/acceptance-matrix.md)来自develop，保留原编号、字段、附件和历史SHA。JSON是逐项状态来源；本页数字只是按版本汇总。

| 固定来源 | 本人本地 | 集成登记 | 如何使用 |
|---|---|---|---|
| develop `dfb23271` 内现有矩阵 | 80通过／0失败／51阻断 | 59通过／72阻断 | 本材料分支本地链接指向该版本 |
| 待合入#27，head `7096b496` | 80通过／0失败／51阻断 | 62通过／69阻断 | 三个NF-UI受影响补验已通过；登记及附件尚随#27等待合入 |

#27的[固定矩阵](https://github.com/Gindama713/nchu-web-learning_platform/blob/7096b496504f62181f60987062b1397bdb96a937/docs/evidence/c12a/acceptance-matrix.json)、[正式审计](https://github.com/Gindama713/nchu-web-learning_platform/blob/7096b496504f62181f60987062b1397bdb96a937/docs/C12A_ACCEPTANCE_AUDIT.md)及[补验快照](https://github.com/Gindama713/nchu-web-learning_platform/blob/7096b496504f62181f60987062b1397bdb96a937/docs/evidence/c12a/c12b-code-head-ci.json)可按该head复核。`integration_recheck_followups[2]`记录在干净develop上的两份报告及10图。只有SPEC-006/NF-UI、SPEC-008/NF-UI、SPEC-012/NF-UI的集成登记变化，其余128行相同。C12c不复制、修改或重新执行这些证据。

## 当前缺口与后续顺序

下一轮先做下方更正章节中的004→008 R37定向验证；该工作可与#27/#28真实审阅并行，不以两个材料/补证PR待合入阻塞已在develop的业务接缝验证。#27实际合入后仍须核验merge祖先再同步；若仅增加已验收文档证据，不重复跑两个C12b脚本。

完整SPEC关闭、I-01/I-02/I-03整链、R22/R45全组证据、R47完整真实非作者复核、Linux4核8GB/50会话/worker性能、课程验收后90天保留与生产同点恢复、Gitea及超星/课堂均未凭本轮关闭。003/004/007/017/018及其他队友接缝由原负责人配合，不能把代码已合入等同整链通过。

本轮只做文档检查、已有证据一致性检查和远程读取；没有重新执行完整业务/浏览器测试，没有更改源码、旧迁移、数据库、API或CI。出现的新文档检查失败应修正后保留检查记录；历史业务/辅助检查失败继续保存在原实施说明和报告中。

## 本人剩余工作清点与下一步（2026-10-16更正）

本节是行动安排，不是第二套验收矩阵。**撤回33cab7e清单中“没有可独立推进的编码或验证项”的结论。** 上轮沿用C12a的旧阻断描述，未充分核对已合入队友模块，把“尚未重新验证接缝”写成“队友尚未完成”。003/004/007等当时已经包含在所用develop及当前分支中；本次更正不写成刚发生的新合入，也不将其模块已合入等同本人跨模块验收通过。

### 已核实的合入事实

本次fetch后origin/develop仍为 `dfb23271b470a93d557a2695fed0e04caf59d0d2`。下表各PR元数据均实读merged=true，actual merge逐个核验为origin/develop及当前材料分支祖先（各exit 0）。仅定向核对已知PR和本人接缝，不开展全组源码审计。

| 模块／PR | actual merge SHA |
|---|---|
| 009／[#18](https://github.com/Gindama713/nchu-web-learning_platform/pull/18) | `53d9a2a4db9aa715c8951a99a25005b497b38024` |
| 003／[#19](https://github.com/Gindama713/nchu-web-learning_platform/pull/19) | `991566cbdb84a036259363d43b89a16dc52cdbed` |
| 004／[#20](https://github.com/Gindama713/nchu-web-learning_platform/pull/20) | `4399cb8138c3f56f23c535f23fe2a5af1d819998` |
| 007／[#21](https://github.com/Gindama713/nchu-web-learning_platform/pull/21) | `d3e0e3325a2892097780b23ca3092140adcccfd3` |
| 017／[#22](https://github.com/Gindama713/nchu-web-learning_platform/pull/22) | `5eea466ec2a9b9f23cc4ccf9f1548d16545b43d1` |
| 010C／[#23](https://github.com/Gindama713/nchu-web-learning_platform/pull/23) | `6ec4c53f6130b3ad3f17b52c757afbf2c0e39b66` |
| 015／[#24](https://github.com/Gindama713/nchu-web-learning_platform/pull/24) | `eaaf043f16e1725886a83166b33c13867ef368dc` |
| 第二次课堂整合／[#26](https://github.com/Gindama713/nchu-web-learning_platform/pull/26) | `dfb23271b470a93d557a2695fed0e04caf59d0d2` |

[应用入口](../backend/app.py)已注册resources/preparations/demo；[resources.py](../backend/apis/resources.py)已有授权内容、旧版当前权限校验和question-imports；[preparations.py](../backend/apis/preparations.py)已有quiz关联、同课校验、复制及发布；[demo.py](../backend/apis/demo.py)已有演示会话及列表。这里只确认代码和注册事实，没有新跑业务，也不判定完整003/004/007验收。旧B12 Q9 preparations 404是历史响应，不能继续用作当前入口不存在的依据。

#27固定head `7096b496504f62181f60987062b1397bdb96a937`、本次更正开始的#28 head `33cab7eac170606382c05fc8ed3b3e2a72bd689d`仍待合入；更正提交最终head及独立CI只写PR和两份本地排除交接，不循环提交自身SHA。

### A/B：可立即开展的本人任务及顺序

A类编码以定向验证发现的本人缺陷为准，目前未据本次只读核对确认新增业务缺陷；不能预先承诺一定需要改代码。B类已有可独立开展的真实接缝验证，不需继续等待003/004/007“开始开发”。按以下顺序分包：

| 顺序／范围 | 具体缺口依据、入口及下一步 | 完成条件及责任边界 |
|---|---|---|
| 1：**004→008，SPEC-008/R37**，关联R01/R36/R44适用子集 | PRD§11.5 SPEC-008及R37、APIC§3备课随堂测关联/§4.4、DBD§3 preparation_quiz/§4。现004已合入，而原矩阵仍引用404阻断；先核对已有测试是否已覆盖真实008，缺少时补真实001/005/006/008/004集成。定位[preparations.py](../backend/apis/preparations.py)、[quizzes.py](../backend/apis/quizzes.py)、[test_preparations.py](../tests/test_preparations.py)、[test_quizzes.py](../tests/test_quizzes.py) | 走真实知识→题目→quiz草稿/专用发布→备课关联/复制/发布及学生读取。覆盖跨课/非quiz/重复ID拒绝、未发布quiz阻止备课发布、复制不自动复制或发布quiz、冻结名单过滤、开始前仅元数据、讲评前后保护及越权/撤权；检查DB关联及状态不被旁路改写。优先完成该有限包，不直接扩成全部I-03 |
| 2：003→006/008，R01及R44适用子集 | 003导入/下载已经有代码；待验证本人题库校验、版本和保密服务与真实资源协作。定位[resources.py](../backend/apis/resources.py)、[question.py](../backend/models/question.py)、[practice.py](../backend/models/practice.py)，沿用APIC§3/4/11和DBD§3/9 | 教师真实源文件导入成功、单条非法全批回滚、原键幂等；学生资源列表/全部旧版/备课均无法取得题库源文件或未讲评解析。先核对已有证据，仅补尚未覆盖的接缝；资源/导入本体缺陷记录给石佰合，不代修 |
| 3：007入口及I-03本人子链，006/008 R02/R44 | 007演示及列表已注册，须从真实入口验证，不再等007开发。先验证004→007→008入口，再与既有006错题→010B掌握度→011检索证据接通；014节点只核对链所需能力，不笼统断言未实现 | 成功及关键失败可复现，明确真实HTTP/UI与算法/故障夹具层次；I-03整链未实际执行前保持未关闭。本人不接管007引擎、004备课或014预警 |

下一轮先执行顺序1。验证和必要本人修复走从最新已核验origin/develop建立或同步的本人008后续feature；不把业务修复或新联测包混入纯材料#28，不改写#27。若缺陷位于004/003/007，保留实际响应、契约差异、负责人和本人阻塞点，不以“接缝修复”接管队友模块。源码未改时也只补确有缺口的证据，不重跑全部已有独立测试。

005/R20旧“011尚未合入”的历史辨析仍成立：#14/#15 actual merge已核验为develop祖先；005改文/下架→011失效、503及恢复已有[固定证据](SPEC-011_IMPLEMENTATION.md#适用验收与证据性质)。相对干净tested `36854081b1ba991a89bacbf7d797ab0620619ae3`，011模型/测试/原浏览器脚本diff为空，005 KnowledgeStore原15方法AST相同。无需把重复C10当作新的接缝验证，也未据此关闭完整R20。

### C：仍需确认的具体契约及其他链路

- **005图文**：003已有授权资源实现，不能再写“003未完成”。尚需确认的是005知识引用关系、同课/资源可见性校验、event_id重试、撤权显示及有效APIC/DBD变更；现APIC§3.1仍禁止知识图片、DBD未定义知识资源引用。先定向核实003能提供的PNG/JPEG和权限行为，再列出真实缺少的契约；未确认前不放开img/外部URL、不写推测适配。003资源由石佰合维护，005接入由黄俊诚负责，契约按真实非作者复核要求处理。
- **I-01**：009/017/010C均已合入，后续应按本人005节点参与定向验证，不能继续整包记为等待开发；本轮不审计其引擎或统计实现，不提前判整链通过。
- **I-02及NF-ISOLATION**：009已合入；018/010D的实际引擎、worker、有效成绩及隔离本轮未核验，状态是“待核实具体能力”，不是已证实未实现或已验收。石佰合负责018/010D，黄俊诚只验证012既定消费节点；不增未知实验成绩字段、不新建事实表。017/010C由罗浩铭负责；019全组组织由姜苏豪负责。

原矩阵131行及#27三个NF-UI分版本事实保持，未全量重判其他128行。本次更正行动清单不将任何阻断行自动改为通过/不适用；下一轮仅对实际执行的有效编号补证，并保留旧判定、历史404/失败、head/tested和附件的追溯关系。

### D：评审、环境与课堂事项

| 事项 | 实际责任与触发条件 |
|---|---|
| #27/#28真实审阅及合入；R47完整非作者复核 | 实际评审人/合并负责人提供具体记录并操作。当前两PR无反馈；本人收到反馈后仅处理对应文件。实际合入后fetch，先核验actual merge属于origin/develop祖先，再按流程同步；仅已验收证据合入不重跑两个C12b脚本。AI自查/CI不充作批准 |
| NF-PERF | 目标环境负责人提供Linux4核8GB、50会话与真实worker，由本人对适用API参与测量；记录普通API p95等实际结果。现有测试耗时不替代目标测量 |
| NF-DATA、NF-ISOLATION | 部署/数据与018负责人提供数据库、资源、电路同点恢复环境及真实隔离证据；成绩/报告课程验收后90天保留和管理员清理留痕须按实际时间与治理执行。本地SQLite副本证据不充作生产恢复 |
| 教师最终格式、真实检查/教学账号、Gitea、超星及课堂 | 教师/检查人员、组长与归档负责人提供格式附件及实际检查/提交记录。黄俊诚届时补个人材料并按教师格式定稿；现有6页Word仍为准备稿，小组ZIP/发布不在本轮执行范围 |

本次更正只更新下一步安排及已合入事实，没有执行新业务联测、实现修复或重生成Word。下一步可立即开展004→008的R37定向验证；真实评审、目标环境和教师材料分别保留等待条件。后续按实际缺陷归属及证据更新，不再用未核验代替未实现。
