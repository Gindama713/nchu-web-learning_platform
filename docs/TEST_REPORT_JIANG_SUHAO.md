# 姜苏豪负责模块测试与交接记录

原始执行日期：2026-10-19；证据核对日期：2026-10-22；负责人：24201718 姜苏豪。范围为 SPEC-001、002、010A、014、016 及 SPEC-019 的本轮改动。本地命令来自 `feature/jiang-completion-20261019`；最终 PR head、合并提交与 CI 另按实际记录，不把本机 Windows 测试当作目标环境或教师验收。

## 已执行检查

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_recognition tests.test_identity_attendance -q` | 12 项通过 | F01—F05 固定字节、门与标签坐标、OR/XOR、阈值、上传确认、成绩隔离、用户与考勤 HTTP |
| `npm test` | 135 项通过 | 前端现有模块单元和组件契约 |
| `npm run lint` 与 `npm run build` | 通过；Vite 7.3.7 构建 46 模块 | 前端静态规则和生产构建 |
| `python -m ruff check backend tests scripts` | 通过 | Python 代码静态规则 |
| `python scripts/check_docs.py` 与 `git diff --check` | 通过 | 六份主文档、老师目录与本地链接、补丁空白 |
| 后端 `unittest discover` 全量 | 本机 375 项通过，995.564 秒；命令启动于 OR/XOR 修复前 | 证明当时其余模块无回归；修复后定向 12 项已另测，最终 head 以 PR CI 全量为准 |

最终 head `faf17789bdd0f6bedf073fd1d4c6bd68994664dd` 的 [Actions run 39260824775](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/39260824775) 已复核：ci-policy、ci-lint、ci-build、ci-test、ci-required 为 success；ci-grader 按 develop 规则 skipped。ci-test 日志显示后端 **376 项通过（223.298 秒）**、前端 **135 项通过**。该 head 经 [PR #39](https://github.com/Gindama713/nchu-web-learning_platform/pull/39) 合入 develop，merge SHA `2973bef7bfadb429fe8b17cfadf2d3a2685c796a`。这是集成分支的 CI 证据；skipped 的真实评测不能写成通过，亦不构成 main 发布放行。

## 规格与测试映射

以下只定位实际存在的可复现测试，不能因为同一个测试包含多步断言，就推定 PRD 的全部 AC、共通 R 和非功能项都已关闭。规范性验收全集仍以 [PRD 第 11 节](PRD.md#accept-spec-001) 为准。

| 个人范围 | 实际测试入口与已证明行为 | 仍需另行验收 |
|---|---|---|
| 001/002 | `test_identity_attendance_and_frozen_participants`、`test_last_admin_cannot_be_deactivated`、`test_uc01_leave_rejection_resubmission_close_and_correction`：账号/课程授权、最后管理员保护、冻结名单、签到及请假闭环 | 真实账号与扫码、跨进程并发和目标环境；R47 非作者复核 |
| 010A | `test_c01_perfect_correlation` 至 `test_c04_missing_performance`、`test_personal_scope_has_no_class_metrics`、`test_analytics_export_keeps_original_snapshot_after_correction`：固定算例、个人隔离、旧快照 CSV | 真实非空班级数据、教师人工复算和完整跨模块事实链 |
| 014 | `test_rules_work_without_cluster_or_attendance_denominator`、`test_all_good_students_do_not_force_warning`、`test_cluster_is_deterministic_with_real_weak_group`、`test_real_fact_joins_and_required_modes`、`test_warning_run_is_atomic_idempotent_and_teacher_only`：规则/聚类降级、真实表输入、事务与权限 | 真实教学数据、完整实验依赖、教师处理有效性与课堂判定 |
| 016 | `test_fixed_v2_png_inputs_and_hashes`、`test_threshold_boundaries`、`test_or_and_xor_contours_are_joined_before_matching`、`test_fixed_recognition_pngs_through_authenticated_http`、`test_recognition_confirmation_cannot_change_grades`：固定图、阈值、上传确认和成绩隔离 | 一般照片/旋转/手绘泛化、另一设备运行、完整越权与非法框逐项登记 |
| 019 | 本 PR 的五个成功 job 与 develop 合并、分支 `protected` 只读状态 | main/release 真实失败阻断、直推拒绝、Gitea 同 SHA、回灌及部署恢复演练 |

本机浏览器以临时 SQLite 合成教师和两个课程执行登录、查看教师课程成员、生成空样本 010A 快照及切换课程。空样本返回 null 指标和 `insufficient_pairs`，页面显示周趋势；切课后原快照和筛选被清除。此项只证明本地 UI 冒烟，未使用真实教学账号或非空班级成绩。临时数据库和会话密码未进入 Git。

## 失败、修复与复测

本轮检查发现原识别实现将标准 OR/XOR 的分离弧线切成两个外轮廓，导致两类正向标准图都返回空结果。将门符号定位的固定闭运算核从 3×5 调整到 3×15，按新配置更新模板 SHA，并新增 OR/XOR 双门回归。F01—F05 与全部 12 项定向测试复测通过。本机 375 项全量命令在修复前启动，因此不能把该运行冒称修复后全量；最终完整验证依赖本 PR 对应 head 的 CI。原计划 v1 图片没有文件，不能把未执行的 SHA 写成通过；本轮以仓库内 v2 PNG 和 SHA 承担固定输入验收。

## 未关闭的验收

SPEC-001/002 的真实课堂账号、签到二维码实际扫码和并发压力，010A 的真实非空班级卷与考勤配对，014 的真实全依赖数据课堂演示，016 的非固定照片泛化效果及另一目标设备验证仍需证据。SPEC-019 的 main/release 拒绝演练、固定 Logisim JAR 的真实评测与目标环境、备份恢复、50 会话、Gitea 同 SHA 归档尚未完成。此报告不将这些项记为通过，也不授权 main 发布。

复现入口和完整设计见 [个人实施记录](JIANG_SUHAO_IMPLEMENTATION.md)、[PRD](PRD.md)、[APIC](APIC.md) 与 [变更回滚手册](CHG-RB.md)。测试输出和最终 head 对应的 CI 在 PR 留证；恢复/回退时保留数据库与上传文件一致副本及所有历史分析快照。

## 2026-11-20 回归补记（教学助手上线后）

历史数字（135 项前端、376 项后端）保留在原表，不覆盖；以下是当前仓库的实测结果。

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_assistant tests.test_assistant_phrasings` | 18 项通过 | 教学助手接口、权限、空数据降级、约 130 条问法分类 |
| `python -m unittest tests.test_identity_attendance` | 10 项通过（新增 1 项） | 新增 AC-05：跨课选卷 404、同课同卷 200 |
| 前端 `npm test` | 281 项通过（新增 17 项） | 新增 `warning-client` 5 项、`warning-view` 4 项、`recognition-client` 4 项、`recognition-view` 4 项，补齐 014/016 页面此前零测试的缺口 |
| 前端 `npm run lint` / `npm run build` | 通过 | 静态规则与生产构建 |
| `ruff check`（助手与新增测试） | 通过 | Python 静态规则 |

