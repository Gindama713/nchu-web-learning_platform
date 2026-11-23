# 结课验收前的缺口清单与进阶建议

整理时间：2026-11-23　整理人：姜苏豪（组长）　对象：g24201710 全组

本文只写**核实过的事实**：每条都给出文件位置、命令输出或提交号，不写「应该没问题」。
按「已修 / 阻断 / 扣分 / 技术不足 / 进阶建议」分级，最后给出到 11-27 的排期。

---

## 0 一句话结论

功能与测试已经够了，**卡在交付动作上**：代码还没合并进 `develop`、没进 Gitea、超星三件套的命名与格式还没做、
石佰合个人材料一份都没有。技术上剩下的问题都不影响演示，属于「有余力再改」。

| 类别 | 数量 | 谁来做 |
|---|---|---|
| 本轮已修 | 4 | 姜苏豪（已完成，提交 `12e4d91`） |
| 阻断交付 | 5 | 组长 2 项 + 石佰合 1 项 + 全组 2 项 |
| 扣分风险 | 4 | 分组补 |
| 技术不足（不阻断） | 6 | 有余力再动 |

---

## 1 本轮已修（有提交与实测）

### 1.1 换位超时状态回补：一个会让 CI 变红的真实回归

- **现象**：`tests.test_seat_swap.test_expires_after_fifteen_minutes` 失败，
  `AssertionError: 'pending' != 'expired'`（60 项里 1 失败，11-23 实测）。
- **原因**：为了让前端 3 秒轮询不写库，`/seat-swaps/incoming` 把 `expire_stale` 整个摘掉了。
  结果超时申请只有在打开换位面板时才落库为 `expired`，直接调轮询接口读到的仍是 `pending`。
- **修法**：`expire_stale` 改成**先 SELECT 探一次、确实有超时行才 UPDATE**；
  轮询端点重新调用它。正常时段仍是纯读（不发 UPDATE、不抢 SQLite 单写者锁），
  真有申请过期才写一次并提交。
- **验证**：`test_seat_swap` 17 项全过；`test_polls / test_classroom / test_identity_attendance / test_assistant`
  合计 61 项通过。

### 1.2 ruff 门禁：163 处 → 0

- **现象**：`ci-lint` 跑的是 `ruff check backend tests scripts`，本次分支上该命令报 **163 处**
  （UP031 70、ISC004 43、RUF059 13、F541 6、BLE001 3、S110 3、PLW1510 3、I001 3、F841 3、SIM102 2 …），
  几乎都在 `scripts/` 的一次性验收脚本里。`ci-required` 要求 lint 成功，**PR 必红**。
- **对照**：用同一条命令在 `origin/develop` 的快照上跑是 `All checks passed!`，
  说明这 163 处是本次分支带进来的，不是历史遗留。
- **修法**：自动修 102 处（含 unsafe fixes）；`backend/` 4 处按真实原因处理
  （`logs.py` 三处故意吞异常补 `S110` 说明，`polls.py` 合并嵌套 if）；新增 `ruff.toml`，
  只豁免 `scripts/*` 的四类规则，理由写在文件头（那些脚本的输出要与 11 月验收记录逐条对照）。
- **验证**：`ruff check backend tests scripts` → `All checks passed!`。

### 1.3 补组员分工表 `docs/TEAM.md`

- 任务书交付说明明确要求「组员分工表」，且根目录 `成员名单.txt` 一直写着「分工详见 docs/TEAM.md」，
  但**该文件此前不存在**——老师顺着名单点过去会直接 404。
- 新建内容：模块归属（每人 1 基础 + 1 独立统计 + 若干智能/难点）、交叉评审对象、交付材料索引、
  分支与合并约定、课堂提交物命名。石佰合一栏如实写「待补」。

### 1.4 老师门户页补「小组交付」分组

- `docs/index.html` 是给老师看的静态入口，原来只有六份主文档、个人材料、检查点、个人报告，
  **没有小组大作业报告和分工表**。已加一组：分工表 / 小组报告（md + docx）/ 教学助手演示脚本。
- 已用脚本校验：5 个分组、所有条目路径都存在、JS 语法可执行。

---

## 2 阻断项（不做就交不出去或直接扣分）

### 2.1 `develop` 还没合并：32 个提交卡在本地

- 事实：`git rev-list --left-right --count origin/develop...develop` → `0 32`；
  `origin/develop` 仍停在 `d75f810`。
- 分支已推：`feature/assistant-20261120` → `12e4d91`（11-23 已推）。
- **动作**：打开 https://github.com/Gindama713/nchu-web-learning_platform/pull/new/feature/assistant-20261120
  开 PR，等 `ci-policy / ci-lint / ci-test / ci-build / ci-required` 五项绿后合并。
- **风险**：`ci-test` 会跑全量后端（本机 Windows 上约 15 秒/用例，全量很久），
  本地只能抽查；合并前必须等 CI 结果，不能看本地绿就合。

### 2.2 项目没有托管在 Gitea（任务书硬性要求）

