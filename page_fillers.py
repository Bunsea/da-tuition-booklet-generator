"""Add small, concept-matched maths activities to genuinely sparse student pages."""

from __future__ import annotations

import re
import math
import hashlib
import random
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
ACTIVITY_HEADINGS = ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")
ACTIVITY_MIN_HEIGHT = {"puzzle": 225.0, "fact": 160.0, "pun": 145.0, "visual": 170.0}


def _has_activity_panel(text: str) -> bool:
    normalized = str(text or "").casefold()
    return "maths brain break" in normalized or any(title.casefold() in normalized for title in ACTIVITY_HEADINGS)


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
                circle_puzzles = [
                    ("A seating shifts one chair clockwise for everyone. What changes about each person's neighbours?", "Nothing", "A rotation preserves the relative order and neighbour pairs."),
                    ("Two circular seating sketches are mirror images. Are they always the same arrangement?", "No", "A reflection reverses clockwise order; rotation alone does not."),
                    ("Why can one person be fixed before counting a round-table seating?", "It removes duplicate rotations", "Every circular arrangement can be rotated until the chosen person is at the reference seat."),
                    ("A round table has no labelled first chair. Which part of a seating matters: absolute chair numbers or neighbour order?", "Neighbour order", "Rotating everyone changes chair numbers but preserves who sits next to whom."),
                    ("If a seating is turned halfway around the table, has the arrangement changed?", "No", "A whole-table rotation keeps the same circular order."),
                ]
                fact, answer, explanation = circle_puzzles[(variant - len(activities)) % len(circle_puzzles)]
                return fact, answer, answer, explanation
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
                group_puzzles = [
                    ("A committee list reads Ava, Ben, Chloe. Would writing the same names in reverse create a new committee?", "No", "A committee records membership, not the order of names."),
                    ("A team needs a captain and vice-captain. Does swapping the two people leave the team roles unchanged?", "No", "The roles distinguish the two positions, so order matters."),
                    ("A playlist order changes but its selected songs stay the same. Is it the same selection?", "Yes", "The chosen set is unchanged even if the listing order changes."),
                    ("Two students are chosen for an unlabelled pair. Does choosing Sam before Lee make a different pair?", "No", "The same two members form one unordered group."),
                    ("Which cares about order: choosing a team, or assigning first and second place?", "Assigning places", "A team is unordered; first and second are distinct roles."),
                ]
                fact, answer, explanation = group_puzzles[(variant - len(activities)) % len(group_puzzles)]
                return fact, answer, answer, explanation
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
                extra_puzzles = [
                    ("Without expanding it, how many trailing zeroes does 25! have?", "6", "Count factors of 5: floor(25/5) + floor(25/25) = 5 + 1 = 6."),
                    ("A student says 0! = 0 because zero appears in its name. What is 0! by definition?", "1", "The empty product is defined as 1, which keeps factorial rules consistent."),
                    ("Complete the unrolling: 7! = 7 × 6 × ___.", "5!", "Since 6! = 6 × 5!, then 7! = 7 × 6 × 5!."),
                    ("How many factors are in the fully expanded product 8 × 7 × 6 × 5 × 4 × 3 × 2 × 1?", "8", "There is one factor for each whole number from 8 down to 1."),
                    ("True or false: the jump from 6! to 7! multiplies the value by 7.", "True", "The recurrence is 7! = 7 × 6!."),
                ]
                fact, answer, explanation = extra_puzzles[variant - len(activities)]
                return "Use factorial structure rather than expanding a long product.", fact, answer, explanation
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
            ordered_puzzles = [
                ("Kai earns gold and Noor earns silver. Would swapping their medals be the same podium?", "No", "Gold and silver are distinct positions, so the order changes the result."),
                ("A code uses A, B and C once each. Is ABC the same code as BAC?", "No", "Codes are ordered; changing the position changes the code."),
                ("For a race podium, why does swapping first and second place create a new outcome?", "The roles are different", "A gold-medal result differs from a silver-medal result."),
                ("A, B and C are assigned to president, secretary and treasurer. Does changing the assignment matter?", "Yes", "Each role is distinct, so a different order is a different assignment."),
                ("A seating chart is read from left to right. Would reversing the row usually create a new arrangement?", "Yes", "The objects occupy different ordered positions."),
            ]
            fact, answer, explanation = ordered_puzzles[(variant - len(activities)) % len(ordered_puzzles)]
            return "In an arrangement, position or role changes the outcome.", fact, answer, explanation
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
            facts = [
                "10! is 3,628,800, so factorials become enormous surprisingly quickly.",
                "0! equals 1: the empty product has to act as the multiplication identity.",
                "Every new factorial multiplies the previous one by the next whole number.",
                "5! counts the 120 possible orders of five distinct objects in a line.",
                "Once n is at least 2, n! is even because its product contains a factor of 2.",
                "The number of trailing zeroes in 25! is 6: five factors of 5, plus one more from 25.",
                "For r objects chosen and ordered from n, nPr = n!/(n-r)!; the leftover factorial cancels.",
                "A circular arrangement of n distinct people has (n-1)! orders because rotations repeat.",
            ]
            fact = facts[serial % len(facts)]
        elif any(word in text for word in ("probability", "chance", "random")):
            facts = [
                "A probability of 0 means impossible; a probability of 1 means certain.",
                "The probabilities of all outcomes in a complete sample space add to 1.",
                "For a fair coin, yesterday's result does not change the next toss.",
                "Complementary events have probabilities that add to 1.",
                "If two events cannot happen together, they are mutually exclusive.",
                "An outcome can belong to several events, even though it occurs only once.",
                "For equally likely outcomes, probability is a count of favourable outcomes divided by the total.",
                "A probability is a number from 0 to 1, inclusive; it is never a percentage above 100%.",
            ]
            fact = facts[serial % len(facts)]
        elif "binomial" in text:
            facts = [
                "Pascal's triangle starts with 1, and each inside entry adds the two above it.",
                "The rows of Pascal's triangle read the same forwards and backwards.",
                "The coefficients in row n add to 2^n, the number of subsets of n items.",
                "The first and last coefficient in every Pascal row are 1.",
                "Binomial coefficients count which factors contribute a chosen term in an expansion.",
                "The middle coefficient is largest in an even-numbered row of Pascal's triangle.",
                "Pascal's triangle can be built without expanding any brackets.",
                "Each new row in Pascal's triangle begins and ends with 1.",
            ]
            fact = facts[serial % len(facts)]
        else:
            start = serial + 1
            fact = f"The sequence {start}, {start + 2}, {start + 4}, ... has a constant difference of 2."
        return fact, fact, "", ""

    if kind == "pun":
        puns = [
            ("Why did the student wear glasses in maths class? To improve division!", "Division is a maths operation; vision is what you see."),
            ("Combinations make great party guests: they never care who arrives first.", "A combination is an unordered selection."),
            ("Factorials are dramatic. Put an exclamation mark after anything and they multiply everything!", "The symbol ! tells us to multiply every whole number down to 1."),
            ("I tried to make a maths pun about infinity, but it went on forever.", "Infinity describes something without an end."),
            ("Parallel lines have so much in common. It is a shame they will never meet.", "Parallel lines stay the same distance apart."),
            ("Why was 6 afraid of 7? Because 7 ate 9!", "It is a number joke: the words “ate” and “eight” sound alike."),
            ("Why did the calculator break up with the pencil? It felt like it was being used.", "We use pencils to work and calculators to calculate; “being used” can also mean being taken advantage of."),
            ("Why was the maths book sad? It had too many problems.", "A maths problem is a question to solve; a personal problem is a difficulty."),
        ]
        if serial >= len(puns):
            return None
        pun, explanation = puns[serial]
        return explanation, pun, "", explanation

    # The visual cards are drawn with ReportLab vector shapes, so they remain
    # crisp in print and never depend on an external image or opaque label.
    if "circle" in text or "circular" in text:
        circle_captions = [
            "Anchor one seat to see why rotations are duplicates.",
            "Follow each neighbour clockwise around a circular table.",
            "A mirror image reverses the order; a rotation does not.",
            "Six seats, one fixed person, and five positions left to fill.",
            "Trace the same seating from a different starting chair.",
            "Compare clockwise order with its reflected arrangement.",
            "A circular arrangement has no special first seat.",
            "Rotate the table: the relative seating stays unchanged.",
        ]
        return circle_captions[serial % len(circle_captions)], circle_captions[serial % len(circle_captions)], "", ""
    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric", "combination")):
        visual_captions = [
            "Unroll a factorial one factor at a time.",
            "Compare how quickly consecutive factorial values grow.",
            "Watch the available choices shrink across five positions.",
            "Match each factorial to its evaluated value.",
            "Build an arrangement count from the choices at each position.",
            "See how adding one object multiplies the previous total.",
            "Split a factorial into a short product and a smaller factorial.",
            "Count the choices at each position: 4 × 3 × 2 × 1.",
        ]
        caption = visual_captions[serial % len(visual_captions)]
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

    # Question and solution boxes often include a large blank writing area.
    # Character bounds alone miss that rectangle, so a filler can land on top
    # of it even when the text appears to leave enough room. Include substantial
    # vector objects in the occupied-area check; ignore small rules and the
    # full-page watermark image.
    try:
        for page_object in page.get_objects():
            if getattr(page_object, "type", None) != 2:  # PDF path / vector object
                continue
            bounds = page_object.get_bounds()
            if not bounds or len(bounds) != 4:
                continue
            left, bottom, right, top = map(float, bounds)
            object_width = max(0.0, right - left)
            object_height = max(0.0, top - bottom)
            if (PAGE_MARGIN - 4 <= bottom < height - PAGE_MARGIN
                    and right > PAGE_MARGIN and left < width - PAGE_MARGIN
                    and (object_height >= 20 or object_width * object_height >= 1600)):
                body_bottom.append(bottom)
    except Exception:
        # Text-based detection remains available for malformed or unsupported
        # vector objects.
        pass
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
    page_canvas.drawString(x + 14, top - 24, ACTIVITY_HEADINGS[variant % len(ACTIVITY_HEADINGS)])
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
        quick_fact = Paragraph(f"<b>Quick fact:</b> {fact}", detail_style)
        _, fact_height = quick_fact.wrap(inner_width, 42)
        quick_fact.drawOn(page_canvas, x + 14, body_top - fact_height)
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        challenge_label_y = body_top - fact_height - 12
        page_canvas.drawString(x + 14, challenge_label_y, "BRAIN TEASER")
        puzzle = Paragraph(challenge, main_style)
        puzzle_top = challenge_label_y - 9
        _, puzzle_height = puzzle.wrap(inner_width, max(30, puzzle_top - body_bottom - 60))
        puzzle.drawOn(page_canvas, x + 14, puzzle_top - puzzle_height)
        visual_top = puzzle_top - puzzle_height - 12
        visual_bottom = body_bottom + 18
        _draw_mini_visual(
            page_canvas, x, width, visual_top, visual_bottom, concept, topic, serial,
            mode="steps", activity_text=challenge,
        )
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
        page_canvas.drawString(x + 14, body_top, "WORDPLAY")
        pun = Paragraph(challenge, ParagraphStyle(
            "BrainBreakPun", parent=main_style, fontSize=15, leading=20, alignment=1,
        ))
        _, pun_height = pun.wrap(inner_width, max(40, body_top - body_bottom - 55))
        pun_y = body_top - 30 - pun_height
        pun.drawOn(page_canvas, x + 14, pun_y)
        detail = Paragraph(explanation, detail_style)
        _, detail_height = detail.wrap(inner_width, 32)
        detail_y = pun_y - detail_height - 10
        detail.drawOn(page_canvas, x + 14, max(body_bottom + 4, detail_y))
        visual_top = detail_y - 12
        visual_bottom = body_bottom + 8
        visual_height = max(0, visual_top - visual_bottom)
        if visual_height >= 38:
            _draw_pun_visual(
                page_canvas, x + width / 2, (visual_top + visual_bottom) / 2,
                serial, width=min(240, width - 40), height=visual_height,
            )
    else:
        page_canvas.setFillColor(muted)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawString(x + 14, body_top, "A LITTLE MATHS PICTURE")
        caption = Paragraph(challenge, main_style)
        _, caption_height = caption.wrap(inner_width, 34)
        caption.drawOn(page_canvas, x + 14, body_bottom + 3)
        _draw_mini_visual(
            page_canvas, x, width, body_top - 12, body_bottom + caption_height + 14,
            concept, topic, serial, mode="picture",
        )


