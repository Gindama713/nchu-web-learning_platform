# SPEC-020 教学助手实施计划

负责人：姜苏豪。范围与验收以 [PRD](../../docs/PRD.md#accept-spec-020)、[APIC 第16节](../../docs/APIC.md) 为准。

复用 010A 考勤、010B 掌握度、011 检索、014 预警的既有计算，提供只读提问入口；不接外部模型，不新增业务表或迁移。先按会话与课程成员校验权限，再分类意图、取事实、生成文字与图表。

实现位置：`backend/apis/assistant.py`、`backend/models/assistant_charts.py`、`frontend/js/assistant-client.js`、`frontend/js/assistant-view.js`。规则版本 `assistant-rules-v1`，普通事实窗口最近 28 天；最近点名按最近一次关闭任务查询。

验证顺序：后端事实与权限回归、口语分类回归、前端图表与动作回归，最后执行 [演示脚本](../../docs/DEMO_SCRIPT_ASSISTANT_20261120.md)。课堂操作、脱敏截图与离线实测单独记录，自动测试通过不代表教师验收。
