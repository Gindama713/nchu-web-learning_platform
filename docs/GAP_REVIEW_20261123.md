# 结课验收前的缺口清单与进阶建议

整理时间：2026-11-23 19:15（第 2 版）　整理人：姜苏豪（组长）　对象：g24201710 全组

第 1 版写于 18:40，当时 PR 未合并、石佰合材料为空。19:00 前后 PR #91 合并、交付工具链落地，
本文按**当前仓库实际状态**重写：已解决的移入第 1 节，剩下的逐条给证据与责任人。
每条都可用附录命令复核，不写「应该没问题」。

---

## 0 结论速览

| 维度 | 状态 |
|---|---|
| 代码合并 | ✅ PR #91 已合并，`develop` 到 `606890c` |
| 文档六件套 | ✅ PRD / README / APIC / ADR / CHG-RB / DBD 齐全，`check_docs.py` 通过 |
| 个人材料 | ✅ 4/4：设计报告（md+docx）、测试报告、用户手册、检查点 |
| 交付工具 | ✅ `package_submission.py` / `verify_submission.py` / `gitea-archive.sh` / `SUBMISSION.md` / `specs/020-assistant/` |
| 测试 | ✅ 后端全量 560 项通过（1303 秒）；前端 294 项；ruff 全绿 |
| 外部提交 | ❌ Gitea 归档、超星上传**都还没做**（需要校园网 / 账号） |
| 人工闭环 | ❌ C12C 50 条阻断、CP-4 双浏览器实测、16 个 SPEC 的证据目录 |

**一句话**：不能再叫「差很多东西」了，剩下的是**两类**——(a) 只能在校内网和超星上做的手动动作；
(b) 三个人各自的现场实测与证据补齐。技术上剩下的都不影响演示。

---

## 1 已解决（有提交号，可复核）

### 1.1 换位超时状态回补 —— 曾是一个会让 CI 变红的真回归

- 现象：`tests.test_seat_swap.test_expires_after_fifteen_minutes` 报 `'pending' != 'expired'`。
- 原因：为了让前端 3 秒轮询不写库，`/seat-swaps/incoming` 把 `expire_stale` 整个摘掉了，
  超时申请只在打开换位面板时才落库。
- 修法：`expire_stale` 改成**先 SELECT 探、确实有超时行才 UPDATE**，轮询端点重新调用。
  正常时段仍是纯读；真有申请过期才写一次。（`12e4d91`）

### 1.2 ruff 门禁 163 处 → 0

- `ci-lint` 跑 `ruff check backend tests scripts`，本次分支曾报 163 处；
  同一条命令在 `origin/develop` 快照上是 `All checks passed!`，说明是分支带进来的。
- 自动修 102 处 + `backend/` 4 处按真实原因处理 + 新增 `ruff.toml` 只豁免 `scripts/*` 四类。（`12e4d91`）

### 1.3 补齐此前缺失的交付物

| 项 | 说明 |
|---|---|
| `docs/TEAM.md` | 组员分工表；`成员名单.txt` 一直引用它但文件不存在 |
| `docs/SUBMISSION.md` | 超星提交操作说明（命名、口令、人工核对项） |
| `scripts/package_submission.py` | 按 `XX班_第X组_` 生成三件套 + SHA256 核对清单 |
| `scripts/verify_submission.py` | 机器自检：命名/摘要/目录域/页码/源码包 |
| `scripts/gitea-archive.sh` | 校园 Gitea 归档与 checkpoint tag |
| `specs/020-assistant/` | 教学助手的 plan/spec/tasks/wireframes，追溯链补到 020 |
| `ci-grader` 覆盖 develop | 018 真实引擎不再只在 main/release 上验 |
| 石佰合四件材料 | TEST_REPORT / USER_GUIDE / 检查点 2026-11-23 / 设计报告 |

### 1.4 报告版式补齐（本轮实测）

五份 Word 报告的封面、Word 目录域、页脚 PAGE 域全部生成并逐份校验：

