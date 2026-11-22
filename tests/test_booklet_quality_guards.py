import unittest
from fractions import Fraction

from pdf_generator import (
    _collinear_3d_parameter,
    build_latex_theory_booklet_source,
    format_latex_question_with_subparts,
    format_latex_solution_steps,
    validate_booklet_collinearity,
)


class TestBookletQualityGuards(unittest.TestCase):
    def test_rejects_impossible_3d_collinearity_prompt(self):
        question = (
            r"Three points $P(2,3,-1)$, $Q(5,-1,3)$ and $R(k,11,-11)$ "
            r"are collinear. Determine $k$."
        )
        booklet = {"concepts": [{"teacher_examples": [{"problem_text": question}]}]}
        with self.assertRaisesRegex(ValueError, "fixed coordinates cannot be collinear"):
            validate_booklet_collinearity(booklet)
        with self.assertRaisesRegex(ValueError, "fixed coordinates cannot be collinear"):
            build_latex_theory_booklet_source(booklet, has_logo=False)

    def test_accepts_consistent_prompt_and_checks_answer(self):
        question = (
            r"Three points $P(2,3,-1)$, $Q(5,-1,3)$ and $R(k,11,-9)$ "
            r"are collinear. Determine $k$."
        )
        self.assertEqual(_collinear_3d_parameter(question), ("k", Fraction(-4)))
        booklet = {"concepts": [{"practice_questions": [{"text": question, "final_answer": "$k=-4$"}]}]}
        validate_booklet_collinearity(booklet)
        booklet["concepts"][0]["practice_questions"][0]["final_answer"] = "$k=4$"
        with self.assertRaisesRegex(ValueError, "stated answer conflicts"):
            validate_booklet_collinearity(booklet)
        booklet["concepts"][0]["practice_questions"][0] = {
            "text": question, "worked_solution": r"Thus, $k=4$."
        }
        with self.assertRaisesRegex(ValueError, "stated answer conflicts"):
            validate_booklet_collinearity(booklet)

    def test_subparts_and_run_on_working_get_separate_lines(self):
        question = (
            r"Given $A(3,-2,5)$ and $B(-1,4,2)$, determine: "
            r"(a) The position vector $\vec{OA}$. "
            r"(b) The displacement vector $\vec{AB}$."
        )
        formatted = "\n".join(format_latex_question_with_subparts(question, as_item=False))
        self.assertEqual(formatted.count(r"\item"), 2)
        self.assertIn(r"\vec{AB}", formatted)

        solution = r"Set up the equations: 1) $2p-q=7$ [1 mark] 2) $-p+3q=-11$. Substitute $q$."
        working = format_latex_solution_steps(solution)
        self.assertIn("equations:", working)
        self.assertIn("Substitute", working)
        self.assertGreaterEqual(working.count(r"\par"), 3)

    def test_render_source_uses_australian_spelling_and_bounds_long_heading(self):
        booklet = {
            "year_level": "Year 12",
            "topic": "Vectors",
            "concepts": [{
                "concept_name": "Geometric proofs using vectors, medians, diagonals, orthocentres and perpendicularity",
                "theory_content": "Emphasize visualizing the vector.",
                "teacher_examples": [],
            }],
        }
        source = build_latex_theory_booklet_source(booklet, has_logo=False)
        self.assertIn("Emphasise visualising", source)
        self.assertNotIn("Emphasize", source)
        self.assertIn(r"\parbox[t]{0.96\linewidth}", source)


if __name__ == "__main__":
    unittest.main()
