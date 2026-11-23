"""校验提交物命名、摘要和 Word 域；不将机器检查冒充脱敏或课堂验收。"""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.package_submission import submission_prefix


def check(directory, prefix, require_source=False):
    errors = []
    names = [f"{prefix}_成员名单.txt", f"{prefix}_大作业报告.docx"]
    if require_source:
        names.append(f"{prefix}_大作业源码及设计文件.zip")
    for name in names:
        if not (directory / name).is_file():
            errors.append(f"缺少：{name}")
    try:
        manifest = json.loads((directory / "核对清单.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files"].items():
            path = directory / name
            if path.parent != directory or not path.is_file():
                errors.append(f"清单文件无效：{name}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                errors.append(f"摘要不一致：{name}")
        if require_source and not manifest["source_included"]:
            errors.append("清单未包含源码包")
    except (OSError, ValueError, KeyError) as error:
        errors.append(f"清单不可用：{error}")
    report = directory / names[1]
    if report.is_file():
        try:
            with zipfile.ZipFile(report) as archive:
                if archive.testzip():
                    errors.append("DOCX ZIP 完整性检查失败")
                document = ET.fromstring(archive.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                fields = [e.get(f"{{{ns['w']}}}instr", "") for e in document.findall(".//w:fldSimple", ns)]
                fields += [e.text or "" for e in document.findall(".//w:instrText", ns)]
                if not any("TOC " in value for value in fields):
                    errors.append("报告缺少 TOC 目录域")
                footers = b"".join(archive.read(n) for n in archive.namelist()
                                   if n.startswith("word/footer") and n.endswith(".xml"))
                if b"PAGE" not in footers:
                    errors.append("报告缺少 PAGE 页码域")
                if "计算机组成原理" not in "".join(document.itertext()):
                    errors.append("报告缺少项目标题")
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
            errors.append(f"DOCX 不可用：{error}")
    source = directory / f"{prefix}_大作业源码及设计文件.zip"
    if source.is_file():
        try:
            with zipfile.ZipFile(source) as archive:
                if archive.testzip():
                    errors.append("源码 ZIP 完整性检查失败")
                for name in archive.namelist():
                    path = Path(name)
                    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
                        errors.append(f"源码 ZIP 路径无效：{name}")
        except (OSError, zipfile.BadZipFile) as error:
            errors.append(f"源码 ZIP 不可用：{error}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--class-name", default="242017")
    parser.add_argument("--group", default="10")
    parser.add_argument("--require-source", action="store_true")
    args = parser.parse_args()
    errors = check(args.directory.resolve(), submission_prefix(args.class_name, args.group), args.require_source)
    print("\n".join(errors) if errors else "提交物命名、摘要、目录与页码结构：OK")
    print("截图打码、Word 更新目录后的排版、个人确认和外部提交回执：需人工核验。")
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
