-- SPEC-015 知识图谱：知识点先修/包含关系。
-- type: prerequisite（先修）或 contains（包含）。source≠target，先修环由事务内图算法拒绝。

CREATE TABLE knowledge_edge (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    target_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    type TEXT NOT NULL CHECK(type IN ('prerequisite','contains')),
    created_at TEXT NOT NULL,
    UNIQUE(source_id, target_id, type),
    CHECK(source_id <> target_id)
);
CREATE INDEX knowledge_edge_source ON knowledge_edge(source_id, type);
CREATE INDEX knowledge_edge_target ON knowledge_edge(target_id, type);
