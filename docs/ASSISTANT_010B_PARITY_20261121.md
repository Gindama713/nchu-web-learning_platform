# 教学助手与 010B 统计对照样例（2026-11-21）

用途：给姜苏豪核对助手时间范围、查询对象和统计口径。**同一学生、同一课程、同一窗口、同一截止时刻**下，助手必须复用 010B/010A/011/014 的结果，不能另建算法或统计表。本文数值均由 `tests/test_assistant.py` 的固定夹具产生，不含演示库数据。

## 1 固定条件

- 课程：`CPU`（测试课程），学生：`STUDENT01`。
- 窗口：`2026-10-23T08:00:00.000Z` 至 `2026-11-20T08:00:00.000Z`（半开区间，28 天）。
- 事实截止：`2026-11-20T08:00:00.000Z`；页面/助手都应使用同一个 `source_until`。
- 题目与试卷：一张 `exam` 试卷，两个题位：客观判断题 100 分、简答题 50 分；学生已交卷，客观题 100 分，简答已作答但**未批**（`attempt.status=partial`，简答 `score_hundredths=NULL`）。

## 2 客观题掌握度：助手与 010B 必须一致

`knowledge_analysis.metrics()` 的结果：

| 字段 | 值 | 分母/说明 |
|---|---:|---|
| `answered_count` | 1 | 只算已作答的客观题样本；简答待批不进分母 |
| `correct_count` | 1 | 客观题正确数 |
| `mastery` | 1.0 | 1 / 1；助手显示 100.0% |
| 简答待批 | 不计入 wrong_count，也不计 0 分 | 不是错题，不是未答 |

助手问“我做了多少题？”的固定结果：

- `做题总数 = 1`（不是 2）；
- `正确 / 错误 = 1/0`；
- `正确率 = 100.0%`；
- 简答待批不出现在对错环形或错题知识点中。

对应回归：`tests/test_assistant.py::AssistantTest::test_my_attempts_matches_010b_and_excludes_pending_short`。该用例直接调用 `knowledge_analysis.metrics()`，断言助手的事实数字与 010B 相同。

## 3 成绩：已批、待批、缺交、漏答

同一试卷时 `score_analysis.metrics()` 的字段定义：

| 字段 | 本次值 | 说明 |
|---|---:|---|
| `expected_count` | 1 | 冻结名单中的应受人卷次 |
| `submitted_count` | 1 | 已交卷份数 |
| `missing_count` | 0 | 应交未交，**不是 0 分** |
| `graded_count` | 0 | 只算整卷已定分的 attempt |
| `partial_count` | 1 | 有简答待批，整卷未定分 |
| `mean_score` | `null` | 没有已批整卷时不算 0 |
| `mean_percentage` | `null` | 同上 |

助手问“我成绩怎么样？”的固定结果：

- 只有“待批 1 份”，没有已评分成绩；
- 不输出 `null%`，不说“0 分”；
- 已批 0 分才是真实的 0；缺交、待批、漏答都不能混成 0。

页面 CSV 使用同一个 `analysis_run` 快照，因此 `graded_count`、`partial_count`、`missing_count` 与页面数字一致，不重新按另一套 SQL 计算。

## 4 考勤：冻结分母与真实 0

固定夹具：关闭的任务有 2 名冻结参与人，`STUDENT01` 出勤、`STUDENT02` 缺勤。

| 查询 | `expected_count` | 到勤率 | 说明 |
|---|---:|---:|---|
| 教师班级 | 2 人次 | 50.0% | `(present+late)/冻结参与人`，缺勤是真实 0 |
| 学生本人 | 1 人次 | 100.0% | 只取本人参与行 |

没有考勤任务时 `expected_count=0`、到勤率 `null`；这与“0 人到勤”不同。助手和 010A 页面都使用 `analytics.facts()` + `interval_metrics()`，不按 `attendance_task` 当前名单重算。

## 5 完成率、掌握度、正确率各自的分母

| 指标 | 分子 | 分母 | 时间筛选 |
|---|---|---|---|
| 完成率/进度 | 当前已发布知识点中本人 `completed=1` 数 | 当前已发布知识点数 | 日期**不**筛选进度；只筛选作答 |
| 知识点掌握度 | 正确客观题样本数 | 已作答客观题样本数 | 窗口内作答事件 |
| 做题正确率 | 正确客观题样本数 | 已作答客观题样本数 | 窗口内作答事件 |
| 班级到勤率 | present + late 人次 | 冻结参与人任务人次 | 窗口内已关闭任务 |
| 班级平均百分比 | 已批 attempt 的百分比之和 | 已批整卷数 | 按 paper.start_at 窗口 |
| 随堂测逐题正确率 | `correct_count` | `submitted_count` | 冻结答卷；漏答算错 |

## 6 助手必须复用的现有服务

- 考勤：`backend/apis/analytics.py::facts/interval_metrics`
- 成绩：`backend/models/score_analysis.py::extract/metrics`
- 客观题与进度：`backend/models/knowledge_analysis.py::extract/metrics`
- 知识问答：`backend/models/qa.py`（011）
- 预警：`backend/apis/warnings.py`

助手本身只读，不写 `analysis_run`，不另建统计表。`student_attempts` 已在 2026-11-21 改为从 `knowledge_analysis.extract()` 的样本生成，简答待批不会再被当成错误。

## 7 复核命令

```powershell
# 助手固定对照（含简答待批排除）
.\.venv\Scripts\python.exe -m unittest tests.test_assistant.AssistantTest.test_my_attempts_matches_010b_and_excludes_pending_short -v

# 010B 页面/CSV 同快照与边界
.\.venv\Scripts\python.exe -m unittest tests.test_score_analytics tests.test_knowledge_analytics tests.test_quiz_analytics_integration -v

# 助手全部意图
.\.venv\Scripts\python.exe -m unittest tests.test_assistant tests.test_assistant_phrasings -v
```
