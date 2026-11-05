"""把个人设计报告 Markdown 转成与组内其他报告一致的 docx 版式。"""
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

SRC, DST = sys.argv[1], sys.argv[2]
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
    run.font.color.rgb = None


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
section.page_width, section.page_height = Cm(21.59), Cm(27.94)
section.left_margin = section.right_margin = Cm(2.23)
section.top_margin, section.bottom_margin = Cm(2.16), Cm(1.91)

normal = doc.styles["Normal"]
normal.font.name = FONT
normal.font.size = Pt(BODY_PT)
normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

lines = open(SRC, encoding="utf-8").read().splitlines()
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
