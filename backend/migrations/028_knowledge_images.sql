-- SPEC-005 知识点图片：固定资源版本引用，不保存 URL 或任意 HTML。
-- resource_version 的宽高只对图片版本有值，旧版本保持 NULL。

ALTER TABLE resource_version ADD COLUMN width INTEGER;
ALTER TABLE resource_version ADD COLUMN height INTEGER;

CREATE TABLE knowledge_image (
    id INTEGER PRIMARY KEY,
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    resource_version_id INTEGER NOT NULL REFERENCES resource_version(id),
    placement TEXT NOT NULL CHECK(placement IN ('content','example')),
    position INTEGER NOT NULL CHECK(position >= 0),
    alt TEXT NOT NULL DEFAULT '' CHECK(length(alt) <= 200),
    caption TEXT NOT NULL DEFAULT '' CHECK(length(caption) <= 200),
    created_at TEXT NOT NULL,
    UNIQUE(knowledge_id, placement, position)
);
CREATE INDEX knowledge_image_knowledge
    ON knowledge_image(knowledge_id, placement, position);
