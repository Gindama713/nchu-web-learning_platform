"""把个人设计报告 Markdown 转成与组内其他报告一致的 docx 版式。"""
import argparse
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source")
parser.add_argument("destination")
parser.add_argument("--cover-title", help="封面标题；不传时保留原版式")
parser.add_argument("--cover-info", action="append", default=[], help="封面信息，可重复")
parser.add_argument("--toc", action="store_true", help="插入 Word 目录域")
parser.add_argument("--page-numbers", action="store_true", help="页脚页码，封面不显示")
args = parser.parse_args()
SRC, DST = args.source, args.destination
FONT = "Microsoft YaHei"
BODY_PT = 10.5


def set_run_font(run, size=BODY_PT, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def add_inline(paragraph, text):
    """处理 **粗体**、`代码`、[文字](链接)，链接只保留文字。"""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    for piece in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            set_run_font(paragraph.add_run(piece[2:-2]), bold=True)
        elif piece.startswith("`") and piece.endswith("`"):
            run = paragraph.add_run(piece[1:-1])
            set_run_font(run)
            run.font.name = "Consolas"
        else:
            set_run_font(paragraph.add_run(piece))


def body(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(21)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.35
    add_inline(p, text)


def heading(doc, text, level):
    p = doc.add_heading(level=level)
    p.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    set_run_font(run, size=15 if level == 1 else 12.5, bold=True)
    run.font.color.rgb = RGBColor(0, 0, 0)


def table(doc, rows):
    header, body_rows = rows[0], rows[1:]
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, cell_text in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        add_inline(cell.paragraphs[0], f"**{cell_text}**")
    for row in body_rows:
        cells = t.add_row().cells
        for i, cell_text in enumerate(row[: len(header)]):
            cells[i].text = ""
            add_inline(cells[i].paragraphs[0], cell_text)
    doc.add_paragraph()


doc = Document()
section = doc.sections[0]
section.left_margin = section.right_margin = Cm(2.23)
section.top_margin, section.bottom_margin = Cm(2.16), Cm(1.91)
section.page_width, section.page_height = Cm(21), Cm(29.7)
for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
    doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)


def field(paragraph, instruction, placeholder=""):
    # TOC 更新后跨多个段落，须用复杂域，不能限制在 fldSimple 内。
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    paragraph.add_run()._r.append(begin)
    code = OxmlElement("w:instrText")
    code.set(qn("xml:space"), "preserve")
    code.text = instruction
    paragraph.add_run()._r.append(code)
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    paragraph.add_run()._r.append(separate)
    set_run_font(paragraph.add_run(placeholder))
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(end)


if args.cover_title:
    section.different_first_page_header_footer = True
    p = doc.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(110)
    p.paragraph_format.space_after = Pt(48)
    set_run_font(p.add_run(args.cover_title), size=24, bold=True)
    for info in args.cover_info:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.add_run(info), size=12)
    doc.add_page_break()
if args.toc:
    p = doc.add_paragraph(style="Title")
    set_run_font(p.add_run("目录"), size=20, bold=True)
    field(doc.add_paragraph(), ' TOC \\o "1-3" \\h \\z \\u ', "打开 Word 后全选并按 F9 更新目录")
    setting = OxmlElement("w:updateFields")
    setting.set(qn("w:val"), "true")
    doc.settings.element.append(setting)
    doc.add_page_break()
if args.page_numbers:
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field(p, " PAGE ", "1")

normal = doc.styles["Normal"]
normal.font.name = FONT
normal.font.size = Pt(BODY_PT)
normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

with open(SRC, encoding="utf-8") as _f:
    lines = _f.read().splitlines()
i = 0
pending_rows = []


def flush_table():
    global pending_rows
    if pending_rows:
        table(doc, pending_rows)
        pending_rows = []


while i < len(lines):
    line = lines[i].rstrip()
    if line.startswith("|"):
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            pending_rows.append(cells)
        i += 1
        continue
    flush_table()
    if not line:
        i += 1
        continue
    if line.startswith("# "):
        p = doc.add_paragraph(style="Title")
        set_run_font(p.add_run(line[2:]), size=20, bold=True)
    elif line.startswith("## "):
        heading(doc, line[3:], 1)
    elif line.startswith("### "):
        heading(doc, line[4:], 2)
    elif re.match(r"^\d+\.\s", line):
        body(doc, line)
    elif line.startswith("- "):
        p = doc.add_paragraph(style="List Bullet")
        add_inline(p, line[2:])
    else:
        body(doc, line)
    i += 1

flush_table()
doc.save(DST)
print("已生成", DST)
