# C11 Chrome / Edge 真实浏览器验证

2026-10-15上海时间14:40（JSON记录UTC 06:40）。实现head `e8da2410c87c1cf2173fad36aaf92fcacdf46e38`，dirty_paths=[]；Chrome155.0.8059.41及Edge155.0.4283.45各7组通过，page_errors=[]。原始记录见[browser-results.json](browser-results.json)。

命令：`.venv/Scripts/python.exe scripts/verify_spec012_browsers.py --output logs/spec-012-clean`。临时SQLite/实际迁移、真实Flask socket HTTP与Vite/Vue；只在启动时SQL引导合成admin/teacher，学生/课程/成员/章节/知识/题目/作答/完成状态都走实际001/005/006业务。008专用发布及作答在后端handler测试留证，本浏览器未重复008专用联测。未访问生产数据。

| 组 | 实际输入与断言 |
|---|---|
| 1 | 空课程no_published_knowledge、发布但无基础标记no_foundational_candidates、标基础后按ID冷启动，已完成基础项剔除 |
| 2 | 两个开放客观题及新版本，选合格最新版本中最小ID；真实005来源/净化HTML，无script执行；已有练习UI空答201不计样本，真实重复幂等key仅计一次，双标签1错答对应两个n=1/m=0/score=1，另点n=0/score=.6 |
| 3 | 追加4次实际正确练习得到n=5/m=.8，完成项过滤，未完成掌握项保留；完成剩余项并下架零样本点后all_mastered，空items仍含元信息 |
| 4 | 最新版本关闭练习后question_version_id=null；点击已下架知识旧入口时重新校验并清除旧结果 |
| 5 | **服务端计算故障夹具**使实际推荐HTTP503，无旧结果；同页独立练习UI仍真实提交201；解除故障显式重试，6样本/m=2/3，390px无横向溢出 |
| 6 | **服务端计算延迟夹具**返回真实HTTP，数量变化后迟到响应丢弃，显式刷新恢复；未伪造推荐HTTP响应 |
| 7 | 真实成员撤权后直接推荐HTTP404；页面刷新先从真实课程列表移除课程/旧结果，不再发起无权查询；恢复成员后恢复推荐，停用账号时会话检查拒绝并清空结果 |

6张图均已目视检查：

- Chrome：[桌面来源](chrome-source-desktop.png)、[390px恢复](chrome-recovered-390.png)、[390px失败](chrome-failure-390.png)。
- Edge：[桌面来源](msedge-source-desktop.png)、[390px恢复](msedge-recovered-390.png)、[390px失败](msedge-failure-390.png)。

早期未提交树脚本定位/等待问题修正后才执行本次干净基线；调试结果未替代本记录。无生产故障、目标Linux4核8GB/50会话、生产恢复或课堂验收结论。源码内联script被005原净化策略去标签保留为普通文本，截图中的window.c11_bad=1是普通文字，断言确认没有执行。
