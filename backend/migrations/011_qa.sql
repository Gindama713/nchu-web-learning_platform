CREATE TABLE qa_index (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL UNIQUE REFERENCES course(id),
    corpus_revision TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    built_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ready','failed')),
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((status='ready' AND error_code IS NULL) OR
          (status='failed' AND error_code='INDEX_UNAVAILABLE'))
);

CREATE TABLE qa_query (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    course_id INTEGER NOT NULL REFERENCES course(id),
    question TEXT NOT NULL CHECK(length(question) BETWEEN 1 AND 500),
    matched_ids_json TEXT NOT NULL CHECK(json_valid(matched_ids_json)),
    similarities_json TEXT NOT NULL CHECK(json_valid(similarities_json)),
    index_revision TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX qa_query_owner_course ON qa_query(user_id,course_id,id);
