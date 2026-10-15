# SPEC-011 检索问答实施记录

负责人：黄俊诚（24201716）。范围为C10，依据[PRD§4.3](PRD.md#qa-recommendation-acceptance)、[011有效验收](PRD.md#accept-spec-011)、[APIC](APIC.md)第5.2节及[DBD](DBD.md)第3/5节。只返回知识检索片段与出处，不接生成模型、向量库或新调度平台；不开展C11。

## 接入基线与评审边界

2026-10-15 fetch后origin/develop=`cdbda1e4a6bce19e2a5c4016a528d1d3d8b2aceb`，从该基线新建`feature/spec-011-qa`。远程没有同名011分支。PR #13仍open/非draft、head=`a6870326e31be2018d9fb135ef29b099d82aa6d4`；真实reviews、review_threads、issue comments均空。当前head的[Actions38678908036](https://github.com/Gindama713/nchu-web-learning_platform/actions/runs/38678908036)已重新查询，policy/lint/test/build/required均success，grader按develop规则skipped。没有实际评审缺陷或本轮阻断项；保留013评审状态，不复制其未合入代码，不重复C08/C09、C07或010B专用联测。

## C10a 算法、索引与持久化

`qa-tfidf-v1`查询与语料共用NFKC（包括HTML字符实体）、英文小写、去标签和空白合并。固定PC/ALU/ACC/IR别名用英文词边界（字母/数字/下划线不可紧邻，中文可紧邻），长缩写优先。每个当前已发布知识按title/content/example组成一篇文档，scikit-learn字符1—3gram、min_df=1、平滑IDF、L2归一化。未舍入余弦相似度≥0.10后按原值降序、知识ID升序取top_k；响应数值round到6位，页面补足6位显示。摘录仅去HTML的正文前200字符。

语料revision为按ID排序的当前已发布知识id/title/content/example/content_revision的规范JSON SHA-256；空语料也有稳定revision。内容或发布集合变化在下次请求的快照及最终写事务校验中立即使旧缓存失效，不依赖定时任务或005进程内通知。各应用实例持有可丢弃完整索引对象；进程重启/备份恢复从事实重建，不反序列化pickle或信任数据库ready标记直接返回旧内容。

读取快照后释放事务，在写锁外构建/搜索。短BEGIN IMMEDIATE内重新核验会话、课程访问及当前revision；变动则最多重新读取/构建3次，持续变动返回503 INDEX_UNAVAILABLE。完整提交qa_index与qa_query后才原子替换缓存。构建/搜索失败丢弃该课缓存，当前revision落failed/INDEX_UNAVAILABLE，返回503且不含旧片段；下一次请求可重建恢复。持久化任一步失败整体回滚，不发布半成品。其他进程同样受最终数据库revision门控。

新增`011_qa.sql`，不改旧迁移。qa_index一课一行记录revision/算法/built_at/status/error_code；qa_query仅保存会话本人、课程、最多500字符原问题、命中ID、对应未舍入相似度、revision及算法版本。无查询历史读取端点，不能凭用户输入查询他人记录；未授权/非法请求和失败重建不写成功查询记录。复用001/005会话、Origin、CSRF及课程访问；接口按APIC的L可查，管理员同样只检索已发布语料。`Cache-Control: no-store`。

Context7已查询当前scikit-learn TF-IDF/归一化、Vue watcher异步失效及Playwright Python浏览器验证文档；没有升级依赖。业务实现、证据与正式记录版本化，两份个人记录继续info/exclude。

## 分段验证与待续

C10a：`python -m unittest tests.test_qa -v`，15项通过（11.746秒）；5项算法组件测试、10项真实001/005 Flask HTTP-handler/SQLite集成测试，账户仅bootstrap，课程/学生注册/成员/章节/知识更新及下架均走真实业务接口。包括并发查询、第二线程实际005更新/撤权、构建失败夹具、qa_index/qa_query触发器故障回滚及受控SQLite备份恢复；不等同真实网络socket、浏览器或生产恢复。首轮夹具同线程嵌套请求失败已改成独立线程，旧失败不记通过。页面/组件、真实双浏览器、全量回归及PR/当前head CI将在后续节登记，尚不能据此关闭完整SPEC。

回退：保留知识/用户/会话/查询及配套schema的一致性备份和增量；用匹配代码与数据库恢复，索引缓存可丢弃重建。不得删除历史查询来掩盖失败、不改旧SQL或共享分支。两名实际非作者复核、目标Linux4核8GB/50会话性能、生产恢复及课堂证据须单独登记，不由本地自动测试代替。
