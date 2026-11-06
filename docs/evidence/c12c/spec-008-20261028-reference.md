# SPEC-008 2026-10-28 C05a/C05b 补证引用

黄俊诚（24201716），2026-10-28，Asia/Shanghai。本文只索引 008 C05 新基线补证，不复制 PR #46 的原始证据，也不把未合入证据写成本分支或 develop 已有事实。

## 来源与合入状态

| 项目 | 实际值 |
|---|---|
| develop 基线 | `8e32fb41ab9453f8b4b4f8e7be86153a183b88dc` |
| 证据分支 | `feature/spec-008-acceptance-evidence` |
| tested_head | `55167f6f1b04c91606e6e53fa5e7ca339b9cfcbe`（`working_tree_dirty=false`） |
| 证据/记录提交 | `e5b1041502407d46423905844f392c040c9be122` |
| PR head | `9a8343c7a475271f338c5e82a03456b2e8a9d441` |
| PR #46 | open/非draft/merged=false/reviews=[]，base develop `8e32fb4` |
| head CI | run [40647967505](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/40647967505) completed/success；policy/test/lint/build/required success，grader skipped（按 PR #46 说明和上一轮交接记录，本轮未重新查询该 run） |
| 合入结论 | 未合入 develop，不构成合入事实或教师验收 |

PR #46 说明和 `docs/SPEC-008_IMPLEMENTATION.md` 2026-10-28 节记录同一组事实。本文与矩阵中的“008补证引用”都只作未合入证据索引；008 相关行的“通过”仍以已合入 PR #9 的原有证据为基础。

## 验证范围

- 定向后端 48 项通过（`tests.test_quizzes` 15、`tests.test_quiz_analytics_integration` 1、`tests.test_attempts` 16、`tests.test_papers` 16，113.238 秒）。
- 前端 135 项、lint/build 通过；全仓 ruff、`scripts/check_docs.py` 通过。
- Chrome 155.0.8059.86、Edge 156.0.4314.50 各 10 组真实 HTTP/UI 通过（共 20 组），`page_errors=[]`；报告顶层 `status=passed`。
- 使用真实 001 账号/课程/成员、真实 005 知识 API、真实 006 题库/编卷/作答、真实 008 quiz API 和临时 SQLite；服务器 `TEST_NOW` 只控制开始/截止/讲评窗口，网络故障只 abort 真实已提交响应。
- 浏览器运行 2026-10-28 06:56:03—06:56:33 UTC；服务器窗口 06:57—06:58 UTC。390px 元数据/作答/统计/待批/讲评截图已目视，`documentElement.scrollWidth<=innerWidth`。

## 覆盖与未覆盖

| 覆盖 | 本轮证据 |
|---|---|
| AC-01 / R12 | 开始/截止窗口、开始前仅元数据、截止拒新提交、成功键原 201 字节重放 |
| AC-02 / R18 | 同键截止后原响应重放、异内容 409、quiz/paper 同一答卷 |
| AC-03 / R33 | 应交/已交/缺交、漏答分母、简答 null、多选比例 >1、零分母 null、待批不混已批均分 |
| AC-04 / R36 | 讲评 CSRF/Origin 四组 403、仅截止后同课教师可讲评、重复保留首次时刻、讲评前 paper/attempt/错题及同 question 两版本无答案/解析、review 后释放 |
| R16 / R25 / R27 | 发布冻结名单与通知去重、专用发布身份保护、人工批改后原成功快照不变 |
| NF-SEC / NF-UI | 讲评无头/仅 Origin/仅 CSRF/异源+有效 CSRF 均 403；双浏览器各 10 组、390px 无横向溢出 |

未覆盖、仍阻断：R01（003 题库资源/004 备课）、R02（007 页面）、R37（004 契约缺陷与备课 UI）、R44 跨模块完整 UC-02、两名真实非作者复核、NF-PERF 目标环境、生产迁移/恢复及课堂验收。

## 原始入口

以下链接固定到 PR #46 head `9a8343c`，合入状态变化后仍可按该 SHA 复核：

- [浏览器报告 browser-results.json](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/browser-results.json)
- [实施记录 2026-10-28 节](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/SPEC-008_IMPLEMENTATION.md)
- [Chrome 统计](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/chrome-teacher-statistics.png)
- [Chrome 待批](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/chrome-student-pending.png)
- [Chrome 讲评](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/chrome-student-reviewed.png)
- [Edge 统计](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/msedge-teacher-statistics.png)
- [Edge 待批](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/msedge-student-pending.png)
- [Edge 讲评](https://github.com/Gindama713/nchu-web-learning_platform/blob/9a8343c7a475271f338c5e82a03456b2e8a9d441/docs/evidence/spec-008/acceptance-20261028/msedge-student-reviewed.png)

本分支已有的 2026-10-14 旧基线证据仍见 [spec-008/browsers](../spec-008/browsers/browser-results.json)；两者不能相加为新通过数。

## 复现

```powershell
.venv/Scripts/python.exe -m unittest tests.test_quizzes tests.test_quiz_analytics_integration tests.test_attempts tests.test_papers -v
.venv/Scripts/python.exe -m scripts.verify_spec008_quizzes --output docs/evidence/spec-008/acceptance-20261028
```

以上命令需要 PR #46 head 的测试/脚本；本材料分支未复制这些未合入文件，因此不在本分支执行或声称新跑。复现环境、账号和故障夹具见 PR #46 说明及原报告。
