# SPEC-013 智能组卷实施记录

负责人：黄俊诚（24201716）。本轮执行 C08，API、草稿 paper/item 同事务保存、replay_of 权限和教师页面留在 C09；不自动发布。

## C08a 候选与历史输入

从核验的 origin/develop `253a736a79a6b6778e8bde0e58673d1f4c7641d7` 创建 `feature/spec-013-paper-generation`。2026-10-14 fetch 与 GitHub 元数据核验：008 [PR #9](https://github.com/Gindama713/nchu-web-learning_platform/pull/9) open、非 draft、未合入，head `fafc69aecf723d06181e807bc1124aed2bd915de`；010B [PR #10](https://github.com/Gindama713/nchu-web-learning_platform/pull/10) open/draft、未合入，head `a750f8024f2f58fa72097bff521bdf1a75fe75d7`。保留 008→010B 专用联测阻塞，未复制两个 feature。

`backend/models/generation_input.py` 在独立 SQLite 读事务内冻结本课未归档 question 最新 version、标签、全部候选、参数、截止及 seed，读取完释放事务。候选身份先按 version_id 升序分配 NumPy PCG64 原始随机键，再按实际正确率（整数比值精确比较）、无样本排后、已保存键、version_id 排序。负 seed 映射为无符号 64 位，仅用于首次生成键；原 signed 64 位 seed 保存。键保存为 16 位十六进制字符串，避免 JSON/浏览器整数精度损失。重放加载保存键，不运行 RNG；算法版本 `paper-backtrack-v1`。

历史按固定 question_version 统计本课真实 paper answer 与 practice_attempt；只计截止前 answered=1 的已评分客观事实，partial 答卷中的已评分客观题有效，漏答/简答排除。正确为原配分满分或 practice.correct=1，样本为事实数量；无样本 rate=null，简答 n=0/rate=null。不把旧版本历史迁到新版本，不读取 wrong_question 投影作为事实。history_until 不晚于 source_until。

保密冻结排除 ever_public=1、任一版本 practice_available=1 或 published paper 已到 start_at 的全部题目身份；新私有版本不能恢复资格。发布时的当前占用/公开资格复核仍沿用 006，并由 C09 接入，候选快照不能替代发布检查。

C08a 本地验证：`.venv/Scripts/python.exe -m unittest tests.test_generation_input -v`，5 项通过（16.210 秒）；受影响 ruff 与 git diff --check 通过。使用真实 001/005/006 HTTP 创建题目、知识、发布及作答；归档状态和 501 候选属于明确 SQL 边界夹具，不能冒充教师 HTTP 归档验收。测试初轮遗漏真实幂等键、误用不存在的归档接口，已改为带 UUID 的真实作答与明确归档夹具并重跑通过。

## 当前交接与下一恢复

C08a 候选、历史、排序、不可变序列化及输入 SHA-256 已实施；C08b 回溯、预算、精确配分和持久快照正在本轮继续。SPEC-013 完整验收未关闭，尚无 generated-papers API、教师页面或真实 C09 重放链。每次恢复先 fetch 核验 develop/#9/#10；008 合入时优先按 010B 正式交接补专用联测，不带入其他 feature。
