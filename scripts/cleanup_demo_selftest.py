"""清理演示库里由自测/压测脚本创建的点到任务，恢复课堂演示的干净数据。

只删除 title 以「自测-g24201710-」或「压测-g24201710-」开头的任务，
以及这些任务在 attendance_record / attendance_seat / attendance_participant /
leave_request 中的关联行。正式任务与历史数据一律不动。

用法：
    # 只看会删什么，不写库
    python scripts/cleanup_demo_selftest.py --db D:/Desktop/WebBigHomework/wt-demo/instance/app.db

    # 备份并真正清理
    python scripts/cleanup_demo_selftest.py --db <同路径> --apply
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PREFIXES = ("自测-g24201710-%", "压测-g24201710-%")
CHILD_TABLES = ("attendance_record", "attendance_seat",
                "attendance_participant", "leave_request")


def main(argv=None):
    parser = argparse.ArgumentParser(description="清理演示库中的自测/压测点到数据")
    parser.add_argument("--db", required=True, help="演示库绝对路径")
    parser.add_argument("--apply", action="store_true", help="真正写入；默认只演练")
    parser.add_argument("--no-backup", action="store_true", help="跳过备份（不推荐）")
    args = parser.parse_args(argv)

    path = Path(args.db)
    if not path.is_file():
        print(f"数据库不存在：{path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        cond = " OR ".join("title LIKE ?" for _ in PREFIXES)
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM attendance_task WHERE " + cond, PREFIXES)]
        print(f"命中自测/压测任务 {len(ids)} 条，id={ids[:8]}{'…' if len(ids) > 8 else ''}")
        if not ids:
            print("无需清理。")
            return 0

        placeholders = ",".join("?" for _ in ids)
        before_tasks = conn.execute("SELECT COUNT(*) FROM attendance_task").fetchone()[0]
        before_records = conn.execute("SELECT COUNT(*) FROM attendance_record").fetchone()[0]

        if args.apply and not args.no_backup:
            backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(path, backup)
            print(f"备份 -> {backup} ({backup.stat().st_size} 字节)")

        conn.execute("BEGIN IMMEDIATE")
        for table in CHILD_TABLES:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "task_id" not in cols:
                continue
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE task_id IN ({placeholders})",
                ids).fetchone()[0]
            if count:
                conn.execute(f"DELETE FROM {table} WHERE task_id IN ({placeholders})", ids)
            print(f"  {table}: 删除 {count} 行")

        removed = conn.execute(
            f"DELETE FROM attendance_task WHERE id IN ({placeholders})", ids).rowcount
        print(f"  attendance_task: 删除 {removed} 行")

        if args.apply:
            conn.commit()
            print("已提交。")
        else:
            conn.rollback()
            print("演练模式：已回滚，未写库。加 --apply 才会真正清理。")
            return 0

        after_tasks = conn.execute("SELECT COUNT(*) FROM attendance_task").fetchone()[0]
        after_records = conn.execute("SELECT COUNT(*) FROM attendance_record").fetchone()[0]
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM attendance_task WHERE " + cond, PREFIXES).fetchone()[0]
        print(f"任务 {before_tasks} -> {after_tasks}；签到记录 {before_records} -> {after_records}")
        print(f"残留自测任务 {remaining} 条；外键违规 {len(violations)} 条")
        if violations[:3]:
            print("外键违规样例：", [tuple(v) for v in violations[:3]])
        return 0 if remaining == 0 and not violations else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