- 任务书原文：「项目须托管在 Gitea」「所有文档、代码、测试用例均须提交至 Gitea」「每位成员须有独立的提交记录」。
- 现状：只有 GitHub 仓库；课堂服务器 `http://10.83.68.223:3000` 在**当前网络下不可达**
  （11-23 实测 `curl` 无响应），必须在校园网内做。
- **动作**（脚本已备 `test-tmp/gitea-archive.sh`）：
  1. 校内网建空仓库 `g24201710/project`；
  2. `GITEA_URL=http://10.83.68.223:3000/g24201710/project.git bash gitea-archive.sh`；
  3. 脚本自动补 `checkpoint-1-docs`（main 初始提交）与 `checkpoint-2-dev`（develop HEAD）两个 tag，
     用 `--all --tags` 推，**不用 `--mirror`、不 force**；
  4. 推完逐 ref 核对 SHA，不一致不算提交成功。
- **建议提前一天试推**：仓库体积不小，课堂当天首次推容易超时。

### 2.3 石佰合个人材料：0 份

- 事实：`docs/reports/` 只有黄俊诚、姜苏豪、罗浩铭三份个人设计报告；
  `docs/` 下没有 `TEST_REPORT_SHIBAIHE`、`USER_GUIDE_SHIBAIHE`；
  `docs/checkpoints/` 五个文件里没有他的；`docs/evidence/` 没有 spec-003/009/018/010d。
- 他的**代码在主干且有测试**（`backend/engines/grading.py` 真调 `java -Xmx…` + `LOGISIM_JAR_PATH`；
  `tests/test_grading*`、`tests/test_experiments.py`、`tests/test_circuit_lab.py` 齐全），
  缺的纯粹是个人文档。任务书按人核对材料，这一栏空白直接扣个人分。
- **动作**（按优先级）：设计报告 → 测试报告（跑一遍他负责的测试并贴结果）→ 用户手册 → 检查点。

### 2.4 超星提交物命名不合规

任务书附件的命名要求（原文截图核对过）：

| 提交人 | 文件名格式 |
|---|---|
| 组长 | `XX班_第X组_成员名单.txt`、`XX班_第X组_大作业报告.docx`、`XX班_第X组_大作业源码及设计文件.zip` |
| 组员 | `学号_姓名_设计报告.docx` |

现状：小组报告叫 `g24201710_小组大作业报告.docx`，名单叫 `成员名单.txt`，源码包是
`课程学习系统_整合版_2026xxxx.zip`——**三个都不符合**。组员那份 `24201718_姜苏豪_设计报告.docx` 是合规的。

- **动作**：确认班级写法（报告里写的是「班级：242017」），按 `242017班_第10组_…` 另存一份再上传；
  源码包按要求重命名（内容见 2.5 的说明，暂不打包）。
- **建议做成脚本**：`scripts/package_submission.py` 按命名规则生成三件套，避免手改漏改。

### 2.5 小组报告缺封面、目录、页码

- 事实：`docs/reports/g24201710_小组大作业报告.md` 没有目录；`scripts/md2docx_report.py`
  只做标题/段落/表格转换，不生成封面页、目录域、页码。
- 任务书写「报告的具体格式参见附件」，但下发 docx 里**只有命名表格的两张图片，没有格式模板**，
  所以具体样式不可知；按常见要求补封面 + 目录 + 页码最稳。
- **动作**：给 `md2docx_report.py` 加三个开关（封面信息、TOC 域、页脚页码），重新生成 docx。
  目录是 Word 域，打开后按 F9 更新一次即可。

---

## 3 扣分风险（做了更稳）

| # | 问题 | 证据 | 影响 | 建议 |
|---|---|---|---|---|
| 3.1 | 证据目录只覆盖 7/23 个 SPEC | `docs/evidence/` 仅有 spec-005/006/008/010b/011/012/013；缺 001/002/003/004/007/009/010/010a/010c/010d/014/015/016/017/018/019 | 检查「各模块设计与实现代码」时，缺证据的模块只能口头说明 | 每个缺的模块补 2—3 张截图 + 一次运行日志；优先补自己负责的 014/016 |
| 3.2 | SPEC-020（教学助手）没有 `specs/020-*` 目录 | `specs/` 只到 `019-engineering-delivery`；`check_docs.py` 的 `SPEC_CODES` 也只到 019 | 「需求—设计—实现—测试」追溯链在 020 上断了 | 补 `specs/020-assistant/{plan,spec,tasks,wireframes}.md`，并把 `check_docs.py` 的编号范围放开 |
| 3.3 | 用户手册缺一人 | `USER_GUIDE_*` 只有黄、姜、罗三份 | 同上，按人核对 | 随 2.3 一起补 |
| 3.4 | 018 真实引擎只在 main/release 上验证 | `ci.yml` 的 `ci-grader` 条件是 `base_ref == main || release/*` | develop 上看不到真实评测证据，检查时只能引用 main 的一次记录 | 若时间允许，把 `ci-grader` 也挂到 develop（用 xvfb，一条命令即可） |

---