```
24201716_黄俊诚_设计报告.docx   封面=True 目录域=True 页脚页码=True
24201718_姜苏豪_设计报告.docx   封面=True 目录域=True 页脚页码=True
24201723_罗浩铭_设计报告.docx   封面=True 目录域=True 页脚页码=True
24201737_石佰合_设计报告.docx   封面=True 目录域=True 页脚页码=True
g24201710_小组大作业报告.docx   封面=True 目录域=True 页脚页码=True
```

预览包已生成并自检通过：`test-tmp/submission-preview-20261123/`
（`242017班_第10组_大作业报告.docx` + `242017班_第10组_成员名单.txt` + `核对清单.json`）。

### 1.5 全量后端测试

`PYTHONPATH= python -m unittest discover -s tests` → **Ran 560 tests，OK，1303 秒**。
两个坑写进第 4 节第 5 条：不带 `PYTHONPATH=` 会报 109 个 `tearDown` 假错（沙箱 shim 拦 `Path.unlink`）。

---

## 2 剩下的阻断项

### 2.1 Gitea 归档（只能在校内网做）

- 任务书硬性要求「项目须托管在 Gitea」「所有文档、代码、测试用例均须提交至 Gitea」。
- 现状：只有 GitHub；课堂服务器 `http://10.83.68.223:3000` 在当前网络下不可达（11-23 实测）。
- 步骤：建空仓库 → `GITEA_URL=... DOCS_REF=... bash scripts/gitea-archive.sh` →
  脚本为 `origin/develop` 建检查 2 tag 并逐 ref 核对 SHA；**不用 `--mirror`、不 force**。
- 提醒：仓库体积不小，**提前一天试推一次**，当天只补 tag。

### 2.2 超星上传（需要账号与校园网）

- 三件套已在本地生成，但**本地生成 ≠ 已提交**。
- 上传前必须人工做三件事：① Word 里全选按 F9 更新目录并逐页检查分页；
  ② 确认班级写法（现在按 `242017班` 生成，若教学班写法不同要加 `--class-name` 重跑）；
  ③ 截图脱敏检查（姓名/学号/Cookie/令牌）。
- 源码包：提交定稿、工作区干净后执行
  `python scripts/package_submission.py --class-name 242017 --group 10 --output <新目录> --include-source`，
  再 `python scripts/verify_submission.py <新目录> --require-source`。

### 2.3 C12C 矩阵仍有 50 条阻断（黄俊诚）

- `docs/checkpoints/HUANG_JUNCHENG_C12C.md`：131 行，81 通过 / 0 失败 / **50 阻断** / 0 待执行。
- 阻断分两类：42 条共通/环境类，8 条页面类。要按当前 head 重跑一遍，能关的关、关不掉的写清原因。

### 2.4 CP-4 双浏览器实测仍是「待执行」（罗浩铭）

- `docs/checkpoints/LUO_HAOMING_2026-11-05.md` 里 TV-01/TV-02 仍记「未执行」，缺执行日期、
  动作 JSON、逐步状态与复核人。
- 需要：教师单步 / 学生页跟随 / 刷新恢复 / 并发冲突各一张图，按 CP-4 表格填写。

---

## 3 扣分风险

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| 3.1 | 证据目录只有 8/24 个 SPEC | `docs/evidence/` 有 005/006/008/010b/011/012/013/020；缺 001/002/003/004/007/009/010/010a/010c/010d/014/015/016/017/018/019 | 检查「各模块设计与实现代码」时，缺证据的模块只能口头说明 |
| 3.2 | 014 真实批次聚类降级 | 课程 16 的 `analysis_run 548`、110 条、`sample_size=0`，因无到期实验版本 | 不是 bug，但被问「为什么没聚类」要能解释 |
| 3.3 | 018 真实引擎本地无 JAR | `ci-grader` 需要下载固定 SHA 的 Logisim 并跑 xvfb | 本地无法复现，只能引用 CI 记录 |
| 3.4 | 班级写法未最终确认 | 报告与预览包都按 `242017班` 生成 | 写错要返工重打包 |

---

## 4 代码层面的具体不足（不阻断演示，检查时可能被问）

