"""按任务书生成超星提交物；默认只生成名单和报告，--include-source 才打源码包。"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def submission_prefix(class_name, group):
    if not class_name or any(c in class_name for c in '<>:"/\\|?*'):
        raise ValueError("班级不能为空或含文件名禁用字符")
    if not group.isdecimal() or int(group) < 1:
        raise ValueError("组号必须为正整数")
    return f"{class_name.removesuffix('班')}班_第{int(group)}组"


def source_files(root):
    # 只归档版本控制跟踪的交付文件；不收本地截图、数据库、凭据或临时目录。
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    excluded = {".git", ".venv", "node_modules", "instance", "uploads", "logs",
                "test-tmp", "grader-work", "backups", "__pycache__", "dist"}
    for name in raw.decode("utf-8").split("\0"):
        if not name:
            continue
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or excluded.intersection(path.parts)
                or any(part.startswith(".env") for part in path.parts)
                or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".log", ".pyc"}):
            continue
        candidate = root / path
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"归档文件不存在或为符号链接：{name}")
        if not candidate.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"归档路径越界：{name}")
        yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-name", default="242017")
    parser.add_argument("--group", default="10")
    parser.add_argument("--output", type=Path, required=True, help="新建的输出目录，不覆盖现有文件")
    parser.add_argument("--include-source", action="store_true")
    parser.add_argument("--report-docx", type=Path, help="使用已更新目录并逐页检查的 Word 成稿")
    args = parser.parse_args()
    prefix = submission_prefix(args.class_name, args.group)
    output = args.output.resolve()
    if output.exists():
        parser.error("输出目录已存在，请使用新目录以保留旧交付物")
    report = ROOT / "docs/reports/g24201710_小组大作业报告.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "submission"
        stage.mkdir()
        shutil.copyfile(ROOT / "成员名单.txt", stage / f"{prefix}_成员名单.txt")
        if args.report_docx:
            shutil.copyfile(args.report_docx, stage / f"{prefix}_大作业报告.docx")
        else:
            subprocess.run([
            sys.executable, str(ROOT / "scripts/md2docx_report.py"), str(report),
            str(stage / f"{prefix}_大作业报告.docx"),
            "--cover-title", "计算机组成原理课程学习系统小组大作业报告",
            "--cover-info", "课程：Web 高级编程",
            "--cover-info", f"班级：{args.class_name.removesuffix('班')}　组号：第{int(args.group)}组",
            "--cover-info", "组长：姜苏豪 24201718",
            "--cover-info", "成员：黄俊诚 24201716　罗浩铭 24201723　石佰合 24201737",
            "--cover-info", "完成时间：2026 年 11 月", "--toc", "--page-numbers",
            ], check=True)
        if args.include_source:
            if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
                parser.error("源码包须从干净提交生成，请先提交并核验文件清单")
            with zipfile.ZipFile(stage / f"{prefix}_大作业源码及设计文件.zip", "w",
                                 zipfile.ZIP_DEFLATED) as archive:
                for path in source_files(ROOT):
                    archive.write(ROOT / path, path.as_posix())
        manifest = {"source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_included": args.include_source,
            "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir()}}
        (stage / "核对清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        # copytree 让交付目录继承目标 ACL，不继承 Windows 临时目录的私有权限。
        shutil.copytree(stage, output)
    print(f"已生成：{output}")
    print("人工核对：班级写法、Word 目录与排版、截图脱敏、个人确认、Gitea 各 ref SHA、超星上传回执。")
    if not args.include_source:
        print("源码包未生成；提交定稿后使用 --include-source。")


if __name__ == "__main__":
    main()
