"""SPEC-015 知识图谱：先修关系、环检测与可达路径。"""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.models.knowledge import KnowledgeError, KnowledgeStore
from backend.models.knowledge_migration import CHECKSUM, VERSION, apply


class KnowledgeGraphTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name) / "fixture.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE user(id INTEGER PRIMARY KEY,role TEXT,active INTEGER);
                CREATE TABLE course(id INTEGER PRIMARY KEY,teacher_id INTEGER,chapters_revision INTEGER DEFAULT 0);
                CREATE TABLE course_member(course_id INTEGER,user_id INTEGER,member_role TEXT,active INTEGER);
                CREATE TABLE schema_migration(version TEXT PRIMARY KEY,checksum TEXT,applied_at TEXT);
                INSERT INTO user VALUES(1,'teacher',1),(2,'student',1),(3,'student',1);
                INSERT INTO course(id,teacher_id) VALUES(1,1);
                INSERT INTO course_member VALUES(1,1,'teacher',1),(1,2,'student',1),(1,3,'student',1);
            """)
            db.execute("BEGIN IMMEDIATE")
            apply(db)
            db.execute("INSERT INTO schema_migration VALUES(?,?,?)", (VERSION, CHECKSUM, "2026-10-13T00:00:00Z"))
            db.executescript("""
                CREATE TABLE knowledge_edge (
                    id INTEGER PRIMARY KEY,
                    source_id INTEGER NOT NULL REFERENCES knowledge_point(id),
                    target_id INTEGER NOT NULL REFERENCES knowledge_point(id),
                    type TEXT NOT NULL CHECK(type IN ('prerequisite','contains')),
                    created_at TEXT NOT NULL,
                    UNIQUE(source_id, target_id, type),
                    CHECK(source_id <> target_id)
                );
            """)
        self.store = KnowledgeStore(self.path)
        self.chapter = self.store.add_chapter(1, 1, {"title": "CPU"})["id"]
        # 知识点：1=ALU, 2=寄存器, 3=加法器, 4=CPU
        self.alu = self._create("ALU", True)
        self.reg = self._create("寄存器", True)
        self.adder = self._create("加法器", True)
        self.cpu = self._create("CPU", True)

    def tearDown(self):
        self.temporary.cleanup()

    def _create(self, title, published):
        return self.store.save_knowledge(1, self.chapter, {
            "title": title, "content": f"<p>{title}</p>", "example": "",
            "published": published, "is_foundational": False,
        }, True)["id"]

    def test_add_prerequisite_edge(self):
        edge = self.store.add_edge(1, 1, {"source_id": self.reg, "target_id": self.alu, "type": "prerequisite"})
        self.assertEqual(edge["source_id"], self.reg)
        self.assertEqual(edge["target_id"], self.alu)
        self.assertEqual(edge["type"], "prerequisite")

    def test_self_loop_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.alu, "type": "prerequisite"})

    def test_prerequisite_cycle_rejected(self):
        # 加法器 -> ALU 先修
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.alu, "type": "prerequisite"})
        # ALU -> 加法器 会形成环
        with self.assertRaises(KnowledgeError) as ctx:
            self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.adder, "type": "prerequisite"})
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "PREREQUISITE_CYCLE")

    def test_longer_cycle_rejected(self):
        # 加法器 -> 寄存器 -> ALU
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.reg, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.reg, "target_id": self.alu, "type": "prerequisite"})
        # ALU -> 加法器 形成 3 环
        with self.assertRaises(KnowledgeError) as ctx:
            self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.adder, "type": "prerequisite"})
        self.assertEqual(ctx.exception.code, "PREREQUISITE_CYCLE")

    def test_contains_edge_no_cycle_check(self):
        # contains 类型不做环检测
        self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.adder, "type": "contains"})
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.alu, "type": "contains"})

    def test_graph_returns_nodes_edges_and_paths(self):
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.alu, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.reg, "target_id": self.alu, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.cpu, "type": "contains"})
        graph = self.store.knowledge_graph(1, 1)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertEqual(node_ids, {self.alu, self.reg, self.adder, self.cpu})
        edge_types = {(e["source"], e["target"], e["type"]) for e in graph["edges"]}
        self.assertIn((self.adder, self.alu, "prerequisite"), edge_types)
        self.assertIn((self.alu, self.cpu, "contains"), edge_types)
        # 先修可达：加法器->ALU, 寄存器->ALU
        paths = {(p["from"], p["to"]) for p in graph["prerequisite_paths"]}
        self.assertIn((self.adder, self.alu), paths)
        self.assertIn((self.reg, self.alu), paths)

    def test_transitive_reachability(self):
        # 加法器 -> 寄存器 -> ALU
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.reg, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.reg, "target_id": self.alu, "type": "prerequisite"})
        graph = self.store.knowledge_graph(1, 1)
        paths = {(p["from"], p["to"]) for p in graph["prerequisite_paths"]}
        # 直接路径
        self.assertIn((self.adder, self.reg), paths)
        self.assertIn((self.reg, self.alu), paths)
        # 传递路径：加法器 -> ALU
        self.assertIn((self.adder, self.alu), paths)

    def test_root_id_filters_subgraph(self):
        self.store.add_edge(1, 1, {"source_id": self.adder, "target_id": self.alu, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.reg, "target_id": self.alu, "type": "prerequisite"})
        self.store.add_edge(1, 1, {"source_id": self.alu, "target_id": self.cpu, "type": "contains"})
        # 以 ALU 为根：应包含 ALU、加法器、寄存器（先修），但不含 CPU（contains 不算先修路径）
        graph = self.store.knowledge_graph(1, 1, root_id=self.alu)
        related_ids = {n["id"] for n in graph["nodes"]}
        self.assertEqual(related_ids, {self.alu, self.adder, self.reg})

    def test_mastery_from_real_progress(self):
        # 学生 2 完成 ALU
        self.store.personal_state(2, self.alu, {"completed": True}, "progress")
        graph = self.store.knowledge_graph(2, 1)
        alu_node = next(n for n in graph["nodes"] if n["id"] == self.alu)
        self.assertEqual(alu_node["mastery"], 1.0)
        reg_node = next(n for n in graph["nodes"] if n["id"] == self.reg)
        self.assertEqual(reg_node["mastery"], 0.0)

    def test_student_sees_only_published(self):
        draft = self._create("草稿", False)
        self.store.add_edge(1, 1, {"source_id": draft, "target_id": self.alu, "type": "prerequisite"})
        graph = self.store.knowledge_graph(2, 1)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertNotIn(draft, node_ids)
        self.assertIn(self.alu, node_ids)
