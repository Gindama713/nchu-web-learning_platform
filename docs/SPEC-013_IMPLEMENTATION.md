# SPEC-013 智能组卷实施记录

负责人：黄俊诚（24201716）。本轮执行 C08，API、草稿 paper/item 同事务保存、replay_of 权限和教师页面留在 C09；不自动发布。

## C08a 候选与历史输入

从核验的 origin/develop `253a736a79a6b6778e8bde0e58673d1f4c7641d7` 创建 `feature/spec-013-paper-generation`。2026-10-14 fetch 与 GitHub 元数据核验：008 [PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9) open、非 draft、未合入，head `fafc69aecf723d06181e807bc1124aed2bd915de`；010B [PR #10](https://github.com/Gindama713/nchu-web-learning_platform/pull/10) open/draft、未合入，head `a750f8024f2f58fa72097bff521bdf1a75fe75d7`。保留 008→010B 专用联测阻塞，未复制两个 feature。

`backend/models/generation_input.py` 在独立 SQLite 读事务内冻结本课未归档 question 最新 version、标签、全部候选、参数、截止及 seed，读取完释放事务。候选身份先按 version_id 升序分配 NumPy PCG64 原始随机键，再按实际正确率（整数比值精确比较）、无样本排后、已保存键、version_id 排序。负 seed 映射为无符号 64 位，仅用于首次生成键；原 signed 64 位 seed 保存。键保存为 16 位十六进制字符串，避免 JSON/浏览器整数精度损失。重放加载保存键，不运行 RNG；算法版本 `paper-backtrack-v1`。

历史按固定 question_version 统计本课真实 paper answer 与 practice_attempt；只计截止前 answered=1 的已评分客观事实，partial 答卷中的已评分客观题有效，漏答/简答排除。正确为原配分满分或 practice.correct=1，样本为事实数量；无样本 rate=null，简答 n=0/rate=null。不把旧版本历史迁到新版本，不读取 wrong_question 投影作为事实。history_until 不晚于 source_until。

保密冻结排除 ever_public=1、任一版本 practice_available=1 或 published paper 已到 start_at 的全部题目身份；新私有版本不能恢复资格。发布时的当前占用/公开资格复核仍沿用 006，并由 C09 接入，候选快照不能替代发布检查。

C08a 本地验证：`.venv/Scripts/python.exe -m unittest tests.test_generation_input -v`，5 项通过（16.210 秒）；受影响 ruff 与 git diff --check 通过。使用真实 001/005/006 HTTP 创建题目、知识、发布及作答；归档状态和 501 候选属于明确 SQL 边界夹具，不能冒充教师 HTTP 归档验收。测试初轮遗漏真实幂等键、误用不存在的归档接口，已改为带 UUID 的真实作答与明确归档夹具并重跑通过。

## C08b 求解、整数配分与持久快照

求解使用冻结顺序、先选后跳过的确定性回溯；按question身份去重，按剩余难度配额的独立身份数量及剩余可选知识覆盖剪枝。每节点进入时计数，包含根、剪枝及终点，最多100000次；穷尽树返回422 INFEASIBLE_CONSTRAINTS，还需要第100001次访问返回503 SEARCH_LIMIT。不使用运行耗时作预算，不返回partial选题。求解在数据库写事务外执行。

总分先严格换算整数百分之一分，按选中顺序divmod均分，余数给前若干题；每题至少1，总和与输入精确一致。生成的Solution含有序版本、整数配分、覆盖及实际节点数。保存前再次检查数量/独立question/配额/覆盖/顺序/配分，不能保存部分或不合规结果。

`013_generation_snapshot.sql`由原公共runner接入：不可变表存全候选、历史、参数、seed、算法版本、source_until、SHA-256与selected_ids；同课程版本及选中候选插入触发器防错误引用。旧SQL不变，引用版本沿用006全局保留。内部save要求调用方已有事务，不自行commit；load校验输入哈希与并行历史，replay仅从保存输入复算，并对照原selected_ids。paper新列/外键、API权限与draft事务由C09追加，C08不会建草稿或发布。

C08b专题验证：`python -m unittest tests.test_generation_solver tests.test_generation_snapshot -v`，13项通过（6.548秒）；全仓ruff通过。包含200组独立穷举对照、实际100000节点、500候选/100选题、同题两版、无样本排序、精确余数、WAL真实第二请求在读取期间新增版本/作答、存储回滚/不可变/版本同课程触发器、带数据备份副本完整性/外键与原快照复算。预算用例初轮22候选在88639节点已证明无解（422正确）；改为33候选后确实耗尽100000节点并验证503，未放宽算法或改写断言掩盖结果。

## 验收证据与未完成项

| 编号 | C08证据与结果 | 剩余范围 |
|---|---|---|
| AC-01 | solver正常约束/多标签/配额/精确总分，通过 | C09真实教师操作与draft/item |
| AC-02 | 同question两版不重复；freeze最新版本，通过 | C09生成卷固定版本外键 |
| AC-03 | 配额/覆盖/题量不可行422，预算503区分，通过 | HTTP错误状态/教师失败页 |
| AC-04 | 保存输入/排序键/seed复算，RNG被禁仍一致，通过 | replay_of HTTP权限与持久卷 |
| AC-05 / R14 | 新题/版本/真实作答后保存快照及备份副本选题配分一致，200组穷举/实际预算，通过 | 教师新增题后端到端replay_of |
| R25 | 公开身份所有版本排除候选，通过 | C09当前资格复核与006/008发布联合 |
| R22/R45/R46/R47 | 版本保留、存储回滚/备份组件证据，通过；完整共通验收待执行 | 完整权限/生产恢复/性能/真实评审与课堂证据 |

用例由AI于2026-10-14—15在本地受控数据库执行，预期与实际断言一致；所有用户/数据为合成，无真实学生资料。算法夹具不能冒充HTTP、目标Linux4核8GB/50会话、worker、课堂或非作者评审。前端未改，本轮不要求C08浏览器截图。正式运行/用户说明见README§8.6；生产迁移未执行。

2026-10-15全量回归：`.venv/Scripts/python.exe -m unittest discover -s tests -v`，后端125项通过（190.409秒，C08新增18）；`npm test`前端46项通过，`npm run lint`/`npm run build`通过；全仓`ruff check backend tests`、六文档链接和`git diff --check`通过。序列化重算补强禁用secrets seed RNG后单项另通过（0.008秒）。本013分支来自develop，未包含010B/008 feature，故125/46不能与010B分支131/54当作同一套代码的数量比较。

回退：先保存题目版本、作答、审计与全部generation_snapshot的一致性备份/增量，恢复配套代码和数据库恢复点；不DROP快照/历史表，不修改已应用迁移。旧代码不认识新快照时明确不可用，不重算冒充原结果。

## 当前交接与下一恢复

C08a提交`16c1928`已推送本feature；C08b算法/持久快照已实施，全量回归通过，正在PR收口，最终SHA/CI见本节后续更新。SPEC-013完整验收未关闭，无generated-papers API、教师页面或C09真实HTTP重放链。恢复先fetch核验develop/#9/#10；008合入时优先在010B原分支merge develop补专用联测。008仍未合入则C09继续本013分支，先对齐新增013快照迁移，再追加paper.seed/algorithm_version/generation_snapshot_id FK及发布冻结治理；API首次/replay_of二选一，冻结→无写锁求解→重新授权/资格核验→短事务保存snapshot+draft paper/item+审计。重放只接新title，读取旧快照，不读新题库；发布仍用006/008现行保护，不自动发布，不接管队友模块。
