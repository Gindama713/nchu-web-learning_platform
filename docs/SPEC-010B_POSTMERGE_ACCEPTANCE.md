# 黄俊诚七 SPEC 合入后复验与验收收口

黄俊诚（24201716）。本包由用户于2026-10-19授权，执行人为Codex自动验证；不是非作者批准或教师验收。范围为005、006、008、010B、011、012、013的原阻塞项复验、131行状态整理和材料导航。

## 当前结论

核验基线为 develop `2973bef7bfadb429fe8b17cfadf2d3a2685c796a`。#27—#35已由#38整合，#36的018、#37的010D及#39的组长收尾代码均在该基线。逐一读取真实PR合入元数据，并用Git核验actual merge与原head均为基线祖先。[PR快照](evidence/postmerge-20261019/remote-prs.json)、[005/011/012快照](evidence/postmerge-20261019/core-prs.json)。

**131行现为本地81通过/50阻断、集成81通过/50阻断；31项原始/继承AC均在本人适用范围通过。完整七SPEC、I-01/I-02/I-03、课堂和发布仍未关闭。**

相对基线仅16行集成由阻断改通过，其中005/R20的本地结果也改通过。其余改动只纠正过期依赖描述和补当前证据；没有把预期失败、CI跳过或代码存在判为验收通过。[唯一矩阵JSON](evidence/c12a/acceptance-matrix.json)与[Markdown](evidence/c12a/acceptance-matrix.md)同步；原head/tested/附件及已有历史字段不覆盖，变更前字段逐行留在POSTMERGE_原字段，[复算记录](evidence/postmerge-20261019/reconciliation.json)证明原字段可逐值恢复。

| SPEC | 本地通过/阻断 | 集成通过/阻断 | 仍缺内容 |
|---|---|---|---|
| SPEC-005 | 9/7 | 9/7 | 图文资源引用契约；另有6项共通/环境 |
| SPEC-006 | 14/9 | 14/9 | R01/R02/R44备课/演示页面与完整角色链；另有6项共通/环境 |
| SPEC-008 | 14/10 | 14/10 | R01/R02/R37/R44备课/演示页面与完整角色链；另有6项共通/环境 |
| SPEC-010B | 15/6 | 15/6 | 6项共通/环境；统计主体和已定义消费子链已验 |
| SPEC-011 | 9/6 | 9/6 | 6项共通/环境；旧“待合入”不再作为阻断 |
| SPEC-012 | 10/6 | 10/6 | 6项共通/环境；旧“待合入”不再作为阻断 |
| SPEC-013 | 10/6 | 10/6 | 6项共通/环境；不重开组卷开发 |

## 原阻塞项实际复验

| 原问题 | 本次实际结果 | 保留边界 |
|---|---|---|
| R37-004-01/02 | 未发布quiz关联备课发布返回409 QUIZ_NOT_PUBLISHED；元数据含window_state=upcoming。8项handler全部通过，Chrome/Edge各6组通过 | 004备课页面仍未注册，不关闭完整R37 |
| I03-007 future revision | after_revision=99返回数据库真实revision；列表、角色权限及本人子链3项全部通过 | 007课堂演示页面仍缺，未演示从该页面进入知识/quiz |
| I01-017窗口/撤权/重做 | 未来窗口拒绝创建、截止拒绝新提交、撤权后三种旧写入404、重做生成新draft且保留旧提交；连同原事实消费共6项全部通过 | 017/010C工作台/统计页面仍缺，不关闭完整I-01 |
| 005→011与011原“待合入” | 当前集合/改文/下架/revision、索引失败503/恢复、无匹配、出处、撤权；双浏览器各9组通过，完整回归中的算法边界继续通过 | 005/R20仅其基础标记/revision→011适用部分，不代验014预警或016识别 |
| 012原“待合入” | 冷启动、样本/掌握过滤、真实练习/幂等、故障期间继续作答、撤权/恢复；双浏览器各7组通过 | 不新增实验评测事实参与推荐的规则，不声称完整I-02通过 |

修复来自已合入#38；本包没有修改backend、tests、frontend、迁移、API/DBD、业务算法或CI。仅修正旧验证脚本对已修复行为的断言/结果标签，以及推荐浏览器夹具的生命周期。

## 本轮验证与证据层次

- 后端完整回归：376项，661.473秒，0失败；在干净2973bef启动，本包没有改变backend/tests来源。包含全部七SPEC及既有跨模块用例，不等同真实worker或目标性能。[原日志](evidence/postmerge-20261019/backend-full.txt)。
- 前端135项、ESLint、生产构建通过；[测试](evidence/postmerge-20261019/frontend-tests.txt)、[lint](evidence/postmerge-20261019/frontend-lint.txt)、[构建](evidence/postmerge-20261019/frontend-build.txt)。
- 定向handler：8+6+3=17项，0失败/错误/预期失败；[R37原响应及表事实](evidence/postmerge-20261019/r37-handlers/handlers.json)、[I01](evidence/postmerge-20261019/i01-handlers/report.json)、[I03](evidence/postmerge-20261019/i03-handlers/report.json)。
- Chrome155.0.8059.80、Edge155.0.4283.62：R37各6组、I03各7组、QA各9组、推荐各7组，page_errors均[]。[R37](evidence/postmerge-20261019/r37-browsers/browsers.json)、[I03](evidence/postmerge-20261019/i03-browsers/report.json)、[QA](evidence/postmerge-20261019/qa-browsers/report.json)、[推荐](evidence/postmerge-20261019/recommendation-browsers-final/browser-results.json)。
- R37/I03/QA及三个handler报告的干净tested为90a69c49ea24677c0bea26f5a8f3825a91066922；推荐最终干净tested为d8509d6fb250825974ab30f3ad3015c77427127a。后续证据/文档提交不是这些运行的tested，不循环把自身SHA写进自身。
- 30张正式截图保留；自动断言按脚本实际覆盖范围登记，目视抽查9张代表图，名单在[验证摘要](evidence/postmerge-20261019/verification-summary.json)。未声称全部截图逐张人工验收。
- 本机Python 3.13.12、Node v24.14.0，Windows；与课程目标/CI的Python3.12、Node22分别记录。