def _draw_mini_visual(page_canvas, x, width, top, bottom, concept, topic, serial, mode="steps", activity_text=""):
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
    prompt = str(activity_text or "").lower()
    if mode == "steps" and any(phrase in prompt for phrase in ("handshake", "shake hands", "high-five", "high five")):
        radius = min(20, max(14, available * 0.11))
        orbit = min(60, max(44, available * 0.30))
        diagram_center_y = bottom + available * 0.62
        people = ("A", "B", "C", "D", "E", "F")
        for i, person in enumerate(people):
            angle = math.radians(90 - i * 60)
            cx = center_x + orbit * math.cos(angle)
            cy = diagram_center_y + orbit * math.sin(angle)
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.circle(cx, cy, radius, stroke=1, fill=1)
            page_canvas.setFillColor(colors.HexColor("#25345B"))
            page_canvas.setFont("Helvetica-Bold", 10)
            page_canvas.drawCentredString(cx, cy - 3, person)
        page_canvas.setFillColor(colors.HexColor("#596B9D"))
        page_canvas.setFont("Helvetica-Oblique", 8.5)
        page_canvas.drawCentredString(center_x, bottom + 3, "Draw one line for each pair.")
        return
    if mode == "steps" and "trailing zero" in prompt:
        limit_match = re.search(r"(\d+)\s*!", prompt)
        limit = int(limit_match.group(1)) if limit_match else 20
        labels = [str(value) for value in range(5, limit + 1, 5)][:8]
        if not labels:
            labels = ["5", "10"]
        gap = min(58, (width - 96) / max(1, len(labels) - 1))
        start_x = center_x - gap * (len(labels) - 1) / 2
        row_y = bottom + available * 0.60
        for i, label in enumerate(labels):
            cx = start_x + i * gap
            page_canvas.setFillColor(fills[3] if int(label) % 25 == 0 else fills[i % len(fills)])
            page_canvas.circle(cx, row_y, 17, stroke=1, fill=1)
            page_canvas.setFillColor(colors.HexColor("#25345B"))
            page_canvas.setFont("Helvetica-Bold", 9)
            page_canvas.drawCentredString(cx, row_y - 3, label)
        page_canvas.setFillColor(colors.HexColor("#596B9D"))
        page_canvas.setFont("Helvetica-Oblique", 8.5)
        caption = "Multiples of 5 contribute factors to trailing zeroes."
        if limit >= 25:
            caption += " Each multiple of 25 contributes one extra factor of 5."
        page_canvas.drawCentredString(center_x, row_y - 31, caption)
        return

    if mode in ("steps", "picture") and ("circular" in text or "circle" in text):
        radius = min(52, max(28, available * 0.30))
        center_y = bottom + available * 0.54
        page_canvas.setStrokeColor(stroke)
        page_canvas.circle(center_x, center_y, radius, stroke=1, fill=0)
        for i in range(6):
            angle = math.radians(90 - i * 60)
            cx = center_x + radius * math.cos(angle)
            cy = center_y + radius * math.sin(angle)
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.circle(cx, cy, 10, stroke=1, fill=1)
            page_canvas.setFillColor(colors.HexColor("#25345B"))
            page_canvas.setFont("Helvetica-Bold", 7.5)
            page_canvas.drawCentredString(cx, cy - 2.5, str(i + 1))
        if mode == "picture":
            page_canvas.setFillColor(colors.HexColor("#596B9D"))
            page_canvas.setFont("Helvetica-Oblique", 8.5)
            labels = ["Anchor one seat.", "Track neighbour order.", "Rotation keeps the order.",
                      "A reflection reverses it.", "There is no first seat.", "Same neighbours, new view.",
                      "Fix a chair, then count.", "Turn the table, not the seating."]
            page_canvas.drawCentredString(center_x, center_y - radius - 18, labels[serial % len(labels)])
        return

    if any(word in text for word in ("factorial", "permutation", "arrangement", "combinatoric", "combination")):
        if mode == "picture" and serial != 0:
            _draw_factorial_picture(page_canvas, center_x, mid_y, width, available, serial, fills, stroke)
        elif mode == "growth" or (mode == "picture" and serial == 0):
            if mode == "picture":
                # The first visual variant is the clear vertical countdown.
                labels = ["5!", "5 × 4!", "5 × 4 × 3!"]
                rows = 3 if available >= 140 else 2 if available >= 88 else 1
                row_gap = min(90, available / (rows + 1))
                for i, label in enumerate(labels[:rows]):
                    y = top - row_gap * (i + 1)
                    box_width = min(width - 48, max(170, len(label) * 9 + 48))
                    page_canvas.setFillColor(fills[i % len(fills)])
                    page_canvas.roundRect(center_x - box_width / 2, y - 15, box_width, 30, 7, stroke=1, fill=1)
                    page_canvas.setFillColor(colors.HexColor("#25345B"))
                    page_canvas.setFont("Helvetica-Bold", 11)
                    page_canvas.drawCentredString(center_x, y - 4, label)
                    if i < rows - 1:
                        page_canvas.setStrokeColor(stroke)
                        page_canvas.line(center_x, y - 18, center_x, y - row_gap + 20)
                        page_canvas.line(center_x, y - row_gap + 20, center_x - 3, y - row_gap + 25)
                        page_canvas.line(center_x, y - row_gap + 20, center_x + 3, y - row_gap + 25)
                page_canvas.setFillColor(colors.HexColor("#596B9D"))
                page_canvas.setFont("Helvetica-Oblique", 8.5)
                page_canvas.drawCentredString(center_x, bottom + 2, "Unroll one factor at a time.")
                return
            base_y = bottom + 20
            chart_height = max(10, min(available - 28, 125))
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
        else:
            n = 4 + serial
            labels = [f"{n}!", f"{n} × {n - 1}!", f"{n} × {n - 1} × {n - 2}!"]
            rows = 3 if available >= 140 else 2 if available >= 88 else 1
            row_gap = min(90, available / (rows + 1))
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


