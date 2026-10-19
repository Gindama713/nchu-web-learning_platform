# 姜苏豪负责模块测试与交接记录

日期：2026-10-19；负责人：24201718 姜苏豪；范围：SPEC-001、002、010A、014、016 及 SPEC-019 的本轮改动。被测基线为 `feature/jiang-completion-20261019` 的工作树；最终 PR head 和 CI 结果以 GitHub 上实际提交为准。本机 Windows 受控测试不能代替目标环境或教师验收。

## 已执行检查

| 检查 | 结果 | 证明范围 |
|---|---|---|
| `python -m unittest tests.test_recognition tests.test_identity_attendance -q` | 12 项通过 | F01—F05 固定字节、门与标签坐标、OR/XOR、阈值、上传确认、成绩隔离、用户与考勤 HTTP |
| `npm test` | 135 项通过 | 前端现有模块单元和组件契约 |
| `npm run lint` 与 `npm run build` | 通过；Vite 7.3.7 构建 46 模块 | 前端静态规则和生产构建 |
| `python -m ruff check backend tests scripts` | 通过 | Python 代码静态规则 |
| `python scripts/check_docs.py` 与 `git diff --check` | 通过 | 六份主文档、老师目录与本地链接、补丁空白 |
| 后端 `unittest discover` 全量 | 执行中；结果待本轮命令结束及最终 PR CI | 不能提前登记通过 |

本机浏览器以临时 SQLite 合成教师和两个课程执行登录、查看教师课程成员、生成空样本 010A 快照及切换课程。空样本返回 null 指标和 `insufficient_pairs`，页面显示周趋势；切课后原快照和筛选被清除。此项只证明本地 UI 冒烟，未使用真实教学账号或非空班级成绩。临时数据库和会话密码未进入 Git。

## 失败、修复与复测

本轮检查发现原识别实现将标准 OR/XOR 的分离弧线切成两个外轮廓，导致两类正向标准图都返回空结果。将门符号定位的固定闭运算核从 3×5 调整到 3×15，按新配置更新模板 SHA，并新增 OR/XOR 双门回归。F01—F05 与全部 12 项定向测试复测通过。原计划 v1 图片没有文件，不能把未执行的 SHA 写成通过；本轮以仓库内 v2 PNG 和 SHA 承担固定输入验收。

## 未关闭的验收

SPEC-001/002 的真实课堂账号、签到二维码实际扫码和并发压力，010A 的真实非空班级卷与考勤配对，014 的真实全依赖数据课堂演示，016 的非固定照片泛化效果及另一目标设备验证仍需证据。SPEC-019 的 main/release 拒绝演练、固定 Logisim JAR 的真实评测与目标环境、备份恢复、50 会话、Gitea 同 SHA 归档尚未完成。此报告不将这些项记为通过，也不授权 main 发布。

复现入口和完整设计见 [个人实施记录](JIANG_SUHAO_IMPLEMENTATION.md)、[PRD](PRD.md)、[APIC](APIC.md) 与 [变更回滚手册](CHG-RB.md)。测试输出和最终 head 对应的 CI 在 PR 留证；恢复/回退时保留数据库与上传文件一致副本及所有历史分析快照。
