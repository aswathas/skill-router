# -*- coding: utf-8 -*-
"""Render the paper to PDF with reportlab (two-column, ACM-like).

This machine has no LaTeX toolchain, so the .tex in this directory is the
canonical artefact and this renderer produces the PDF from the same content
definition. Anyone with acmart can compile the .tex to the same paper.
"""

import pathlib
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = pathlib.Path(__file__).resolve().parent
BODY_FONT = "Times-Roman"
BODY_BOLD = "Times-Bold"
BODY_ITAL = "Times-Italic"
MONO = "Courier"


def styles():
    return {
        "title": ParagraphStyle("title", fontName=BODY_BOLD, fontSize=17, leading=20,
                                 alignment=1, spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", fontName=BODY_ITAL, fontSize=10.5, leading=13,
                                   alignment=1, spaceAfter=8),
        "authors": ParagraphStyle("authors", fontName=BODY_FONT, fontSize=10, leading=13,
                                  alignment=1, spaceAfter=2),
        "affil": ParagraphStyle("affil", fontName=BODY_ITAL, fontSize=9, leading=11,
                                alignment=1, spaceAfter=8),
        "abstracthead": ParagraphStyle("abstracthead", fontName=BODY_BOLD, fontSize=9, leading=11,
                                       alignment=1, spaceBefore=4, spaceAfter=2),
        "abstract": ParagraphStyle("abstract", fontName=BODY_FONT, fontSize=8.6, leading=10.6,
                                   alignment=TA_JUSTIFY, spaceAfter=4),
        "keywords": ParagraphStyle("keywords", fontName=BODY_FONT, fontSize=8.4, leading=10.4,
                                   alignment=1, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName=BODY_BOLD, fontSize=11.5, leading=13.5,
                              spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", fontName=BODY_BOLD, fontSize=9.6, leading=11.6,
                              spaceBefore=7, spaceAfter=2),
        "body": ParagraphStyle("body", fontName=BODY_FONT, fontSize=9.1, leading=11.4,
                               alignment=TA_JUSTIFY, spaceAfter=5, firstLineIndent=11),
        "caption": ParagraphStyle("caption", fontName=BODY_BOLD, fontSize=8.2, leading=10,
                                  spaceBefore=6, spaceAfter=3),
        "cell": ParagraphStyle("cell", fontName=BODY_FONT, fontSize=7.3, leading=8.8),
        "cellb": ParagraphStyle("cellb", fontName=BODY_BOLD, fontSize=7.3, leading=8.8),
        "ref": ParagraphStyle("ref", fontName=BODY_FONT, fontSize=8.3, leading=10.4,
                              alignment=TA_JUSTIFY, leftIndent=13, firstLineIndent=-13,
                              spaceAfter=3),
    }


def build(C, sections, results_subsections):
    st = styles()
    out = HERE / "skill-router.pdf"
    doc = BaseDocTemplate(str(out), pagesize=letter,
                          leftMargin=0.78 * inch, rightMargin=0.78 * inch,
                          topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                          title=C.TITLE, author=", ".join(C.AUTHORS))
    gap = 0.26 * inch
    colw = (doc.width - gap) / 2.0
    colh = doc.height
    title_h = 3.95 * inch

    f_title = Frame(doc.leftMargin, doc.height - title_h, doc.width, title_h - 0.1 * inch, id="title",
                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    body_h = doc.height - title_h - doc.bottomMargin
    f_c1 = Frame(doc.leftMargin, doc.bottomMargin, colw, body_h, id="c1",
                 leftPadding=0, rightPadding=6, topPadding=0, bottomPadding=0)
    f_c2 = Frame(doc.leftMargin + colw + gap, doc.bottomMargin, colw, body_h, id="c2",
                 leftPadding=6, rightPadding=0, topPadding=0, bottomPadding=0)
    g_c1 = Frame(doc.leftMargin, doc.bottomMargin, colw, colh, id="g1",
                 leftPadding=0, rightPadding=6, topPadding=0, bottomPadding=0)
    g_c2 = Frame(doc.leftMargin + colw + gap, doc.bottomMargin, colw, colh, id="g2",
                 leftPadding=6, rightPadding=0, topPadding=0, bottomPadding=0)

    def on_page(canv, doc_):
        canv.saveState()
        canv.setFont(BODY_FONT, 7.5)
        canv.drawString(doc_.leftMargin, 0.45 * inch,
                        "Capability Routing for Agent Skill Libraries")
        canv.drawRightString(letter[0] - doc_.rightMargin, 0.45 * inch, str(doc_.page))
        canv.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[f_title, f_c1, f_c2], onPage=on_page),
        PageTemplate(id="later", frames=[g_c1, g_c2], onPage=on_page),
    ])

    story = []
    story.append(Paragraph(escape(C.TITLE), st["title"]))
    story.append(Paragraph(escape(C.SUBTITLE), st["subtitle"]))
    story.append(Paragraph("&nbsp;&nbsp;".join(escape(a) for a in C.AUTHORS), st["authors"]))
    story.append(Paragraph(escape(C.AFFIL[0]), st["affil"]))
    story.append(Paragraph("ABSTRACT", st["abstracthead"]))
    story.append(Paragraph(escape(C.ABSTRACT), st["abstract"]))
    story.append(Paragraph("KEYWORDS&nbsp;&nbsp;" + escape(C.KEYWORDS), st["keywords"]))
    story.append(NextPageTemplate("later"))

    def add_table(rows, caption, num):
        head, body = rows[0], rows[1:]
        avail = colw - 10
        n = len(head)
        if n == 8:
            widths = [avail * f for f in (0.30, 0.10, 0.10, 0.09, 0.11, 0.10, 0.10, 0.10)]
        elif n == 4:
            widths = [avail * f for f in (0.40, 0.15, 0.22, 0.23)]
        else:
            widths = [avail * 0.55] + [avail * 0.45 / (n - 1)] * (n - 1)
        data = [[Paragraph("<b>%s</b>" % escape(h), st["cellb"]) for h in head]]
        for r in body:
            data.append([Paragraph(escape(str(c)), st["cell"]) for c in r])
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("TOPLINE", (0, 0), (-1, 0), 0.7, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        block = [Paragraph("Table %d. %s" % (num, escape(caption)), st["caption"]), t]
        story.append(KeepTogether(block))
        story.append(Spacer(1, 6))

    tnum = 0
    for s in sections:
        story.append(Paragraph(escape(s["title"]), st["h2"]))
        for p in s["paras"]:
            story.append(Paragraph(escape(p), st["body"]))
        if s["title"] == "Results":
            for sub, paras in results_subsections:
                story.append(Paragraph(escape(sub), st["h3"]))
                for p in paras:
                    story.append(Paragraph(escape(p), st["body"]))
            tnum += 1
            for key, caption, label in C.TABLE_SPECS:
                tnum += 1
                add_table(C.RESULTS[key], caption, tnum)

    story.append(Paragraph("References", st["h2"]))
    for idx, (key, authors, title, venue) in enumerate(C.REFERENCES, 1):
        story.append(Paragraph("[%d]&nbsp;&nbsp;%s. <i>%s</i>. %s."
                                % (idx, escape(authors), escape(title), escape(venue)),
                                st["ref"]))

    doc.build(story)
    print("wrote", out, out.stat().st_size, "bytes")
