import io
import re
import unittest

import pypdfium2 as pdfium
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from page_fillers import _activity_for, fill_sparse_private_theory_pages


def _sample_pdf(text_y):
    output = io.BytesIO()
    page = canvas.Canvas(output, pagesize=A4)
    page.drawString(54, text_y, "Concept A: Factorial notation")
    page.save()
    return output.getvalue()


class TestPrivateTheoryPageFillers(unittest.TestCase):
    def test_selects_correct_activity_for_concept(self):
        self.assertIn("Find the error", _activity_for("Factorial notation", "Combinatorics")[1])
        self.assertNotEqual(
            _activity_for("Factorial notation", "Combinatorics", variant=0)[1],
            _activity_for("Factorial notation", "Combinatorics", variant=1)[1],
        )
        self.assertIn("different group", _activity_for("Counting unordered selections", "Combinatorics")[1])
        self.assertIn("circular arrangement", _activity_for("Arrangements in a circle", "Combinatorics")[1])
        self.assertIn("BANANA", _activity_for(
            "Arrangements", "Combinatorics", "arrangements of letters in the word MATHEMATICS"
        )[1])

    def test_adds_activity_to_underfilled_page_without_adding_pages(self):
        original = _sample_pdf(430)
        result = fill_sparse_private_theory_pages(original, {
            "topic": "Combinatorics",
            "concepts": [{"name": "Factorial notation"}],
        })
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        self.assertTrue(any(heading in text for heading in
                            ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")))

    def test_leaves_well_used_page_unchanged(self):
        original = _sample_pdf(180)
        result = fill_sparse_private_theory_pages(original, {
            "topic": "Combinatorics",
            "concepts": [{"name": "Factorial notation"}],
        })
        self.assertEqual(result, original)

    def test_panel_stays_inside_page_bounds(self):
        result = fill_sparse_private_theory_pages(_sample_pdf(430), {
            "topic": "Combinatorics",
            "concepts": [{"name": "Factorial notation"}],
        })
        document = pdfium.PdfDocument(result)
        self.assertEqual(len(document), 1)
        self.assertGreater(document[0].get_size()[1], 800)
        text = document[0].get_textpage().get_text_range()
        self.assertTrue(any(heading in text for heading in
                            ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")))

    def test_sparse_pages_get_distinct_brain_breaks(self):
        output = io.BytesIO()
        page = canvas.Canvas(output, pagesize=A4)
        for _ in range(8):
            page.drawString(54, 430, "Concept A: Factorial notation")
            page.showPage()
        page.save()
        result = fill_sparse_private_theory_pages(output.getvalue(), {
            "topic": "Combinatorics",
            "concepts": [{"name": "Factorial notation"}],
        })
        texts = [p.extract_text() for p in PdfReader(io.BytesIO(result)).pages]
        card_content = []
        for text in texts:
            for heading in ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS"):
                if heading in text:
                    card_content.append(text.split(heading, 1)[1].strip())
                    break
        self.assertEqual(len(set(card_content)), 8)
        headings = [heading for heading in ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")
                    if any(heading in text for text in texts)]
        self.assertEqual(len(headings), 4)
        self.assertTrue(any("DID YOU KNOW" in t for t in texts))
        self.assertTrue(any("MATHS PUN" in t for t in texts))
        self.assertTrue(any("A LITTLE MATHS PICTURE" in t for t in texts))

    def test_activity_type_is_randomized_but_sized_to_available_space(self):
        # About 30% of the usable page remains. A compact option should fit,
        # while the larger puzzle layout should be held for a roomier page.
        result = fill_sparse_private_theory_pages(_sample_pdf(280), {
            "topic": "Combinatorics",
            "concepts": [{"name": "Factorial notation"}],
        })
        text = PdfReader(io.BytesIO(result)).pages[0].extract_text()
        self.assertTrue(any(heading in text for heading in
                            ("QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")))
        self.assertNotIn("QUICK MATHS PUZZLE", text)

    def test_activity_bank_returns_four_distinct_activity_types(self):
        samples = [_activity_for("Factorial notation", "Combinatorics", variant=i) for i in range(4)]
        self.assertIn("Find the error", samples[0][1])
        self.assertIn("10! is 3,628,800", samples[1][1])
        self.assertIn("improve division", samples[2][1])
        self.assertIn("Unroll a factorial", samples[3][1])

    def test_factorial_visuals_and_puns_are_substantively_distinct(self):
        visuals = [_activity_for("Factorial notation", "Combinatorics", variant=3 + 4 * serial)[1]
                   for serial in range(8)]
        facts = [_activity_for("Factorial notation", "Combinatorics", variant=1 + 4 * serial)[1]
                 for serial in range(8)]
        puns = [_activity_for("Factorial notation", "Combinatorics", variant=2 + 4 * serial)[1]
                for serial in range(8)]
        self.assertEqual(len(set(visuals)), 8)
        self.assertEqual(len(set(facts)), 8)
        self.assertEqual(len(set(puns)), 8)
        self.assertIn("consecutive factorial values", visuals[1])
        self.assertIn("available choices shrink", visuals[2])

    def test_pun_panel_uses_a_distinct_label_and_no_generic_starburst(self):
        from page_fillers import _draw_activity_panel

        output = io.BytesIO()
        page = canvas.Canvas(output, pagesize=A4)
        _draw_activity_panel(page, A4[0], 54, 330, "Factorial notation", "Combinatorics", "", variant=2)
        page.save()
        text = PdfReader(io.BytesIO(output.getvalue())).pages[0].extract_text()
        self.assertIn("MATHS PUN", text)
        self.assertIn("WORDPLAY", text)
        self.assertNotIn("MATHS PUN\nMATHS PUN", text)

    def test_student_puzzle_card_does_not_reveal_its_answer(self):
        from page_fillers import _draw_activity_panel

        output = io.BytesIO()
        page = canvas.Canvas(output, pagesize=A4)
        _draw_activity_panel(page, A4[0], 54, 330, "Arrangements together", "Combinatorics", "", variant=4)
        page.save()
        text = PdfReader(io.BytesIO(output.getvalue())).pages[0].extract_text()
        self.assertIn("Six people all shake hands", text)
        self.assertIn("Draw one line for each pair", text)
        self.assertNotIn("Answer:", text)
        self.assertNotIn("Each handshake is a pair", text)

    def test_pun_is_plainly_understandable_for_students(self):
        pun = _activity_for("Factorial notation", "Combinatorics", variant=30)[1]
        self.assertEqual(pun, "Why was the maths book sad? It had too many problems.")

    def test_filling_is_idempotent(self):
        booklet = {"topic": "Combinatorics", "concepts": [{"name": "Factorial notation"}]}
        first_pass = fill_sparse_private_theory_pages(_sample_pdf(430), booklet)
        second_pass = fill_sparse_private_theory_pages(first_pass, booklet)
        text = PdfReader(io.BytesIO(second_pass)).pages[0].extract_text()
        self.assertEqual(sum(text.count(heading) for heading in
                             ("QUICK MATHS PUZZLE", "QUICK MATHS FACT", "MATHS PUN", "VISUAL MATHS")), 1)


if __name__ == "__main__":
    unittest.main()
