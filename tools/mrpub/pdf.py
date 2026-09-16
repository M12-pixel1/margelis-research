"""Markdown -> PDF for Margelis Research Notes.

Output is byte-reproducible for identical inputs and pinned dependencies:
  * ReportLab invariant mode (fixed document ID derived from content),
  * SOURCE_DATE_EPOCH = publication date (fixed CreationDate/ModDate),
  * no stream compression (zlib implementations differ between platforms),
  * bundled fonts (tools/fonts, DejaVu 2.35), embedded as subsets.
"""
from __future__ import annotations

import html
import io
import os
from pathlib import Path

from markdown_it.tree import SyntaxTreeNode
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, HRFlowable,
                                KeepTogether, ListFlowable, ListItem, PageTemplate, Paragraph, Preformatted,
                                Spacer, Table, TableStyle)

from . import mdparse
from .common import FONTS, Note, epoch_of, human_date, slugify

INK = colors.HexColor("#1c2127")
MUTED = colors.HexColor("#5a626d")
ACCENT = colors.HexColor("#7a5418")
LINK = "#1f4f8f"
RULE = colors.HexColor("#d8d2c4")
PANEL = colors.HexColor("#f4f1ea")
HEAD_BG = colors.HexColor("#ebe5d8")

FONT_FILES = {
    "MR-Serif": "DejaVuSerif.ttf",
    "MR-Serif-Bold": "DejaVuSerif-Bold.ttf",
    "MR-Serif-Italic": "DejaVuSerif-Italic.ttf",
    "MR-Serif-BoldItalic": "DejaVuSerif-BoldItalic.ttf",
    "MR-Sans": "DejaVuSans.ttf",
    "MR-Sans-Bold": "DejaVuSans-Bold.ttf",
    "MR-Mono": "DejaVuSansMono.ttf",
}

PAGE_W, PAGE_H = A4
MARGIN_X = 22 * mm
MARGIN_TOP = 24 * mm
MARGIN_BOTTOM = 22 * mm


def register_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in FONT_FILES.items():
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, str(FONTS / filename)))
    for family, (n, b, i, bi) in {
        "MR-Serif": ("MR-Serif", "MR-Serif-Bold", "MR-Serif-Italic", "MR-Serif-BoldItalic"),
        "MR-Sans": ("MR-Sans", "MR-Sans-Bold", "MR-Sans", "MR-Sans-Bold"),
        "MR-Mono": ("MR-Mono", "MR-Mono", "MR-Mono", "MR-Mono"),
    }.items():
        addMapping(family, 0, 0, n)
        addMapping(family, 1, 0, b)
        addMapping(family, 0, 1, i)
        addMapping(family, 1, 1, bi)


def styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="MR-Serif", fontSize=9.8, leading=14.4, textColor=INK, splitLongWords=1)
    s = {
        "body": ParagraphStyle("body", spaceAfter=6.5, **base),
        "ref": ParagraphStyle("ref", spaceAfter=3.2, leftIndent=14, bulletIndent=0,
                              bulletFontName="MR-Sans", bulletFontSize=8.4, **base),
        "li": ParagraphStyle("li", spaceAfter=1.6, **base),
        "h2": ParagraphStyle("h2", fontName="MR-Sans-Bold", fontSize=12.4, leading=16, textColor=INK,
                             spaceBefore=15, spaceAfter=6.5),
        "h3": ParagraphStyle("h3", fontName="MR-Sans-Bold", fontSize=10.6, leading=14, textColor=INK,
                             spaceBefore=10, spaceAfter=4),
        "title": ParagraphStyle("title", fontName="MR-Sans-Bold", fontSize=23, leading=28, textColor=INK,
                                spaceAfter=5),
        "subtitle": ParagraphStyle("subtitle", fontName="MR-Serif-Italic", fontSize=13.4, leading=18,
                                   textColor=MUTED, spaceAfter=0),
        "author": ParagraphStyle("author", fontName="MR-Serif-Bold", fontSize=10.6, leading=14, textColor=INK),
        "affil": ParagraphStyle("affil", fontName="MR-Serif", fontSize=10, leading=13.5, textColor=INK),
        "label": ParagraphStyle("label", fontName="MR-Sans", fontSize=8.6, leading=12, textColor=MUTED),
        "box": ParagraphStyle("box", fontName="MR-Sans", fontSize=8.6, leading=12, textColor=INK),
        "th": ParagraphStyle("th", fontName="MR-Sans-Bold", fontSize=8.2, leading=11, textColor=INK),
        "td": ParagraphStyle("td", fontName="MR-Serif", fontSize=8.4, leading=11.2, textColor=INK,
                             splitLongWords=1),
        "code": ParagraphStyle("code", fontName="MR-Mono", fontSize=8.5, leading=12.2, textColor=INK),
    }
    s["ref"].bulletColor = ACCENT
    return s