## 4 代码层面的具体不足（不阻断演示，但检查时可能被问）

1. **`frontend/js/main.js` 1690 行**：路由、状态、模板、事件全在一个文件里。能跑，但改一处要全文搜。
   建议拆成 `router / state / views`，或至少把轮询节拍器、课程切换逻辑抽成独立模块。
2. **仍在用 Werkzeug 开发服务器**：`backend/app.py` 里 `app.run(..., threaded=True)`。
   课程规模够用，但这不是生产 WSGI 服务器（gunicorn/waitress）。
3. **`access_log` 无保留策略、`session` 只在登出/重登时清理**：
   `backend/apis/identity.py` 只有登出与同用户互踢的 DELETE，没有过期行清理任务，表会单调增长。
4. **SQLite 单写者 + 读写互斥**：11-12 已把「每个请求都写库」的三处改掉（会话续期限频、日志攒批、换位读取纯读），
   但任何新功能只要在请求主链路写库，多人并发时仍会排队。这条要写进新功能的评审清单。
5. **本地跑不动全量后端测试**：Windows 上约 15 秒/用例，全套 50+ 文件要很久，
   所以「本地全绿」不能代替 CI。日常只能按文件抽查（`python -m unittest tests.xxx`）。
6. **教学助手是规则分类，不是语义模型**：完全没有词表线索的说法（例如「给我整点有用的」）仍会走澄清。
   这是刻意选择（断网可跑、数字可复算），但被问「为什么不上大模型」时要按 `DEMO_SCRIPT` 第 3 节的话术回答。

---

## 5 进阶建议（按性价比排序）

### A. 交付工程化（半天，直接降低出错概率）

1. `scripts/package_submission.py`：一条命令生成超星三件套（按班级/组号命名），并打印核对清单。
2. `md2docx_report.py` 加封面/TOC/页码（见 2.5），三个报告一起重生成。
3. `scripts/verify_submission.py`：检查命名、文件是否存在、docx 是否含目录、截图是否打码。

### B. 演示加分（半天）

4. 教学助手加「把这次回答导出为 PNG」：回答卡片本身就是 DOM，用 canvas 渲染或直接截图，
   现场交报告时能贴图。
5. 演示脚本加一段「断网演示」：拔网线后提问仍能答，直接证明不依赖外部模型——这是本方案最强的差异点。
6. 图表加 hover 数值（`<title>` 已用于环形，条形/折线补齐），投屏时鼠标一放就有数。

### C. 技术深度（有余力再做，别影响交付）

7. **CI 加固**：把 `ci-grader` 从 main/release 扩到 develop，让 018 的真实引擎在每次 PR 都被验一遍。
8. **数据清理任务**：`access_log` 保留 30 天、`session` 清理过期行，挂在启动时或定时线程里。
9. **前端拆分**：先把 `main.js` 里「课程切换 / 轮询节拍 / 请求封装」三块抽出去，风险最小、收益最大。
10. **助手的可解释性**：给每个 `facts` 加「怎么算的」一行（分母、时间窗、样本数），
    比现在只在 `caveats` 里说更硬。

### D. 不要再做的事（避免返工）

- 不要为了「看起来像 AI」去接大模型 API：会破坏「数字可复算、断网可跑」这条底线，且现场网络不可控。
- 不要再用 `git checkout <分支>` 切分支（会重写整个工作区，中途打断会丢文件）；用 `git branch -f` 或 `git switch`。
- 不要在没有 CI 结果的情况下合并 PR，也不要用 `--no-verify` 跳过钩子。

---

## 6 排期（到 11-27）

| 日期 | 谁 | 做什么 |
|---|---|---|
| 11-23（今天） | 姜苏豪 | 开 PR、盯 CI；确认班级写法，定下三件套命名 |
| 11-24 | 石佰合 | 设计报告 + 测试报告 + 用户手册 + 检查点（四件里至少先交前两件） |
| 11-24 | 罗浩铭 | 补 CP-4 实测记录（双浏览器演示截图）；`evidence/spec-004\|007\|017\|010c` |
| 11-24 | 黄俊诚 | C12C 矩阵 50 条阻断按当前 head 重跑；个人报告补 11 月内容 |
| 11-25 | 姜苏豪 | 报告封面/目录/页码；`evidence/spec-014\|016`；`specs/020` 目录；重生成三份 docx |
| 11-26 | 全组 | 校内网 Gitea 归档 + 两个 checkpoint tag；核对 SHA |
| 11-27 | 姜苏豪 | 按命名生成超星三件套并上传；最后一遍 `check_docs` + 冒烟 |

---

## 附：本文事实的复核命令

```bash
# CI 是否会红
.venv/Scripts/ruff.exe check backend tests scripts      # 期望 All checks passed
.venv/Scripts/python.exe scripts/check_docs.py          # 期望 OK
cd frontend && npm test                                 # 期望 294 项
# 换位过期回归
.venv/Scripts/python.exe -m unittest tests.test_seat_swap
# 远端是否已合并
git rev-list --left-right --count origin/develop...develop   # 期望 0 0
```
