# C10 同步后的真实浏览器验证

执行日期2026-10-15。脚本：`python -m scripts.verify_spec011_qa --output logs/spec-011-synced-browsers`。干净tested_head=`36854081b1ba991a89bacbf7d797ab0620619ae3`，base develop=`f9c49b19c59053be2b171e0b7f2a35d1e050e57e`；[原始report.json](report.json)的dirty_paths=[]。Chrome155.0.8059.41、Edge155.0.4283.45各9组通过，page_errors=[]。

账户仅受控bootstrap，001注册/课程/成员使用实际handler建数据；005知识发布/改文/下架、011问答、001撤权、005进度及006练习提交使用真实socket HTTP，页面为实际Vue/SQLite实现。只有索引构建失败使用明确的unittest.mock故障注入；阈值边界和同分原始double为算法组件测试，不能把夹具伪称真实自然语料或生产故障。

PC命中当前已发布知识、草稿隔离、6位分数及出处正文；零向量/no_match；真实修改引发revision变化；构建失败HTTP503清除页面旧内容且实际练习提交201/学习进度仍成功；显式重试恢复；真实下架遇故障不泄漏旧片段、恢复后empty_corpus；真实延迟响应在问题改变后丢弃；390px无文档横向溢出；成员撤权404后清空/禁用；SQLite记录身份/原始分数/revision/算法及FK完整性均已断言。

已目视核对匹配/失败/390px截图。以下证据仅为受控本地集成，不代表50会话目标性能、生产恢复、课堂验收或实际非作者评审。

| 浏览器 | 匹配与出处 | 故障状态 | 390px |
|---|---|---|---|
| Chrome | [匹配](chrome-matched.png) | [故障](chrome-failure.png) | [手机宽度](chrome-mobile.png) |
| Edge | [匹配](msedge-matched.png) | [故障](msedge-failure.png) | [手机宽度](msedge-mobile.png) |
