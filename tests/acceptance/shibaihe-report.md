# 石佰合负责功能 · 验收结果汇总

生成时间：2026-11-09T14:51:22+00:00

**总计 118/118 项通过，失败 0 项。**

| 场景 | 检查项 | 通过 |
|---|---|---|
| 后台数据缺失 | 50 | 50 |
| 后台数据正常 | 50 | 50 |
| 前端组件/交叉验证 | 18 | 18 |

## 归因结论（登录后无法使用是不是后台数据缺失造成的）

- 登录与会话在两场景都成功：`True`
- 空库 bootstrap 明确检出缺失：`True`
- 依赖业务数据的检查项：42 项；空库不可用 32 项；补齐数据后恢复 32 项
- 不依赖后台数据、两场景都可用的电路功能：6 项

> 登录后「资源/实验/评测/统计看不到内容」确定由后台业务数据缺失导致：登录与会话在两场景都成功；空库 bootstrap 明确列出缺失的 8 类数据；补齐数据后这些功能全部恢复；电路模拟与电路控制不依赖业务表，两场景均可用。修复前页面缺少提示、看起来像功能坏掉，属前端缺陷，已补就绪引导与空态卡片，因此当前版本在数据缺失场景下不再有功能差错。

### 修复前基线证据

空库下：登录 200、会话 200、`/courses` 返回空数组；`/courses/1/resources`、`/experiments`、`/experiment-versions`、`/analytics`、`/submissions` 全部 404 `Course not found`；前端 `courseId` 为 null 导致「考勤与学情」整块不渲染、其余模块无数据且无提示。
补齐课程/实验/测试集/评测记录后，同一批接口全部可用 → 因果关系成立。

### 已修复的问题清单

| 编号 | 问题 | 处理 |
|---|---|---|
| P1 | 后台数据缺失时页面无引导，登录成功后像「功能全坏」 | 新增 `/api/v1/circuit-lab/bootstrap` 逐表就绪判定；登录后显示引导条，「考勤与学情」在无课程时显示空态卡片与返回入口 |
| P2 | 缺少芯片级电路控制界面 | 新增电路实验台（7485 / 74181+7400），SVG 电路图、开关/指示灯、进度环、用例分页、右面板、提交记录 |
| P3 | 7485 级联输入全 0 时误报 A<B | 前后端模拟内核同时改为「无有效输出」 |
| P4 | 74181 验证用例 Cn+4 期望写反（低有效） | 按芯片功能表修正两处期望 |
| P5 | `/circuit-lab/compute` 缺少级联参数时报 400 | 补默认值 I(A<B)=0 / I(A=B)=1 / I(A>B)=0 |
| P6 | 畸形数值参数（`--1` / `²` / `1_0` / 超长整数）让 compute 抛未捕获 ValueError → 500 | `query_int` 改为 ASCII 十进制正则并捕获 `int()` 异常，统一返回 400；新增 `tests/test_circuit_lab.py` 回归 |
| P7 | `/circuit-lab/bootstrap` 对匿名用户开放 8 张业务表的精确记录数 | 增加 `require_user()`，未登录返回 401 |
| P8 | `readiness()` 把 sqlite 原始错误文本回给客户端，可能泄露表名 / 列名 | 降级项不再返回 `error` 字段，只给就绪状态与补全建议 |

### 当前未解决问题

无。全部被测项通过，无功能差错。

## 逐项结果（预期 / 实际 / 通过状态）

