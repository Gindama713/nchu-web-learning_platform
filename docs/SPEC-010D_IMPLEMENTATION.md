# SPEC-010D 电路评测统计分析实施与验证

责任人：石佰合（24201737）。2026-10-18，Asia/Shanghai。
依据：[PRD §4.1 分工与样例](PRD.md#modules-acceptance)、[PRD §11 SPEC-010D 有效验收](PRD.md#accept-spec-010d)、[APIC §5/§5.1/§7](APIC.md)、[DBD §5](DBD.md)。

## 基线、边界与依赖

本轮从 `develop` 的 `15718fb`（SPEC-018 合入后的 merge 提交）新建 `feature/spec-010d-grading-analysis`。010D 的全部输入来自 018 已合入的事实表，因此必须在 018 合并后开发；本分支没有复制 018 分支代码，也未修改 018 的模型、引擎或端点。

本文只实现统计维度 `grading`，不接管 010A/010B/010C，不新增迁移，不修改 `analysis_run` 既有 SQL，不改 `submission`/`grading_run` 的写入路径。

| 依赖 | 当前接入 | 边界 |
|---|---|---|
| 001 会话、课程成员、`analysis_run`、公共 analytics 路由 | 真实实现；查询前同事务授权，保存前再鉴权 | 不新建快照表，不接管 010A |
| 009 实验版本与冻结时间窗 | 只读 `experiment_version.status='published'` 且 `submission_modes` 含 `circuit` | 不发布/修改实验 |
| 018 `submission`/`grading_run`/`test_suite` | 只读；教学成绩取 `effective_run`，可靠性另计全部 run | 不重评、不改分、不回收租约（回收逻辑仍属 018 引擎） |
| 018 前端工作台 | 不修改；010D 只在分析页增加只读维度 | 学生提交/报告入口仍归 018 |

## 实现与可复算口径

- [grading_analysis.py](../backend/models/grading_analysis.py)：同一 `BEGIN` 读快照内提取本课程全部已发布 circuit 版本、对应 `submission`（`created_at<=source_until`，个人范围在 SQL 内限定本人）及其全部 `grading_run`。缺表返回 503 `DEPENDENCY_UNAVAILABLE`。
- 教学分布单元为 `(student_id, experiment_version_id)`：按 `(created_at, id)` 倒序取首个具有有效 run 的 submission，再取该 submission 下 id 最大的有效 run。有效状态为 `accepted/wrong_answer/timeout/resource_limit/invalid_circuit`；`queued/running/system_error` 不覆盖既有有效成绩（对齐 APIC §7 末段与 R19）。
- `pass_rate = accepted_count / effective_count`；`student_count` 为有效成绩去重学生数；`sample_size = effective_count`。PRD §4.1 样例（5 名学生中 2 名 accepted → 40%）由 `test_teaching_distribution_matches_prd_sample_and_recomputes` 真实复算。
- 运行可靠性独立统计区间内**全部** run：`run_count`、`system_error_count`、`timeout_count`、`resource_limit_count`；平台故障不进教学分母、不覆盖学生既有有效分（R05）。
- 分数分箱固定 `[0,60)/[60,70)/[70,80)/[80,90)/[90,100]`，按未舍入原始分（0—100，`score_hundredths/100`）分箱；超时与限额按 018 引擎规则记 0 分并进入分母。
- `metrics.suites` 按 `suite_id` 分组，字段与总体同口径；只出现过 `system_error` 的测试集同样列出，避免可靠性数据被隐藏。`submission_count` 在 suite 层为“在该 suite 产生过 run 的 submission 数”。
- 时间窗按 `experiment_version.start_at` 左闭右开选任务（对齐 APIC §5.3 末段“成绩及完成率按发布任务 start_at”）；`series` 按上海周一 00:00 切分，首尾裁剪。空样本计数为 0、比率与均分为 `null`，仍保存合法快照。
- [grading_analytics.py](../backend/apis/grading_analytics.py)：只接受 `dimension/from/to/student_id`；空值、重复字段、不适用筛选与超范围 ID 返回 400。学生只读本人；教师选学生必须是本课当前有效学生，否则 404。计算在读事务提交后执行，短写事务复核会话/课程/目标学生后整体保存 `parameters_json`、`input_snapshot_json`、`result_json`；插入与补 ID 的 UPDATE 同事务，失败 503 且无可用 ID。
- [analytics.py](../backend/apis/analytics.py) 仅增加 `grading` 分派、快照读取白名单及导出分支；[statistics_csv.py](../backend/apis/statistics_csv.py) 增加 grading 的 `overall/series` 标量、分箱与 suites 段。CSV 只序列化已保存结果，不重读事实表，沿用 BOM、公式前缀转义与 no-store。

## 测试及有效编号登记

执行人：石佰合任务下的助手自动执行；2026-10-18 本机 Windows，临时独立 SQLite 与真实 Flask API。账号 bootstrap 后，学生注册、登录、课程/成员、实验配置、测试集验证发布、提交、worker 领取与结果提交、重评均经真实接口；worker 结果注入走 `backend.engines.grading` 的真实租约路径，不是 API mock。

[test_grading_analytics.py](../tests/test_grading_analytics.py) 复用 018 的 `GradingFixture`（本轮把该 fixture 从 `GradingTest` 拆出，测试方法仍全部留在 `GradingTest`，018 用例零改动）。

| 有效编号 | 入口与已覆盖输入/预期 | 仍需补证 |
|---|---|---|
| SPEC-010/AC-01（010D 继承） | `test_teaching_distribution_matches_prd_sample_and_recomputes`：5 名学生 2 名 accepted → 40%；保存输入复算 metrics/series 完全一致 | 真实课堂数据复算 |
| SPEC-010/AC-02（010D 继承） | `test_scope_permissions_and_invisible_objects`：班级/本人/指定学生；他人学生 403、非成员与他课教师 404、未登录 401；跨课导出 404 | 真实教师/学生账号联调 |
| SPEC-010/AC-03（010D 继承） | `test_empty_sample_keeps_null_metrics_and_saves_snapshot`：空样本与区间外均计数 0、比率/均分 null、快照可恢复 | 页面无数据展示（前端用例覆盖文案） |
| SPEC-010/AC-04（010D 继承） | `test_snapshot_and_csv_frozen_across_regrade`：重评后旧快照与旧 CSV 字节不变，新查询才反映；CSV 含 dimension/ID/suites/分箱 | 目标环境导出回归 |
| R05 | `test_timeout_and_resource_limit_zero_but_system_error_excluded`：超时/限额 0 分进分母；故障 run 不计分且不覆盖既有 accepted | TV-01 真实 JAR 的故障注入 |
| R16 | `test_member_exit_keeps_historical_denominator`：成员退出后历史分母与通过率不漂移；退出者查询 404 | 冻结名单发布/转入场景 |
| R19 | `test_queued_and_system_error_do_not_replace_effective_score`：排队不覆盖有效分，`latest_run` 待评且 `effective_run` 为 null，同 submission 仅一活动 run | 018 重试上限另由 T018 覆盖 |
| R29 | `test_expired_lease_worker_lost_leaves_teaching_denominator`：过期租约续租/提交失败，回收为 system_error，进入可靠性而非教学分母 | 全停机重启回收（018 worker 用例） |
| R30 | `test_statistics_project_real_facts_not_hardcoded`：直接改 `grading_run` 事实后新查询随之变化，证明不硬编码样例 | 真实三项电路成功/失败/异常由 TV-01 人工执行 |
| 参数与依赖 | `test_strict_filters_duplicates_and_missing_dependency`：空值/重复/未知/超范围 400，缺表 503，跨课快照 404 | — |

前端回归：`frontend/js/analytics-client.test.js`（grading 只带 dimension/from/to/student_id）与 `frontend/js/analytics-view.test.js`（通过率、suite 分组、可靠性列、空样本、学生无导出）。

## 未关闭项

- TV-01 真实 Logisim JAR 冒烟仍待固定 JAR 后执行（与 018 同一遗留），010D 的 R30 自动化只证明统计读取真实事实表。
- 目标环境（Linux 4 核 8GB、50 会话）性能、完整生产备份恢复、真实课堂数据复算与 Gitea 归档未执行。
- 010D 整体验收不以本文件自动化测试为通过结论，CP-3 需按 PRD §11.1 补 PR/Actions/merge SHA 与人工证据。
