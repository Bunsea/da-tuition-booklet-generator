import unittest
import os
from pdf_generator import (
    split_implication_chain,
    sanitize_latex_compilation_safety,
    count_unescaped_dollars,
    generate_latex_theory_booklet_pdf
)

class TestTheoryCompilationSafety(unittest.TestCase):
    def test_split_implication_chain_prose_and_math(self):
        line1 = "Set $2 + k = 3 \\implies k = 1.$"
        steps1 = split_implication_chain(line1)
        self.assertTrue(len(steps1) >= 2)
        for s in steps1:
            self.assertEqual(count_unescaped_dollars(s) % 2, 0, f"Unbalanced dollars in {s}")

        line2 = "For real outputs, $25 - (x - 4)^2 \\ge 0 \\implies (x - 4)^2 \\le 25 \\implies -1 \\le x \\le 9$."
        steps2 = split_implication_chain(line2)
        self.assertEqual(len(steps2), 3)
        for s in steps2:
            self.assertEqual(count_unescaped_dollars(s) % 2, 0, f"Unbalanced dollars in {s}")

        line3 = "Denominator 2 - y \\neq 0 \\implies y \\neq 2"
        steps3 = split_implication_chain(line3)
        self.assertEqual(len(steps3), 2)
        for s in steps3:
            self.assertEqual(count_unescaped_dollars(s) % 2, 0, f"Unbalanced dollars in {s}")

    def test_sanitize_latex_compilation_safety_balances_dollars(self):
        broken_tex = (
            "\\begin{document}\n"
            "\\noindent\\hspace*{0.25cm}For real outputs, $25 - (x - 4)^2 \\ge 0\n"
            "\\noindent\\hspace*{0.25cm}$\\displaystyle \\implies -1 \\le x \\le 9$.\n"
            "\\end{document}\n"
        )
        safe_tex = sanitize_latex_compilation_safety(broken_tex)
        for line in safe_tex.splitlines():
            if line.strip() and not line.strip().startswith("%"):
                self.assertEqual(count_unescaped_dollars(line) % 2, 0, f"Odd dollars in line: {line}")

    def test_sanitize_latex_compilation_safety_closes_display_math_and_envs(self):
        broken_tex = (
            "\\begin{document}\n"
            "\\begin{enumerate}\n"
            "\\item \\begin{practicesolutionbox}\n"
            "\\[\n"
            "x = 5\n"
            "\\end{document}\n"
        )
        safe_tex = sanitize_latex_compilation_safety(broken_tex)
        self.assertIn("\\]", safe_tex)
        self.assertIn("\\end{practicesolutionbox}", safe_tex)
        self.assertIn("\\end{enumerate}", safe_tex)

    def test_teacher_theory_booklet_latex_compiles_successfully(self):
        mock_booklet = {
            "topic": "Functions & Relations",
            "year_level": "Year 11 Advanced",
            "concepts": [
                {
                    "title": "Domain and Range",
                    "explanation": "A relation is a function if every input has at most one output.",
                    "key_rules": ["Vertical Line Test: cuts at most once."],
                    "worked_examples": [
                        {
                            "q_num": 1,
                            "question": "Find the domain of $f(x) = \\sqrt{25 - (x - 4)^2}$.",
                            "solution": (
                                "For real outputs, $25 - (x - 4)^2 \\ge 0 \\implies (x - 4)^2 \\le 25 \\implies -1 \\le x \\le 9$.\n"
                                "Domain: $[-1, 9]$."
                            ),
                            "final_answer": "Domain: $[-1, 9]$"
                        }
                    ],
                    "practice_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Medium",
                            "text": "Find the range of $y = x^2 + 3$.",
                            "worked_solution": (
                                "Since $x^2 \\ge 0$ for all real $x$ [1 mark]:\n"
                                "$y \\ge 3$ [1 mark for final range]."
                            ),
                            "final_answer": "$y \\ge 3$"
                        },
                        {
                            "q_num": 2,
                            "difficulty": "Hard",
                            "text": "State the domain of $y = \\frac{1}{x - 3}$.",
                            "worked_solution": (
                                "Denominator cannot be zero [1 mark]:\n"
                                "$x - 3 \\neq 0 \\implies x \\neq 3$ [1 mark]."
                            ),
                            "final_answer": "All real $x \\neq 3$"
                        }
                    ]
                }
            ]
        }
        pdf_bytes = generate_latex_theory_booklet_pdf(mock_booklet, mode="teacher")
        self.assertIsNotNone(pdf_bytes, "Teacher theory booklet LaTeX compilation should not fail or return None")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Output must be valid PDF bytes")

    def test_financial_currency_and_percent_question_no_cutoff(self):
        """Verify that questions with currency ($7 500) and percentages (4.8% p.a.) never get cut off."""
        mock_booklet = {
            "topic": "Financial Mathematics",
            "year_level": "Year 11 Advanced",
            "concepts": [
                {
                    "title": "Compound Interest",
                    "explanation": "Compound interest is calculated on both initial principal and accumulated interest.",
                    "key_rules": ["$FV = PV(1 + r)^n$"],
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Direct Future Value and Interest Calculation",
                            "problem_text": (
                                "An amount of $7 500 is invested at 4.8% p.a. compounded monthly for 5 years. Find: "
                                "(a) The future value of the investment. (b) The total compound interest earned."
                            ),
                            "worked_solution": (
                                "Identify parameters [1 mark]:\n"
                                "$P = \\$7500$, $r = \\frac{0.048}{12} = 0.004$, $n = 5 \\times 12 = 60$.\n"
                                "(a) Future value [1 mark]:\n"
                                "$FV = 7500(1 + 0.004)^{60} \\approx \\$9529.23$.\n"
                                "(b) Total interest [1 mark]:\n"
                                "$I = FV - P = 9529.23 - 7500 = \\$2029.23$."
                            ),
                            "teaching_notes": "Emphasize converting annual rate to monthly rate."
                        }
                    ],
                    "practice_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Easy",
                            "text": "Calculate the interest earned on $12 000 at 5.5% p.a. for 3 years.",
                            "worked_solution": "$I = P \\times r \\times t = 12000 \\times 0.055 \\times 3 = \\$1980$ [1 mark].",
                            "final_answer": "$\\$1980$"
                        }
                    ]
                }
            ]
        }
        pdf_bytes = generate_latex_theory_booklet_pdf(mock_booklet, mode="teacher")
        self.assertIsNotNone(pdf_bytes, "Teacher theory booklet LaTeX compilation should not fail")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Output must be valid PDF bytes")

        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(p.extract_text() for p in reader.pages)
        self.assertIn("compounded monthly for 5 years", full_text, "Question text must not be cut off at percentage")
        self.assertIn("The future value of the investment", full_text, "Subpart (a) must be rendered")
        self.assertIn("The total compound interest earned", full_text, "Subpart (b) must be rendered")

    def test_financial_percentage_in_math_mode_not_corrupted(self):
        """Verify that questions with percentage math wrappers ($5.4%$, $5.4\%$, or $5.4%) do not corrupt into math italics."""
        mock_booklet = {
            "topic": "Financial Mathematics",
            "year_level": "Year 11 Advanced",
            "concepts": [
                {
                    "title": "Compound Interest",
                    "explanation": "Compound interest calculations.",
                    "key_rules": ["$FV = PV(1 + r)^n$"],
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Direct Formula Substitution for Future Value and Interest",
                            "problem_text": (
                                "An investor deposits $12 500 into a high-interest fixed term account paying "
                                "$5.4\\%$ p.a. compounded annually for 4 years. "
                                "(a) Calculate the total value of the investment at the end of the term, correct to the nearest cent. "
                                "(b) Determine the total compound interest earned over the 4 years."
                            ),
                            "worked_solution": "$FV = 12500(1.054)^4 = \\$15448.29$.",
                            "teaching_notes": ""
                        }
                    ],
                    "practice_questions": []
                }
            ]
        }
        pdf_bytes = generate_latex_theory_booklet_pdf(mock_booklet, mode="teacher")
        self.assertIsNotNone(pdf_bytes, "Teacher theory booklet LaTeX compilation should succeed")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Output must be valid PDF bytes")

        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(p.extract_text() for p in reader.pages)
        # Verify text is not collapsed into math italics
        self.assertIn("compounded annually", full_text, "Words must have normal spacing, not collapsed math italics")
        self.assertIn("for 4 years", full_text, "Remaining question text must be present")
        self.assertIn("paying 5.4% p.a.", full_text, "Percentage must render in text mode without math italic corruption")
        self.assertIn("correct to the nearest cent", full_text, "Subpart (a) text must be present")
        self.assertIn("Determine the total compound interest", full_text, "Subpart (b) text must be present")

    def test_worked_solution_steps_separated_on_new_lines(self):
        """Verify that multi-step worked solutions have each step separated on a new line and not glued together."""
        from pdf_generator import format_latex_solution_steps, clean_set_notation

        # Verify clean_set_notation does NOT strip newlines between math expressions
        raw_multiline = "$A = 30\\,000, r = 0.052, n = 4$\n$A = P(1 + r)^n$\n$30\\,000 = P(1 + 0.052)^4$"
        cleaned = clean_set_notation(raw_multiline)
        self.assertIn("\n", cleaned, "clean_set_notation must preserve newlines between math expressions")

        # Verify format_latex_solution_steps separates steps
        formatted = format_latex_solution_steps(raw_multiline)
        self.assertNotIn("n = 4A = P", formatted, "Steps must not be glued together")
        self.assertIn("A = 30", formatted)
        self.assertIn("A = P", formatted)
        self.assertIn("30\\,000 = P", formatted)

        # Full booklet compilation test
        mock_booklet = {
            "topic": "Financial Mathematics",
            "year_level": "Year 11 Advanced",
            "concepts": [
                {
                    "title": "Present Value Calculations",
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Present Value Evaluation",
                            "problem_text": "Find the present value needed to accumulate $30 000 in 4 years at 5.2% p.a.",
                            "teaching_notes": "Avoid premature rounding.",
                            "worked_solution": (
                                "$A = 30\\,000, r = 0.052, n = 4$\n"
                                "$A = P(1 + r)^n$\n"
                                "$30\\,000 = P(1 + 0.052)^4$\n"
                                "$30\\,000 = P(1.052)^4$\n"
                                "$P = \\frac{30\\,000}{(1.052)^4}$\n"
                                "$P = 24\\,493.99...$\n"
                                "To the nearest dollar, $P = \\$24\\,494$."
                            )
                        }
                    ],
                    "practice_questions": []
                }
            ]
        }
        pdf_bytes = generate_latex_theory_booklet_pdf(mock_booklet, mode="teacher")
        self.assertIsNotNone(pdf_bytes)
        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(p.extract_text() for p in reader.pages)
        # Ensure the glued string from the bug does NOT appear
        self.assertNotIn("n = 4A = P", full_text, "Steps must not be glued together into a single line")
        self.assertIn("A=P", full_text)
        self.assertIn("nearest dollar", full_text)

    def test_account_stem_bullet_formatting(self):
        """Verify Account 1, Account 2, and concluding question prompt each start on separate lines."""
        from pdf_generator import split_stem_bullet_items, format_latex_question_with_subparts

        ex3_text = (
            "Chloe has $12 000 to invest. She splits the money into two separate accounts for 3 years: "
            "- Account 1: $7000 invested at 4.5% p.a. simple interest. "
            "- Account 2: $5000 invested at 4.2% p.a. compounded annually. "
            "Calculate the total interest earned from both accounts combined at the end of the 3 years."
        )

        intro, bullets, trailing = split_stem_bullet_items(ex3_text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("Account 1:", bullets[0])
        self.assertIn("Account 2:", bullets[1])
        self.assertTrue(trailing.startswith("Calculate"))

        lines = format_latex_question_with_subparts(ex3_text, as_item=False)
        formatted_str = "\n".join(lines)
        self.assertIn(r"\textbullet\enspace \textbf{Account 1:}", formatted_str)
        self.assertIn(r"\textbullet\enspace \textbf{Account 2:}", formatted_str)
        self.assertIn(r"\par\nopagebreak\vspace{0.08cm}\noindent Calculate", formatted_str)

    def test_hsc_removal_junior_vs_senior(self):
        """Verify 'NSW HSC / Trial Style Question' is stripped for junior years and kept for senior years."""
        from pdf_generator import format_teacher_example_heading

        raw_title = "Exam Style: NSW HSC / Trial Style Question"

        # Junior years must have HSC/Trial label stripped
        for yl in ["Year 7", "Year 8", "Year 9", "Year 10", "Year 10 (Advanced)"]:
            h_junior = format_teacher_example_heading(3, raw_title, year_level=yl)
            self.assertEqual(h_junior, "Example 3: Exam Questions", f"Failed for junior year: {yl}")
            self.assertNotIn("HSC", h_junior)
            self.assertNotIn("Trial", h_junior)

        # Senior years must preserve the label
        for yl in ["Year 11", "Year 11 Advanced", "Year 12", "Year 12 Extension 1"]:
            h_senior = format_teacher_example_heading(3, raw_title, year_level=yl)
            self.assertEqual(h_senior, "Example 3: Exam Questions (NSW HSC / Trial Style Question)", f"Failed for senior year: {yl}")

    def test_title_raggedright_prevents_stretched_words(self):
        """Verify that \\raggedright is injected inside title minipage to prevent justified stretching."""
        from pdf_generator import build_latex_theory_booklet_source

        mock_booklet = {
            "title": "Year 10 (Advanced) Maths - Consumer Arithmetic & Financial Mathematics Theory & Practice Booklet",
            "topic": "Consumer Arithmetic & Financial Mathematics",
            "year_level": "Year 10",
            "concepts": [
                {
                    "title": "Compound Interest",
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Practice",
                            "problem_text": "Find interest on $1000.",
                            "worked_solution": "$I = PRN$"
                        }
                    ]
                }
            ]
        }
        tex_source = build_latex_theory_booklet_source(mock_booklet, mode="teacher", font_theme="charter")
        self.assertIn(r"\begin{minipage}[t]{0.70\textwidth}", tex_source)
        # Ensure \raggedright is present inside the title minipage before the title text
        expected_header = r"\begin{minipage}[t]{0.70\textwidth}" + "\n" + r"\vspace{0pt}" + "\n" + r"\raggedright"
        self.assertIn(expected_header, tex_source)

    def test_complete_year10_booklet_pdf_compilation(self):
        """Full end-to-end PDF compilation for Year 10 booklet with multi-account question and multi-line title."""
        mock_booklet = {
            "title": "Year 10 (Advanced) Maths - Consumer Arithmetic & Financial Mathematics Theory & Practice Booklet",
            "topic": "Consumer Arithmetic & Financial Mathematics",
            "year_level": "Year 10",
            "concepts": [
                {
                    "title": "Simple and Compound Interest Comparison",
                    "theory_content": "- **Core Definition**: Interest earned over time.",
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Practice: Basic Simple Interest",
                            "problem_text": "Calculate the simple interest on $5000 at 4% p.a. for 2 years.",
                            "worked_solution": "$I = P \\times R \\times N = 5000 \\times 0.04 \\times 2 = \\$400$."
                        },
                        {
                            "example_num": 2,
                            "title": "Further Practice: Compound Interest",
                            "problem_text": "Calculate the compound interest on $5000 at 4% p.a. compounded annually for 2 years.",
                            "worked_solution": "$A = P(1 + r)^n = 5000(1.04)^2 = \\$5408$.\n$I = 5408 - 5000 = \\$408$."
                        },
                        {
                            "example_num": 3,
                            "title": "Exam Style: NSW HSC / Trial Style Question",
                            "problem_text": (
                                "Chloe has $12 000 to invest. She splits the money into two separate accounts for 3 years: "
                                "- Account 1: $7000 invested at 4.5% p.a. simple interest. "
                                "- Account 2: $5000 invested at 4.2% p.a. compounded annually. "
                                "Calculate the total interest earned from both accounts combined at the end of the 3 years."
                            ),
                            "worked_solution": (
                                "For Account 1 (Simple Interest):\n"
                                "$I_1 = 7000 \\times 0.045 \\times 3 = \\$945$.\n"
                                "For Account 2 (Compound Interest):\n"
                                "$A_2 = 5000 \\times (1 + 0.042)^3 = 5000 \\times 1.131366... = \\$5656.83$.\n"
                                "$I_2 = 5656.83 - 5000 = \\$656.83$.\n"
                                "Total Interest earned:\n"
                                "$I_{\\text{total}} = 945 + 656.83 = \\$1601.83$."
                            )
                        }
                    ],
                    "practice_questions": []
                }
            ]
        }
        pdf_bytes = generate_latex_theory_booklet_pdf(mock_booklet, mode="teacher", font_theme="charter")
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(len(pdf_bytes) > 5000)

        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(p.extract_text() for p in reader.pages)

        # 1. Verify title appears
        self.assertIn("Consumer Arithmetic", full_text)
        self.assertIn("Financial Mathematics", full_text)

        # 2. Verify junior year does not contain "NSW HSC / Trial Style Question"
        self.assertNotIn("NSW HSC", full_text)
        self.assertNotIn("Trial Style Question", full_text)
        self.assertIn("Example 3: Exam Questions", full_text)

        # 3. Verify accounts and question prompt appear
        self.assertIn("Account 1:", full_text)
        self.assertIn("Account 2:", full_text)
        self.assertIn("Calculate the total interest earned", full_text)

    def test_fund_a_and_fund_b_bullet_formatting(self):
        """Verify Fund A, Fund B, and concluding question prompt each start on separate lines."""
        from pdf_generator import split_stem_bullet_items, format_latex_question_with_subparts

        ex2_text = (
            "A 25-year-old worker has an existing super balance of $40 000. No further contributions are made. "
            "The funds are invested for 30 years with gross investment returns of 7.5% p.a. "
            "- Fund A charges total annual fees of 0.5% p.a. "
            "- Fund B charges total annual fees of 1.5% p.a. "
            "Calculate the final balance in each fund after 30 years, and determine the difference caused by the 1% fee differential."
        )

        intro, bullets, trailing = split_stem_bullet_items(ex2_text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("Fund A", bullets[0])
        self.assertIn("Fund B", bullets[1])
        self.assertTrue(trailing.startswith("Calculate"))

        lines = format_latex_question_with_subparts(ex2_text, as_item=False)
        formatted_str = "\n".join(lines)
        self.assertIn(r"\textbullet\enspace \textbf{Fund A}", formatted_str)
        self.assertIn(r"\textbullet\enspace \textbf{Fund B}", formatted_str)
        self.assertIn(r"\par\nopagebreak\vspace{0.08cm}\noindent Calculate", formatted_str)

    def test_watermark_is_resized_19_2cm(self):
        """Verify that background logo watermark is sized at 80% (19.2cm) across theory booklets."""
        from pdf_generator import build_latex_theory_booklet_source

        mock_booklet = {
            "title": "Year 10 Maths - Functions",
            "topic": "Functions",
            "year_level": "Year 10",
            "concepts": [{"title": "Concept 1"}]
        }
        tex_source = build_latex_theory_booklet_source(mock_booklet, mode="student_class", font_theme="charter")
        self.assertIn("width=19.2cm", tex_source)

    def test_student_class_and_student_private_editions(self):
        """Verify Student Class omits note/work boxes and Student Private has filled theory notes."""
        from pdf_generator import build_latex_theory_booklet_source

        mock_booklet = {
            "title": "Year 10 Maths - Financial Mathematics",
            "topic": "Financial Mathematics",
            "year_level": "Year 10",
            "concepts": [
                {
                    "title": "Compound Interest",
                    "theory_content": "- **Core Definition**: Interest on interest.",
                    "key_formulas": ["$A = P(1+r)^n$"],
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Practice",
                            "problem_text": "Calculate A.",
                            "worked_solution": "$A = 1000$"
                        }
                    ],
                    "practice_questions": []
                }
            ]
        }

        # 1. Student Class edition: demonstrations/questions only; students use their own notebook.
        tex_class = build_latex_theory_booklet_source(mock_booklet, mode="student_class")
        self.assertNotIn(r"\begin{theorybox}[", tex_class)
        self.assertNotIn("THE BIG IDEA (HOW TO THINK ABOUT IT)", tex_class)
        self.assertNotIn("DA MASTER METHOD", tex_class)
        self.assertIn("Teacher Demonstration Examples", tex_class)
        self.assertNotIn("Interest on interest", tex_class)
        self.assertNotIn(r"\begin{workingbox}", tex_class)
        self.assertIn("THEORY STUDENT CLASS", tex_class)

        # 2. Student Private edition: pre-printed theory notes, zero working boxes
        tex_private = build_latex_theory_booklet_source(mock_booklet, mode="student_private")
        self.assertIn("Interest on interest", tex_private)
        self.assertIn(r"A = P(1+r)^n", tex_private)
        self.assertNotIn(r"\vspace*{4.0cm}", tex_private)
        self.assertNotIn(r"\begin{workingbox}", tex_private)
        self.assertIn("THEORY STUDENT PRIVATE", tex_private)

        # 3. Teacher edition: filled theory + model solutions + zero working boxes
        tex_teacher = build_latex_theory_booklet_source(mock_booklet, mode="teacher")
        self.assertIn("Interest on interest", tex_teacher)
        self.assertIn(r"\begin{solutionbox}", tex_teacher)
        self.assertNotIn(r"\begin{workingbox}", tex_teacher)
        self.assertIn("TEACHER MASTER", tex_teacher)

    def test_practice_solution_marking_breakdown_safety(self):
        """Verify that [1 mark for part (a), 2 marks for part (b)...] does not fragment into broken lines or display math brackets."""
        from pdf_generator import format_latex_practice_solution, split_question_subparts

        # 1. Test solution with trailing mark allocation block
        raw_sol = """
(a) Find gradient: $m = 2$.
(b) Using part (a), find equation: $y = 2x + 1$.
(c) From (b), find intercept: $(0, 1)$.
[1 mark for part (a), 2 marks for part (b), 1 mark for part (c)]
"""
        formatted = format_latex_practice_solution(raw_sol)
        # Must not contain broken lines or math bracket
        self.assertNotIn(r"\displaystyle ]", formatted)
        self.assertNotIn(", 2 marks for part", formatted)
        self.assertNotIn(", 1 mark for part", formatted)
        # Subpart marks must be properly attributed to subparts
        self.assertIn("[1 mark]", formatted)
        self.assertIn("[2 marks]", formatted)
        # Cross-references must not be split
        self.assertIn("Using part (a)", formatted)
        self.assertIn("From (b)", formatted)

        # 2. Test split_question_subparts does not falsely split mark allocation blocks
        mark_block = "[1 mark for part (a), 2 marks for part (b), 1 mark for part (c)]"
        stem, subparts = split_question_subparts(mark_block)
        self.assertEqual(subparts, [])
        self.assertEqual(stem, mark_block)


    def test_private_demo_follows_theory_box_without_forced_page_break(self):
        """Keep the private demonstration next to short notes when enough space remains."""
        from pdf_generator import build_latex_theory_booklet_source

        mock_booklet = {
            "title": "Year 10 (Advanced) Maths - Consumer Arithmetic Theory & Practice Booklet",
            "topic": "Consumer Arithmetic",
            "year_level": "Year 10",
            "concepts": [
                {
                    "concept_name": "Compound Interest",
                    "theory_content": "- **Core Definition**: Interest computed on principal and accumulated interest.\n- **Key Rules**: $A = P(1+r)^n$.\n- **DA Quick-Method**: 1. State formula. 2. Substitute. 3. Solve.",
                    "key_formulas": ["A = P(1 + r)^n", "I = A - P"],
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Applying: Direct Substitution",
                            "problem_text": "Calculate the compound interest on $5000 at 5% p.a. for 3 years.",
                            "worked_solution": "$A = 5000(1.05)^3 = 5788.13$.\n$I = 5788.13 - 5000 = 788.13$."
                        }
                    ]
                }
            ]
        }
        tex_private = build_latex_theory_booklet_source(mock_booklet, mode="student_private")
        self.assertNotRegex(tex_private, r"\\newpage\s+\\needspace\{(?:7\.0|12\.0)cm\}\s+\\subsection\*\{Teacher Demonstration Examples\}")
        self.assertRegex(tex_private, r"\\needspace\{(?:7\.0|12\.0)cm\}\s+\\subsection\*\{Teacher Demonstration Examples\}")

        tex_class = build_latex_theory_booklet_source(mock_booklet, mode="student_class")
        # In student_class, no unconditional \newpage before Teacher Demonstration Examples
        self.assertNotIn("\\newpage\n\\needspace{6.5cm}\n\\subsection*{Teacher Demonstration Examples}", tex_class)
        self.assertIn("\\needspace{6.5cm}\n\\subsection*{Teacher Demonstration Examples}", tex_class)

    def test_financial_maths_fallback_diagrams(self):
        """Verify get_concept_fallback_tikz returns high-clarity diagrams for all 5 Year 10 Financial Maths subtopics."""
        from pdf_generator import get_concept_fallback_tikz

        # 1. Compound Interest
        diag_ci = get_concept_fallback_tikz("1.1 Compound interest calculations and formula: A = P(1 + r)^n")
        self.assertIn("Snowball Effect", diag_ci)
        self.assertIn("A = P(1+r)^n", diag_ci)

        # 2. Fractional Compounding Periods
        diag_frac = get_concept_fallback_tikz("1.2 Fractional compounding periods (monthly, quarterly, daily)")
        self.assertIn("Compounding Quarterly", diag_frac)
        self.assertIn("End Q1", diag_frac)

        # 3. Depreciation (Must NOT match linear functions y = mx + c)
        diag_deprec = get_concept_fallback_tikz("1.3 Straight-line and declining-balance asset depreciation")
        self.assertIn("Declining-Balance", diag_deprec)
        self.assertIn("Straight-Line", diag_deprec)
        self.assertNotIn("y = mx + c", diag_deprec)

        # 4. Credit Card Interest
        diag_cc = get_concept_fallback_tikz("1.4 Credit card interest, repayments and personal loans")
        self.assertIn("Billing Cycle (30 Days)", diag_cc)
        self.assertIn("Payment Window (25 Days)", diag_cc)
        self.assertIn("Up to 55 Days Interest-Free", diag_cc)

        # 5. Superannuation Growth
        diag_super = get_concept_fallback_tikz("1.5 Comparing superannuation growth and investment options")
        self.assertIn("Expected Return", diag_super)
        self.assertIn("Life-Stage Strategy", diag_super)

    def test_credit_card_collision_sanitization(self):
        """Verify sanitize_tikz_diagram detects and fixes colliding credit card timelines."""
        from pdf_generator import sanitize_tikz_diagram

        colliding_diag = r"""
\begin{center}
\begin{tikzpicture}
\draw (0,0) -- (10,0);
\node at (2, 0.5) {Billing Cycle (30 days)};
\node at (4, 0.5) {Payment Window (25 days)};
\end{tikzpicture}
\end{center}
"""
        sanitized = sanitize_tikz_diagram(colliding_diag)
        # Replaced with verified double-tiered timeline
        self.assertIn("Up to 55 Days Interest-Free", sanitized)
        self.assertIn("Billing Cycle (30 Days)", sanitized)
        self.assertIn("Payment Window (25 Days)", sanitized)

    def test_financial_formula_simplifications(self):
        """Verify negative exponents and obscure interest formulas are simplified to Stage 5 friendly forms."""
        from pdf_generator import format_theory_formula, clean_set_notation

        # Negative exponent present value formula -> fraction form
        f1 = clean_set_notation(r"P = A(1 + r)^{-n}")
        self.assertIn(r"\frac{A}{(1 + r)^{n}}", f1)
        self.assertNotIn("-n", f1)

        f2 = format_theory_formula(r"Present Value: P = A(1 + r)^{-n}")
        self.assertIn(r"\frac{A}{(1 + r)^{n}}", f2)

        # Obscure compound interest formula -> A - P
        f3 = clean_set_notation(r"I = P[(1+r)^n - 1]")
        self.assertIn("I = A - P", f3)


if __name__ == "__main__":
    unittest.main()
