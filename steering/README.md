# 全局设计导航（steering）

老师给出的 `steering` 四项在此集中阅读；课程任务书指定的六份主文档仍保留原路径，避免更改 Gitea 提交入口和现有引用。此目录是导航与决策摘要，字段、验收、迁移及发布规则的规范正文仍以主文档为准。

| 主题 | 导航 | 规范正文 |
|---|---|---|
| 产品与必做范围 | [product](product.md) | [PRD](../docs/PRD.md) |
| 数据库与生命周期 | [database](database.md) | [DBD](../docs/DBD.md) |
| 架构与交付 | [architecture](architecture.md) | [ADR](../docs/ADR.md)、[CHG-RB](../docs/CHG-RB.md) |
| HTTP 契约 | [api-contract](api-contract.md) | [APIC](../docs/APIC.md) |

逐模块计划、规格、任务及界面设计见 [specs](../specs/README.md)。需求或接口改变时，在同一 PR 更新主文档和受影响的摘要，再跑 `python scripts/check_docs.py`。
