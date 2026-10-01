"""Add small, concept-matched maths activities to genuinely sparse student pages."""

from __future__ import annotations

import re
import math
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


MIN_UNUSED_RATIO = 0.28  # 30% target, with a small tolerance for headers and page geometry.
PAGE_MARGIN = 54.0
MAX_PANEL_RATIO = 0.72
CONTENT_TO_PANEL_GAP = 30.0


def _question_activity(concept: str, topic: str, page_context: str = "", variant: int = 0) -> Tuple[str, str, str, str]:
    """Return a short, checked puzzle for this topic."""
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
                "A classmate counts each arrangement of BANANA as different when identical letters swap. Which letters cause the overcount?",
                "A and N",
                "The three A's are identical, and the two N's are identical; swapping copies changes nothing.",
                ),
                ("Repeated letters are counted once because identical copies cannot be told apart.", "In the word LEVEL, which letters would you avoid counting as distinct swaps?", "The two Ls and two Es", "Swapping identical Ls or identical Es leaves the word unchanged."),
                ("Identical symbols do not create new outcomes when their positions are exchanged.", "A code contains the symbols M, A, M, A. Which swaps leave the code arrangement unchanged?", "Swapping the two Ms or the two As", "Each pair consists of identical symbols, so exchanging either pair makes no visible change."),
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
                "Four friends each high-five every other friend exactly once. How many high-fives happen?",
                "6",
                "There are 4 × 3 ordered greetings, but each pair was counted twice: 4 × 3 ÷ 2 = 6.",
                ),
                ("When a pair is counted from both directions, divide by two to remove the duplicate count.", "Six people all shake hands once with each other. How many handshakes take place?", "15", "Each handshake is a pair: 6 × 5 ÷ 2 = 15."),
                ("A handshake is one unordered pair, even though two people take part.", "At a table of eight people, how many different pairs of people can chat?", "28", "Count 8 × 7 ordered choices, then divide by 2: 28 pairs."),
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
                "Five friends change seats by all moving one place clockwise. Is it a new circular arrangement?",
                "No",
                "Everyone has the same neighbours in the same order; a rotation does not create a new seating." ,
                ),
                ("Fixing one person at the top of a circle gives each rotation a single reference point.", "Around a round table, do clockwise and counter-clockwise seatings always count as the same?", "No", "A reflection reverses the order of neighbours; it is not just a rotation."),
                ("In a circle, a rotation preserves who sits next to whom.", "Three friends sit around a tiny round table. How many different neighbour pairs can be formed?", "3", "Each pair of friends sits next to each other in a three-seat circle."),
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
                "Mia and Omar are both on a committee. Is {Mia, Omar} a different group from {Omar, Mia}?",
                "No",
                "A committee is an unordered group; changing the listing order does not change its members.",
                ),
                ("A selection records who is chosen, not the order they were picked.", "A team is listed as Ava, Ben, Chloe. Does listing Chloe first create a new team?", "No", "The same three people are members, so the selection is unchanged."),
                ("Order matters for roles but not for an unassigned group.", "Is choosing a captain and vice-captain an unordered selection?", "No", "The roles differ, so swapping the two people changes the outcome."),
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
                "Find the error: a student writes 5! = 5 × 5. What should the second factor be?",
                "4",
                "A factorial counts down by one: 5! = 5 × 4 × 3 × 2 × 1.",
                ),
                ("Consecutive factorials differ by exactly their larger number.", "A student says 8! divided by 7! is 7. Which number is correct?", "8", "Since 8! = 8 × 7!, dividing by 7! leaves 8."),
                ("A factorial contains every positive whole number down to 1.", "If 6! = 720, what is the remainder when 6! is divided by 7?", "6", "720 = 7 × 102 + 6, so the remainder is 6."),
            ]
            if variant >= len(activities):
                numerator = variant + 20
                answer = sum(numerator // (5 ** power) for power in range(1, 8) if 5 ** power <= numerator)
                return (
                    "Trailing zeroes come from factors of 10, so count pairs of 2s and 5s in the factorial.",
                    f"Without expanding it, how many trailing zeroes does {numerator}! have?",
                    str(answer),
                    f"Count factors of 5: floor({numerator}/5) + floor({numerator}/25) + ... = {answer}.",
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


def _activity_kind(variant: int) -> str:
    return ("puzzle", "fact", "pun", "visual")[variant % 4]


def _activity_for(concept: str, topic: str, page_context: str = "", variant: int = 0) -> Optional[Tuple[str, str, str, str]]:
    """Return unique topic-matched copy for a puzzle, fact, pun, or visual."""
    text = f"{concept} {topic} {page_context}".lower()
    kind = _activity_kind(variant)
    serial = variant // 4

    if kind == "puzzle":
        return _question_activity(concept, topic, page_context, serial)

    if kind == "fact":
        if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric", "combination")):
            n = 8 + serial
            fact = f"{n}! = {math.factorial(n):,} — factorials grow faster than most people expect."
        elif any(word in text for word in ("probability", "chance", "random")):
            total = 6 + serial
            fact = f"For a fair spinner numbered 1 to {total}, each number has probability 1/{total}."
        elif "binomial" in text:
            power = 4 + serial
            fact = f"The coefficients in row {power} of Pascal's triangle add to 2^{power} = {2 ** power}."
        else:
            start = serial + 1
            fact = f"The sequence {start}, {start + 2}, {start + 4}, ... has a constant difference of 2."
        return fact, fact, "", ""

    if kind == "pun":
        puns = [
            ("Permutations are so orderly: they always know how to take a different position.", "A permutation counts outcomes where changing the order changes the result."),
            ("Combinations make great party guests: they never care who arrives first.", "A combination is an unordered selection."),
            ("Factorials are dramatic. Put an exclamation mark after anything and they multiply everything!", "The symbol ! tells us to multiply every whole number down to 1."),
            ("I tried to make a maths pun about infinity, but it went on forever.", "Infinity describes something without an end."),
            ("Parallel lines have so much in common. It is a shame they will never meet.", "Parallel lines stay the same distance apart."),
            ("The number 7 ate 9. It was told to keep its hands off the other integers.", "A tiny number joke, with a nod to integer sequences."),
            ("I asked the calculator for a joke. It said the answer was 0, and I got no reaction.", "Zero is the additive identity: adding it changes no number."),
            ("A circle told a joke, but the punchline went around in circles.", "A circle returns to its starting point after one complete turn."),
        ]
        if serial >= len(puns):
            return None
        pun, explanation = puns[serial]
        return explanation, pun, "", explanation

    # The visual cards are drawn with ReportLab vector shapes, so they remain
    # crisp in print and never depend on an external image or opaque label.
    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric", "combination")):
        n = 4 + serial
        caption = f"A countdown view of {n}!"
    elif any(word in text for word in ("probability", "chance", "random")):
        n = 5 + serial
        caption = f"A sample space with {n} equally likely outcomes"
    elif "binomial" in text:
        n = 3 + serial
        caption = f"The start of Pascal's triangle, row {n}"
    else:
        n = 4 + serial
        caption = f"A number pattern with {n} steps"
    return caption, caption, "", ""


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
    if fact is None:
        return
    x = PAGE_MARGIN
    width = page_width - 2 * PAGE_MARGIN
    top = panel_bottom + panel_height
    kind = _activity_kind(variant)
    serial = variant // 4

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
    body_top = top - 48
    body_bottom = panel_bottom + 20
    ink = colors.HexColor("#25345B")
    muted = colors.HexColor("#596B9D")
    main_style = ParagraphStyle(
        "BrainBreakMain", fontName="Helvetica-Bold", fontSize=12, leading=16,
        textColor=ink, spaceAfter=0,
    )
    detail_style = ParagraphStyle(
        "BrainBreakDetail", fontName="Helvetica", fontSize=9.5, leading=13,
        textColor=colors.HexColor("#374151"), spaceAfter=0,
    )

    if kind == "puzzle":
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawString(x + 14, body_top, "BRAIN TEASER")
        puzzle = Paragraph(challenge, main_style)
        _, puzzle_height = puzzle.wrap(inner_width, max(30, body_top - body_bottom - 60))
        puzzle_top = body_top - 9
        puzzle.drawOn(page_canvas, x + 14, puzzle_top - puzzle_height)
        answer_y = body_bottom + 25
        page_canvas.setFillColor(colors.HexColor("#374151"))
        page_canvas.setFont("Helvetica-Bold", 8.5)
        page_canvas.drawString(x + 14, answer_y, f"Answer: {answer}")
        answer_detail = Paragraph(explanation, detail_style)
        _, detail_height = answer_detail.wrap(inner_width, 30)
        answer_detail.drawOn(page_canvas, x + 14, answer_y - detail_height - 4)
        visual_top = puzzle_top - puzzle_height - 12
        visual_bottom = answer_y + detail_height + 15
        _draw_mini_visual(page_canvas, x, width, visual_top, visual_bottom, concept, topic, serial, mode="steps")
    elif kind == "fact":
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawString(x + 14, body_top, "DID YOU KNOW?")
        main = Paragraph(fact, main_style)
        _, main_height = main.wrap(inner_width, 55)
        main.drawOn(page_canvas, x + 14, body_top - 10 - main_height)
        _draw_mini_visual(page_canvas, x, width, body_top - 24 - main_height, body_bottom, concept, topic, serial, mode="growth")
    elif kind == "pun":
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawString(x + 14, body_top, "MATHS PUN")
        pun = Paragraph(challenge, ParagraphStyle(
            "BrainBreakPun", parent=main_style, fontSize=15, leading=20, alignment=1,
        ))
        _, pun_height = pun.wrap(inner_width, max(40, body_top - body_bottom - 55))
        pun_y = body_bottom + (body_top - body_bottom - pun_height) / 2
        pun.drawOn(page_canvas, x + 14, pun_y)
        detail = Paragraph(explanation, detail_style)
        _, detail_height = detail.wrap(inner_width, 32)
        detail.drawOn(page_canvas, x + 14, max(body_bottom + 4, pun_y - detail_height - 10))
        _draw_math_doodle(page_canvas, x + width - 60, body_top - 28, serial)
    else:
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawString(x + 14, body_top, "A LITTLE MATHS PICTURE")
        caption = Paragraph(challenge, main_style)
        _, caption_height = caption.wrap(inner_width, 34)
        caption.drawOn(page_canvas, x + 14, body_bottom + 3)
        _draw_mini_visual(page_canvas, x, width, body_top - 12, body_bottom + caption_height + 14, concept, topic, serial)


def _draw_mini_visual(page_canvas, x, width, top, bottom, concept, topic, serial, mode="steps"):
    """Draw a small, topic-specific vector illustration inside the card."""
    available = top - bottom
    if available < 38:
        return
    text = f"{concept} {topic}".lower()
    mid_y = bottom + available * 0.53
    center_x = x + width / 2
    stroke = colors.HexColor("#7285C2")
    fills = [colors.HexColor(v) for v in ("#E4E9FF", "#E4F5EF", "#FFF0DA", "#FCE5EA", "#E8F3FA")]
    page_canvas.setStrokeColor(stroke)
    page_canvas.setLineWidth(1)
    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric", "combination")):
        if mode == "growth":
            base_y = bottom + 26
            chart_height = max(45, available - 72)
            values = [(5, 120), (6, 720), (7, 5040), (8, 40320)]
            bar_width = min(62, (width - 100) / len(values) * 0.58)
            gap = (width - 100) / len(values)
            start_x = center_x - gap * 1.5
            for i, (n, value) in enumerate(values):
                bx = start_x + i * gap
                bar_h = max(12, chart_height * value / values[-1][1])
                page_canvas.setFillColor(fills[i % len(fills)])
                page_canvas.roundRect(bx - bar_width / 2, base_y, bar_width, bar_h, 5, stroke=1, fill=1)
                page_canvas.setFillColor(colors.HexColor("#25345B"))
                page_canvas.setFont("Helvetica-Bold", 9)
                page_canvas.drawCentredString(bx, base_y - 14, f"{n}!")
                page_canvas.setFont("Helvetica", 8)
                page_canvas.drawCentredString(bx, base_y + bar_h + 5, f"{value:,}")
            page_canvas.setFillColor(colors.HexColor("#596B9D"))
            page_canvas.setFont("Helvetica-Oblique", 8.5)
            page_canvas.drawCentredString(center_x, bottom + 7, "The bars show how quickly the values grow.")
        else:
            n = 4 + serial
            labels = [f"{n}!", f"{n} × {n - 1}!", f"{n} × {n - 1} × {n - 2}!"]
            rows = len(labels) if available >= 105 else 1
            row_gap = min(54, available / (rows + 1))
            for i, label in enumerate(labels[:rows]):
                y = top - row_gap * (i + 1)
                box_width = min(width - 48, max(170, len(label) * 9 + 48))
                box_height = min(38, max(28, row_gap * 0.64))
                page_canvas.setFillColor(fills[i % len(fills)])
                page_canvas.roundRect(center_x - box_width / 2, y - box_height / 2, box_width, box_height, 7, stroke=1, fill=1)
                page_canvas.setFillColor(colors.HexColor("#25345B"))
                page_canvas.setFont("Helvetica-Bold", 11)
                page_canvas.drawCentredString(center_x, y - 4, label)
                if i < rows - 1:
                    page_canvas.setStrokeColor(colors.HexColor("#7285C2"))
                    page_canvas.line(center_x, y - box_height / 2 - 2, center_x, y - row_gap + box_height / 2 + 3)
                    page_canvas.line(center_x, y - row_gap + box_height / 2 + 3, center_x - 3, y - row_gap + box_height / 2 + 8)
                    page_canvas.line(center_x, y - row_gap + box_height / 2 + 3, center_x + 3, y - row_gap + box_height / 2 + 8)
            if rows > 1:
                page_canvas.setFillColor(colors.HexColor("#596B9D"))
                page_canvas.setFont("Helvetica-Oblique", 8.5)
                page_canvas.drawCentredString(center_x, bottom + 2, "Peel off one factor at a time.")
    elif "probability" in text or "chance" in text:
        count = min(10, 5 + serial)
        radius = min(20, max(12, width / (count * 2.7)))
        columns = min(5, count)
        gap = min(64, (width - 60) / max(1, columns - 1))
        start_x = center_x - gap * (columns - 1) / 2
        for i in range(count):
            row = i // columns
            col = i % columns
            cx = start_x + col * gap
            cy = mid_y - row * (radius * 2 + 12)
            page_canvas.setFillColor(fills[1] if i % 2 == 0 else fills[3])
            page_canvas.circle(cx, cy, radius, stroke=1, fill=1)
            page_canvas.setFillColor(colors.HexColor("#25345B"))
            page_canvas.setFont("Helvetica", 8)
            page_canvas.drawCentredString(cx, cy - 3, str(i + 1))
    elif "binomial" in text:
        rows = min(5, 3 + serial % 3)
        for row in range(rows):
            vals = [str(math.comb(row, col)) for col in range(row + 1)]
            spacing = min(36, (width - 80) / max(1, row)) if row else 30
            row_x = center_x - spacing * row / 2
            y = mid_y + (rows - row - 1) * 19
            for col, value in enumerate(vals):
                page_canvas.setFillColor(fills[(row + col) % len(fills)])
                page_canvas.circle(row_x + col * spacing, y, 9, stroke=1, fill=1)
                page_canvas.setFillColor(colors.HexColor("#25345B"))
                page_canvas.setFont("Helvetica-Bold", 7.5)
                page_canvas.drawCentredString(row_x + col * spacing, y - 2.5, value)
    else:
        count = 5
        labels = [str(serial + i) for i in range(count)]
        gap = min(44, (width - 60) / (count - 1))
        start_x = center_x - gap * (count - 1) / 2
        for i, label in enumerate(labels):
            bx = start_x + i * gap
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(bx - 13, mid_y - 13, 26, 26, 4, stroke=1, fill=1)
            page_canvas.setFillColor(colors.HexColor("#25345B"))
            page_canvas.setFont("Helvetica-Bold", 9)
            page_canvas.drawCentredString(bx, mid_y - 3, label)


def _draw_math_doodle(page_canvas, center_x, center_y, serial):
    page_canvas.saveState()
    page_canvas.setStrokeColor(colors.HexColor("#A6B3DA"))
    page_canvas.setFillColor(colors.HexColor("#E7ECFA"))
    page_canvas.setLineWidth(1.2)
    page_canvas.circle(center_x, center_y, 18 + serial % 3 * 2, stroke=1, fill=1)
    radius = 18 + serial % 3 * 2
    page_canvas.setStrokeColor(colors.HexColor("#596B9D"))
    for angle in range(0, 360, 60):
        radians = math.radians(angle)
        end_x = center_x + radius * 0.75 * math.cos(radians)
        end_y = center_y + radius * 0.75 * math.sin(radians)
        page_canvas.line(center_x, center_y, end_x, end_y)
        page_canvas.setFillColor(colors.HexColor("#596B9D"))
        page_canvas.circle(end_x, end_y, 2.2, stroke=0, fill=1)
    page_canvas.restoreState()


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
                if candidate is None:
                    continue
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
