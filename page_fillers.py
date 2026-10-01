"""Add small, concept-matched maths activities to genuinely sparse student pages."""

from __future__ import annotations

import re
import math
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
CONTENT_TO_PANEL_GAP = 30.0


def _activity_for(concept: str, topic: str, page_context: str = "", variant: int = 0) -> Tuple[str, str, str, str]:
    """Return a checked fact, challenge, answer, and answer explanation."""
    text = f"{concept} {topic} {page_context}".lower()
    def choose(items):
        if variant < len(items):
            return items[variant]
        return None
    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric")):
        if "letters" in text and any(word in text for word in ("word", "repeated", "together")):
            activities = [
                (
                "Repeated letters are indistinguishable, so divide by the factorial of each repeated count.",
                "How many distinct arrangements can be made from the letters in BANANA?",
                "60",
                "There are 6 letters, with A repeated 3 times and N repeated twice: 6!/(3!2!) = 60.",
                ),
                ("Repeated letters are counted once by dividing out their repeated factorials.", "How many distinct arrangements can be made from LEVEL?", "30", "LEVEL has 5 letters, with L and E each repeated twice: 5!/(2!2!) = 30."),
                ("A repeated letter does not create a new arrangement when identical copies swap.", "How many distinct arrangements can be made from MAMA?", "6", "There are 4 letters with M and A each repeated twice: 4!/(2!2!) = 6."),
            ]
            if variant >= len(activities):
                total = variant + 7
                repeated = 2 + variant % 3
                answer = math.factorial(total) // math.factorial(repeated)
                return (
                    "Identical symbols are counted once; divide by the factorial of their repeated count.",
                    f"A code has {repeated} identical A symbols and {total - repeated} distinct symbols. How many arrangements are possible?",
                    f"{answer:,}",
                    f"There are {total} symbols in total, with {repeated} identical: {total}!/{repeated}! = {answer:,}.",
                )
            return choose(activities)
        if any(word in text for word in ("together", "adjacent", "gap")):
            activities = [
                (
                "Grouping items together turns the group into one unit before you arrange the units.",
                "Four friends and three siblings sit in a row. How many arrangements keep the siblings together?",
                "720",
                "Arrange the five units in 5! ways, then the siblings in 3! ways: 5! x 3! = 720.",
                ),
                ("Treat the required adjacent pair as one block, then arrange the block and remaining people.", "Five students line up. How many arrangements keep Ava and Ben together?", "48", "Treat Ava and Ben as one block: 4! ways to arrange the units and 2! ways within the block, so 4! x 2 = 48."),
                ("A block can be arranged internally after its position among the other units is chosen.", "Six books are arranged in a row. How many arrangements keep two particular books together?", "240", "Treat the pair as one unit: 5! x 2! = 240."),
            ]
            if variant >= len(activities):
                friends = variant + 4
                answer = math.factorial(friends + 1) * math.factorial(3)
                return (
                    "Group the required three people as one unit, then arrange that unit with everyone else.",
                    f"{friends} friends and three siblings sit in a row. How many arrangements keep the siblings together?",
                    f"{answer:,}",
                    f"Arrange {friends + 1} units, then the three siblings: {friends + 1}! x 3! = {answer:,}.",
                )
            return choose(activities)
        if "circle" in text or "circular" in text:
            activities = [
                (
                "At a round table, rotating everyone together does not create a new arrangement.",
                "Six friends sit around a circular table. How many distinct arrangements are there?",
                "120",
                "Fix one friend as an anchor, then arrange the other five: 5! = 120.",
                ),
                ("For circular arrangements, fix one person to remove rotations that represent the same seating.", "How many ways can seven people sit around a round table?", "720", "Fix one person, then arrange the other six: 6! = 720."),
                ("A circular arrangement of n distinct people has (n-1)! rotations.", "How many distinct circular arrangements are there for five people?", "24", "Fix one person and arrange the remaining four: 4! = 24."),
            ]
            if variant >= len(activities):
                people = variant + 6
                answer = math.factorial(people - 1)
                return (
                    "Fix one person to remove rotations that represent the same circular seating.",
                    f"How many distinct ways can {people} people sit around a circular table?",
                    f"{answer:,}",
                    f"Fix one person and arrange the other {people - 1}: ({people - 1})! = {answer:,}.",
                )
            return choose(activities)
        if any(word in text for word in ("combination", "unordered", "selection")):
            activities = [
                (
                "For a committee, swapping two members does not make a new committee.",
                "Choose a 3-person team from 8 students. How many teams can be formed?",
                "56",
                "Order does not matter, so use 8C3 = 8!/(3!5!) = 56.",
                ),
                ("A selection is unordered, so use combinations rather than permutations.", "Choose 2 students from a group of 9. How many pairs are possible?", "36", "9C2 = 9 x 8 / 2 = 36."),
                ("Count each group once, regardless of the order in which its members are chosen.", "A club selects 4 people from 10 volunteers. How many groups can it form?", "210", "10C4 = 10!/(4!6!) = 210."),
            ]
            if variant >= len(activities):
                group_size = 2 + variant % 4
                population = variant + 10
                answer = math.comb(population, group_size)
                return (
                    "For an unordered selection, changing the order of the chosen people does not create a new group.",
                    f"How many different groups of {group_size} can be chosen from {population} students?",
                    f"{answer:,}",
                    f"Use combinations: {population}C{group_size} = {answer:,}.",
                )
            return choose(activities)
        if "factorial" in text:
            activities = [
                (
                "Factorials grow quickly: 10! is already 3,628,800.",
                "Without a calculator, simplify the ratio of nine factorial to seven factorial.",
                "72",
                "Cancel 7!: the ratio is 9 x 8 = 72.",
                ),
                ("A factorial ratio often simplifies by cancelling the smaller factorial.", "Without a calculator, simplify the ratio of eight factorial to six factorial.", "56", "Cancel 6!: the ratio is 8 x 7 = 56."),
                ("Expand only as many factors as are needed to cancel the denominator.", "Without a calculator, simplify the ratio of ten factorial to eight factorial.", "90", "Cancel 8!: the ratio is 10 x 9 = 90."),
            ]
            if variant >= len(activities):
                numerator = variant + 12
                answer = numerator * (numerator - 1)
                return (
                    "Cancel the smaller factorial first, then multiply only the remaining factors.",
                    f"Without a calculator, simplify the ratio of {numerator} factorial to {numerator - 2} factorial.",
                    f"{answer:,}",
                    f"Cancel ({numerator - 2})!: the remaining product is {numerator} x {numerator - 1} = {answer:,}.",
                )
            return choose(activities)
        activities = [
            (
            "When order matters, assigning the same people to different roles changes the outcome.",
            "Seven finalists compete for gold, silver and bronze. How many podiums are possible?",
            "210",
            "The three places are ordered: 7P3 = 7 x 6 x 5 = 210.",
            ),
            ("Permutations count selections where different orders represent different outcomes.", "How many ways can four students be assigned president and vice-president from a group of ten?", "90", "There are 10 choices for president and 9 for vice-president: 10 x 9 = 90."),
            ("For an ordered selection, reduce the number of choices after each pick.", "How many ordered pairs can be chosen from six different objects?", "30", "There are 6 choices first and 5 second: 6 x 5 = 30."),
        ]
        if variant >= len(activities):
            finalists = variant + 7
            answer = math.perm(finalists, 3)
            return (
                "When order matters, the same people in different roles count as different outcomes.",
                f"{finalists} finalists compete for gold, silver and bronze. How many podiums are possible?",
                f"{answer:,}",
                f"The places are ordered: {finalists}P3 = {finalists} x {finalists - 1} x {finalists - 2} = {answer:,}.",
            )
        return choose(activities)
    if any(word in text for word in ("probability", "chance", "random")):
        activities = [
            (
            "A probability is always between 0 and 1, inclusive.",
            "A bag has 4 red and 6 blue counters. What is the chance of drawing red?",
            "2/5",
            "There are 4 red counters out of 10 equally likely counters: 4/10 = 2/5.",
            ),
            ("The probabilities of all outcomes in a complete sample space add to 1.", "A fair coin is tossed twice. What is the probability of two heads?", "1/4", "The equally likely outcomes are HH, HT, TH and TT; only HH works."),
            ("For equally likely outcomes, probability is favourable outcomes divided by total outcomes.", "A fair six-sided die is rolled. What is the probability of an even result?", "1/2", "Three of the six outcomes are even, so 3/6 = 1/2."),
        ]
        if variant >= len(activities):
            sides = variant + 6
            favourable = len(range(2, sides + 1, 2))
            divisor = math.gcd(favourable, sides)
            answer = f"{favourable // divisor}/{sides // divisor}"
            return (
                "For equally likely outcomes, divide the favourable outcomes by the total possible outcomes.",
                f"A fair spinner is numbered 1 to {sides}. What is the probability of landing on an even number?",
                answer,
                f"There are {favourable} even numbers out of {sides}, so the probability is {answer}.",
            )
        return choose(activities)
    if "binomial" in text:
        activities = [
            (
            "The coefficients in each row of Pascal's triangle add to a power of 2.",
            "What is the coefficient of x^2 in (x + 2)^4?",
            "24",
            "Choose two x factors and two 2 factors: 4C2 x 2^2 = 6 x 4 = 24.",
            ),
            ("The general term in a binomial expansion combines a choose coefficient with powers of each term.", "What is the coefficient of x in (x + 3)^3?", "27", "Choose one x: 3C1 x 3^2 = 27."),
            ("Pascal's triangle gives the coefficients for powers of a binomial.", "What is the coefficient of x^2 in (x + 1)^5?", "10", "The coefficient is 5C2 = 10."),
        ]
        if variant >= len(activities):
            power = variant + 5
            exponent = 1 + variant % (power - 1)
            answer = math.comb(power, exponent)
            return (
                "Use the binomial coefficient to count the ways to choose which factors contribute x.",
                f"What is the coefficient of x^{exponent} in (x + 1)^{power}?",
                f"{answer:,}",
                f"The coefficient is {power}C{exponent} = {answer:,}.",
            )
        return choose(activities)
    activities = [
        (
        "Look for a pattern in the differences between consecutive terms.",
        "What number comes next: 1, 2, 4, 7, 11, ...?",
        "16",
        "The differences are 1, 2, 3, 4, so add 5 next: 11 + 5 = 16.",
        ),
        ("A constant second difference often signals a quadratic sequence.", "What number comes next: 2, 5, 10, 17, ...?", "26", "The differences are 3, 5, 7; add 9 next to get 26."),
        ("Check whether each term is made by multiplying the previous term by a fixed number.", "What number comes next: 3, 6, 12, 24, ...?", "48", "Each term doubles, so 24 x 2 = 48."),
    ]
    if variant >= len(activities):
        start = variant + 2
        return (
            "Look at the pattern in the differences between consecutive terms.",
            f"What number comes next: {start}, {start + 2}, {start + 6}, {start + 12}, ...?",
            str(start + 20),
            f"The differences are 2, 4, 6, so add 8 next: {start + 12} + 8 = {start + 20}.",
        )
    return choose(activities)


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
    variant: int = 0,
) -> None:
    fact, challenge, answer, explanation = _activity_for(concept, topic, page_context, variant)
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
        used_challenges = set()
        activity_index = 0

        for index, original_page in enumerate(source.pages):
            text = page_texts[index]
            if "plain answers" in text.casefold() or "quick answers" in text.casefold():
                output.add_page(original_page)
                continue
            # Make the operation idempotent: never add a second panel to a page
            # that already contains one.
            if "maths brain break" in text.casefold():
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

            available_height = lowest_y - PAGE_MARGIN - CONTENT_TO_PANEL_GAP
            panel_height = min(available_height, body_height * MAX_PANEL_RATIO)
            if panel_height < body_height * MIN_UNUSED_RATIO - 14:
                output.add_page(original_page)
                continue

            # Pick a different checked activity for each inserted page. If a
            # booklet has more sparse pages than available activities in that
            # concept family, leave the remaining page clean instead of repeat.
            selected = None
            for variant_offset in range(32):
                candidate = _activity_for(active_concept, topic, text, activity_index + variant_offset)
                if candidate[1] not in used_challenges:
                    selected = (variant_offset, candidate)
                    break
            if selected is None:
                output.add_page(original_page)
                continue
            variant_offset, candidate = selected
            used_challenges.add(candidate[1])
            activity_index += 1

            overlay_buffer = BytesIO()
            overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
            _draw_activity_panel(
                overlay_canvas, page_width, PAGE_MARGIN, panel_height, active_concept, topic, text,
                activity_index - 1 + variant_offset,
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
