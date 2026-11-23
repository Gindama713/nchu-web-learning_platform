# SPEC-020 实现与测试追溯

| 验收项 | 实现 | 自动验证 |
|---|---|---|
| AC-01、03、04、05 事实一致、降级、来源、只读与复算 | `backend/apis/assistant.py` | `tests/test_assistant.py` |
| AC-02、06、07 课程与学生权限、单生资料、本人学习记录 | 同上 | `tests/test_assistant.py` |
| AC-08 口语、指代与澄清 | `classify`、`match_student` | `tests/test_assistant_phrasings.py` |
| AC-09 图与事实同源、空态与两点趋势 | `backend/models/assistant_charts.py`、`frontend/js/charts.js` | `tests/test_assistant.py`、`frontend/js/charts.test.js`、`frontend/js/assistant-view.test.js` |

运行：`python -m unittest tests.test_assistant tests.test_assistant_phrasings`；在 frontend 内运行 `npm test`。

尚需现场执行：[演示记录](../../docs/DEMO_SCRIPT_ASSISTANT_20261120.md) 中的教师/学生操作、外网断开时的本机访问、脱敏截图。此文件记录覆盖关系，不声明这些现场项目已通过。
