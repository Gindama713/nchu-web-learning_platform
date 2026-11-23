# Web 运行与维护（2026-11-23）

以下命令在仓库根目录、已安装 `backend/requirements.lock` 的环境中执行。生产设置强 `SECRET_KEY`、HTTPS `APP_ORIGIN`、外置 `DATABASE_PATH` 与 `UPLOAD_ROOT`；密钥不进入备份。先构建前端，再用 `python -m backend.serve` 启动单进程 Waitress，前台 Ctrl+C 停止。默认仅监听127.0.0.1:8000，HOST/PORT/WEB_THREADS可覆盖；HTTPS入口及目标Linux服务管理须单独验证。

## 健康与 worker 集成

`GET /api/v1/health` 分别返回 web_ready/db_ready/engine_ready/worker_ready/grader_ready、队列计数及 maintenance。全部就绪且非维护才200，其余503。HTTP探针不启动Java；路径指向任意普通文件不能使引擎就绪。

配置 `LOGISIM_JAR_PATH` 后执行真实正反例自检：

```powershell
python -m flask --app backend.app engine-check
```

检查固定JAR的SHA256，并通过正式命令构造/执行器/解析器分别运行正确和故意错误的可信通道向量。成功记录有效300秒；JAR身份变化或记录过期失效。该检查不证明学生队列已被消费，也不证明评测沙箱已经完整隔离。

SPEC-018 常驻worker接入契约（真实循环内调用，不能由假心跳线程替代）：

```python
from backend.runtime import check_engine, publish_worker_status

# 启动及每300秒到期前调用；失败停止新领取并发布error。
check_engine(database_path)
# 真实空闲/执行/暂停循环每不超过5秒发布；执行期必须与续租一起继续发布。
publish_worker_status(database_path, worker_id, "idle")  # running / paused / error
# 正常退出：
publish_worker_status(database_path, worker_id, "stopped")
```

心跳超过45秒或状态为paused/error/stopped时worker不就绪。claim_run/claim_validation已接维护标记，维护时不领取，也不回收排队任务；已经运行的任务允许续租并提交结果。当前仓库尚无正式常驻worker，必须由石佰合接入；Web不自动启动验收脚本。

## 维护、备份、恢复

```powershell
python -m flask --app backend.app maintenance on
python -m flask --app backend.app maintenance status
python -m flask --app backend.app backup create --destination backups/checkpoint-20261123
python -m flask --app backend.app backup verify --directory backups/checkpoint-20261123
python -m flask --app backend.app backup restore --directory backups/checkpoint-20261123 --destination backups/restored-20261123
```

维护标记保存在数据库旁，跨Web/CLI进程生效、重启后仍保留；除health外API全部503，普通业务事务在取得写锁后再次校验。当前采用全面暂停，不提供维护账号的业务写入例外。公共help/who入口保留，维护时不写访问日志或会话续期。

备份必须先进入维护，若有running评测或测试集验证任务则拒绝，等待其完成后重试。取得SQLite写锁冻结引用，用SQLite备份API生成数据库副本并复制全部file_object文件（包括资源、识别图片及电路）；清单记录迁移版本/校验和、数据库SHA256、每文件大小/SHA256及时间。缺文件、哈希不符、外键或完整性检查失败不发布备份目录。维护关闭与备份使用同一操作锁，备份中途不能解除维护。

恢复只接受不存在的新目录，不覆盖当前数据库或uploads，完整校验后发布；恢复副本仍自动处于维护状态。失败不解除原库维护。验证后停止原Web/worker，再把DATABASE_PATH与UPLOAD_ROOT同时切向新目录；生产继续使用原外置SECRET_KEY，开发副本需要重新登录。需要回切时保留新旧数据，不能直接覆盖仍在写入的数据库。

对恢复副本检查资源、电路、连线及统计后，明确关闭对应数据库的维护：

```powershell
python -m flask --app backend.app maintenance off
```

无可用worker或引擎时health继续degraded，不因维护解除而伪报整体就绪。异常断电遗留 `.operations-lock` 时，先确认无维护操作进程并保留失败记录，再由操作人处理锁文件；程序不自动猜测并删除锁。

## 清理与访问日志

```powershell
python -m flask --app backend.app cleanup --retention-days 90 --batch-size 1000
```

每次最多各清理1000条过期会话和超过90天访问日志；保留期不得低于90天。不删audit_event、成绩、快照、电路及资源。生产默认AUTO_CLEANUP=1，复用现有扫描线程每分钟执行一批；开发默认关闭，可显式开启。维护期间暂停清理。该策略不是“课程验收后90天”的成绩/快照清理器，后者本轮不删除。

访问日志按数据库分别缓冲，事务内整批落盘；失败保留重试，最多10000条，溢出计数而不无限积压。`GET /api/v1/logs/summary` 向授权用户返回buffer.pending/flush_failures/dropped，后台每5秒尝试到期批次，正常退出尽量补写。进程强杀仍可能丢失内存尾部，不能称为持久消息队列；关键业务audit仍在业务事务中。

## 可重复验证

```powershell
python -m unittest tests.test_operations tests.test_assistant tests.test_assistant_phrasings tests.test_scaffold -v
python scripts/verify_runtime.py --students 50 --report test-tmp/jiang-runtime-50.json
```

HTTP脚本只创建临时数据库及合成会话，实际启动Waitress、并发签到/轮询/助手，再用独立CLI切维护并验证旧会话被拒绝，最后停止测试进程。会话为夹具签发，不衡量登录限流；不连接真实演示库。报告区分请求失败、落库数量与延迟，不能替代交卷/真实worker混合负载或Linux4核8GB验收。

本机本轮记录：Windows 11、Python3.14、50会话、200请求、0失败、50签到、p95=636.1ms；真实固定Logisim通道正反例自检通过。全量测试结论以最终代码对应的执行结果为准，未推送不声称远端CI通过。