成功业务由真实handler或socket HTTP产生；账号bootstrap、TEST_NOW、通知回滚触发器、索引/推荐故障和延迟均按原脚本显式标注。R37备课操作是socket API，使用现成008页面看题/交卷/讲评，不伪装成备课UI点击。I01本轮仅handler复验，复用原固定浏览器能力证据；I03用现成错题/统计/知识/QA面板手动进入，不声称自动跳转。013等未新跑专门浏览器整包，复用原固定证据，算法/API由本轮完整回归覆盖。

## 失败留痕与夹具限制

最初Git配置的6468代理连接失败；本次命令临时使用系统已有7897代理后fetch/push成功，未改全局代理或关闭证书校验。

推荐首次运行在干净90a69c上Chrome7组通过、Edge未完成；退出时临时库PermissionError遮蔽最初异常，因此不能确诊Edge第一处失败。原[失败报告](evidence/postmerge-20261019/preflight/recommendation-browsers/browser-results.json)、[控制台](evidence/postmerge-20261019/preflight/recommendation-console.txt)及诊断截图保留。核对发现旧005浏览器夹具以非TESTING应用启动新增评测扫描器，且使用多线程WSGI。夹具改为TESTING=True以停用无关扫描器，并采用既有验证使用的单线程WSGI；补异常因果链位置留痕后，干净d8509d6双浏览器各7组通过。该结果不证明生产扫描器关闭、并发/吞吐或隔离验收通过，原失败也不以未保留的响应猜测成特定业务缺陷。

辅助检查曾有一次PowerShell内嵌引号解析失败、一处Ruff re.M别名提示，以及链接检查器将合法目录误判为非文件，均在正式材料检查前修正；它们不是业务用例失败。完整后端原日志中的ResourceWarning保留，不改写成无警告。最终[材料检查](evidence/postmerge-20261019/material-checks.json)按每批最多3份文档核对链接、131行/31项AC、业务源码无差异及脱敏；[文件SHA清单](evidence/postmerge-20261019/sha256.json)可校验本包附件。

## 剩余工作与恢复条件

50条阻断由42条共通/环境（每SPEC的R22/R45/R47、NF-PERF/DATA/ISOLATION）和8条页面/完整角色链组成。逐项编号仍以唯一矩阵为准，数量不表示课程完成率。

| 后续项 | 负责人/触发条件 |
|---|---|
| 005图文知识 | 黄俊诚与石佰合先冻结PNG/JPEG、同课引用、当前权限/撤权、事件重试及APIC/DBD契约，再实现；本包不放开图片/外部URL |
| 004/007及017/010C页面 | 罗浩铭按现分工提供可操作入口；黄俊诚再复验本人008/010B消费及完整I-01/I-03适用节点。静态注册与运行时标题核对见[页面清单](evidence/postmerge-20261019/ui-inventory.json) |
| 018真实引擎和隔离 | 石佰合完成固定JAR、真实电路、worker与权限隔离；本包的夹具停用扫描器不能充作证明 |
| 目标性能、生产同点恢复、90天治理 | 组长协调目标环境，成员按本人API参与；普通测试/SQLite副本不能替代 |
| R47、Gitea、教师与报告模板 | 实际非作者/教师及组长提供逐项复核、固定tag/SHA和检查记录；Word仍是原准备稿，不凭本包定稿或发布 |

## 复现与回退

从包含本包脚本的feature运行，使用临时库；每个浏览器命令顺序执行，需空闲5000/5173及本机Chrome/Edge。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.verify_r37_handlers --output logs/recheck/r37
.\.venv\Scripts\python.exe -m scripts.verify_i01_handlers --output logs/recheck/i01
.\.venv\Scripts\python.exe -m scripts.verify_i03_handlers --output logs/recheck/i03
.\.venv\Scripts\python.exe -m scripts.verify_r37_browsers --output logs/recheck/r37-ui
.\.venv\Scripts\python.exe -m scripts.verify_i03_browsers --output logs/recheck/i03-ui
.\.venv\Scripts\python.exe -m scripts.verify_spec011_qa --output logs/recheck/qa-ui
.\.venv\Scripts\python.exe -m scripts.verify_spec012_browsers --output logs/recheck/recommendation-ui
.\.venv\Scripts\python.exe -m scripts.reconcile_postmerge_acceptance
```

最后一条只校验本次固定证据对应的矩阵和历史保全，不运行业务或批准状态；需要重新生成同一固定收口时用--write，不能拿它替新基线自动改判。

回退仅撤销本包脚本、状态/导航和证据增量，不回滚#38修复，不修改数据库、旧事实、迁移或队友实现。本包最终head CI及PR在实际完成后独立读取并登记到PR与本地交接；未授权代合并、部署或归档。