def _draw_factorial_picture(page_canvas, center_x, center_y, width, height, serial, fills, stroke):
    """Render varied factorial visual explainers instead of a number-swapped template."""
    page_canvas.saveState()
    page_canvas.setStrokeColor(stroke)
    page_canvas.setLineWidth(1.2)
    ink = colors.HexColor("#25345B")
    labels = ["5", "4", "3", "2", "1"]
    if serial == 1:
        # A compact value comparison chart.
        values = [(3, 6), (4, 24), (5, 120), (6, 720)]
        bar_w = 42
        gap = min(72, (width - 100) / 3)
        base = center_y - min(56, height * .30)
        max_h = min(112, height * .56)
        for i, (n, value) in enumerate(values):
            cx = center_x + (i - 1.5) * gap
            bar_h = max(9, max_h * value / 720)
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(cx - bar_w / 2, base, bar_w, bar_h, 4, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 8)
            page_canvas.drawCentredString(cx, base - 12, f"{n}!")
            page_canvas.setFont("Helvetica", 7.5)
            page_canvas.drawCentredString(cx, base + bar_h + 4, f"{value:,}")
    elif serial == 2:
        # Choice slots shrink from left to right.
        count = 5
        gap = min(80, (width - 100) / (count - 1))
        start_x = center_x - gap * (count - 1) / 2
        for i, number in enumerate(range(count, 0, -1)):
            cx = start_x + i * gap
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(cx - 28, center_y - 22, 56, 44, 6, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 10)
            page_canvas.drawCentredString(cx, center_y + 2, f"{number} choices")
            page_canvas.setFont("Helvetica", 8)
            page_canvas.drawCentredString(cx, center_y - 12, f"slot {i + 1}")
    elif serial == 3:
        # Four matching cards pair factorials with their values.
        pairs = [(3, 6), (4, 24), (5, 120), (6, 720)]
        card_height = 28
        row_offset = min(38, max(0, height / 2 - card_height / 2 - 3))
        for i, (n, value) in enumerate(pairs):
            row, col = divmod(i, 2)
            cx = center_x + (col - .5) * min(150, width * .34)
            cy = center_y + (.5 - row) * row_offset
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(cx - 62, cy - card_height / 2, 124, card_height, 6, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 10)
            page_canvas.drawCentredString(cx, cy - 3, f"{n}! = {value}")
    elif serial == 4:
        # Product tiles show the factors individually.
        gap = min(66, (width - 100) / 4)
        start_x = center_x - 2 * gap
        for i, factor in enumerate(labels):
            cx = start_x + i * gap
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.circle(cx, center_y, 20, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 12)
            page_canvas.drawCentredString(cx, center_y - 4, factor)
            if i < 4:
                page_canvas.setFont("Helvetica", 11)
                page_canvas.drawCentredString(cx + gap / 2, center_y - 4, "×")
    elif serial == 5:
        # A horizontal chain demonstrates recursive reduction.
        items = ["5!", "5 × 4!", "5 × 4 × 3!"]
        gap = min(155, (width - 90) / 2)
        for i, item in enumerate(items):
            cx = center_x + (i - 1) * gap
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(cx - 51, center_y - 18, 102, 36, 7, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 10)
            page_canvas.drawCentredString(cx, center_y - 4, item)
            if i < 2:
                end_x = cx + gap - 56
                page_canvas.setStrokeColor(stroke)
                page_canvas.line(cx + 54, center_y, end_x, center_y)
                page_canvas.line(end_x - 5, center_y + 4, end_x, center_y)
                page_canvas.line(end_x - 5, center_y - 4, end_x, center_y)
    elif serial == 6:
        # A number line highlights factorial jumps rather than just listing them.
        values = [(1, "1!"), (2, "2!"), (6, "3!"), (24, "4!"), (120, "5!")]
        left = center_x - min(width * .40, 205)
        right = center_x + min(width * .40, 205)
        y = center_y
        page_canvas.setStrokeColor(stroke)
        page_canvas.line(left, y, right, y)
        for i, (_, label) in enumerate(values):
            cx = left + (right - left) * i / (len(values) - 1)
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.circle(cx, y, 10, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 8)
            page_canvas.drawCentredString(cx, y - 25, label)
    else:
        # Four clear stages show the shrinking number of choices in 4!.
        gap = min(116, (width - 100) / 3)
        card_width, card_height = min(88, gap - 12), 38
        y = center_y + 5
        for i, number in enumerate((4, 3, 2, 1)):
            cx = center_x + (i - 1.5) * gap
            page_canvas.setFillColor(fills[i % len(fills)])
            page_canvas.roundRect(cx - card_width / 2, y - card_height / 2, card_width, card_height, 6, stroke=1, fill=1)
            page_canvas.setFillColor(ink)
            page_canvas.setFont("Helvetica-Bold", 9)
            page_canvas.drawCentredString(cx, y - 3, f"{number} choice" if number == 1 else f"{number} choices")
            page_canvas.setFont("Helvetica", 7.5)
            page_canvas.drawCentredString(cx, y - card_height / 2 - 10, f"position {i + 1}")
            if i < 3:
                end_x = cx + card_width / 2 + 5
                next_x = cx + gap - card_width / 2 - 5
                page_canvas.setStrokeColor(stroke)
                page_canvas.line(end_x, y, next_x, y)
                page_canvas.line(next_x - 4, y + 3, next_x, y)
                page_canvas.line(next_x - 4, y - 3, next_x, y)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 9)
        page_canvas.drawCentredString(center_x, center_y - 35, "4 × 3 × 2 × 1 = 24 arrangements")
    page_canvas.restoreState()


