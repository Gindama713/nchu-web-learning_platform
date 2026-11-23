# 组员分工表（g24201710 · 242017 班）

课程：《Web 高级编程》　题目：计算机组成原理课程学习系统（中央处理器）
组长：姜苏豪 24201718　组员：黄俊诚 24201716、罗浩铭 24201723、石佰合 24201737

本表是立项分工的归档版本，按实际 SPEC 归属与代码提交记录核对后整理。任务书要求「每人至少负责 2 个模块」，
下表中每人都是「1 个基础模块 + 1 个独立统计子模块 + 若干智能/难点模块」，并在组内互为评审。

## 1 模块归属

| 成员 | 基础模块（必做） | 独立统计子模块 | 智能 / 难点模块 | 交叉评审对象 |
|---|---|---|---|---|
| 姜苏豪（组长） | SPEC-001 用户与课程权限<br>SPEC-002 考勤（二维码/手势签到、座位与换位、课堂投票） | SPEC-010A 考勤与学习表现统计 | SPEC-014 学习预警<br>SPEC-016 受限图片识别<br>SPEC-019 工程协作与交付<br>SPEC-020 教学助手 | 石佰合的评测权限边界 |
| 黄俊诚 | SPEC-005 课程知识<br>SPEC-006 习题与试卷<br>SPEC-008 随堂测 | SPEC-010B 知识掌握度与分类成绩 | SPEC-011 检索问答<br>SPEC-012 个性化推荐<br>SPEC-013 智能组卷 | 姜苏豪模块 |
| 罗浩铭 | SPEC-004 课前备课<br>SPEC-007 课堂演示<br>SPEC-017 实验箱连线 | SPEC-010C 实验完成率与连线错误 | SPEC-015 先修知识图谱 | 黄俊诚模块的交互与算法输入 |
| 石佰合 | SPEC-003 教学资源<br>SPEC-009 实验辅助与电路实验台<br>SPEC-018 电路在线评测 | SPEC-010D 评测通过率与故障统计 | 隔离评测与时序判分（难点模块） | 罗浩铭的实验端口与验证规则 |

模块与需求条目的对应关系见 [PRD 第 4 节](PRD.md#modules-acceptance)，接口见 [APIC](APIC.md)，
数据表见 [DBD](DBD.md)，架构决策见 [ADR](ADR.md)。

## 2 交付材料索引

| 成员 | 设计报告 | 测试报告 | 用户手册 | 检查点 |
|---|---|---|---|---|
| 姜苏豪 | [24201718_姜苏豪_设计报告](reports/24201718_姜苏豪_设计报告.md) | [TEST_REPORT_JIANG_SUHAO](TEST_REPORT_JIANG_SUHAO.md) | [USER_GUIDE_JIANG_SUHAO](USER_GUIDE_JIANG_SUHAO.md) | [JIANG_SUHAO_2026-11-20](checkpoints/JIANG_SUHAO_2026-11-20.md) |
| 黄俊诚 | [24201716_黄俊诚_设计报告](reports/24201716_黄俊诚_设计报告.md) | [TEST_REPORT_HUANG_JUNCHENG](TEST_REPORT_HUANG_JUNCHENG.md) | [USER_GUIDE_HUANG_JUNCHENG](USER_GUIDE_HUANG_JUNCHENG.md) | [HUANG_JUNCHENG_C12C](checkpoints/HUANG_JUNCHENG_C12C.md) |
| 罗浩铭 | [24201723_罗浩铭_设计报告](reports/24201723_罗浩铭_设计报告.md) | [TEST_REPORT_LUO_HAOMING](TEST_REPORT_LUO_HAOMING.md) | [USER_GUIDE_LUO_HAOMING](USER_GUIDE_LUO_HAOMING.md) | [LUO_HAOMING_2026-11-05](checkpoints/LUO_HAOMING_2026-11-05.md) |
| 石佰合 | 待补（学号 24201737） | 待补 | 待补 | 待补 |

石佰合的 SPEC-003/009/018/010D 代码与 `tests/test_grading*`、`tests/test_experiments.py`、
`tests/test_circuit_lab.py` 都在主干并有 CI 覆盖；缺的是个人交付文档，检查时按人核对会扣个人分。

## 3 协作约定

- **分支**：`main` 只接受 `release/*`、`hotfix/*`；`develop` 只接受 `feature/*`、`docs/*`、`test/*`；
  分支名带 SPEC 或日期，例如 `feature/spec-018-grader-real-engine`。
- **提交信息**：`feat(spec-006): ...` 形式关联 SPEC 编号，便于需求—提交—测试追溯。
- **合并门禁**：`ci-policy`、`ci-lint`、`ci-test`、`ci-build` 四项必过，`main`/`release` 另加 `ci-grader`。
- **检查点**：每阶段结果写入 `docs/checkpoints/`，记录时间、执行人、输入、预期、实际与证据位置。
- **评审**：按上表交叉评审，评审意见落在 PR 评论或检查点文档里，不口头通过。

## 4 课堂提交物命名

按任务书附件要求：

- 组长：`XX班_第X组_成员名单.txt`、`XX班_第X组_大作业报告.docx`、`XX班_第X组_大作业源码及设计文件.zip`
- 组员：`学号_姓名_设计报告.docx`

本仓库内对应的源文件是根目录 `成员名单.txt`、[小组大作业报告](reports/g24201710_小组大作业报告.md)、
[各人设计报告](reports/)，提交超星前按上面的命名另存一份。