1. **`frontend/js/main.js` 1690 行**：路由、状态、模板、事件都在一个文件里，改一处要全文搜。
2. **仍用 Werkzeug 开发服务器**：`app.run(..., threaded=True)`，不是 gunicorn/waitress。
3. **`access_log` 无保留策略、`session` 只在登出/重登时清理**：表会单调增长。
4. **SQLite 单写者**：11-12 已把三处「每请求写库」改掉，但新功能凡在请求主链路写库仍会排队。
5. **本地跑全量测试的两个坑**：① 不带 `PYTHONPATH=` 会报 109 个 `tearDown` 假错
   （WorkBuddy 的 `cli/vendor/shim/sitecustomize.py` 拦 `Path.unlink` 并起子进程做删除检查，
   与代码无关）；② 平均约 2.3 秒/用例，全套 22 分钟，早先记的「15 秒/用例」是误判。
6. **教学助手是规则分类**：完全没有词表线索的说法（如「给我整点有用的」）会走澄清。
   这是刻意选择（断网可跑、数字可复算），被问到时按 `DEMO_SCRIPT` 第 3 节话术回答。

---

## 5 进阶建议（按性价比，已完成的不再列）

### A. 演示加分（半天，最划算）

1. 助手加「把这次回答导出为 PNG」，现场交报告可直接贴图。
2. 演示脚本加一段**断网演示**：拔网线后提问仍能答——这是本方案最强的差异点。
3. 图表补 hover 数值（环形已有 `<title>`，横条/折线补齐）。

### B. 证据补齐（1 天，直接影响「各模块代码可核对」）

4. 给缺证据的 16 个 SPEC 各建 `docs/evidence/spec-XXX/`，至少 3 张截图 + 一次运行日志；
   优先补自己负责的 014/016，再补 001/002（考勤/权限，量最大）。
5. 建一个模板 `docs/evidence/_TEMPLATE.md`（场景、命令、预期、实际、截图名），避免每次现编。

### C. 技术债（有余力再做，别影响交付）

6. `main.js` 先抽三块：课程切换、轮询节拍、请求封装；风险最小、收益最大。
7. `access_log` 保留 30 天、`session` 清理过期行，挂在启动时或定时线程。
8. 助手 `facts` 加「怎么算的」一行（分母、时间窗、样本数），比只在 `caveats` 里说更硬。

### D. 不要再做

- 不要为「看起来像 AI」接大模型 API：破坏「可复算 + 断网可跑」，现场网络不可控。
- 不要用 `git checkout <分支>` 切分支（会重写工作区，打断就丢文件）；用 `git switch` 或 `git branch -f`。
- 不要在 CI 未绿时合并 PR，也不要用 `--no-verify` 跳过钩子。

---

## 6 排期（11-24 起）

| 日期 | 谁 | 做什么 |
|---|---|---|
| 11-24 | 黄俊诚 | C12C 50 条阻断按当前 head 重跑，能关的关、关不掉的写原因 |
| 11-24 | 罗浩铭 | CP-4 双浏览器实测 + `evidence/spec-004\|007\|017\|010c` |
| 11-25 | 姜苏豪 | 补 `evidence/spec-014\|016`；EVIDENCE 模板；确认班级写法 |
| 11-26 | 全组 | **校内网** Gitea 归档 + 两个 checkpoint tag，逐 ref 核对 SHA |
| 11-27 | 姜苏豪 | F9 更新目录、逐页检查 → `--include-source` 出正式包 → 超星上传并留存回执 |

---

## 附：本文事实的复核命令

```bash
# 文档 / lint / 前端
python scripts/check_docs.py                            # 期望 OK
.venv/Scripts/ruff.exe check backend tests scripts      # 期望 All checks passed
cd frontend && npm test                                 # 期望 294 项
# 全量后端（务必带 PYTHONPATH=，否则沙箱 shim 会报一批假 errors）
PYTHONPATH= .venv/Scripts/python.exe -m unittest discover -s tests   # 期望 Ran 560 tests, OK
# 换位过期回归
.venv/Scripts/python.exe -m unittest tests.test_seat_swap
# 交付物
python scripts/package_submission.py --class-name 242017 --group 10 --output <新目录> \
  --report-docx docs/reports/g24201710_小组大作业报告.docx
python scripts/verify_submission.py <新目录>
# 远端是否已合并
git rev-list --left-right --count origin/develop...develop   # 期望 0 0
```
