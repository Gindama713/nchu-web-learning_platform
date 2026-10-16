# 第二次课堂提交：组员操作提示词

组号 g24201710。此文件供组员在自己的 Git 工作区使用，目标是在老师的 Gitea 仓库保留各人的真实提交，再由组长归档可运行的整合版本。日常开发源仍是 GitHub；课堂 Gitea 地址由老师现场提供，不要猜测地址，也不要提交密钥、数据库、虚拟环境或 `node_modules`。

| 提交人 | 学号 | 本次个人功能分支 |
|---|---|---|
| 黄俊诚 | 24201716 | `feature/spec-006-exercises`、`feature/spec-010b-knowledge-analysis`、`feature/spec-011-qa`、`feature/spec-012-recommendation`（此前 SPEC-008、013 已进入 develop） |
| 罗浩铭 | 24201723 | `feature/spec-004-preparation`、`feature/spec-007-cpu-demo`、`feature/spec-017-wiring-simulation`、`feature/spec-010c-wiring-analysis`、`feature/spec-015-knowledge-graph`（后一个分支包含前四个分支的历史） |
| 石佰合 | 24201737 | `feature/spec-003-resources`、`feature/spec-009-labs` |
| 姜苏豪（组长） | 24201718 | 已并入 develop 的 SPEC-001、002、010A、014、016、019；最终整合及冲突修复在 `feature/classroom-integration-20261016` |

给组员使用的提示词（复制到各自的代码助手，先填入老师提供的 Gitea 仓库地址）：

> 我是 g24201710 的【姓名/学号】，负责上表所列功能。请先确认当前 Git 仓库、未提交改动、GitHub 远端、我的分支和个人提交作者；不要覆盖或重写任何已有提交。老师的 Gitea 仓库地址是【粘贴真实地址】。请用我的 Gitea 账号添加/核对名为 `classroom` 的远端，先 `fetch`，确认不会覆盖远端已有分支，再把我负责的各个 `feature/*` 分支逐一推送到 Gitea 同名分支。若分支已存在，只允许正常快进推送；出现非快进或权限错误就停止并报告，不要使用 `--force`。每次推送后核对 Gitea 对应分支的提交 SHA 与作者，向组长报告分支名、末端 SHA 和 Gitea 页面链接。不要把其他组员的提交改成我的作者，不要直接推老师仓库的 `main`，也不要把个人分支误称为完整可运行版本。

课堂操作顺序：组长先确认老师仓库地址与提交规则；组员分别使用自己的账号推送上述个人分支；组长核对三个组员的分支与作者，然后将已验证的 `feature/classroom-integration-20261016` 完整提交历史归档到老师仓库的第二次提交分支，并依老师要求通过 PR 或指定方式纳入最终验收分支。这个整合分支包含各人的原始提交和组长的合并修复，不能用复制文件、重新初始化仓库或压成单个新提交代替。

组长完成后在老师仓库核对：六份需求设计文档、`backend`、`frontend`、`tests`、`scripts` 和 `.github/workflows` 均在同一提交中；新库迁移可执行；前端测试、lint 和构建可执行；`/api/v1/health` 如实报告数据库就绪与评测 worker 尚未就绪。Logisim 在线评测 SPEC-018 未完成，不得把本次阶段提交称为课程最终完成版。
