"""Add small, concept-matched maths activities to genuinely sparse student pages."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


MIN_UNUSED_RATIO = 0.28  # 30% target, with a small tolerance for headers and page geometry.
PAGE_MARGIN = 54.0
MAX_PANEL_RATIO = 0.72


def _activity_for(concept: str, topic: str, page_context: str = "") -> Tuple[str, str, str, str]:
    """Return a checked fact, challenge, answer, and answer explanation."""
    text = f"{concept} {topic} {page_context}".lower()
    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric")):
        if "letters" in text and any(word in text for word in ("word", "repeated", "together")):
            return (
                "Repeated letters are indistinguishable, so divide by the factorial of each repeated count.",
                "How many distinct arrangements can be made from the letters in BANANA?",
                "60",
                "There are 6 letters, with A repeated 3 times and N repeated twice: 6!/(3!2!) = 60.",
            )
        if any(word in text for word in ("together", "adjacent", "gap")):
            return (
                "Grouping items together turns the group into one unit before you arrange the units.",
                "Four friends and three siblings sit in a row. How many arrangements keep the siblings together?",
                "720",
                "Arrange the five units in 5! ways, then the siblings in 3! ways: 5! x 3! = 720.",
            )
        if "circle" in text or "circular" in text:
            return (
                "At a round table, rotating everyone together does not create a new arrangement.",
                "Six friends sit around a circular table. How many distinct arrangements are there?",
                "120",
                "Fix one friend as an anchor, then arrange the other five: 5! = 120.",
            )
        if any(word in text for word in ("combination", "unordered", "selection")):
            return (
                "For a committee, swapping two members does not make a new committee.",
                "Choose a 3-person team from 8 students. How many teams can be formed?",
                "56",
                "Order does not matter, so use 8C3 = 8!/(3!5!) = 56.",
            )
        if "factorial" in text:
            return (
                "Factorials grow quickly: 10! is already 3,628,800.",
                "No calculator: simplify 9!/7!.",
                "72",
                "Cancel 7!: 9!/7! = 9 x 8 = 72.",
            )
        return (
            "When order matters, assigning the same people to different roles changes the outcome.",
            "Seven finalists compete for gold, silver and bronze. How many podiums are possible?",
            "210",
            "The three places are ordered: 7P3 = 7 x 6 x 5 = 210.",
        )
    if any(word in text for word in ("probability", "chance", "random")):
        return (
            "A probability is always between 0 and 1, inclusive.",
            "A bag has 4 red and 6 blue counters. What is the chance of drawing red?",
            "2/5",
            "There are 4 red counters out of 10 equally likely counters: 4/10 = 2/5.",
        )
    if "binomial" in text:
        return (
            "The coefficients in each row of Pascal's triangle add to a power of 2.",
            "What is the coefficient of x^2 in (x + 2)^4?",
            "24",
            "Choose two x factors and two 2 factors: 4C2 x 2^2 = 6 x 4 = 24.",
        )
    return (
        "Look for a pattern in the differences between consecutive terms.",
        "What number comes next: 1, 2, 4, 7, 11, ...?",
        "16",
        "The differences are 1, 2, 3, 4, so add 5 next: 11 + 5 = 16.",
    )


def _page_text_and_lowest_body_y(page) -> Tuple[str, Optional[float]]:
    import pypdfium2 as pdfium

    width, height = page.get_size()
    text_page = page.get_textpage()
    text = text_page.get_text_range()
    body_bottom = []
    for index in range(text_page.count_chars()):
        left, bottom, right, top = text_page.get_charbox(index)
        if PAGE_MARGIN < bottom < height - PAGE_MARGIN and right > PAGE_MARGIN and left < width - PAGE_MARGIN:
            body_bottom.append(bottom)
    return text, min(body_bottom) if body_bottom else None


def _draw_activity_panel(
    page_canvas: canvas.Canvas,
    page_width: float,
    panel_bottom: float,
    panel_height: float,
    concept: str,
    topic: str,
    page_context: str,
) -> None:
    fact, challenge, answer, explanation = _activity_for(concept, topic, page_context)
    x = PAGE_MARGIN
    width = page_width - 2 * PAGE_MARGIN
    top = panel_bottom + panel_height

    page_canvas.setFillColor(colors.HexColor("#F5F8FF"))
    page_canvas.setStrokeColor(colors.HexColor("#7285C2"))
    page_canvas.setLineWidth(1.2)
    page_canvas.roundRect(x, panel_bottom, width, panel_height, 9, stroke=1, fill=1)

    page_canvas.setFillColor(colors.HexColor("#25345B"))
    page_canvas.setFont("Helvetica-Bold", 13)
    page_canvas.drawString(x + 14, top - 24, "MATHS BRAIN BREAK")
    page_canvas.setStrokeColor(colors.HexColor("#D4DAEA"))
    page_canvas.line(x + 14, top - 33, x + width - 14, top - 33)

    inner_width = width - 28
    fact_style = ParagraphStyle(
        "BrainBreakFact", fontName="Helvetica", fontSize=9.5, leading=13,
        textColor=colors.HexColor("#374151"), spaceAfter=0,
    )
    challenge_style = ParagraphStyle(
        "BrainBreakChallenge", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
        textColor=colors.HexColor("#172554"), spaceAfter=0,
    )
    paragraph = Paragraph(f"<b>Quick fact:</b> {fact}", fact_style)
    _, fact_height = paragraph.wrap(inner_width, 80)
    paragraph.drawOn(page_canvas, x + 14, top - 43 - fact_height)

    challenge_y = top - 56 - fact_height
    page_canvas.setFillColor(colors.HexColor("#596B9D"))
    page_canvas.setFont("Helvetica-Bold", 9)
    page_canvas.drawString(x + 14, challenge_y, "CHALLENGE")
    challenge_para = Paragraph(challenge, challenge_style)
    _, challenge_height = challenge_para.wrap(inner_width, 100)
    challenge_para.drawOn(page_canvas, x + 14, challenge_y - 7 - challenge_height)

    answer_y = panel_bottom + 25
    page_canvas.setFillColor(colors.HexColor("#374151"))
    page_canvas.setFont("Helvetica-Bold", 8.5)
    page_canvas.drawString(x + 14, answer_y, f"Self-check: {answer}")
    page_canvas.setFont("Helvetica", 8)
    explanation_width = stringWidth(explanation, "Helvetica", 8)
    if explanation_width <= inner_width:
        page_canvas.drawString(x + 14, answer_y - 12, explanation)
    else:
        answer_para = Paragraph(explanation, ParagraphStyle(
            "BrainBreakAnswer", fontName="Helvetica", fontSize=8, leading=10,
            textColor=colors.HexColor("#374151"),
        ))
        _, answer_height = answer_para.wrap(inner_width, 26)
        answer_para.drawOn(page_canvas, x + 14, answer_y - 14 - answer_height)

    work_top = challenge_y - 15 - challenge_height
    work_bottom = answer_y + 12
    if work_top - work_bottom > 18:
        page_canvas.setFillColor(colors.HexColor("#596B9D"))
        page_canvas.setFont("Helvetica-Oblique", 8)
        page_canvas.drawString(x + 14, work_top - 4, "Show your thinking:")
        first_line = work_top - 19
        page_canvas.setStrokeColor(colors.HexColor("#C7CDDC"))
        line_gap = 19
        y = first_line
        while y > work_bottom and y > panel_bottom + 38:
            page_canvas.line(x + 14, y, x + width - 14, y)
            y -= line_gap


def fill_sparse_private_theory_pages(pdf_bytes: bytes, booklet_data: Dict[str, Any]) -> bytes:
    """Add one concept-matched brain-break card to Student Private pages with 28%+ blank body area."""
    try:
        import pypdfium2 as pdfium

        source = PdfReader(BytesIO(pdf_bytes))
        if not source.pages:
            return pdf_bytes
        document = pdfium.PdfDocument(pdf_bytes)
        output = PdfWriter()
        page_texts = []
        page_lows = []
        for page in document:
            text, lowest_y = _page_text_and_lowest_body_y(page)
            page_texts.append(text)
            page_lows.append(lowest_y)

        concepts = booklet_data.get("concepts", []) or []
        concept_names = [str(concept.get("name") or concept.get("concept") or "") for concept in concepts]
        active_concept = ""
        topic = str(booklet_data.get("topic") or "Mathematics")
        changed = False

        for index, original_page in enumerate(source.pages):
            text = page_texts[index]
            if "plain answers" in text.casefold() or "quick answers" in text.casefold():
                output.add_page(original_page)
                continue
            heading = re.search(r"Concept\s+[A-Z0-9]+:\s*([^\r\n]+)", text, re.IGNORECASE)
            if heading:
                active_concept = heading.group(1).strip()
            for concept_name in concept_names:
                if concept_name and concept_name.casefold() in text.casefold():
                    active_concept = concept_name
                    break
            if not active_concept:
                output.add_page(original_page)
                continue
            lowest_y = page_lows[index]
            page_height = float(original_page.mediabox.height)
            page_width = float(original_page.mediabox.width)
            body_height = page_height - 2 * PAGE_MARGIN
            unused_ratio = ((lowest_y - PAGE_MARGIN) / body_height) if lowest_y is not None and body_height > 0 else 0
            if unused_ratio < MIN_UNUSED_RATIO:
                output.add_page(original_page)
                continue

            available_height = lowest_y - PAGE_MARGIN - 14
            panel_height = min(available_height, body_height * MAX_PANEL_RATIO)
            if panel_height < body_height * MIN_UNUSED_RATIO - 14:
                output.add_page(original_page)
                continue

            overlay_buffer = BytesIO()
            overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
            _draw_activity_panel(
                overlay_canvas, page_width, PAGE_MARGIN, panel_height, active_concept, topic, text
            )
            overlay_canvas.save()
            overlay_buffer.seek(0)
            overlay_page = PdfReader(overlay_buffer).pages[0]
            output.add_page(original_page)
            output.pages[-1].merge_page(overlay_page)
            changed = True

        document.close()
        if not changed:
            return pdf_bytes
        result = BytesIO()
        output.write(result)
        return result.getvalue()
    except Exception:
        # The original booklet remains available if PDF text positioning fails.
        return pdf_bytes
