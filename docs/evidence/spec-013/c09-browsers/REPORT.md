# C09真实HTTP/UI验证（2026-10-15）

执行人：AI，本地Windows受控环境、合成账号/课程。使用已安装Chrome155.0.8059.41、Edge155.0.4283.45，headless；不代表教师课堂、Linux4核8GB/50会话、worker或生产环境验收。

干净tested_head：`fd89dab00baedaf0d743c8cfe51f03a86f1e4444`，dirty_paths=[]。命令：`.venv/Scripts/python.exe scripts/verify_spec013_browsers.py --output logs/spec-013-browsers-clean`。两浏览器各5组通过、page_errors=[]，原始时间/检查在[browser-results.json](browser-results.json)。只有初始管理员/教师账号为SQL引导，其余身份、课程、知识、题目、作答、生成、发布均真实HTTP，无伪造响应。脚本先完成初始会话恢复，登录后显式“重新加载试卷”，以现有UI恢复启动阶段并发模块请求；不改共享鉴权或队友模块。

| 用例 | 输入/预期 | 实际 |
|---|---|---|
| 首次生成 | 3简单题、10.01分、知识标签、seed=9223372036854775807；仅draft、无名单；配分334/334/333 | 两浏览器均符合，固定版本/覆盖及完整seed可见 |
| 重放 | 首次后HTTP新增题/版本/真实practice作答；原快照仅新标题 | 原选题及精确配分不变；界面无新约束/seed，学生无生成入口 |
| 移动端 | 390px重放结果 | 无横向溢出；截图可读 |
| 确定无解 | 100题配额而实际仅4题；应422，不交付草稿 | INFEASIBLE_CONSTRAINTS；保留参数、纠正提示、旧结果清除 |
| quiz发布接缝 | 生成kind=quiz草稿，教师查看后显式008专用发布 | published、冻结名单1人、review_at=null；无自动讲评 |

桌面结果：[Chrome](chrome-result-desktop.png)、[Edge](msedge-result-desktop.png)。390px重放：[Chrome](chrome-replay-390.png)、[Edge](msedge-replay-390.png)；失败：[Chrome](chrome-failure-390.png)、[Edge](msedge-failure-390.png)。已人工读取图像核对390px排版。早期预跑/失败轮留logs，不作为本正式通过证据；旧010B截图不复用。

HTTP专题包含真实100000节点503、非法组合/权限/CSRF/撤权、保存故障回滚和备份重放，详见[013实施记录](../../../SPEC-013_IMPLEMENTATION.md)。本地后端176项293.361秒、前端68项的完整日志在父目录，业务源码分别对应3925d50/e3d92e8；后续提交只改浏览器脚本/文档/证据。GitHub CI须另按PR当前head/base/tested核验，不能将本地或旧CI当作当前CI。