# --------------------------------------------------------------------------- inline
def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline(node: SyntaxTreeNode) -> str:
    return "".join(_inline(child) for child in node.children)


def _inline(node: SyntaxTreeNode) -> str:
    t = node.type
    if t == "text":
        return _esc(node.content)
    if t == "softbreak":
        return " "
    if t == "hardbreak":
        return "<br/>"
    if t == "strong":
        return "<b>" + "".join(_inline(c) for c in node.children) + "</b>"
    if t == "em":
        return "<i>" + "".join(_inline(c) for c in node.children) + "</i>"
    if t == "code_inline":
        return f'<font face="MR-Mono" size="8.4">{_esc(node.content)}</font>'
    if t == "link":
        href = html.escape(str(node.attrs.get("href", "")), quote=True)
        inner = "".join(_inline(c) for c in node.children)
        return f'<a href="{href}" color="{LINK}">{inner}</a>'
    raise ValueError(f"unsupported inline element: {t}")


# --------------------------------------------------------------------------- blocks
class SpacedText(Flowable):
    """Single line of letter-spaced text (series kicker)."""

    def __init__(self, text: str, font: str, size: float, color, char_space: float = 1.6):
        super().__init__()
        self.text, self.font, self.size, self.color, self.char_space = text, font, size, color, char_space

    def wrap(self, avail_w, avail_h):
        return avail_w, self.size * 1.4

    def draw(self):
        t = self.canv.beginText(0, self.size * 0.35)
        t.setFont(self.font, self.size)
        t.setCharSpace(self.char_space)
        t.setFillColor(self.color)
        t.textOut(self.text)
        t.setCharSpace(0)
        self.canv.drawText(t)


def panel(flowables, width: float, pad: float = 9) -> Table:
    tbl = Table([[flowables]], colWidths=[width], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "MR-Sans"),
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), pad + 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad + 1),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]))
    return tbl


