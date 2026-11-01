-- C08 immutable algorithm evidence. C09 will add paper linkage in its own migration.
CREATE TABLE generation_snapshot (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    seed INTEGER NOT NULL CHECK(typeof(seed)='integer'),
    algorithm_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL CHECK(json_valid(parameters_json) AND json_type(parameters_json)='object'),
    candidates_json TEXT NOT NULL CHECK(json_valid(candidates_json) AND json_type(candidates_json)='array'
        AND json_array_length(candidates_json)<=500),
    history_json TEXT NOT NULL CHECK(json_valid(history_json) AND json_type(history_json)='array'),
    source_until TEXT NOT NULL,
    input_sha256 TEXT NOT NULL CHECK(length(input_sha256)=64),
    selected_ids_json TEXT NOT NULL CHECK(json_valid(selected_ids_json) AND json_type(selected_ids_json)='array'
        AND json_array_length(selected_ids_json) BETWEEN 1 AND 100)
);
CREATE INDEX generation_snapshot_course ON generation_snapshot(course_id,id);

CREATE TRIGGER generation_snapshot_version_guard BEFORE INSERT ON generation_snapshot
WHEN EXISTS (
    SELECT 1 FROM json_each(NEW.candidates_json) candidate WHERE NOT EXISTS (
        SELECT 1 FROM question_version v JOIN question q ON q.id=v.question_id
        WHERE v.id=json_extract(candidate.value,'$.version_id')
            AND q.id=json_extract(candidate.value,'$.question_id') AND q.course_id=NEW.course_id))
    OR EXISTS (
        SELECT 1 FROM json_each(NEW.selected_ids_json) selected WHERE NOT EXISTS (
            SELECT 1 FROM json_each(NEW.candidates_json) candidate
            WHERE json_extract(candidate.value,'$.version_id')=selected.value))
BEGIN SELECT RAISE(ABORT,'snapshot versions must be same-course candidates'); END;
CREATE TRIGGER generation_snapshot_no_update BEFORE UPDATE ON generation_snapshot
BEGIN SELECT RAISE(ABORT,'generation snapshots are immutable'); END;
CREATE TRIGGER generation_snapshot_no_delete BEFORE DELETE ON generation_snapshot
BEGIN SELECT RAISE(ABORT,'generation snapshots are retained'); END;
