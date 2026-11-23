# 石佰合负责模块测试记录

材料归属：24201737 石佰合。本轮由 Codex 协助执行和整理，不代表本人操作或教师课堂验收。基线为 `bd2f3f9` 上的本轮工作树；代码变更与验证范围见结课交付记录。

## 1 自动测试范围

```sh
python -m unittest tests.test_resources tests.test_experiments tests.test_circuit_lab tests.test_grading tests.test_grading_analytics tests.test_grading_engine_contract tests.test_grading_executor_timeout tests.test_grading_worker
```

覆盖资源上传/版本/权限/事件去重、实验发布与提交、实验台非法输入、评测排队/幂等/权限/重评、租约和进程超时、评测统计快照/CSV/系统故障口径。集成测试调用真实 Flask 路由与临时 SQLite；部分 worker 终态由测试注入，不能称为真实 Logisim 通过。

## 2 本轮执行状态

2026-11-23，Windows，使用原仓库 `.venv` Python 和依赖，当前目录为 `wt-week10`。初次沙箱运行因临时目录 ACL 拒绝访问而失败，未计为产品结论；正常临时目录权限重跑后 **98 项通过，132.360 秒，0 失败**。输出含未关闭测试文件的 ResourceWarning，未导致断言失败。原始日志保存在本机 `test-tmp/shibaihe-20261123.log`，不提交含环境细节的完整日志。

## 3 真实引擎与课堂验证

真实引擎另运行 `scripts/ci_grader_smoke.py`，必须校验固定 JAR 摘要且验证正确电路、错误电路与零用例；Linux 使用 xvfb。当前本地这组集成测试不承担该证明。ci-grader 已扩展到 develop PR，并进入 ci-required 必需依赖；实际通过与否以当前提交的 CI 记录为准。

待本人完成：双会话操作、脱敏截图、目标环境实测、独立 Gitea 提交与教师检查。前端完整测试和交付脚本检查属于小组验证，不计作个人独立工作量。
