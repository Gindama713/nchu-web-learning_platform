# 姜苏豪个人交付索引

姜苏豪，学号 24201718，242017 班 g24201710 组。本文供组员和课程检查人员定位本人负责的设计、实现、测试及待补证据。依据为仓库根目录的课程任务说明及 [PRD 分工](PRD.md#team-plan)。本人负责 SPEC-001、002 两个基础模块，SPEC-010A 独立统计模块，SPEC-014、016 智能模块和 SPEC-019 工程协作；实验箱连线与 Logisim 在线评测由全组协作完成，不能用本人的模块测试代替。

| 课程所需材料 | 本人入口 | 证据范围 |
|---|---|---|
| 需求、接口、架构、数据库与变更 | [六份主文档索引](../README.md#1-文档入口)、[本人实施记录](JIANG_SUHAO_IMPLEMENTATION.md) | 统一规范在 PRD/APIC/DBD 等主文档；个人记录说明具体实现，不另立契约 |
| 代码与测试 | `backend/apis/identity.py`、`attendance.py`、`analytics.py`、`warnings.py`、`recognition.py`，`frontend/js/main.js`，对应 `tests/test_*.py` | [测试报告](TEST_REPORT_JIANG_SUHAO.md)逐项标明本地、CI 和未执行范围 |
| 阶段检查 | [个人检查点材料](checkpoints/JIANG_SUHAO_2026-10-22.md) | CP-1 至 CP-5 的可演示内容及待教师确认项 |
| 运行与用户说明 | [本人模块使用说明](USER_GUIDE_JIANG_SUHAO.md)、[README 本地运行](../README.md#8-本地运行与验证) | 教师、学生、管理员操作及失败处理；目标环境仍需实测 |
| 个人设计报告 | [Word 准备稿](reports/24201718_姜苏豪_设计报告.docx)、[Markdown 内容源](reports/24201718_姜苏豪_设计报告.md) | 任务书要求的个人文件名；教师最终格式附件未提供，不能称为按附件定稿 |

## 可复核的 GitHub 记录

本人收尾分支 `feature/jiang-completion-20261019` 的最终 head 为 `faf17789bdd0f6bedf073fd1d4c6bd68994664dd`。[PR #39](https://github.com/Gindama713/nchu-web-learning_platform/pull/39) 已合入 `develop`，实际 merge SHA 为 `2973bef7bfadb429fe8b17cfadf2d3a2685c796a`。[对应 Actions run](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/39260824775) 的 ci-policy、ci-lint、ci-build、ci-test、ci-required 均为 success；ci-grader 在 develop 规则下为 skipped。该次 `ci-test` 日志显示后端 376 项、前端 135 项通过。合并及 CI 是工程证据，不等同教师检查、非作者规格复核或 `main` 发布验收。

2026-10-20 已将该 merge SHA 快进同步到本机课堂目录 `D:\Desktop\WebBigHomework(5)\WebBigHomework`，当时 `develop` 工作区干净；这只是本机同步记录，没有 Gitea 提交证明。组员各自提交的 Gitea 分支、课堂检查结果、超星材料须按实际发生的时间与 SHA 另行登记。

## 尚不能勾选的交付

真实教学账号的签到与权限演示、非空班级成绩配对、目标环境/固定 Java 与 Logisim JAR、完整连线及电路判分、50 会话和备份恢复、main/release 拒绝演练、Gitea 同 SHA 归档均未由本材料证明。课程最终小组报告、源码设计 ZIP 和超星提交属于组长汇总责任；应在全组验收和教师格式附件齐备后制作，不能把个人 Word 报告改名充作小组报告。
