-- seed/algorithm_version already exist in 006b; append only the snapshot FK.
ALTER TABLE paper ADD COLUMN generation_snapshot_id INTEGER REFERENCES generation_snapshot(id);
CREATE INDEX paper_generation_snapshot ON paper(generation_snapshot_id);
CREATE TRIGGER paper_generation_insert_guard BEFORE INSERT ON paper
WHEN NEW.generation_snapshot_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM generation_snapshot s WHERE s.id=NEW.generation_snapshot_id
    AND s.course_id=NEW.course_id AND s.seed=NEW.seed AND s.algorithm_version=NEW.algorithm_version
    AND json_extract(s.parameters_json,'$.kind')=NEW.kind
    AND json_extract(s.parameters_json,'$.confidential')=NEW.confidential)
BEGIN SELECT RAISE(ABORT,'generation snapshot must match paper'); END;
-- Also covers the quiz review exception in the original published-paper guard.
CREATE TRIGGER paper_generation_frozen BEFORE UPDATE ON paper
WHEN NEW.generation_snapshot_id IS NOT OLD.generation_snapshot_id
    OR ((OLD.generation_snapshot_id IS NOT NULL) AND (
        NEW.course_id IS NOT OLD.course_id OR NEW.seed IS NOT OLD.seed
        OR NEW.algorithm_version IS NOT OLD.algorithm_version OR NEW.kind IS NOT OLD.kind
        OR NEW.confidential IS NOT OLD.confidential))
BEGIN SELECT RAISE(ABORT,'generation provenance is immutable'); END;
