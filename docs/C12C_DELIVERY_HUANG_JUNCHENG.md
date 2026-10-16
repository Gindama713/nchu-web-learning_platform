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

先由真实评审人和合并负责人处理#27；实际合入后核验merge祖先并同步。若仅增加已验收文档证据，不重复跑两个C12b脚本。随后按新依赖或具体反馈处理受影响项。材料可继续审阅，不必等全部外部条件齐备。

完整SPEC关闭、I-01/I-02/I-03整链、R22/R45全组证据、R47完整真实非作者复核、Linux4核8GB/50会话/worker性能、课程验收后90天保留与生产同点恢复、Gitea及超星/课堂均未凭本轮关闭。003/004/007/017/018及其他队友接缝由原负责人配合，不能把代码已合入等同整链通过。

本轮只做文档检查、已有证据一致性检查和远程读取；没有重新执行完整业务/浏览器测试，没有更改源码、旧迁移、数据库、API或CI。出现的新文档检查失败应修正后保留检查记录；历史业务/辅助检查失败继续保存在原实施说明和报告中。