真实数据证据（wt-demo 课程 16，160 名在课学生，2026-11-20）：

- 014 首次在真实课堂数据上生成批次：`analysis_run_id=548`，`warning_count=110`，`model_status=insufficient_data`、`sample_size=0`。原因不是算法出错，而是该课程没有到期的实验版本，实验完成率分母为 0，按规格「不填造分母」降级为规则提示；110 条均为 `RECENT_ATTENDANCE`（最近两次考勤异常），与 11-13 现场签到结果一致。
- 016 固定 F01—F05 与上传/确认仍由 `tests.test_recognition` 覆盖；前端新增的 4 项补的是页面层：上传后显示识别项与低置信度、未识别提示、标签未补齐时拒绝确认。

### 2026-11-20 教学助手出图（SPEC-020/AC-09）

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_assistant` | **16 项通过**（13 → 16） | 新增：环形圆心等于「应到人次」、无可画数据时 `charts=[]`、两周才有折线（1.0 / 0.5） |
| `node --test js/charts.test.js` | 6 项通过 | 横条按 max 归一、null/NaN 不画、0 值留 1px、环形 total 只累加正值、折线 <2 点空态、未知 colorKey 回退 |
| `node --test js/assistant-view.test.js` | 11 项通过（8 → 11） | 环形/条形渲染、无 `charts` 不画空占位、未知图表类型忽略 |
| `npm test`（全量） | **294 项通过** | 含统计页改用共享 `chartNode` 后无回归 |
| 无头 Edge（wt-demo 课程 16） | 教师 9/9、学生 9/9 | 图元计数与后端数值逐个对应；截图 `chart-teacher-donut.png`、`chart-teacher-bar.png`、`chart-student-two.png`（不入库） |

仍不能由本材料证明：真实班级非空成绩配对（课程 16 三份卷无人提交）、一般照片/旋转/手绘的识别泛化、目标 Linux 与 50 会话性能、Gitea 同 SHA 归档、非作者评审。
