# 代码补全与实测记录（2026-11-25）

本轮补齐常驻在线评测、时钟事件适配、教师基础配置与知识配图，并完成独立进程及浏览器实测。Gitea 不在本轮范围；尚未推送的新代码不宣称远端 CI 已通过。

## 可复现入口

从仓库根目录执行，先安装 `backend/requirements.lock`，在 frontend 执行 `npm ci`、`npm run build`。Web 和 worker 使用同一 DATABASE_PATH、UPLOAD_ROOT、LOGISIM_JAR_PATH；正式环境另配强 SECRET_KEY 与 HTTPS APP_ORIGIN，不能使用测试账号。

```sh
python -m flask --app backend.app db-upgrade
python -m backend.serve
# 另一个终端，同样的环境变量；Ubuntu 默认使用 bubblewrap
python -m backend.worker --sandbox bubblewrap
```

Ubuntu 依赖 Java 21、bubblewrap、xvfb、xauth、util-linux；命名空间必须可用。Windows 开发可用 `--sandbox native`，production 拒绝该模式。生产服务管理、备份与停止方式见 [RUNTIME_OPERATIONS](RUNTIME_OPERATIONS.md)。

固定 Logisim-evolution 5.0.0 JAR SHA256：`6b368e894742c04cc83aa9830f869bcab0190ede4df43ad6fecdb89b3a23a41c`。不要以任意同名 JAR 替换。

```sh
# 临时合成账号与临时库；真实HTTP、Waitress、独立常驻worker及真实Java
python scripts/verify_grading_live.py --jar /path/to/logisim.jar --sandbox bubblewrap --load --report test-tmp/grading-live/report.json
# Windows 已安装的 Chrome/Edge，不自动下载浏览器；另装 requirements-browser.txt
python scripts/verify_grading_live.py --jar C:/path/to/logisim.jar --browser-only --report test-tmp/browser-live/report.json
```

脚本失败返回非0；报告和 web/worker 日志写入 report 所在目录。`--browser-only` 只验证界面，不伪装成电路评测结果。脚本复用现有测试夹具初始化临时数据；领取、续租、执行及提交结果均由真实独立worker完成，不注入判分结果。

## 已核实结果

| 范围 | 结果与边界 |
|---|---|
| Windows / Python 3.14 / Java 21 | EXP-01 ALU8（8例）、EXP-02 REG8（4例）、EXP-04 CPU8（11例）：正确电路accepted，移除导线反例wrong_answer，真实重评accepted，其他学生读取404 |
| Ubuntu 24.04 / WSL2 Linux 6.18 / Python 3.12.3 / Java 21 | 同样23例及完整“配置→标准/反例验证→发布→学生提交→报告→重评”通过；bubblewrap内部运行Xvfb，不共享宿主显示 |
| Linux 并发请求 | CPU评测期间50个合成会话发出200次session/课程/实验轮询及只读助教请求，0失败，单次实测p95 644.7ms，请求完成后worker仍running；不等于50个并行Java任务或课堂全功能压测 |
| Chrome / Edge | 教师载入公开模板、基础表单同步高级JSON、保存配置及测试集；教师上传知识图片、学生查看、下架后图片404、重新发布恢复，均通过 |
| 390×844窄屏 | 两浏览器检查评测和知识页面、整个文档横向宽度无溢出，无pageerror；实测还修复了同页ALU网格挤宽页面的问题 |
| Ubuntu 全量后端回归 | Python 3.12.3，575项全部通过，耗时590.057秒；该子进程移除宿主注入的GIT_CONFIG_*环境变量，原始日志位于test-tmp/completion-linux-final/full-backend.log |
| 最终定向回归 | 后端评测/worker/图片/线程扫描44项通过；前端302项通过（含高级JSON结构错误恢复）；Ruff、ESLint、构建通过。Vite仍有既有的单JS包超过500kB提示 |

本地原始报告位于 `test-tmp/completion-windows/report.json`、`test-tmp/completion-linux-final/report.json`、`test-tmp/completion-ui/report.json`，浏览器截图位于后者目录；这些临时产物不进入提交，需用上方命令重新生成。

Windows 后端全量曾执行573项，其中572项通过，1项提交打包测试因宿主继承的 GIT_CONFIG_VALUE_0 缺失导致 git init 失败；仅移除该子进程的 GIT_CONFIG_* 注入后该项重跑通过，没有修改全局Git配置。之后增加的worker冷启动及真实扫描线程检查包含在最终44项回归中。

## 实现约束

- `port_schema.clock` 显式声明独立1位时钟；输入先稳定、边沿后采样、省略输入保持前值；每例独立重置引擎状态，时序模板先同步复位。无时钟的旧profile哈希不变；未声明clock的边沿不能静默按组合逻辑执行。
- 公开模板覆盖必需评分组，仍需教师按课程目标扩充边界用例。基础表单编辑同一份JSON，保留高级配置；配置变更后必须重新验证标准/反例才能发布。
- 知识图片仅PNG/JPEG、≤5MiB，绑定已保存的知识点。正文和例题用 `[[image:ID]]` 引用；跨知识点引用被拒绝，外部img继续清理。学生读取时即时检查课程授权、发布状态及引用是否仍存在。
- worker 单并发、OS锁防重入、真实心跳、自检刷新、续租及失租取消；Web过期任务扫描已修复Flask应用上下文问题。新增流程纳入CI配置，远端执行结果仍需推送后核验。

## 尚不能宣称完成的验收

没有课堂现场、教师签字、指定4核8GB实体机、正式HTTPS/systemd部署或Gitea核验。WSL本次有32个可用CPU和约16GB内存；单个Java任务限制1核，不把该环境冒充课程指定机器。

Linux已有无网/非root/只读挂载/私有临时目录、CPU与输出/时间限制；内存使用JVM堆限制。总RSS 512MiB及线程/进程数的cgroup硬限制尚未部署验收，PRD要求保持不变；正式对外开放前仍需补齐该环境约束。