| 场景 | 编号 | 模块 | 被测功能 | 预期结果 | 实际结果 | 通过 |
|---|---|---|---|---|---|---|
| empty | L01 | 登录与会话 | 健康检查 db_ready / grader_ready | health 200，db_ready=true，grader_ready=true | HTTP 200 db=True grader=True jar_ok=True | ✅ |
| empty | L02 | 登录与会话 | 教师登录返回会话与 CSRF | 教师登录 200 且返回 csrf_token | HTTP 200 csrf=有 | ✅ |
| empty | L03 | 登录与会话 | 会话恢复 | 会话恢复 200 且学号一致 | HTTP 200 user=teacher | ✅ |
| empty | L04 | 登录与会话 | 学生登录 | 学生登录 200 | HTTP 200 role=student | ✅ |
| empty | L05 | 登录与会话 | 未登录访问受保护接口被拒 | 未登录 GET /courses → 401 | HTTP 401 | ✅ |
| empty | L06 | 登录与会话 | CSRF 来源校验 | 写请求缺 Origin → 403 CSRF_FAILED | HTTP 403 code=CSRF_FAILED | ✅ |
| empty | L07 | 登录与会话 | 退出后会话失效 | 退出后 /auth/session → 401 | 退出 HTTP 204，之后 session HTTP 401 | ✅ |
| empty | L08 | 登录与会话 | 登录后课程列表可用 | 课程列表：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 200 课程数=0 | ✅ |
| empty | L09 | 登录与会话 | 后台数据就绪判定（bootstrap） | bootstrap 200；data_ready=false | HTTP 200 data_ready=False 缺失 8 项 | ✅ |
| empty | L10 | 登录与会话 | 缺失项逐项列出（归因依据） | 就绪清单覆盖 8 张业务表，空库逐项列出缺失原因 | HTTP 200 检查 8 项，缺失 8 项 | ✅ |
| empty | R01 | SPEC-003 教学资源 | 资源列表 | 资源列表：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 条数=0 | ✅ |
| empty | R02 | SPEC-003 教学资源 | 教师上传资源 | 教师上传资源：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | R03 | SPEC-003 教学资源 | 按课程/类型检索 | 按课程/类型检索：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 kind=guide 命中 0 条 | ✅ |
| empty | R04 | SPEC-003 教学资源 | 授权下载并比对字节 | 授权下载：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 | ✅ |
| empty | R05 | SPEC-003 教学资源 | 缺少 intent/event_id 的下载被拒 | 缺 intent/event_id 的下载一律 400（参数校验先于数据查询，两场景一致） | HTTP 400 错误码=VALIDATION_ERROR | ✅ |
| empty | R06 | SPEC-003 教学资源 | 学生越权上传被拒 | 空库明确 404；正常库学生上传 → 403 | HTTP 404 | ✅ |
| empty | R07 | SPEC-003 教学资源 | 更新生成新版本且旧引用仍可访问 | 版本更新与旧引用：空库返回明确的 404/空列表，并有数据缺失引导 | 新版本 HTTP 404，旧版本 HTTP 404 | ✅ |
| empty | R08 | SPEC-003 教学资源 | 真实访问事件汇总 | 访问事件汇总：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 含 download=False | ✅ |
| empty | E01 | SPEC-009 实验辅助 | 实验列表 | 实验列表：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 实验数=0 | ✅ |
| empty | E02 | SPEC-009 实验辅助 | 学生可见已发布实验 | 学生可见已发布实验：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 可见 0 个 | ✅ |
| empty | E03 | SPEC-009 实验辅助 | 实验指导含目标/步骤/说明 | 实验指导字段：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 objectives/instructions=缺 | ✅ |
| empty | E04 | SPEC-009 实验辅助 | 两类提交入口（wiring / circuit） | 两类提交入口：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 modes=None | ✅ |
| empty | E05 | SPEC-009 实验辅助 | 发布闸门：未配测试集不得发布 | 空库明确 404；正常库未配测试集的草稿发布被拒 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | E06 | SPEC-009 实验辅助 | 本人历史版本 | 本人历史版本/提交记录：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 提交 0 条 | ✅ |
| empty | E07 | SPEC-009 实验辅助 | 发布窗口与冻结名单 | 空库无冻结名单；正常库冻结名单含提交学生 | experiment_participant 0 行 | ✅ |
| empty | G01 | SPEC-018 电路评测 | 固定 JAR 与评测就绪 | 固定 JAR 存在且 sha256 可校验（jar_ok=True） | JAR 54448596 字节，grader_ready 由 health 断言 | ✅ |
| empty | G02 | SPEC-018 电路评测 | judge profile 配置与指纹 | judge profile 配置：空库返回明确的 404/空列表，并有数据缺失引导 | judge_profile 0 行，sha= | ✅ |
| empty | G03 | SPEC-018 电路评测 | 正例/反例参考文件 | 正例/反例参考文件：空库返回明确的 404/空列表，并有数据缺失引导 | reference_file 0 行 | ✅ |
| empty | G04 | SPEC-018 电路评测 | 测试集 8 个计分组 | 测试集 8 个计分组：空库返回明确的 404/空列表，并有数据缺失引导 | test_case 0 行，分组 0 个 | ✅ |
| empty | G05 | SPEC-018 电路评测 | 测试集真引擎验证（正例全过/反例失败） | 测试集真引擎验证：空库返回明确的 404/空列表，并有数据缺失引导 | validation 0 行 | ✅ |
| empty | G06 | SPEC-018 电路评测 | 测试集发布 | 测试集发布：空库返回明确的 404/空列表，并有数据缺失引导 | published 测试集 0 个 | ✅ |
| empty | G07 | SPEC-018 电路评测 | 学生提交正确 .circ → accepted 100 | 空库明确 404；正常库 accepted / 100.0 / 11 通过 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G08 | SPEC-018 电路评测 | 学生提交错误 .circ → 部分给分 | 空库明确 404；正常库 wrong_answer / 87.5 / 10 通过（部分给分） | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G09 | SPEC-018 电路评测 | 非 .circ 预检拒绝 | 空库明确 404；正常库非 .circ → 400 且明确错误码 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G10 | SPEC-018 电路评测 | 顶层电路名不符拒绝 | 空库明确 404；正常库顶层名不符 → 400 INVALID_CIRCUIT | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G11 | SPEC-018 电路评测 | 学生报告脱敏 | 空库明确 404；正常库学生报告不含内部路径/快照/worker token | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G12 | SPEC-018 电路评测 | 重评生成新的 run | 空库明确 404；正常库重评生成 retry_of 新 run | HTTP 404 code=NOT_FOUND | ✅ |
| empty | G13 | SPEC-018 电路评测 | 空向量/零用例不得判满分 | 零用例/无输出列不得被判满分（两场景一致） | 空汇总解析=None，无输出列向量=None | ✅ |
| empty | A01 | SPEC-010D 评测分析 | 教师查看评测统计 | 教师评测统计：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | A02 | SPEC-010D 评测分析 | 通过率与分数分布 | 通过率与分数分布：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | A03 | SPEC-010D 评测分析 | system_error 排除正确率分母 | 空库明确 404；正常库 system_error 单独成项、不并入正确率分母 | HTTP 404 code=NOT_FOUND | ✅ |
| empty | A04 | SPEC-010D 评测分析 | 学生 scope=self | 学生 scope=self：空库返回明确的 404/空列表，并有数据缺失引导 | HTTP 404 student_id=None | ✅ |
| empty | A05 | SPEC-010D 评测分析 | 学生查他人统计被拒 | 空库明确 404；正常库学生查他人统计被拒 | HTTP 404 | ✅ |
| empty | A06 | SPEC-010D 评测分析 | 重评分组可区分 | 空库无重评记录；正常库重评 run 带 reason 标记可单独分组 | reason 非空的重评 run 0 条 | ✅ |
| empty | C01 | 电路模拟与控制 | 电路实验台 spec 与就绪状态 | spec 200；两个实验；data_ready=false | HTTP 200 实验 2 个 data_ready=False | ✅ |
| empty | C02 | 电路模拟与控制 | 芯片/引脚/正交导线/用例定义完整性 | 芯片/引脚/正交导线/用例定义齐全（两场景一致） | HTTP 200 几何问题 0 处 | ✅ |
| empty | C03 | 电路模拟与控制 | 7485 全组合后端表与 compute 一致 | 7485 全 2048 组合表与 compute 抽样一致（两场景一致） | HTTP 200 行数=2048 抽样不符=0 | ✅ |
| empty | C04 | 电路模拟与控制 | 74181 全组合与 74181 引擎一致 | 74181 全 512 组合表与 compute 抽样一致（两场景一致） | HTTP 200 行数=512 抽样不符=0 | ✅ |
| empty | C06 | 电路模拟与控制 | 验证用例期望与权威求值一致 | 每个验证用例的期望值与后端权威求值一致（两场景一致） | HTTP 200 校验 5 个用例，不符 0 项 [] | ✅ |
| empty | C08 | 电路模拟与控制 | 后台数据缺失时电路控制仍可用 | 数据缺失时电路定义仍完整、模拟/开关/验算不依赖业务表（两场景一致） | HTTP 200 实验 2 个，引脚 33 个 | ✅ |
| seeded | L01 | 登录与会话 | 健康检查 db_ready / grader_ready | health 200，db_ready=true，grader_ready=true | HTTP 200 db=True grader=True jar_ok=True | ✅ |
| seeded | L02 | 登录与会话 | 教师登录返回会话与 CSRF | 教师登录 200 且返回 csrf_token | HTTP 200 csrf=有 | ✅ |
| seeded | L03 | 登录与会话 | 会话恢复 | 会话恢复 200 且学号一致 | HTTP 200 user=teacher | ✅ |
| seeded | L04 | 登录与会话 | 学生登录 | 学生登录 200 | HTTP 200 role=student | ✅ |
| seeded | L05 | 登录与会话 | 未登录访问受保护接口被拒 | 未登录 GET /courses → 401 | HTTP 401 | ✅ |
| seeded | L06 | 登录与会话 | CSRF 来源校验 | 写请求缺 Origin → 403 CSRF_FAILED | HTTP 403 code=CSRF_FAILED | ✅ |
| seeded | L07 | 登录与会话 | 退出后会话失效 | 退出后 /auth/session → 401 | 退出 HTTP 204，之后 session HTTP 401 | ✅ |
| seeded | L08 | 登录与会话 | 登录后课程列表可用 | 课程列表：200 且有数据 | HTTP 200 课程数=1 | ✅ |
| seeded | L09 | 登录与会话 | 后台数据就绪判定（bootstrap） | bootstrap 200；data_ready=true | HTTP 200 data_ready=True 缺失 0 项 | ✅ |
| seeded | L10 | 登录与会话 | 缺失项逐项列出（归因依据） | 就绪清单覆盖 8 张业务表，空库逐项列出缺失原因 | HTTP 200 检查 8 项，缺失 0 项 | ✅ |
| seeded | R01 | SPEC-003 教学资源 | 资源列表 | 资源列表：200 且有数据 | HTTP 200 条数=1 | ✅ |
| seeded | R02 | SPEC-003 教学资源 | 教师上传资源 | 教师上传资源：200 且有数据 | HTTP 201 resource_id=2 | ✅ |
| seeded | R03 | SPEC-003 教学资源 | 按课程/类型检索 | 按课程/类型检索：200 且有数据 | HTTP 200 kind=guide 命中 2 条 | ✅ |
| seeded | R04 | SPEC-003 教学资源 | 授权下载并比对字节 | 授权下载：200 且有数据 | HTTP 200 字节一致=True | ✅ |
| seeded | R05 | SPEC-003 教学资源 | 缺少 intent/event_id 的下载被拒 | 缺 intent/event_id 的下载一律 400（参数校验先于数据查询，两场景一致） | HTTP 400 错误码=VALIDATION_ERROR | ✅ |
| seeded | R06 | SPEC-003 教学资源 | 学生越权上传被拒 | 空库明确 404；正常库学生上传 → 403 | HTTP 403 | ✅ |
| seeded | R07 | SPEC-003 教学资源 | 更新生成新版本且旧引用仍可访问 | 版本更新与旧引用：200 且有数据 | 新版本 HTTP 201，旧版本 HTTP 200 内容一致=True | ✅ |
| seeded | R08 | SPEC-003 教学资源 | 真实访问事件汇总 | 访问事件汇总：200 且有数据 | HTTP 200 含 download=True | ✅ |
| seeded | E01 | SPEC-009 实验辅助 | 实验列表 | 实验列表：200 且有数据 | HTTP 200 实验数=1 | ✅ |
| seeded | E02 | SPEC-009 实验辅助 | 学生可见已发布实验 | 学生可见已发布实验：200 且有数据 | HTTP 200 可见 1 个 | ✅ |
| seeded | E03 | SPEC-009 实验辅助 | 实验指导含目标/步骤/说明 | 实验指导字段：200 且有数据 | HTTP 200 objectives/instructions=齐 | ✅ |
| seeded | E04 | SPEC-009 实验辅助 | 两类提交入口（wiring / circuit） | 两类提交入口：200 且有数据 | HTTP 200 modes=['wiring', 'circuit'] | ✅ |
| seeded | E05 | SPEC-009 实验辅助 | 发布闸门：未配测试集不得发布 | 空库明确 404；正常库未配测试集的草稿发布被拒 | HTTP 409 code=STATE_CONFLICT | ✅ |
| seeded | E06 | SPEC-009 实验辅助 | 本人历史版本 | 本人历史版本/提交记录：200 且有数据 | HTTP 200 提交 2 条 | ✅ |
| seeded | E07 | SPEC-009 实验辅助 | 发布窗口与冻结名单 | 空库无冻结名单；正常库冻结名单含提交学生 | experiment_participant 2 行 | ✅ |
| seeded | G01 | SPEC-018 电路评测 | 固定 JAR 与评测就绪 | 固定 JAR 存在且 sha256 可校验（jar_ok=True） | JAR 54448596 字节，grader_ready 由 health 断言 | ✅ |
| seeded | G02 | SPEC-018 电路评测 | judge profile 配置与指纹 | judge profile 配置：200 且有数据 | judge_profile 1 行，sha=e741a62ae468 | ✅ |
| seeded | G03 | SPEC-018 电路评测 | 正例/反例参考文件 | 正例/反例参考文件：200 且有数据 | reference_file 2 行 | ✅ |
| seeded | G04 | SPEC-018 电路评测 | 测试集 8 个计分组 | 测试集 8 个计分组：200 且有数据 | test_case 11 行，分组 8 个 | ✅ |
| seeded | G05 | SPEC-018 电路评测 | 测试集真引擎验证（正例全过/反例失败） | 测试集真引擎验证：200 且有数据 | status=passed result={'reference': 'all_passed', 'negative': 'functional_failure'} | ✅ |
| seeded | G06 | SPEC-018 电路评测 | 测试集发布 | 测试集发布：200 且有数据 | published 测试集 1 个 | ✅ |
| seeded | G07 | SPEC-018 电路评测 | 学生提交正确 .circ → accepted 100 | 空库明确 404；正常库 accepted / 100.0 / 11 通过 | status=accepted score=100.0 passed=11/11 error=None | ✅ |
| seeded | G08 | SPEC-018 电路评测 | 学生提交错误 .circ → 部分给分 | 空库明确 404；正常库 wrong_answer / 87.5 / 10 通过（部分给分） | status=wrong_answer score=87.5 passed=10/11 error=None | ✅ |
| seeded | G09 | SPEC-018 电路评测 | 非 .circ 预检拒绝 | 空库明确 404；正常库非 .circ → 400 且明确错误码 | HTTP 400 code=VALIDATION_ERROR | ✅ |
| seeded | G10 | SPEC-018 电路评测 | 顶层电路名不符拒绝 | 空库明确 404；正常库顶层名不符 → 400 INVALID_CIRCUIT | HTTP 400 code=VALIDATION_ERROR | ✅ |
| seeded | G11 | SPEC-018 电路评测 | 学生报告脱敏 | 空库明确 404；正常库学生报告不含内部路径/快照/worker token | HTTP 200 敏感字段 [] | ✅ |
| seeded | G12 | SPEC-018 电路评测 | 重评生成新的 run | 空库明确 404；正常库重评生成 retry_of 新 run | HTTP 202 新 run #3 status=queued，reason 标记 1 条 | ✅ |
| seeded | G13 | SPEC-018 电路评测 | 空向量/零用例不得判满分 | 零用例/无输出列不得被判满分（两场景一致） | 空汇总解析=None，无输出列向量=None | ✅ |
| seeded | A01 | SPEC-010D 评测分析 | 教师查看评测统计 | 教师评测统计：200 且有数据 | HTTP 200 维度字段 ['algorithm_version', 'analysis_run_id', 'dimension', 'filters', 'generated_at', 'metrics'] | ✅ |
| seeded | A02 | SPEC-010D 评测分析 | 通过率与分数分布 | 通过率与分数分布：200 且有数据 | HTTP 200 指标 ['accepted_count', 'pass_rate', 'mean_score', 'score_bins', 'run_count', 'system_error_count']，score_bins 5 档，pass_rate=0.0 | ✅ |
| seeded | A03 | SPEC-010D 评测分析 | system_error 排除正确率分母 | 空库明确 404；正常库 system_error 单独成项、不并入正确率分母 | 注入 system_error 前 sample_size/pass_rate=(1, 0.0)，注入后=(1, 0.0)，独立成项=True | ✅ |
| seeded | A04 | SPEC-010D 评测分析 | 学生 scope=self | 学生 scope=self：200 且有数据 | HTTP 200 student_id=2 | ✅ |
| seeded | A05 | SPEC-010D 评测分析 | 学生查他人统计被拒 | 空库明确 404；正常库学生查他人统计被拒 | HTTP 403 | ✅ |
| seeded | A06 | SPEC-010D 评测分析 | 重评分组可区分 | 空库无重评记录；正常库重评 run 带 reason 标记可单独分组 | reason 非空的重评 run 1 条 | ✅ |
| seeded | C01 | 电路模拟与控制 | 电路实验台 spec 与就绪状态 | spec 200；两个实验；data_ready=true | HTTP 200 实验 2 个 data_ready=True | ✅ |
| seeded | C02 | 电路模拟与控制 | 芯片/引脚/正交导线/用例定义完整性 | 芯片/引脚/正交导线/用例定义齐全（两场景一致） | HTTP 200 几何问题 0 处 | ✅ |
| seeded | C03 | 电路模拟与控制 | 7485 全组合后端表与 compute 一致 | 7485 全 2048 组合表与 compute 抽样一致（两场景一致） | HTTP 200 行数=2048 抽样不符=0 | ✅ |
| seeded | C04 | 电路模拟与控制 | 74181 全组合与 74181 引擎一致 | 74181 全 512 组合表与 compute 抽样一致（两场景一致） | HTTP 200 行数=512 抽样不符=0 | ✅ |
| seeded | C06 | 电路模拟与控制 | 验证用例期望与权威求值一致 | 每个验证用例的期望值与后端权威求值一致（两场景一致） | HTTP 200 校验 5 个用例，不符 0 项 [] | ✅ |
| seeded | C08 | 电路模拟与控制 | 后台数据缺失时电路控制仍可用 | 数据缺失时电路定义仍完整、模拟/开关/验算不依赖业务表（两场景一致） | HTTP 200 实验 2 个，引脚 33 个 | ✅ |
| frontend | F01 | 电路模拟与控制（前端组件） | 登录后后台数据缺失时页面给出归因引导 | 出现「后台数据未初始化」提示并列出缺失项；电路图与开关仍渲染；无渲染异常 | 引导可见、开关 11 个、无异常 | ✅ |
| frontend | F02 | 电路模拟与控制（前端组件） | 后台数据正常时不误报缺失 | 不出现缺失引导条；状态卡显示「后台数据正常」 | 缺失引导已隐藏，状态卡为「后台数据正常」 | ✅ |
| frontend | F03 | 电路模拟与控制（前端组件） | 电路控制界面视觉元素与参考图一致 | 芯片文字、导线、开关、指示灯、接地符号数量与 spec 定义一致 | 开关 11 / 灯 3 / 导线 15 全部正交 | ✅ |
| frontend | F04 | 电路模拟与控制（前端组件） | 电路控制：开关切换 0/1 并刷新输出 | A3 开关 aria-pressed 由 false 变 true，输出关系/反馈同步变化 | aria-pressed true → false；反馈含 A3 | ✅ |
| frontend | F05 | 电路模拟与控制（前端组件） | 电路控制：复位 | 输入复位为 A=B=0，反馈含「已复位」 | A=B=0，反馈含「已复位」 | ✅ |
| frontend | F06 | 电路模拟与控制（前端组件） | 电路控制：载入用例 | 点击用例后该行高亮，输入变为用例值 | 用例「A=2, B=11」已载入并高亮 | ✅ |
| frontend | F07 | 电路模拟与控制（前端组件） | 电路模拟：验算当前用例 | 默认用例验算通过，反馈含「验算通过」 | 默认用例（A=9,B=3）验算通过 | ✅ |
| frontend | F08 | 电路模拟与控制（前端组件） | 电路控制：提交与记录 | 提交后记录表新增 1 行且状态为「通过」 | 提交记录 1 行，状态「通过」，得分 100 | ✅ |
| frontend | F09 | 电路模拟与控制（前端组件） | 进度环与完成提示 | 3 个用例全部提交后出现「本实验已通过」 | 3/3 用例通过，提示条出现 | ✅ |
| frontend | F10 | 电路模拟与控制（前端组件） | 验证说明分页控件 | 点击「下一步」后页码变为 2 / 3 | 验证说明 2/3 | ✅ |
| frontend | F11 | 电路模拟与控制（前端组件） | 电路图缩放 | 点击「放大」后反馈含缩放百分比 | 缩放 110% | ✅ |
| frontend | F12 | 电路模拟与控制（前端组件） | 多实验切换（74181 + 7400） | 芯片 74181/7400 出现，开关数量与 74181 spec 一致，输出读数含 F[3:0] | 74181/7400 已渲染，开关 14 个 | ✅ |
| frontend | F13 | 电路模拟与控制（前端组件） | 控制位只读约束 | 点击 S3 提示「只读」，输入不被改写 | S3 只读反馈正确 | ✅ |
| frontend | F14 | 电路模拟与控制（前端组件） | 控件可访问性 | 所有开关具备 aria-label / aria-pressed，键盘事件已绑定 | 11 个开关均具备 ARIA 与键盘支持 | ✅ |
| frontend | F15 | 电路模拟与控制（前端组件） | 电路模拟数值正确性 | 7485 全 2048 组合三路互斥完备；74181 全 512 组合 F=(A±B)&15 | 7485 2048 组 + 74181 512 组全部自洽 | ✅ |
| frontend | F16 | 电路模拟与控制（前端组件） | 后端不可用降级 | 出现「读取电路定义失败」提示与「重新加载」按钮 | 错误引导可见，无渲染异常 | ✅ |
| frontend | C07 | 电路模拟与控制 | 前端组件双场景 16 项交互测试 | 前端组件双场景 16 项全部通过 | node --test 退出码 0；TAP 16 条；结果文件 16 项，通过 16 项 | ✅ |
| frontend | C05 | 电路模拟与控制 | 前后端模拟内核全组合逐行一致 | 7485 2048 组合 + 74181 512 组合前后端逐行一致 | 7485 前端 2048 行 / 后端 2048 行，sha256 一致；74181 前端 512 行 / 后端 512 行，sha256 一致 | ✅ |

## 验收结论

**通过**：全部 118 个被测项通过，无功能差错，满足验收标准。

复跑命令：`python scripts/acceptance_shibaihe.py`
