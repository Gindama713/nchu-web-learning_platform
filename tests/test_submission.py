"""交付打包边界：命名、排除本地数据、摘要篡改与必需源码。"""

import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

from scripts.package_submission import source_files, submission_prefix
from scripts.verify_submission import check


class SubmissionTest(TestCase):
    def test_names_archive_scope_and_tampering(self):
        self.assertEqual(submission_prefix("242017班", "010"), "242017班_第10组")
        for class_name, group in (("../bad", "10"), ("242017", "0"), ("242017", "x")):
            with self.assertRaises(ValueError):
                submission_prefix(class_name, group)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in ("README.md", ".env", "student.db", "untracked.txt"):
                (root / name).write_text("sample", encoding="utf-8")
            subprocess.run(["git", "add", "README.md", ".env", "student.db"], cwd=root, check=True)
            self.assertEqual(list(source_files(root)), [Path("README.md")])
            prefix = submission_prefix("242017", "10")
            roster = root / f"{prefix}_成员名单.txt"
            roster.write_text("成员", encoding="utf-8")
            report = root / f"{prefix}_大作业报告.docx"
            with zipfile.ZipFile(report, "w") as archive:
                archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:fldSimple w:instr=" TOC "/><w:t>计算机组成原理</w:t></w:document>')
                archive.writestr("word/footer1.xml", '<field> PAGE </field>')
            manifest = {"source_included": False, "files": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (roster, report)}}
            (root / "核对清单.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(check(root, prefix), [])
            self.assertTrue(check(root, prefix, require_source=True))
            roster.write_text("篡改", encoding="utf-8")
            self.assertTrue(any("摘要不一致" in error for error in check(root, prefix)))