def _draw_pun_visual(page_canvas, center_x, center_y, serial, width=180, height=100):
    """Draw a visual that explains the punchline instead of an unrelated starburst."""
    page_canvas.saveState()
    ink = colors.HexColor("#596B9D")
    pale = colors.HexColor("#E7ECFA")
    accent = colors.HexColor("#7285C2")
    page_canvas.setStrokeColor(ink)
    page_canvas.setFillColor(pale)
    page_canvas.setLineWidth(2)
    if serial == 0:
        page_canvas.circle(center_x - 28, center_y, 20, stroke=1, fill=0)
        page_canvas.circle(center_x + 28, center_y, 20, stroke=1, fill=0)
        page_canvas.line(center_x - 8, center_y + 3, center_x + 8, center_y + 3)
        page_canvas.line(center_x - 48, center_y + 5, center_x - 67, center_y + 13)
        page_canvas.line(center_x + 48, center_y + 5, center_x + 67, center_y + 13)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 14)
        page_canvas.drawCentredString(center_x - 28, center_y - 5, "÷")
        page_canvas.drawCentredString(center_x + 28, center_y - 5, "÷")
    elif serial == 1:
        page_canvas.roundRect(center_x - 74, center_y - 22, 62, 44, 9, stroke=1, fill=1)
        page_canvas.roundRect(center_x + 12, center_y - 22, 62, 44, 9, stroke=1, fill=1)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 11)
        page_canvas.drawCentredString(center_x - 43, center_y - 4, "A, B")
        page_canvas.drawCentredString(center_x + 43, center_y - 4, "B, A")
        page_canvas.drawCentredString(center_x, center_y - 4, "=")
    elif serial == 2:
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 15)
        page_canvas.drawCentredString(center_x, center_y + 16, "5!")
        page_canvas.setStrokeColor(accent)
        page_canvas.line(center_x - 78, center_y + 2, center_x + 78, center_y + 2)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 12)
        page_canvas.drawCentredString(center_x, center_y - 20, "5 × 4 × 3 × 2 × 1")
    elif serial == 3:
        path = page_canvas.beginPath()
        path.moveTo(center_x, center_y)
        path.curveTo(center_x - 72, center_y + 62, center_x - 72, center_y - 62, center_x, center_y)
        path.curveTo(center_x + 72, center_y + 62, center_x + 72, center_y - 62, center_x, center_y)
        page_canvas.setStrokeColor(accent)
        page_canvas.drawPath(path, stroke=1, fill=0)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 14)
        page_canvas.drawCentredString(center_x, center_y - 5, "INFINITE")
    elif serial == 4:
        page_canvas.setStrokeColor(ink)
        page_canvas.line(center_x - 90, center_y + 13, center_x + 90, center_y + 13)
        page_canvas.line(center_x - 90, center_y - 13, center_x + 90, center_y - 13)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 10)
        page_canvas.drawCentredString(center_x, center_y - 4, "NEVER MEET")
    elif serial == 5:
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 22)
        page_canvas.drawCentredString(center_x - 48, center_y - 8, "7")
        page_canvas.drawCentredString(center_x + 48, center_y - 8, "9")
        page_canvas.setFillColor(colors.HexColor("#FCE5EA"))
        page_canvas.circle(center_x, center_y, 20, stroke=1, fill=1)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 11)
        page_canvas.drawCentredString(center_x, center_y - 4, "8")
    elif serial == 6:
        page_canvas.roundRect(center_x - 53, center_y - 34, 106, 68, 8, stroke=1, fill=1)
        page_canvas.setFillColor(colors.white)
        page_canvas.roundRect(center_x - 42, center_y + 7, 84, 17, 3, stroke=0, fill=1)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 13)
        page_canvas.drawCentredString(center_x, center_y + 11, "0")
        for row in range(2):
            for col in range(3):
                page_canvas.setFillColor(accent)
                page_canvas.circle(center_x - 22 + col * 22, center_y - 9 - row * 17, 4, stroke=0, fill=1)
    else:
        page_canvas.roundRect(center_x - 45, center_y - 34, 90, 68, 6, stroke=1, fill=1)
        page_canvas.setFillColor(ink)
        page_canvas.setFont("Helvetica-Bold", 10)
        page_canvas.drawCentredString(center_x, center_y + 12, "x + y = ?")
        page_canvas.setLineWidth(1.5)
        page_canvas.line(center_x - 8, center_y - 17, center_x, center_y - 21)
        page_canvas.line(center_x, center_y - 21, center_x + 8, center_y - 17)
        page_canvas.circle(center_x - 10, center_y - 4, 1.5, stroke=0, fill=1)
        page_canvas.circle(center_x + 10, center_y - 4, 1.5, stroke=0, fill=1)
        page_canvas.setFont("Helvetica", 7.5)
        page_canvas.drawCentredString(center_x, center_y - 29, "MATHS BOOK")
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
        # Seed from the source booklet so activity types and prompts are
        # shuffled per booklet, while regenerating the same source stays stable.
        seed_bytes = hashlib.sha256(pdf_bytes + topic.encode("utf-8")).digest()
        activity_rng = random.Random(int.from_bytes(seed_bytes[:8], "big"))
        type_order = list(range(4))
        activity_rng.shuffle(type_order)

        for index, original_page in enumerate(source.pages):
            text = page_texts[index]
            if "plain answers" in text.casefold() or "quick answers" in text.casefold():
                output.add_page(original_page)
                continue
            # Make the operation idempotent: never add a second panel to a page
            # that already contains one.
            if _has_activity_panel(text):
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
            minimum_filler_height = max(120.0, body_height * MIN_UNUSED_RATIO - CONTENT_TO_PANEL_GAP)
            if panel_height < minimum_filler_height:
                output.add_page(original_page)
                continue

            # Shuffle prompts within a randomized type order. Type-specific
            # minimums keep larger activities out of cramped spaces, while the
            # shuffled round guarantees a mix when all four types fit.
            selected = None
            eligible_types = {
                type_index for type_index in type_order
                if panel_height >= ACTIVITY_MIN_HEIGHT[_activity_kind(type_index)]
            }
            if eligible_types:
                start_at = activity_index % len(type_order)
                randomized_order = type_order[start_at:] + type_order[:start_at]
                for type_index in randomized_order:
                    if type_index not in eligible_types:
                        continue
                    serials = list(range(8))
                    activity_rng.shuffle(serials)
                    for serial in serials:
                        variant = serial * 4 + type_index
                        candidate = _activity_for(active_concept, topic, text, variant)
                        if candidate is not None and candidate[1] not in used_challenges:
                            selected = (variant, candidate)
                            break
                    if selected:
                        break
            if selected is None:
                output.add_page(original_page)
                continue
            variant, candidate = selected
            used_challenges.add(candidate[1])
            activity_index += 1

            overlay_buffer = BytesIO()
            overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
            _draw_activity_panel(
                overlay_canvas, page_width, PAGE_MARGIN, panel_height, active_concept, topic, text,
                variant,
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
