import io
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
        self.assertIn("9!/7!", _activity_for("Factorial notation", "Combinatorics")[1])
        self.assertIn("team", _activity_for("Counting unordered selections", "Combinatorics")[1])
        self.assertIn("circular table", _activity_for("Arrangements in a circle", "Combinatorics")[1])
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
        self.assertIn("MATHS BRAIN BREAK", text)
        self.assertIn("CHALLENGE", text)

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
        self.assertIn("Self-check: 72", text)


if __name__ == "__main__":
    unittest.main()
