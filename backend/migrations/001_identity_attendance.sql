CREATE TABLE user (
  id INTEGER PRIMARY KEY, student_no TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('student','teacher','admin')),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), session_version INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE session (
  id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES user(id),
  csrf_hash TEXT NOT NULL, session_version INTEGER NOT NULL,
  expires_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX session_expiry ON session(expires_at);
CREATE TABLE course (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT,
  chapters_revision INTEGER NOT NULL DEFAULT 0, teacher_id INTEGER NOT NULL REFERENCES user(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE course_member (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES course(id),
  user_id INTEGER NOT NULL REFERENCES user(id),
  member_role TEXT NOT NULL CHECK(member_role IN ('student','teacher')),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(course_id,user_id)
);
CREATE INDEX member_user_active ON course_member(user_id,active);
CREATE TABLE notification (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id),
  course_id INTEGER NOT NULL REFERENCES course(id), title TEXT NOT NULL,
  target_type TEXT NOT NULL, target_id INTEGER NOT NULL, read_at TEXT,
  event_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,event_key)
);
CREATE TABLE audit_event (
  id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES user(id), action TEXT NOT NULL,
  object_type TEXT NOT NULL, object_id INTEGER, request_id TEXT NOT NULL,
  before_summary TEXT, after_summary TEXT, created_at TEXT NOT NULL
);
CREATE TABLE rate_event (
  id INTEGER PRIMARY KEY, key_hash TEXT NOT NULL, at TEXT NOT NULL
);
CREATE INDEX rate_event_key_at ON rate_event(key_hash,at);
CREATE TABLE attendance_task (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES course(id), title TEXT NOT NULL,
  start_at TEXT NOT NULL, late_at TEXT NOT NULL, end_at TEXT NOT NULL,
  code_hash TEXT NOT NULL, code_expires_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','closed')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK(start_at <= late_at AND late_at <= end_at AND start_at < end_at)
);
CREATE INDEX attendance_task_course_start ON attendance_task(course_id,start_at);
CREATE TABLE attendance_participant (
  task_id INTEGER NOT NULL REFERENCES attendance_task(id),
  student_id INTEGER NOT NULL REFERENCES user(id), PRIMARY KEY(task_id,student_id)
);
CREATE TABLE attendance_record (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('present','late','leave','absent')),
  checked_at TEXT, source TEXT NOT NULL CHECK(source IN ('checkin','approval','close','correction')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(task_id,student_id),
  FOREIGN KEY(task_id,student_id) REFERENCES attendance_participant(task_id,student_id)
);
CREATE TABLE leave_request (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  reason TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
  reviewer_id INTEGER REFERENCES user(id), review_note TEXT, reviewed_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(task_id,student_id),
  FOREIGN KEY(task_id,student_id) REFERENCES attendance_participant(task_id,student_id)
);
CREATE TABLE leave_review_event (
  id INTEGER PRIMARY KEY, leave_id INTEGER NOT NULL REFERENCES leave_request(id),
  actor_id INTEGER NOT NULL REFERENCES user(id), old_status TEXT NOT NULL,
  new_status TEXT NOT NULL, note TEXT, reason_snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE analysis_run (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES course(id),
  creator_id INTEGER NOT NULL REFERENCES user(id), scope TEXT NOT NULL,
  subject_student_id INTEGER REFERENCES user(id), kind TEXT NOT NULL,
  algorithm_version TEXT NOT NULL, parameters_json TEXT NOT NULL,
  source_until TEXT NOT NULL, generated_at TEXT NOT NULL,
  sample_size INTEGER NOT NULL CHECK(sample_size >= 0), result_json TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL, model_status TEXT, model_parameters_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX analysis_course_creator ON analysis_run(course_id,creator_id,kind);
CREATE TABLE warning (
  id INTEGER PRIMARY KEY, analysis_run_id INTEGER NOT NULL REFERENCES analysis_run(id),
  student_id INTEGER NOT NULL REFERENCES user(id), reasons_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','handled')),
  handled_by INTEGER REFERENCES user(id), note TEXT, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, UNIQUE(analysis_run_id,student_id)
);
CREATE TABLE file_object (
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES user(id),
  storage_key TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
  media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  sha256 TEXT NOT NULL, purpose TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE recognition (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES course(id),
  user_id INTEGER NOT NULL REFERENCES user(id), image_file_id INTEGER NOT NULL REFERENCES file_object(id),
  status TEXT NOT NULL CHECK(status IN ('recognized','unrecognized','confirmed')),
  items_json TEXT NOT NULL, confirmed_items_json TEXT,
  algorithm_version TEXT NOT NULL, template_set_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