class Renderer:
    def __init__(self, width: float):
        self.width = width
        self.s = styles()

    def blocks(self, nodes) -> list:
        out = []
        nodes = list(nodes)
        for idx, node in enumerate(nodes):
            t = node.type
            if t == "heading":
                level = int(node.tag[1])
                text = inline(node.children[0])
                style = self.s["h2"] if level <= 2 else self.s["h3"]
                if level <= 2:
                    out.append(CondPageBreak(34 * mm))
                para = Paragraph(text, style)
                plain = _plain(node.children[0])
                para._bookmark = (slugify(plain), plain, level)
                para._kwn = True
                out.append(para)
            elif t == "paragraph":
                ilnode = node.children[0]
                plain = _plain(ilnode).strip()
                para = Paragraph(inline(ilnode), self.s["body"])
                # "... binds:" lead-ins and bold-only labels stay with the next block;
                # lower-case continuations ("into a replayable record.") stay with the previous one.
                para._kwn = plain.endswith(":") or (len(ilnode.children) == 1 and ilnode.children[0].type == "strong")
                para._kwp = plain[:1].islower()
                out.append(para)
            elif t == "ordered_list" and all(
                    len(li.children) == 1 and li.children[0].type == "paragraph" for li in node.children):
                # numbered references: one unsplittable paragraph per item
                start = int(node.attrs.get("start", 1))
                for k, li in enumerate(node.children):
                    para = Paragraph(inline(li.children[0].children[0]), self.s["ref"], bulletText=f"{start + k}.")
                    para._keep = True
                    out.append(para)
            elif t in ("bullet_list", "ordered_list"):
                flow = self.list_(node, 0)
                flow._keep = len(node.children) <= 10 and len(_plain(node)) <= 600
                out.append(flow)
            elif t in ("fence", "code_block"):
                out.append(panel(Preformatted(node.content.rstrip("\n"), self.s["code"]), self.width))
                out.append(Spacer(1, 7))
            elif t == "table":
                out.append(self.table(node))
                out.append(Spacer(1, 8))
            elif t == "hr":
                if idx + 1 < len(nodes) and nodes[idx + 1].type == "heading":
                    continue  # the heading already separates; avoids a stray rule at a page top
                out.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=10, spaceAfter=4))
            else:
                raise ValueError(f"unsupported block element: {t}")
        return out

    def list_(self, node, depth: int) -> ListFlowable:
        items = []
        for li in node.children:
            flows = []
            for child in li.children:
                if child.type == "paragraph":
                    flows.append(Paragraph(inline(child.children[0]), self.s["li"]))
                elif child.type in ("bullet_list", "ordered_list"):
                    flows.append(self.list_(child, depth + 1))
                else:
                    flows.extend(self.blocks([child]))
            items.append(ListItem(flows))
        common = dict(leftIndent=14, bulletColor=ACCENT, spaceBefore=1 if depth else 0,
                      spaceAfter=2 if depth else 7)
        if node.type == "ordered_list":
            return ListFlowable(items, bulletType="1", bulletFormat="%s.", start=int(node.attrs.get("start", 1)),
                                bulletFontName="MR-Sans", bulletFontSize=8.4, **common)
        return ListFlowable(items, bulletType="bullet", start="•" if depth == 0 else "–",
                            bulletFontName="MR-Serif", bulletFontSize=9.4, **common)

    def table(self, node) -> Table:
        rows, header_rows = [], 0
        for section in node.children:
            for tr in section.children:
                cells = []
                for cell in tr.children:
                    text = inline(cell.children[0]) if cell.children else ""
                    cells.append(Paragraph(text, self.s["th"] if cell.type == "th" else self.s["td"]))
                rows.append(cells)
                if section.type == "thead":
                    header_rows += 1
        ncols = len(rows[0])
        fractions = {3: [0.25, 0.39, 0.36]}.get(ncols, [1.0 / ncols] * ncols)
        tbl = Table(rows, colWidths=[f * self.width for f in fractions], repeatRows=header_rows, hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "MR-Sans"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2),
        ]
        if header_rows:
            style.append(("BACKGROUND", (0, 0), (-1, header_rows - 1), HEAD_BG))
        for r in range(header_rows, len(rows)):
            if (r - header_rows) % 2 == 1:
                style.append(("BACKGROUND", (0, r), (-1, r), PANEL))
        tbl.setStyle(TableStyle(style))
        return tbl


def _plain(inline_node: SyntaxTreeNode) -> str:
    parts = []

    def walk(n):
        if n.type in ("text", "code_inline"):
            parts.append(n.content)
        elif n.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        for c in n.children:
            walk(c)

    walk(inline_node)
    return "".join(parts)


def group_keeps(flows: list) -> list:
    """Bind lead-ins to what follows and continuations to what precedes.

    ReportLab's own keepWithNext does not combine with KeepTogether blocks,
    so page-break grouping is decided here, once, for the whole story.
    """
    chains: list[list] = []
    pending = False
    for f in flows:
        joins = chains and not isinstance(f, CondPageBreak) and (pending or getattr(f, "_kwp", False))
        if joins:
            chains[-1].append(f)
        else:
            chains.append([f])
        pending = getattr(f, "_kwn", False)
    out = []
    for chain in chains:
        if len(chain) > 1 or getattr(chain[0], "_keep", False):
            out.append(KeepTogether(chain))
        else:
            out.append(chain[0])
    return out


# --------------------------------------------------------------------------- page
def title_block(note: Note, r: Renderer) -> list:
    s = r.s
    author = note.authors[0]
    flows = [
        SpacedText(note.series_name.upper(), "MR-Sans-Bold", 8.6, ACCENT),
        Spacer(1, 7 * mm),
        Paragraph(_esc(note.title), s["title"]),
        Paragraph(_esc(note.subtitle), s["subtitle"]),
        Spacer(1, 7 * mm),
        Paragraph(_esc(f"{author['given_name']} {author['family_name']}"), s["author"]),
        Paragraph(_esc(author["affiliation"]), s["affil"]),
        Spacer(1, 2.5 * mm),
        Paragraph(_esc(note.label), s["label"]),
        Spacer(1, 5 * mm),
        panel(Paragraph(f"<b>Status:</b> {_esc(note.meta['status'])}", s["box"]), r.width, pad=6),
        Spacer(1, 5 * mm),
        HRFlowable(width="100%", thickness=0.8, color=RULE, spaceBefore=0, spaceAfter=8),
    ]
    return flows


def _canvas_class(note: Note):
    footer_left = f"{note.series_name} · {note.label}"

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total: int):
            page = self.getPageNumber()
            self.saveState()
            self.setFont("MR-Sans", 7.4)
            self.setFillColor(MUTED)
            y = MARGIN_BOTTOM - 10 * mm
            self.drawString(MARGIN_X, y, footer_left)
            self.drawRightString(PAGE_W - MARGIN_X, y, f"{page} / {total}")
            if page > 1:
                top = PAGE_H - MARGIN_TOP + 9 * mm
                t = self.beginText(MARGIN_X, top)
                t.setFont("MR-Sans-Bold", 7.2)
                t.setCharSpace(1.2)
                t.setFillColor(ACCENT)
                t.textOut(note.series_name.upper())
                t.setCharSpace(0)
                self.drawText(t)
                self.setFont("MR-Sans", 7.4)
                self.setFillColor(MUTED)
                self.drawRightString(PAGE_W - MARGIN_X, top, note.title)
                self.setStrokeColor(RULE)
                self.setLineWidth(0.5)
                self.line(MARGIN_X, top - 3.2 * mm, PAGE_W - MARGIN_X, top - 3.2 * mm)
            self.restoreState()

    return NumberedCanvas


class NoteDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        mark = getattr(flowable, "_bookmark", None)
        if mark:
            key, text, level = mark
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=max(0, level - 2), closed=False)


def render_pdf(note: Note, out_path: Path) -> dict:
    register_fonts()
    rl_config.invariant = 1
    tokens = mdparse.parse(note.md_path.read_text(encoding="utf-8"))
    bad = mdparse.unsupported_tokens(tokens)
    if bad:
        raise ValueError(f"unsupported Markdown elements: {bad}")
    _, body = mdparse.split_title_block(tokens)
    tree = SyntaxTreeNode(body)

    buf = io.BytesIO()
    doc = NoteDoc(
        buf, pagesize=A4,
        leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
        title=note.full_title,
        author=", ".join(note.author_names),
        subject=(f"{note.series_name} Note {note.number}, version {note.version}, "
                 f"{human_date(note.date)}. Status: {note.meta['status']}."),
        keywords=", ".join(note.meta["keywords"]),
        creator=f"{note.series_name} publication pipeline (tools/publish.py)",
        invariant=1, pageCompression=0, lang=note.meta.get("language", "en"),
        initialFontName="MR-Serif", initialFontSize=9.8, initialLeading=14.4,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="note", frames=[frame])])

    r = Renderer(doc.width)
    story = title_block(note, r) + group_keeps(r.blocks(tree.children))

    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch_of(note.date))
    try:
        doc.build(story, canvasmaker=_canvas_class(note))
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous

    data = buf.getvalue()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return {"bytes": len(data), "pages": doc.page}
