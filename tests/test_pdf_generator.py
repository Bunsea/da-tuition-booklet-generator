import unittest
import re
import pdf_generator
import ai_engine
import database
import pypdf
import io

class TestPdfGenerator(unittest.TestCase):
    def test_answer_space_uses_student_instructions_only(self):
        question = (
            "Five people are to be seated around a circular dining table as shown "
            "in the diagram below. In how many different arrangements can they be seated "
            "if rotations are considered identical?\n"
            r"\begin{tikzpicture}\draw (0,0) circle (1);\end{tikzpicture}"
        )
        self.assertEqual(
            pdf_generator.detect_question_response_type(question, "Draw a table, then show that the answer is 24."),
            "compact"
        )
        self.assertEqual(
            pdf_generator.detect_question_response_type("Draw a diagram of the seating arrangement."),
            "diagram"
        )
        self.assertEqual(
            pdf_generator.detect_question_response_type("Explain why rotations give the same arrangement."),
            "reasoning"
        )
        questions = [
            {"item_label": "3", "text": question, "correct_answer": "24"},
            {"item_label": "4", "text": "Explain why rotations are identical.", "correct_answer": "Fix one person."},
        ]
        labels, answers, _, items = pdf_generator.extract_worksheet_answer_sheet_data(questions)
        self.assertEqual([item["type"] for item in items], ["compact", "reasoning"])
        teacher_pdf = pdf_generator.generate_teacher_answer_sheet_pdf(
            question_labels=labels, answers=answers, items=items
        )
        text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(teacher_pdf)).pages)
        self.assertIn("Question 2", text)
        self.assertNotIn("Question 1 — Diagram", text)

    def test_proportional_logo(self):
        rl_img = pdf_generator.get_proportional_logo(target_height=48.0, max_width=70.0)
        self.assertIsNotNone(rl_img)
        # Check aspect ratio preservation
        expected_ratio = 1024.0 / 900.0
        actual_ratio = rl_img.drawWidth / rl_img.drawHeight
        self.assertAlmostEqual(expected_ratio, actual_ratio, places=2)

    def test_student_report_pdf(self):
        mistakes = [
            {
                "question_num": "A 2b",
                "topic": "Algebra",
                "status": "Correct*",
                "correct_answer": "24",
                "details": ""
            },
            {
                "question_num": "B 3d",
                "topic": "Algebra",
                "status": "Incorrect",
                "correct_answer": "16 1/2",
                "details": ""
            },
            {
                "question_num": "C 3j",
                "topic": "Algebra",
                "status": "Correct*",
                "correct_answer": "4 2/5",
                "details": ""
            }
        ]
        pdf_bytes = pdf_generator.generate_student_report_pdf(
            student_name="Ryan Lam",
            term_week_header="Term 2 Week 5 Homework Report",
            score=105,
            total_marks=106,
            accuracy_pct=99.0,
            mistakes=mistakes,
            summary_text="Great work."
        )
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(page.extract_text() for page in reader.pages)
        self.assertIn("PERFORMANCE BREAKDOWN", full_text)
        self.assertIn("Term 2 Week 5 Homework Report", full_text)
        self.assertIn("STUDENT NAME:", full_text)
        self.assertIn("Ryan Lam", full_text)
        self.assertIn("AREAS FOR CORRECTION:", full_text)
        self.assertIn("A Qn 2b | Correct* (24)", full_text)
        self.assertIn("B Qn 3d | Incorrect (16 ½)", full_text)
        self.assertIn("C Qn 3j | Correct* (4 ⅖)", full_text)
        self.assertIn("Accuracy Percentage: 99%", full_text)
        self.assertIn("Total Score: 105 out of 106", full_text)

        # Also test 100% perfect score report
        pdf_perfect = pdf_generator.generate_student_report_pdf(
            student_name="Alice Smith",
            term_week_header="Term 1 Week 2 Homework Report",
            score=50,
            total_marks=50,
            accuracy_pct=100.0,
            mistakes=[],
            class_name="Yr7 Tues 5-7"
        )
        p_reader = pypdf.PdfReader(io.BytesIO(pdf_perfect))
        p_text = "".join(page.extract_text() for page in p_reader.pages)
        self.assertIn("Perfect Score! No corrections needed.", p_text)
        self.assertIn("Class: Yr7 Tues 5-7", p_text)
        self.assertNotIn("\ufffd", p_text)
        self.assertIn("Accuracy Percentage: 100%", p_text)
        self.assertIn("Total Score: 50 out of 50", p_text)

        # A low score must require correction even when the marker returned no
        # question-level mistake records.
        pdf_low = pdf_generator.generate_student_report_pdf(
            student_name="Testing 3",
            term_week_header="Homework Set 1 Report",
            score=12,
            total_marks=18,
            accuracy_pct=66.7,
            mistakes=[]
        )
        low_reader = pypdf.PdfReader(io.BytesIO(pdf_low))
        low_text = "".join(page.extract_text() for page in low_reader.pages)
        self.assertIn("Correction required", low_text)
        self.assertNotIn("Perfect Score! No corrections needed.", low_text)
        self.assertIn("Accuracy Percentage: 67%", low_text)
        self.assertIn("Total Score: 12 out of 18", low_text)

    def test_blank_answer_sheet_with_labels(self):
        labels = ["1(a)", "1(b)", "2", "3(a)", "3(b)(i)", "3(b)(ii)", "4"]
        pdf_bytes = pdf_generator.generate_blank_answer_sheet_pdf(
            question_labels=labels,
            term=3,
            week=8
        )
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_worksheet_pdf_with_header_and_subparts(self):
        questions = [
            {"item_label": "1(a)", "text": "Find $P(A \\cap B)$", "marks": 1, "subtopic": "Addition Rule"},
            {"item_label": "1(b)", "text": "Find $P(A \\cup B)$", "marks": 2, "subtopic": "Addition Rule"},
            {"item_label": "2", "text": "Calculate the conditional probability $P(A \\mid B)$.", "marks": 3, "subtopic": "Conditional Probability"}
        ]
        pdf_bytes = pdf_generator.generate_worksheet_pdf(
            title="Probability Homework",
            year_level="Year 11 (Advanced)",
            topic="Probability",
            questions=questions,
            include_solutions=True,
            term=3,
            week=8,
            sheet_type="Homework"
        )
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_curriculum_subtopics(self):
        subs = ai_engine.get_curriculum_subtopics("Year 11 (Advanced)", "Probability")
        self.assertTrue(any("sample spaces" in s.lower() for s in subs))
        self.assertTrue(any("addition rule" in s.lower() for s in subs))
        self.assertTrue(any("multiplication rule" in s.lower() for s in subs))

        ext_subs = ai_engine.get_curriculum_subtopics("Year 11 (Extension)", "14. Probability")
        self.assertIn("14A Sets and Venn diagrams", ext_subs)
        self.assertIn("14G Conditional probability", ext_subs)

    def test_tikz_sanitization(self):
        raw = "Calculate $\\mathbf{v}$:\n\\begin{tikzpicture}\n\\draw[->] (0,0) -- (3,2);\n\\end{tikzpicture}\nFind 25% of the total."
        sanitized = pdf_generator.sanitize_for_latex(raw)
        self.assertIn("\\begin{tikzpicture}\n\\draw[->] (0,0) -- (3,2);\n\\end{tikzpicture}", sanitized)
        self.assertIn("25\\%", sanitized)

    def test_bonnyrigg_clean_sections_and_qmark(self):
        # Generate questions with multiple subtopics to trigger Set A, Set B
        questions = [
            {
                "item_label": f"{i}",
                "text": f"Question {i} test content $\\mathbf{{v}}_{i}$.",
                "marks": 2 if i % 2 == 0 else 1,
                "subtopic": "Vector Magnitude and Direction" if i <= 6 else "The Scalar (Dot) Product"
            }
            for i in range(1, 13)
        ]
        pdf_bytes = pdf_generator.generate_latex_worksheet_pdf(
            title="Year 12 (Extension 1) Mathematics - Vectors In-Class",
            year_level="Year 12 (Extension 1)",
            topic="Vectors in 2D and 3D",
            questions=questions,
            include_solutions=True,
            term=3,
            week=8,
            sheet_type="In-Class"
        )
        self.assertIsNotNone(pdf_bytes)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(page.extract_text() for page in reader.pages)
        
        # Verify Subtopic Sets (Set A, Set B, ...)
        self.assertIn("Set A", full_text)
        self.assertIn("Set B", full_text)
        self.assertIn("Section 1: Further Practice", full_text)
        self.assertNotIn("(Easy)", full_text)
        self.assertNotIn("(Medium)", full_text)
        
        # Verify 3-section booklet structure
        self.assertIn("ANSWERS", full_text)
        self.assertIn("WORKED SOLUTIONS", full_text)
        sol_idx = max(full_text.find("FULLY WORKED SOLUTIONS"), full_text.find("FULL Y WORKED SOLUTIONS"), full_text.find("WORKED SOLUTIONS"))
        self.assertTrue(full_text.find("ANSWERS") < sol_idx)
        
        # Verify flexible marks
        self.assertIn("(2 marks)", full_text)
        self.assertIn("(1 mark)", full_text)

    def test_get_tiered_sections_for_questions_all_five_tiers(self):
        """Verify get_tiered_sections_for_questions creates all 5 standard sections correctly."""
        questions = [
            {"num": 1, "text": "Q1", "difficulty": "Easy", "marks": 1},
            {"num": 2, "text": "Q2", "difficulty": "Medium", "marks": 2},
            {"num": 3, "text": "Q3", "difficulty": "Hard", "marks": 2},
            {"num": 4, "text": "Q4", "difficulty": "Extremely Hard", "marks": 3},
            {"num": 5, "text": "Q5", "difficulty": "Past Exam", "marks": 4},
        ]
        sections = pdf_generator.get_tiered_sections_for_questions(questions)
        self.assertEqual(len(sections), 5)
        self.assertEqual(sections[0]["section_title"], "Section 1: Commit to Memory")
        self.assertEqual(sections[1]["section_title"], "Section 2: Further Practice")
        self.assertEqual(sections[2]["section_title"], "Section 3: Application")
        self.assertEqual(sections[3]["section_title"], "Section 4: Thinking Creatively")
        self.assertEqual(sections[4]["section_title"], "Section 5: Exam Questions")

    def test_prompt_fstring_formatting(self):
        import inspect
        src = inspect.getsource(ai_engine.generate_curriculum_worksheet)
        globs = {
            "year_level": "Year 12 (Extension 1)",
            "topic": "2. Vectors in 2D and 3D",
            "sheet_type": "In-Class",
            "term": 3,
            "week": 8,
            "difficulty": "Medium",
            "total_requested_items": 12,
            "custom_instructions": "",
            "textbook": "CambridgeMATHS NSW",
            "subtopic_allocation_text": "- Subtopic 1: 2 items",
            "num_mc": 0,
            "mc_prompt_section": "",
            "theory_alignment_text": "",
            "get_stage6_syllabus_boundary_prompt": ai_engine.get_stage6_syllabus_boundary_prompt
        }
        start = src.find('prompt = f"""')
        end = src.find('"""', start + 12) + 3
        prompt_code = src[start:end]
        locs = {}
        exec(prompt_code, globs, locs)
        self.assertIn("\\begin{center}\\begin{tikzpicture}", locs["prompt"])
        self.assertIn("\\end{tikzpicture}\\end{center}", locs["prompt"])

    def test_lesson_cover_sheet_pdf_single_page_strict(self):
        # 1. Blank Sheet (1-page condensed mode)
        blank_pdf = pdf_generator.generate_lesson_cover_sheet_pdf(mode="1page")
        reader_blank = pypdf.PdfReader(io.BytesIO(blank_pdf))
        self.assertEqual(len(reader_blank.pages), 1, "Blank cover sheet in 1page mode must be strictly 1 page A4")

        # 2. Filled Sheet (1-page condensed mode)
        sample_data = {
            "student_name": "Marcus Vance",
            "class_name": "Year 11 Ext 1 (Tue 5-7)",
            "subject": "Mathematics",
            "tutor_name": "Mr. Bunsea",
            "term": 1,
            "week": 5,
            "lesson_date": "2026-03-09",
            "topic": "Vectors in 2D & 3D",
            "subtopic": "Dot Product & Orthogonality",
            "syllabus_outcomes": "ME-V1",
            "materials_used": ["DA Topic Booklet", "Exam Papers"],
            "mastery_data": [
                {"concept": "Scalar Dot Product Formula u.v = |u||v|cos(theta)", "level": "Independent"},
                {"concept": "Orthogonality Condition (u.v = 0)", "level": "Exam Ready"},
                {"concept": "Vector Projections (proj_v u)", "level": "Scaffolded"}
            ],
            "root_cause_tags": ["Careless / Algebraic Slip", "Exam Pacing / Time Pressure"],
            "specific_stumbling_block": "Negative sign dropping during component dot product expansion",
            "intervention_tags": ["Stepped Algorithm / Deconstruction", "Visual / Geometric Sketch / Diagram"],
            "score_engagement": 5,
            "score_confidence": 4,
            "score_independence": 4,
            "tutor_observations": "Marcus was highly engaged, worked methodically through proofs.",
            "attention_flag": "all_clear",
            "homework_assigned": "Ex 4B Q1-6, 8, 10 + DA Vector Master Drill",
            "homework_due": "2026-03-16",
            "target_accuracy": "90%",
            "next_lesson_priority": "Vector Projections and 3D Direction Cosines",
            "parent_soundbite": "Marcus mastered scalar dot products and orthogonal vector proofs today; next week we move directly into projections.",
            "student_clarity": "Crystal Clear",
            "student_support": "Very Supported",
            "student_questions": "Always (100%)",
            "student_difficulty": "Sweet Spot",
            "student_confidence_shift": "Higher",
            "student_request_note": "Do 1 hard HSC exam proof question together next time!"
        }
        filled_pdf = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="1page")
        reader_filled = pypdf.PdfReader(io.BytesIO(filled_pdf))
        self.assertEqual(len(reader_filled.pages), 1, "Filled cover sheet in 1page mode must be strictly 1 page A4")

        # 3. Full 2-Page Double Sided Sheet (Executive Standard)
        full_2page_pdf = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="2page", variation="executive")
        reader_2page = pypdf.PdfReader(io.BytesIO(full_2page_pdf))
        self.assertEqual(len(reader_2page.pages), 2, "Executive cover sheet must be strictly 2 pages A4")

        # 4. Variation 2: The HSC Band 6 Blueprint (1-page and 2-page)
        bp_1p = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="1page", variation="blueprint")
        self.assertEqual(len(pypdf.PdfReader(io.BytesIO(bp_1p)).pages), 1, "Blueprint 1page must be 1 page")
        bp_2p = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="2page", variation="blueprint")
        self.assertEqual(len(pypdf.PdfReader(io.BytesIO(bp_2p)).pages), 2, "Blueprint 2page must be 2 pages")

        # 5. Variation 3: The High-Yield Exam Sprint (1-page and 2-page)
        sp_1p = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="1page", variation="sprint")
        self.assertEqual(len(pypdf.PdfReader(io.BytesIO(sp_1p)).pages), 1, "Sprint 1page must be 1 page")
        sp_2p = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="2page", variation="sprint")
        self.assertEqual(len(pypdf.PdfReader(io.BytesIO(sp_2p)).pages), 2, "Sprint 2page must be 2 pages")

    def test_math_blueprint_years_7_12_accessible_language(self):
        """Verify Blueprint Design is primary default for Years 7-12 with clear language for teachers, students, parents."""
        sample_data = {
            "student_name": "Marcus Vance",
            "class_name": "Year 11 Ext 1 (Tue 5-7)",
            "subject": "Mathematics",
            "tutor_name": "Mr. Bunsea",
            "term": 1,
            "week": 5,
            "lesson_date": "2026-03-09",
            "course_level": "Extension 1",
            "topic": "Vectors in 2D & 3D",
            "subtopic": "Dot Product & Orthogonality",
            "syllabus_outcomes": "ME-V1",
            "materials_used": ["DA Topic Booklet", "Exam Pack"],
            "homework_score": "18/20 (90%)",
            "drill_score": "14/15 (93%)",
            "target_accuracy": "90%+",
            "cognitive_autonomy": "Independent",
            "score_engagement": 5,
            "score_confidence": 4,
            "root_cause_tags": ["Careless / Algebraic Slip"],
            "specific_stumbling_block": "Dropped negative sign during component expansion",
            "homework_assigned": "Ex 4B Q1-6, 8, 10",
            "homework_due": "Next Lesson",
            "next_lesson_priority": "3D Vectors",
            "parent_soundbite": "Marcus had a great lesson on Vectors today. He understood the dot product concept well and worked through questions independently.",
            "student_clarity": "Crystal Clear",
            "student_support": "Very Supported",
            "student_questions": "Always (100%)",
            "student_difficulty": "Sweet Spot",
            "student_confidence_shift": "Higher"
        }
        # Default variation should be blueprint
        pdf_default = pdf_generator.generate_lesson_cover_sheet_pdf(sample_data, mode="2page")
        reader = pypdf.PdfReader(io.BytesIO(pdf_default))
        self.assertEqual(len(reader.pages), 2, "Blueprint 2-page must be strictly 2 pages")

        p1_text = reader.pages[0].extract_text()
        p2_text = reader.pages[1].extract_text()

        # Check Years 7-12 High School & HSC scope
        self.assertTrue("YEARS 7" in p1_text or "YEARS 7-12" in p1_text or "7–12" in p1_text)
        self.assertIn("WHAT WAS TAUGHT TODAY", p1_text)
        self.assertIn("WHAT THE STUDENT UNDERSTOOD & INDEPENDENCE", p1_text)
        self.assertIn("WHY MARKS WERE LOST", p1_text)
        self.assertIn("WHAT THE TUTOR DID TO HELP", p1_text)
        self.assertIn("15-SECOND UPDATE FOR PARENTS", p1_text)

        # Check Page 2 Student Voice accessible wording
        self.assertIn("STUDENT FEEDBACK & GOALS", p2_text)
        self.assertIn("HOW DID TODAY'S LESSON FEEL", p2_text)
        self.assertIn("TEACHING QUALITY & CLASSROOM SUPPORT", p2_text)
        self.assertIn("BREAKTHROUGHS", p2_text)
        self.assertIn("UPCOMING SCHOOL MATH TESTS", p2_text)

        # Check blank 2-page mode
        blank_pdf = pdf_generator.generate_lesson_cover_sheet_pdf(None, mode="2page")
        reader_blank = pypdf.PdfReader(io.BytesIO(blank_pdf))
        self.assertEqual(len(reader_blank.pages), 2, "Blank blueprint must be strictly 2 pages")

    def test_cambridge_curriculum_coverage(self):
        """Verify Cambridge NSW curriculum coverage for all courses Years 5-12 including Year 10 Standard & Advanced with Networks."""
        year_level_options = [
            "Year 5", "Year 6", "Year 7", "Year 8", "Year 9",
            "Year 10 (Standard)", "Year 10 (Advanced)",
            "Year 11 (Standard)", "Year 11 (Advanced)", "Year 11 (Extension)",
            "Year 12 (Standard)", "Year 12 (Advanced)", "Year 12 (Extension 1)", "Year 12 (Extension 2)"
        ]
        for yl in year_level_options:
            topics = ai_engine.get_topics_for_year(yl)
            self.assertGreater(len(topics), 0, f"Year level '{yl}' must have topics defined")
            for t in topics:
                subtopics = ai_engine.get_curriculum_subtopics(yl, t)
                self.assertGreater(len(subtopics), 0, f"Topic '{t}' in '{yl}' must have subtopics defined")

        # Specific verification for Year 10 Networks
        y10_std_topics = ai_engine.get_topics_for_year("Year 10 (Standard)")
        self.assertTrue(any("Networks" in t for t in y10_std_topics), "Year 10 (Standard) must have Networks topic")
        y10_std_net_subs = ai_engine.get_curriculum_subtopics("Year 10 (Standard)", "7. Networks and Graph Theory")
        self.assertTrue(any("Prim's" in s for s in y10_std_net_subs), "Year 10 (Standard) Networks must include Prim's algorithm")

        y10_adv_topics = ai_engine.get_topics_for_year("Year 10 (Advanced)")
        self.assertTrue(any("Networks" in t for t in y10_adv_topics), "Year 10 (Advanced) must have Networks topic")
        y10_adv_net_subs = ai_engine.get_curriculum_subtopics("Year 10 (Advanced)", "10. Networks and Graph Theory")
        self.assertTrue(any("Euler's formula" in s for s in y10_adv_net_subs), "Year 10 (Advanced) Networks must include Euler's formula")

        # Backwards compatibility check for 'Year 10'
        y10_legacy = ai_engine.get_topics_for_year("Year 10")
        self.assertGreater(len(y10_legacy), 0, "Legacy 'Year 10' must resolve successfully")

    def test_theory_booklet_pdf_teacher_and_student(self):
        sample_booklet = {
            "title": "Year 11 (Extension) - Vectors in 2D & 3D Theory Booklet",
            "year_level": "Year 11 (Extension)",
            "topic": "Vectors in 2D and 3D",
            "term": 1,
            "week": 5,
            "concepts": [
                {
                    "name": "Vector Definitions & Components",
                    "theory_text": "A vector is a quantity having both magnitude and direction. In 2D Cartesian coordinates, $\\mathbf{v} = x\\mathbf{i} + y\\mathbf{j}$.",
                    "key_formulas": ["$|\\mathbf{v}| = \\sqrt{x^2 + y^2}$", "$\\hat{\\mathbf{v}} = \\frac{\\mathbf{v}}{|\\mathbf{v}|}$"],
                    "tutor_tips": "Always remind students to sketch the right triangle when computing the angle $\\theta = \\tan^{-1}(y/x)$.",
                    "teacher_examples": [
                        {
                            "problem_text": "Find the unit vector in the direction of $\\mathbf{u} = 3\\mathbf{i} - 4\\mathbf{j}$.",
                            "worked_solution": "$|\\mathbf{u}| = \\sqrt{3^2 + (-4)^2} = 5$.\nTherefore $\\hat{\\mathbf{u}} = \\frac{3}{5}\\mathbf{i} - \\frac{4}{5}\\mathbf{j}$.",
                            "teaching_notes": "Emphasize that the magnitude of $\\hat{\\mathbf{u}}$ is strictly 1."
                        }
                    ],
                    "practice_questions": [
                        {
                            "difficulty": "Easy",
                            "marks": 1,
                            "text": "Find the magnitude of the vector $\\mathbf{v} = 6\\mathbf{i} + 8\\mathbf{j}$.",
                            "worked_solution": "$|\\mathbf{v}| = \\sqrt{6^2 + 8^2} = \\sqrt{100} = 10$.\n[1 mark for correct calculation]",
                            "final_answer": "10"
                        },
                        {
                            "difficulty": "Medium",
                            "marks": 2,
                            "text": "Given $\\mathbf{a} = 2\\mathbf{i} + 5\\mathbf{j}$ and $\\mathbf{b} = -\\mathbf{i} + 3\\mathbf{j}$, find $|2\\mathbf{a} - \\mathbf{b}|$.",
                            "worked_solution": "$2\\mathbf{a} - \\mathbf{b} = (4\\mathbf{i} + 10\\mathbf{j}) - (-\\mathbf{i} + 3\\mathbf{j}) = 5\\mathbf{i} + 7\\mathbf{j}$.\n$|5\\mathbf{i} + 7\\mathbf{j}| = \\sqrt{25 + 49} = \\sqrt{74}$.\n[1 mark for components, 1 mark for magnitude]",
                            "final_answer": "$\\sqrt{74}$"
                        }
                    ]
                }
            ]
        }

        # 1. Test Teacher Edition
        teacher_pdf = pdf_generator.generate_theory_booklet_pdf(sample_booklet, mode="teacher", term=1, week=5)
        self.assertIsNotNone(teacher_pdf)
        self.assertTrue(teacher_pdf.startswith(b"%PDF"))
        teacher_reader = pypdf.PdfReader(io.BytesIO(teacher_pdf))
        self.assertGreaterEqual(len(teacher_reader.pages), 1)
        teacher_text = "".join(page.extract_text() for page in teacher_reader.pages)
        self.assertIn("TEACHER MASTER", teacher_text)
        self.assertTrue(re.search(r"T\s*eaching\s*Note", teacher_text))  # solution box content
        self.assertIn("Final Answer:", teacher_text)
        self.assertTrue(re.search(r"T\s*eacher\s*Demonstration\s*Examples", teacher_text))

        # 2. Test Student Edition
        student_pdf = pdf_generator.generate_theory_booklet_pdf(sample_booklet, mode="student", term=1, week=5)
        self.assertIsNotNone(student_pdf)
        self.assertTrue(student_pdf.startswith(b"%PDF"))
        student_reader = pypdf.PdfReader(io.BytesIO(student_pdf))
        self.assertGreaterEqual(len(student_reader.pages), 1)
        student_text = "".join(page.extract_text() for page in student_reader.pages)
        self.assertIn("STUDENT", student_text)
        self.assertIn("STUDENT CLASS", student_text)
        self.assertNotIn("Plain Answers", student_text)
        self.assertIsNone(re.search(r"T\s*eaching\s*Note", student_text))  # solution box not shown in student edition

    def test_theory_booklet_db_crud(self):
        database.init_db()
        test_content = {
            "title": "Unit Test Theory Booklet",
            "year_level": "Year 12 (Advanced)",
            "topic": "Calculus",
            "concepts": []
        }
        b_id = database.save_theory_booklet(
            title="Unit Test Theory Booklet",
            term=2,
            week=3,
            year_level="Year 12 (Advanced)",
            topic="Calculus",
            content=test_content
        )
        self.assertIsInstance(b_id, int)
        self.assertGreater(b_id, 0)

        # List
        all_booklets = database.get_theory_booklets()
        self.assertTrue(any(b['id'] == b_id for b in all_booklets))

        # Get by id
        fetched = database.get_theory_booklet_by_id(b_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "Unit Test Theory Booklet")
        self.assertEqual(fetched["term"], 2)
        self.assertEqual(fetched["week"], 3)
        self.assertEqual(fetched["content"]["title"], "Unit Test Theory Booklet")

        # Delete
        database.delete_theory_booklet(b_id)
        self.assertIsNone(database.get_theory_booklet_by_id(b_id))

    def test_clean_json_response_with_latex_escapes(self):
        """Verify clean_json_response can parse raw JSON with unescaped LaTeX math escapes without throwing Invalid escape."""
        raw_bad_json = r"""```json
{
  "title": "Vectors Booklet",
  "theory_notes": "Formula: \frac{-b \pm \sqrt{b^2-4ac}}{2a} and \mathbf{v} = 3\mathbf{i} - 4\mathbf{j}",
  "formulas": [
    "|\mathbf{v}| = \sqrt{x^2 + y^2}",
    "\theta = \tan^{-1}(\frac{y}{x})",
    "\{x \mid x > 0\}",
    "Probability 50\%",
  ],
  "nested": {
    "tip": "Check that \Delta > 0 and \alpha \neq \beta",
  }
}
```"""
        data = ai_engine.clean_json_response(raw_bad_json)
        self.assertEqual(data["title"], "Vectors Booklet")
        self.assertIn(r"\frac", data["theory_notes"])
        self.assertIn(r"\sqrt", data["theory_notes"])
        self.assertIn(r"\mathbf{v}", data["theory_notes"])
        self.assertEqual(len(data["formulas"]), 4)
        self.assertIn(r"\tan^{-1}", data["formulas"][1])
        self.assertIn(r"\Delta", data["nested"]["tip"])

    def test_maths_in_focus_curriculum_coverage(self):
        """Verify Maths in Focus textbook curriculum coverage across Stage 6 courses and exclusion of junior years."""
        self.assertIn("CambridgeMATHS NSW", ai_engine.TEXTBOOK_OPTIONS)
        self.assertIn("Maths in Focus (Nelson Cengage)", ai_engine.TEXTBOOK_OPTIONS)

        stage6_courses = [
            "Year 12 (Extension 2)", "Year 12 (Extension 1)", "Year 12 (Advanced)", "Year 12 (Standard)",
            "Year 11 (Extension)", "Year 11 (Advanced)", "Year 11 (Standard)"
        ]

        mif_curr = ai_engine.MATHS_IN_FOCUS_CURRICULUM
        for course in stage6_courses:
            self.assertIn(course, mif_curr, f"Missing course '{course}' in Maths in Focus curriculum!")
            topics = mif_curr[course]
            self.assertGreater(len(topics), 0, f"Course '{course}' has empty topic list in Maths in Focus!")
            for topic, subs in topics.items():
                self.assertGreater(len(subs), 0, f"Topic '{topic}' in '{course}' has empty subtopics in Maths in Focus!")

        junior_courses = [
            "Year 10 (Advanced)", "Year 10 (Standard)", "Year 9 (Advanced)", "Year 9 (Standard)",
            "Year 8", "Year 7", "Year 5 & 6"
        ]
        for course in junior_courses:
            self.assertNotIn(course, mif_curr, f"Junior course '{course}' must NOT be in Maths in Focus!")

    def test_dual_textbook_switching(self):
        """Verify get_topics_for_year and get_curriculum_subtopics work across both textbooks and respect defaults."""
        # 1. Default should be Cambridge
        cambridge_topics = ai_engine.get_topics_for_year("Year 12 (Extension 1)")
        self.assertTrue(any("Vectors" in t for t in cambridge_topics))

        # 2. Maths in Focus explicit selection
        mif_topics = ai_engine.get_topics_for_year("Year 12 (Extension 1)", textbook="Maths in Focus (Nelson Cengage)")
        self.assertTrue(any("Vectors" in t for t in mif_topics))

        # 3. Subtopics from Cambridge
        cam_subs = ai_engine.get_curriculum_subtopics("Year 12 (Extension 1)", "2. Vectors in 2D and 3D", textbook="CambridgeMATHS NSW")
        self.assertTrue(len(cam_subs) > 0)

        # 4. Subtopics from Maths in Focus
        mif_subs = ai_engine.get_curriculum_subtopics("Year 12 (Extension 1)", "2. Vectors in 2D and 3D", textbook="Maths in Focus (Nelson Cengage)")
        self.assertTrue(len(mif_subs) > 0)
        self.assertTrue(any("Component" in s or "Dot" in s or "Geometric" in s or "vector" in s.lower() for s in mif_subs))

        # 5. Alias support
        alias_topics = ai_engine.get_topics_for_year("Year 12 (Extension 2)", textbook="Maths in Focus")
        self.assertTrue(len(alias_topics) > 0)

        cengage_topics = ai_engine.get_topics_for_year("Year 11 (Advanced)", textbook="Cengage")
        self.assertTrue(len(cengage_topics) > 0)

    def test_optional_term_and_week_worksheet_and_booklets(self):
        """Verify that worksheets, answer sheets, and theory booklets generate cleanly without term and week."""
        questions = [
            {"item_label": "1", "text": "Solve for $x$: $2x + 5 = 11$.", "marks": 1, "subtopic": "Linear Equations", "correct_answer": "$x = 3$"}
        ]
        
        # 1. Worksheet PDF with term=None, week=None
        ws_bytes = pdf_generator.generate_worksheet_pdf(
            title="General Linear Equations Worksheet",
            year_level="Year 8",
            topic="Linear Equations",
            questions=questions,
            include_solutions=True,
            term=None,
            week=None,
            sheet_type="Homework"
        )
        self.assertGreater(len(ws_bytes), 500)
        self.assertTrue(ws_bytes.startswith(b"%PDF"))

        # 2. Blank Answer Sheet PDF with term=None, week=None
        ans_bytes = pdf_generator.generate_blank_answer_sheet_pdf(
            question_labels=["1", "2"],
            num_questions=2,
            term=None,
            week=None
        )
        self.assertGreater(len(ans_bytes), 500)
        self.assertTrue(ans_bytes.startswith(b"%PDF"))

        # 3. Theory Booklet PDF with term=None, week=None
        booklet_sample = {
            "year_level": "Year 8",
            "topic": "Linear Equations",
            "concepts": [
                {
                    "concept_name": "Solving Equations",
                    "theory_content": "Equations are solved using inverse operations.",
                    "key_formulas": ["$ax + b = c$"],
                    "tutor_tips": "Keep balance on both sides.",
                    "teacher_examples": [
                        {"example_num": 1, "title": "Basic Equation", "problem_text": "Solve $2x = 6$.", "worked_solution": "$x = 3$"}
                    ],
                    "practice_questions": [
                        {"q_num": 1, "difficulty": "Easy", "marks": 1, "text": "Solve $3x = 12$.", "final_answer": "$x = 4$"}
                    ]
                }
            ]
        }
        tb_bytes = pdf_generator.generate_theory_booklet_pdf(
            booklet_data=booklet_sample,
            mode="teacher",
            term=None,
            week=None
        )
        self.assertGreater(len(tb_bytes), 500)
        self.assertTrue(tb_bytes.startswith(b"%PDF"))

    def test_homework_set_and_clean_title_worksheet_pdf(self):
        """Verify that '1. Sequences and Series' is cleaned to 'Sequences & Series' and displays Homework Set 1."""
        questions = [
            {"item_label": "1", "text": "Find the 10th term.", "marks": 2, "subtopic": "Arithmetic Sequences", "correct_answer": "42"}
        ]
        pdf_bytes = pdf_generator.generate_worksheet_pdf(
            title="Year 12 (Advanced) Maths - Sequences & Series",
            year_level="Year 12 (Advanced)",
            topic="1. Sequences and Series",
            questions=questions,
            include_solutions=True,
            term=3,
            week=8,
            sheet_type="Homework",
            set_number=1
        )
        self.assertIsNotNone(pdf_bytes)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = "".join(page.extract_text() for page in reader.pages)

        # Must have cleaned title with Homework Set 1
        self.assertIn("Sequences & Series", full_text)
        self.assertIn("Homework Set 1", full_text)
        # Must not have leading chapter number
        self.assertNotIn("1. Sequences and Series — Homework", full_text)
        self.assertNotIn("1. Sequences and Series --- Homework", full_text)

    def test_theory_booklet_heading_split_and_non_overlapping_headers(self):
        """Verify that Theory Booklet headings are split across two lines and headers use parbox."""
        booklet_sample = {
            "year_level": "Year 9",
            "topic": "Properties of Geometrical Figures",
            "concepts": [
                {
                    "concept_name": "Angles and Triangles",
                    "theory_content": "Deductive geometry.",
                    "key_formulas": ["$a + b = 90^\\circ$"],
                    "teacher_examples": [{"title": "Example 1: Basic Angles", "problem_text": "Find x", "worked_solution": "x=10"}],
                    "practice_questions": [{"difficulty": "Level 1", "text": "Find y", "marks": 2, "worked_solution": "y=20", "final_answer": "20"}]
                }
            ]
        }
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_sample, mode="teacher")
        # Check two-line heading
        self.assertIn(r"\textbf{\color{danavy}Year 9 Maths}}\\[0.1cm]", tex)
        self.assertIn(r"\textbf{\color{danavy}Properties of Geometrical Figures}}\\[0.15cm]", tex)
        # Check parbox running headers
        self.assertIn(r"\fancyhead[L]{\parbox[b]{0.62\textwidth}", tex)
        self.assertIn(r"\fancyhead[R]{\parbox[b]{0.36\textwidth}", tex)
        self.assertIn("DA Tuition --- Teacher Master", tex)

    def test_prefilled_student_and_teacher_answer_sheets(self):
        """Verify prefilled question numbers in student sheet and prefilled answers in teacher sheet."""
        labels = ["1", "2", "3", "4"]
        answers = ["(B) 120", "$x = 65$", "$540^\\circ$", "PQ = 8 cm"]

        # Student Sheet: prefilled question numbers, blank answers
        s_pdf = pdf_generator.generate_blank_answer_sheet_pdf(
            question_labels=labels,
            num_questions=len(labels),
            term=2,
            week=4
        )
        self.assertIsNotNone(s_pdf)
        s_reader = pypdf.PdfReader(io.BytesIO(s_pdf))
        s_text = s_reader.pages[0].extract_text()
        for l in labels:
            self.assertIn(l, s_text)
        self.assertNotIn("120", s_text)

        # Teacher Sheet: prefilled numbers AND answers
        t_pdf = pdf_generator.generate_teacher_answer_sheet_pdf(
            question_labels=labels,
            answers=answers,
            num_questions=len(labels),
            term=2,
            week=4
        )
        self.assertIsNotNone(t_pdf)
        t_reader = pypdf.PdfReader(io.BytesIO(t_pdf))
        t_text = t_reader.pages[0].extract_text()
        for l in labels:
            self.assertIn(l, t_text)
        self.assertIn("[ TEACHER ANSWER KEY ]", t_text)
        self.assertIn("120", t_text)
        self.assertTrue("540°" in t_text or "540◦" in t_text or "540" in t_text)

    def test_theory_notes_list_continuity_and_page_break_protection(self):
        """Verify list continuity across blank lines, formula ampersand sanitization, and theorybox break settings."""
        # 1. Test format_latex_theory_notes preserves list continuity
        raw_markdown = "1. Item one\n\n2. Item two\n\n3. Item three"
        tex_notes = pdf_generator.format_latex_theory_notes(raw_markdown)
        self.assertEqual(tex_notes.count(r"\begin{enumerate}"), 1, "Should keep numbered items in single enumerate")
        self.assertEqual(tex_notes.count(r"\end{enumerate}"), 1, "Should have exactly one matching end enumerate")

        # 2. Test formula ampersand sanitization
        formula = "Walk: Any sequence of edges & vertices"
        sanitized = pdf_generator.format_theory_formula(formula)
        self.assertIn(r"\&", sanitized, "Ampersand in formula must be escaped to \\&")
        self.assertNotIn(" & ", sanitized, "Bare ampersand must not exist in formula")

        # 3. Test build_latex_theory_booklet_source break settings
        booklet_data = {
            "year_level": "Year 10 (Advanced)",
            "topic": "Networks and Graph Theory",
            "concepts": [
                {
                    "concept_name": "Network Terminology",
                    "theory_content": raw_markdown,
                    "tutor_tips": "Watch out for loops.",
                    "tikz_diagram": "\\begin{tikzpicture}\\node {A};\\end{tikzpicture}"
                }
            ]
        }
        tex_source = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")
        # Diagram must be placed inside theorybox before teacher demonstrations
        start_box_pos = tex_source.find(r"\begin{theorybox}")
        end_box_pos = tex_source.find(r"\end{theorybox}")
        tikz_pos = tex_source.find(r"\begin{tikzpicture}")
        self.assertTrue(start_box_pos < tikz_pos < end_box_pos, "TikZ diagram must be placed inside \\begin{theorybox}...\\end{theorybox} before teacher demonstrations")

    def test_student_plain_answers_margin_alignment(self):
        """Verify student plain answers use align=left and labelindent=0pt to prevent cutoff at margins."""
        booklet_data = {
            "year_level": "Year 10",
            "topic": "Trigonometry",
            "concepts": [
                {
                    "concept_name": "Sine Rule",
                    "practice_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Easy",
                            "marks": 2,
                            "text": "Find x",
                            "worked_solution": "x = 5",
                            "final_answer": "x = 5"
                        }
                    ]
                }
            ]
        }
        # Theory booklet private mode retains the self-checking answers.
        t_src = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_private")
        self.assertIn(r"labelindent=0pt", t_src)
        self.assertIn(r"labelwidth=2.5cm", t_src)
        self.assertIn(r"leftmargin=*", t_src)
        self.assertIn(r"align=left", t_src)

        # Review booklet student mode
        r_data = {
            "year_level": "Year 10",
            "topic": "Trigonometry",
            "concepts": [
                {
                    "concept_name": "Sine Rule",
                    "review_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Standard",
                            "marks": 2,
                            "text": "Find x",
                            "worked_solution": "x = 5",
                            "final_answer": "x = 5"
                        }
                    ]
                }
            ]
        }
        r_src = pdf_generator.build_latex_review_booklet_source(r_data, mode="student")
        self.assertIn(r"labelindent=0pt", r_src)
        self.assertIn(r"labelwidth=2.5cm", r_src)
        self.assertIn(r"leftmargin=*", r_src)
        self.assertIn(r"align=left", r_src)

    def test_diagram_rendering_in_worksheets_and_booklets(self):
        """Verify that TikZ diagrams in questions and solutions are rendered in LaTeX source."""
        tikz_q = r"\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}"
        tikz_sol = r"\begin{tikzpicture}\draw[red] (0,0) circle (1);\end{tikzpicture}"

        # 1. Worksheet
        questions = [
            {
                "num": 1,
                "item_label": "1",
                "subtopic": "Vectors",
                "text": "Calculate the vector.",
                "diagram_tikz": tikz_q,
                "solution_diagram_tikz": tikz_sol,
                "correct_answer": "$2\\mathbf{i}$",
                "solution_steps": "Step 1: draw diagram."
            }
        ]
        ws_src = pdf_generator.build_latex_worksheet_source(
            title="Vectors Worksheet",
            year_level="Year 11 Extension 1",
            topic="Vectors",
            questions=questions,
            include_solutions=True
        )
        self.assertIn(r"\draw (0,0) -- (1,1);", ws_src)
        self.assertIn(r"\draw[red] (0,0) circle (1);", ws_src)

        # 2. Theory booklet with teacher example diagrams and practice question diagrams
        booklet_data = {
            "year_level": "Year 11 Extension 1",
            "topic": "Vectors",
            "concepts": [
                {
                    "concept_name": "Vector Geometry",
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Triangle Law",
                            "problem_text": "Illustrate addition.",
                            "diagram_tikz": tikz_q,
                            "solution_diagram_tikz": tikz_sol,
                            "worked_solution": "Vector sum is AC."
                        }
                    ],
                    "practice_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Level 1",
                            "marks": 2,
                            "text": "Draw vector subtraction.",
                            "diagram_tikz": tikz_q,
                            "solution_diagram_tikz": tikz_sol,
                            "worked_solution": "Subtract BC from AC.",
                            "final_answer": "$\\vec{AB}$"
                        }
                    ]
                }
            ]
        }
        tb_teacher = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")
        self.assertIn(r"\draw (0,0) -- (1,1);", tb_teacher)
        self.assertIn(r"\draw[red] (0,0) circle (1);", tb_teacher)

    def test_answer_sheet_latex_overlay_math_formatting(self):
        """Verify that answer sheet overlay formats LaTeX math equations cleanly and fits cells."""
        raw_ans = r"x = \frac{3 \pm \sqrt{5}}{2}"
        cell_tex = pdf_generator.format_latex_answer_for_cell(raw_ans)
        self.assertTrue(cell_tex.startswith("$") and cell_tex.endswith("$"))
        self.assertIn(r"\frac", cell_tex)

        labels = ["1", "2"]
        answers = [r"\frac{1}{2}", r"(a) $x = 3$ (b) $y = 4$"]
        overlay_tex = pdf_generator.build_latex_answer_sheet_overlay_source(
            labels=labels,
            answers=answers,
            total_pages=1,
            is_teacher=True,
            term=1,
            week=3
        )
        self.assertIn(r"\begin{tikzpicture}[x=1pt, y=1pt]", overlay_tex)
        self.assertIn("max width=105pt", overlay_tex)
        self.assertIn("max height=24pt", overlay_tex)

    def test_review_booklet_bulleted_summary_formatting(self):
        """Verify that review booklet parses markdown bullet points in revision_summary into LaTeX itemize."""
        booklet_data = {
            "title": "Year 8 Mathematics - Number Skills Review",
            "year_level": "Year 8",
            "topic": "Number Skills",
            "concepts": [
                {
                    "concept_name": "Index Laws",
                    "revision_summary": "- **Multiplication Rule**: Add powers when bases are identical ($a^m \\times a^n = a^{m+n}$).\n- **Division Rule**: Subtract powers ($a^m \\div a^n = a^{m-n}$).\n- **Zero Power**: Any non-zero base to power zero equals 1 ($a^0 = 1$).",
                    "key_formulas": ["a^m \\times a^n = a^{m+n}"],
                    "tips_and_tricks": "Always separate coefficients from variables.",
                    "common_pitfalls": ["Multiplying bases instead of adding powers"],
                    "mastery_examples": [
                        {
                            "example_num": 1,
                            "title": "Simplifying Expressions",
                            "problem_text": "Simplify $2x^3 \\times 4x^5$.",
                            "worked_solution": "$8x^8$",
                            "exam_commentary": "Standard 2-mark question."
                        }
                    ],
                    "review_questions": [
                        {
                            "q_num": 1,
                            "difficulty": "Level 1",
                            "marks": 1,
                            "text": "Simplify $x^4 \\times x^3$.",
                            "worked_solution": "$x^7$",
                            "final_answer": "$x^7$"
                        }
                    ]
                }
            ]
        }
        tex_source = pdf_generator.build_latex_review_booklet_source(booklet_data, mode="teacher")
        self.assertIn(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.25em, topsep=0.12em, label={\color{dagold}$\blacktriangleright$}]", tex_source)
        self.assertIn(r"\textbf{Multiplication Rule}", tex_source)
        self.assertIn(r"\textbf{Division Rule}", tex_source)
        self.assertIn(r"\textbf{Zero Power}", tex_source)

    def test_theory_booklet_student_class_omits_working_boxes(self):
        """Verify that student_class theory booklet has no workingbox, uses green badge, and includes answers at the back."""
        booklet_data = {
            "title": "Linear Relationships Theory Booklet",
            "year_level": "Year 9",
            "topic": "Linear Relationships",
            "textbook": "CambridgeMATHS NSW Stage 5.3",
            "concepts": [
                {
                    "concept_name": "Gradient and Intercept",
                    "theory_content": "The gradient-intercept form is $y = mx + b$.",
                    "key_formulas": ["y = mx + b"],
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "problem_text": "Find the gradient of $y = 3x - 5$.",
                            "whiteboard_solution": "$m = 3$"
                        }
                    ],
                    "practice_questions": [
                        {
                            "q_num": 1,
                            "marks": 2,
                            "text": "State the gradient and y-intercept of $y = -2x + 7$.",
                            "worked_solution": "$m = -2$, $b = 7$",
                            "final_answer": "$m = -2$, $b = 7$"
                        }
                    ]
                }
            ]
        }
        tex_class = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_class")
        # Check badge & edition label
        self.assertIn("THEORY STUDENT CLASS (IN-CLASS WORKBOOK)", tex_class)
        self.assertIn("fill=dagreen!15", tex_class)
        # Check that workingbox is omitted to save paper
        self.assertNotIn(r"\begin{workingbox}", tex_class)
        # Class copies contain questions only; answers remain in the private edition.
        self.assertNotIn("Plain Answers (For Student Self-Checking)", tex_class)
        self.assertNotIn("THE EXAMINER", tex_class)
        # Student Class uses the student's own exercise book for notes and working.
        self.assertNotIn(r"\begin{theorybox}[", tex_class)
        self.assertNotIn("THE BIG IDEA (HOW TO THINK ABOUT IT)", tex_class)
        self.assertNotIn("ESSENTIAL FORMULAE", tex_class)
        self.assertNotIn("VISUAL MODEL", tex_class)
        self.assertNotIn("DA MASTER METHOD", tex_class)
        self.assertIn("Teacher Demonstration Examples", tex_class)

        # Confirm student_private mode also omits workingbox but has complete notes badge
        tex_private = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_private")
        self.assertIn("THEORY STUDENT PRIVATE (COMPLETE NOTES)", tex_private)
        self.assertNotIn(r"\begin{workingbox}", tex_private)
        self.assertIn("Plain Answers (For Student Self-Checking)", tex_private)

    def test_theory_checking_understanding_and_private_demo_solutions(self):
        booklet_data = {
            "title": "Permutations Theory Booklet",
            "year_level": "Year 11 (Extension)",
            "topic": "Permutations",
            "concepts": [{
                "concept_name": "Distinct arrangements",
                "theory_content": "Order matters.",
                "teacher_examples": [{
                    "example_num": 1,
                    "title": "Direct counting",
                    "problem_text": "Arrange three people.",
                    "worked_solution": "3! = 6"
                }],
                "checking_understanding_questions": [{
                    "q_num": 1,
                    "text": "Arrange four people.",
                    "worked_solution": "4! = 24",
                    "final_answer": "24"
                }],
                "practice_questions": [{
                    "q_num": 1,
                    "text": "Evaluate 5!.",
                    "part": "Part 1: Commit to Memory",
                }]
            }]
        }

        class_tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_class")
        self.assertNotIn("DA SIGNATURE MASTERCLASS NOTES", class_tex)
        self.assertIn(r"\subsection*{Checking Understanding}", class_tex)
        self.assertNotIn(r"\begin{workingbox}{3.0cm}", class_tex)
        self.assertRegex(class_tex, r"\\vspace\{-0\.30cm\}\s+\\noindent\{\\large\\bfseries\\color\{danavy\}Teacher Demonstration Examples\}")
        self.assertIn(r"Arrange three people.\par\vspace{0.02cm}", class_tex)
        self.assertRegex(class_tex, r"(?s)\\subsection\*\{Checking Understanding\}.*?\\vspace\{0\.16cm\}.*?Practice")

        private_tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_private")
        self.assertIn(r"\begin{solutionbox}[{Model Whiteboard Solution}]", private_tex)
        self.assertIn(r"\subsection*{Checking Understanding}", private_tex)
        self.assertIn(r"\begin{workingbox}{3.0cm}", private_tex)

    def test_factorial_teacher_card_renders_basic_example_and_full_notes(self):
        if not pdf_generator.find_pdflatex():
            self.skipTest("pdflatex is required to inspect the rendered theory booklet")

        booklet_data = {
            "title": "Combinatorics (Ext 1)",
            "year_level": "Year 11 (Extension)",
            "topic": "Combinatorics (Ext 1)",
            "concepts": [{
                "concept_name": "Factorial notation",
                "theory_content": (
                    "- **The Big Idea (How to Think About It)**: "
                    "Factorial notation means multiplying a positive integer down to 1."
                ),
                "teacher_examples": [{
                    "example_num": 1,
                    "problem_text": "Evaluate 6!.",
                    "worked_solution": "6! = 720",
                }],
            }],
        }
        pdf_bytes = pdf_generator.generate_latex_theory_booklet_pdf(booklet_data, mode="teacher")
        self.assertTrue(pdf_bytes)
        page_text = pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
        self.assertIn("6! = 6", page_text)
        self.assertIn("720", page_text)
        self.assertIn("0! = 1", page_text)
        self.assertIn("ESSENTIAL FORMULAE", page_text)
        self.assertIn("DA MASTER METHOD", page_text)
        self.assertIn("THE EXAMINER", page_text)
        self.assertNotIn("Domain:", page_text)

        private_pdf = pdf_generator.generate_latex_theory_booklet_pdf(booklet_data, mode="student_private")
        self.assertTrue(private_pdf)
        private_pages = pypdf.PdfReader(io.BytesIO(private_pdf)).pages
        private_text = "\n".join(page.extract_text() for page in private_pages)
        self.assertRegex(private_pages[0].extract_text(), r"T\s*eacher\s+Demonstration Examples")
        self.assertIn("Evaluate 6!", private_pages[0].extract_text())
        self.assertRegex(private_text, r"T\s*eacher\s+Demonstration Examples")
        self.assertIn("Evaluate 6!", private_text)
        self.assertIn("720", private_text)

        class_pdf = pdf_generator.generate_latex_theory_booklet_pdf(booklet_data, mode="student_class")
        self.assertTrue(class_pdf)
        class_page_text = pypdf.PdfReader(io.BytesIO(class_pdf)).pages[0].extract_text()
        self.assertRegex(class_page_text, r"T\s*eacher\s+Demonstration Examples")
        self.assertNotIn("Core Concept", class_page_text)
        self.assertNotIn("THE BIG IDEA", class_page_text)
        self.assertNotIn("720", class_page_text)

    def test_student_class_reportlab_fallback_has_only_questions(self):
        booklet_data = {
            "title": "Factorial notation",
            "year_level": "Year 11 (Extension)",
            "topic": "Combinatorics (Ext 1)",
            "concepts": [{
                "concept_name": "Factorial notation",
                "theory_content": "Multiply down to one.",
                "key_formulas": ["n! = n(n-1)!"],
                "teacher_examples": [{"example_num": 1, "problem_text": "Evaluate 6!.", "worked_solution": "720"}],
                "checking_understanding_questions": [{"q_num": 1, "text": "Evaluate 5!."}],
                "practice_questions": [{"q_num": 1, "text": "Evaluate 4!.", "final_answer": "24"}],
            }],
        }
        pdf_bytes = pdf_generator.generate_reportlab_theory_booklet_pdf(booklet_data, mode="student_class")
        full_text = "\n".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)
        self.assertIn("Evaluate 6!", full_text)
        self.assertIn("Checking Understanding", full_text)
        self.assertIn("Evaluate 4!", full_text)
        self.assertNotIn("Core Theory", full_text)
        self.assertNotIn("Essential Formulae", full_text)
        self.assertNotIn("Student working", full_text)
        self.assertNotIn("Plain Answers", full_text)

    def test_crowded_combinatorics_diagrams_render_with_clear_labels(self):
        if not pdf_generator.find_pdflatex():
            self.skipTest("pdflatex is required to inspect rendered diagrams")

        diagram_cases = [
            ("Ordered selections", "Ordered Unordered", ("Ordered", "Unordered")),
            ("Factorial countdown", "Peel off leading Remaining countdown", ("Peel off", "Remaining countdown")),
            ("Circular seating", "Anchor (1 way) Chair 5", ("Anchor (1 way)", "Chair 5")),
            ("Sample space", "Sample Space Event", ("Sample Space", "Event")),
        ]
        concepts = []
        for name, labels, _ in diagram_cases:
            concepts.append({
                "concept_name": name,
                "theory_content": "A visual model.",
                "tikz_diagram": rf"\begin{{tikzpicture}}\node at (0,0) {{{labels}}};\end{{tikzpicture}}",
            })
        booklet = {
            "title": "Combinatorics diagram check",
            "year_level": "Year 11 (Extension)",
            "topic": "Combinatorics (Ext 1)",
            "concepts": concepts,
        }
        pdf_bytes = pdf_generator.generate_latex_theory_booklet_pdf(booklet, mode="teacher")
        self.assertTrue(pdf_bytes)
        pages = pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages
        self.assertEqual(len(pages), 4)
        for page, (_, _, expected_labels) in zip(pages, diagram_cases):
            text = page.extract_text()
            for label in expected_labels:
                self.assertIn(label, text)

        circle_source = pdf_generator.sanitize_tikz_diagram(concepts[2]["tikz_diagram"])
        self.assertNotIn("fill=white", circle_source)
        self.assertNotIn("fill opacity", circle_source)

    def test_review_booklet_student_class_omits_working_boxes(self):
        """Verify that student_class review booklet has no reviewworkingbox, uses green badge, and includes quick answers."""
        booklet_data = {
            "title": "Year 10 Mathematics - Trigonometry Review",
            "year_level": "Year 10",
            "topic": "Trigonometry",
            "textbook": "CambridgeMATHS Stage 5.3",
            "concepts": [
                {
                    "concept_name": "Right-Angled Trig",
                    "revision_summary": "SOH CAH TOA rules.",
                    "key_formulas": [r"\sin\theta = \frac{O}{H}"],
                    "tips_and_tricks": "Always label hypotenuse first.",
                    "mastery_examples": [
                        {
                            "example_num": 1,
                            "problem_text": "Calculate the opposite side when angle is 30 deg.",
                            "worked_solution": "$O = H \\sin(30^\\circ)$",
                            "exam_commentary": "Check calculator in degrees mode."
                        }
                    ],
                    "review_questions": [
                        {
                            "q_num": 1,
                            "marks": 2,
                            "difficulty": "Standard",
                            "text": "Find $x$ in a right triangle.",
                            "worked_solution": "$x = 5$",
                            "final_answer": "$x = 5$"
                        }
                    ]
                }
            ]
        }
        tex_class = pdf_generator.build_latex_review_booklet_source(booklet_data, mode="student_class")
        # Check badge & edition label
        self.assertIn("STUDENT CLASS COMPACT REVISION (WORK IN EXERCISE BOOK)", tex_class)
        self.assertIn("fill=dagreen!15", tex_class)
        # Check that reviewworkingbox is omitted to save paper
        self.assertNotIn(r"\begin{reviewworkingbox}", tex_class)
        # Check that quick answers are present at the back
        self.assertIn("Quick Verification Answers", tex_class)
        self.assertIn("exercise book", tex_class.lower())
        self.assertIn("$x = 5$", tex_class)

        # Confirm normal student mode has generous working whitespace (itemsep=1.8cm), while student_class has compact (itemsep=0.6em)
        tex_student = pdf_generator.build_latex_review_booklet_source(booklet_data, mode="student")
        self.assertIn("STUDENT TOPIC REVISION", tex_student)
        self.assertIn("itemsep=1.8cm", tex_student)
        self.assertIn("itemsep=0.6em", tex_class)

    def test_pdf_generator_student_class_filenames(self):
        """Verify pdf_generator filename helpers format Student no space correctly without underscores."""
        tb_data = {"topic": "Linear Relationships", "textbook": "CambridgeMATHS NSW"}
        fn_tb = pdf_generator.get_theory_booklet_download_filename(tb_data, mode="student_class")
        self.assertEqual(fn_tb, "Linear Relationships Theory Student no space (Cambridge).pdf")
        self.assertNotIn("_", fn_tb)

        rb_data = {"topic": "Trigonometry", "textbook": "Maths in Focus"}
        fn_rb = pdf_generator.get_review_booklet_download_filename(rb_data, mode="student_class")
        self.assertEqual(fn_rb, "Trigonometry Review Student no space (Maths in Focus).pdf")
        self.assertNotIn("_", fn_rb)

    def test_sanitize_for_latex_preserves_tabular_and_stem_leaf(self):
        """Verify tabulars, stem-and-leaf plots, and Key annotations are preserved without & escaping."""
        raw_stem = (
            "Examine the following stem-and-leaf plot:\n"
            "\\begin{tabular}{r|l}\n"
            "Stem & Leaf \\\\\n"
            "\\hline\n"
            "1 & 2 9 \\\\\n"
            "2 & 1 3 5 8 \\\\\n"
            "3 & 0 2 4 7 9 \\\\\n"
            "\\end{tabular}\n"
            "Key: 1 | 2 = 12\n"
            "Find the median."
        )
        sanitized = pdf_generator.sanitize_for_latex(raw_stem)
        # Verify column separator & was NOT escaped to \&
        self.assertIn("1 & 2 9 \\\\", sanitized)
        self.assertNotIn(r"1 \& 2 9", sanitized)
        self.assertIn(r"\textbf{Stem} & \textbf{Leaf}", sanitized)
        self.assertIn(r"\textbf{Key:} $1 \mid 2 = 12$", sanitized)
        self.assertIn(r"\begin{center}", sanitized)

    def test_markdown_table_to_latex_conversion(self):
        """Verify markdown tables (frequency tables and stem-and-leaf) convert to LaTeX tabulars."""
        md_table = (
            "| Score | Frequency |\n"
            "|---|---|\n"
            "| 0 | 5 |\n"
            "| 1 | 12 |\n"
            "| 2 | 8 |\n"
        )
        latex_converted = pdf_generator.markdown_table_to_latex(md_table)
        self.assertIn(r"\begin{tabular}{|c|c|}", latex_converted)
        self.assertIn(r"\textbf{Score} & \textbf{Frequency}", latex_converted)
        self.assertIn(r"1 & 12", latex_converted)

        # Ensure passing through sanitize_for_latex keeps & intact
        sanitized = pdf_generator.sanitize_for_latex(md_table)
        self.assertIn(r"\begin{tabular}{|c|c|}", sanitized)
        self.assertIn("1 & 12", sanitized)
        self.assertNotIn(r"1 \& 12", sanitized)

    def test_cartesian_plane_quadrant_sanitization(self):
        """Verify Cartesian plane quadrant labels are repositioned away from axes and points."""
        diag_raw = (
            "\\begin{tikzpicture}[scale=0.75]\n"
            "\\draw[step=1cm,gray!30,very thin] (-4,-4) grid (4,4);\n"
            "\\draw[thick,->] (-4.5,0) -- (4.5,0) node[right] {$x$};\n"
            "\\draw[thick,->] (0,-4.5) -- (0,4.5) node[above] {$y$};\n"
            "\\node at (2.2, 2.2) {\\textbf{Quadrant 1} $(+,+)$};\n"
            "\\node at (-2.2, 2.2) {\\textbf{Quadrant 2} $(-,+)$};\n"
            "\\node at (-2.2, -2.2) {\\textbf{Quadrant 3} $(-,-)$};\n"
            "\\node at (2.2, -2.2) {\\textbf{Quadrant 4} $(+,-)$};\n"
            "\\filldraw[blue] (3,2) circle (2pt) node[above right] {$A(3, 2)$};\n"
            "\\end{tikzpicture}"
        )
        cleaned = pdf_generator.sanitize_tikz_diagram(diag_raw)
        self.assertIn(r"at (1.8, 3.1) {\textbf{Quadrant 1}\\$(+,+)$};", cleaned)
        self.assertIn(r"at (-2.0, 1.4) {\textbf{Quadrant 2}\\$(-,+)$};", cleaned)
        self.assertIn(r"at (-2.0, -2.6) {\textbf{Quadrant 3}\\$(-,-)$};", cleaned)
        self.assertIn(r"at (2.0, -1.4) {\textbf{Quadrant 4}\\$(+,-)$};", cleaned)
        self.assertIn(r"fill=white", cleaned)

    def test_format_practice_difficulty_all_five_tiers(self):
        """Verify modern pedagogical tier formatting for all 5 tiers (Section 1 through 4 + Exam Style)."""
        self.assertEqual(pdf_generator.format_practice_difficulty("Level 1"), "Section 1 - Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("drilling"), "Section 1 - Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("practice"), "Section 1 - Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("easy"), "Section 1 - Practice")

        self.assertEqual(pdf_generator.format_practice_difficulty("Level 2"), "Section 2 - Further Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("further practice"), "Section 2 - Further Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("deeper understanding"), "Section 2 - Further Practice")
        self.assertEqual(pdf_generator.format_practice_difficulty("medium"), "Section 2 - Further Practice")

        self.assertEqual(pdf_generator.format_practice_difficulty("Level 3"), "Section 3 - Application")
        self.assertEqual(pdf_generator.format_practice_difficulty("application"), "Section 3 - Application")
        self.assertEqual(pdf_generator.format_practice_difficulty("hard"), "Section 3 - Application")

        self.assertEqual(pdf_generator.format_practice_difficulty("Level 4"), "Section 4 - Challenging")
        self.assertEqual(pdf_generator.format_practice_difficulty("challenging"), "Section 4 - Challenging")
        self.assertEqual(pdf_generator.format_practice_difficulty("extremely hard"), "Section 4 - Challenging")

        self.assertEqual(pdf_generator.format_practice_difficulty("Exam Style"), "Exam Style")
        self.assertEqual(pdf_generator.format_practice_difficulty("exam"), "Exam Style")
        self.assertEqual(pdf_generator.format_practice_difficulty("hsc"), "Exam Style")

    def test_right_aligned_level_badges_in_booklet_latex(self):
        """Verify that question headers in Theory and Review booklets align level and marks to the right margin."""
        single_concept_data = {
            "title": "Year 7 Maths - Test Review Booklet",
            "year_level": "Year 7",
            "topic": "Data Analysis",
            "textbook": "CambridgeMATHS NSW Stage 4",
            "concepts": [{
                "name": "Mean and Median",
                "revision_summary": "- **Core Definition**: A measure of center.",
                "key_formulas": ["$\\bar{x} = \\frac{\\sum x}{n}$"],
                "mastery_examples": [],
                "review_questions": [{
                    "q_num": 1,
                    "difficulty": "Level 1 - Drilling",
                    "marks": 2,
                    "text": "Calculate the mean of 4, 6, 8.",
                    "worked_solution": "Mean is 6.",
                    "final_answer": "6"
                }],
                "practice_questions": [{
                    "q_num": 1,
                    "difficulty": "Level 2 - Deeper Understanding",
                    "marks": 3,
                    "text": "Calculate the median.",
                    "worked_solution": "Median is 7.",
                    "final_answer": "7"
                }]
            }]
        }
        # Single concept: no TOC, no marks, two-column layout with Part tier headers
        rev_tex = pdf_generator.build_latex_review_booklet_source(single_concept_data, mode="student")
        self.assertIn(r"\begin{multicols}{2}", rev_tex)
        self.assertIn("Revision (Part 1: Commit to Memory)", rev_tex)
        self.assertNotIn("Booklet Contents", rev_tex)
        self.assertNotIn("2~marks", rev_tex)
        self.assertNotIn("Concept A:", rev_tex)

        th_tex = pdf_generator.build_latex_theory_booklet_source(single_concept_data, mode="student")
        self.assertNotIn(r"\begin{multicols}{2}", th_tex)
        self.assertIn("Practice (Part 2: Further Practice)", th_tex)
        self.assertNotIn("Booklet Contents", th_tex)
        self.assertNotIn("3~marks", th_tex)
        self.assertNotIn("Concept A:", th_tex)

        # Multi concept: include Concept A/B and label as Revision A/B (Part X) and Practice A/B (Part X)
        multi_concept_data = {
            "title": "Year 7 Maths - Multi Concept Review",
            "year_level": "Year 7",
            "topic": "Data Analysis",
            "textbook": "CambridgeMATHS NSW Stage 4",
            "concepts": [
                {
                    "name": "Mean and Median",
                    "revision_summary": "Core summary",
                    "mastery_examples": [],
                    "review_questions": [{
                        "q_num": 1,
                        "difficulty": "Level 1 - Drilling",
                        "marks": 2,
                        "text": "Mean problem",
                        "final_answer": "6"
                    }],
                    "practice_questions": [{
                        "q_num": 1,
                        "difficulty": "Level 2 - Deeper Understanding",
                        "marks": 3,
                        "text": "Median problem",
                        "final_answer": "7"
                    }]
                },
                {
                    "name": "Range and Outliers",
                    "revision_summary": "Range summary",
                    "mastery_examples": [],
                    "review_questions": [{
                        "q_num": 1,
                        "difficulty": "Level 3 - Application",
                        "marks": 4,
                        "text": "Range problem",
                        "final_answer": "10"
                    }],
                    "practice_questions": [{
                        "q_num": 1,
                        "difficulty": "Level 3 - Application",
                        "marks": 4,
                        "text": "Outlier problem",
                        "final_answer": "25"
                    }]
                }
            ]
        }
        multi_rev_tex = pdf_generator.build_latex_review_booklet_source(multi_concept_data, mode="student")
        self.assertIn(r"\begin{multicols}{2}", multi_rev_tex)
        self.assertIn("Revision A (Part 1: Commit to Memory)", multi_rev_tex)
        self.assertIn("Revision B (Part 3: Application)", multi_rev_tex)
        self.assertNotIn("2~marks", multi_rev_tex)
        self.assertNotIn("Booklet Contents", multi_rev_tex)

        multi_th_tex = pdf_generator.build_latex_theory_booklet_source(multi_concept_data, mode="student")
        self.assertNotIn(r"\begin{multicols}{2}", multi_th_tex)
        self.assertIn("Practice A (Part 2: Further Practice)", multi_th_tex)
        self.assertIn("Practice B (Part 3: Application)", multi_th_tex)
        self.assertNotIn("3~marks", multi_th_tex)
        self.assertNotIn("Booklet Contents", multi_th_tex)

    def test_review_booklet_answer_sheet_data_and_filenames(self):
        """Verify extract_review_booklet_answer_sheet_data and get_review_booklet_download_filename."""
        single_data = {
            "title": "Practical Optimisation Review Booklet",
            "year_level": "Year 12 (Advanced)",
            "topic": "Practical Optimisation",
            "textbook": "Cambridge",
            "concepts": [{
                "name": "Single Concept",
                "review_questions": [
                    {"q_num": 1, "text": "Q1", "final_answer": "42"},
                    {"q_num": 2, "text": "Q2", "final_answer": "x = 5"}
                ]
            }]
        }
        labels, answers, key = pdf_generator.extract_review_booklet_answer_sheet_data(single_data)
        self.assertEqual(labels, ["1", "2"])
        self.assertEqual(answers, ["42", "x = 5"])
        self.assertEqual(key, {"1": "42", "2": "x = 5"})

        # Multi concept
        multi_data = {
            "title": "Calculus Review Booklet",
            "year_level": "Year 12 (Advanced)",
            "topic": "Calculus",
            "textbook": "Cambridge",
            "concepts": [
                {
                    "name": "Differentiation",
                    "review_questions": [{"q_num": 1, "text": "Q1", "final_answer": "2x"}]
                },
                {
                    "name": "Integration",
                    "review_questions": [{"q_num": 1, "text": "Q2", "final_answer": "x^2 + C"}]
                }
            ]
        }
        m_labels, m_answers, m_key = pdf_generator.extract_review_booklet_answer_sheet_data(multi_data)
        self.assertEqual(m_labels, ["A1", "B1"])
        self.assertEqual(m_answers, ["2x", "x^2 + C"])
        self.assertEqual(m_key, {"A1": "2x", "B1": "x^2 + C"})

        # Filename testing
        fn_student_ans = pdf_generator.get_review_booklet_download_filename(single_data, mode="student_answer_sheet")
        self.assertEqual(fn_student_ans, "DA Student Answer Sheet Practical Optimisation Review (Cambridge).pdf")

        fn_teacher_ans = pdf_generator.get_review_booklet_download_filename(single_data, mode="teacher_answer_sheet")
        self.assertEqual(fn_teacher_ans, "DA Teacher Answer Sheet Practical Optimisation Review (Cambridge).pdf")

        fn_marking_key = pdf_generator.get_review_booklet_download_filename(single_data, mode="marking_key", extension="json")
        self.assertEqual(fn_marking_key, "Marking Key Practical Optimisation Review (Cambridge).json")

    def test_exam_practice_pagination_and_working_boxes(self):
        # Part A questions matching user's scenario
        questions = [
            {"source_tag": "Foundational Drill", "marks": 1, "text": "State whether the set of ordered pairs represents a function."},
            {"source_tag": "Standard Exam Question", "marks": 2, "text": "By applying the vertical line test, explain why x^2 + y^2 = 16 is not a function."},
            {"source_tag": "Applied Graph Analysis", "marks": 2, "text": "A student models a roller coaster loop using (x-5)^2 + (y-5)^2 = 9. Can height be modeled as a function?"},
            {"source_tag": "Distinction Challenge", "marks": 3, "text": "A relation is defined by |x| + |y| = 4. Sketch the relation and prove whether it is a function."},
            {"source_tag": "School Trial Synthesiser", "marks": 3, "text": "For what values of the constant c does the relation represent a function?"}
        ]
        
        # Test pagination for first concept (with cover top matter)
        plan_p1 = pdf_generator.paginate_exam_practice_questions(questions, is_first_concept=True)
        self.assertEqual(len(plan_p1), 2)
        # Page 1 must have exactly 2 questions (Q1 and Q2), moving Q3 to Page 2
        self.assertEqual(len(plan_p1[0]["questions"]), 2)
        self.assertEqual(plan_p1[0]["questions"][0]["source_tag"], "Foundational Drill")
        self.assertEqual(plan_p1[0]["questions"][1]["source_tag"], "Standard Exam Question")
        # Boxes on Page 1 must be enlarged to fill the page down to just above the footer
        self.assertGreaterEqual(plan_p1[0]["box_heights"][0], 5.0)
        self.assertGreaterEqual(plan_p1[0]["box_heights"][1], 7.0)
        # Page 2 must have Q3, Q4, Q5 together
        self.assertEqual(len(plan_p1[1]["questions"]), 3)
        self.assertEqual(plan_p1[1]["questions"][0]["source_tag"], "Applied Graph Analysis")

        # Verify LaTeX generation includes glue protections against decoupling
        package_data = {
            "title": "Year 11 Maths Functions Practice",
            "year_level": "Year 11 (Advanced) Maths",
            "topic": "Functions & Graphs",
            "concepts": [{"concept_name": "Part A", "practice_questions": questions}]
        }
        tex = pdf_generator.build_latex_exam_practice_source(package_data, mode="student")
        self.assertIn(r"\needspace{4.0cm}", tex)
        self.assertIn(r"\par\nopagebreak\vspace{0.18cm}\nopagebreak", tex)
        self.assertIn(r"\nopagebreak\begin{studentworkingbox}", tex)
    def test_hyphenation_suppression_and_question_subparts(self):
        """Verify that hyphenation suppression is active and question subparts are safely parsed without breaking h(x)."""
        # 1. Test split_question_subparts protects math functions like h(x)
        h_q = r"Find the natural domain and range of the function $h(x) = 3 - \sqrt{x+1}$."
        stem, subs = pdf_generator.split_question_subparts(h_q)
        self.assertEqual(subs, [], "Math functions like h(x) should not produce subparts")
        self.assertIn("h(x)", stem)

        # 2. Test split_question_subparts correctly splits (a) and (b)
        multi_q = r"A cylinder has radius $r$ and height $h$. (a) Express the total surface area $A$. (b) Show that $A = 2\pi r^2 + \frac{1000\pi}{r}$."
        stem_m, subs_m = pdf_generator.split_question_subparts(multi_q)
        self.assertEqual(len(subs_m), 2)
        self.assertEqual(subs_m[0][0], "a")
        self.assertEqual(subs_m[1][0], "b")
        self.assertIn("A cylinder has radius", stem_m)

        # 3. Test format_latex_question_with_subparts formats parts in hung enumerate list
        formatted = pdf_generator.format_latex_question_with_subparts(multi_q, as_item=False)
        formatted_str = "\n".join(formatted)
        self.assertIn(r"label=\textbf{(\alph*)}", formatted_str)
        self.assertIn(r"\item Express the total surface area", formatted_str)

        # 4. Verify LaTeX source in theory booklet includes hyphenation suppression and minipage wrapping
        booklet = {
            "title": "Year 11 Maths Test",
            "year_level": "Year 11 (Advanced)",
            "topic": "Functions",
            "concepts": [{
                "name": "Functions",
                "practice_questions": [
                    {"q_num": 1, "text": h_q, "final_answer": "x >= -1"},
                    {"q_num": 2, "text": multi_q, "final_answer": "done"}
                ]
            }]
        }
        th_tex = pdf_generator.build_latex_theory_booklet_source(booklet, mode="student")
        self.assertIn(r"\hyphenpenalty=10000", th_tex)
        self.assertIn(r"\exhyphenpenalty=10000", th_tex)
        self.assertIn(r"\tolerance=9999", th_tex)
        self.assertIn(r"\emergencystretch=2.5em", th_tex)
        self.assertIn(r"\needspace{3.2cm}", th_tex)
        self.assertNotIn(r"(x)~=", th_tex, "(x) must not be falsely split from h")

        # 5. Verify review booklet also includes hyphenation suppression and minipage wrapping
        rev_tex = pdf_generator.build_latex_review_booklet_source(booklet, mode="student")
        self.assertIn(r"\hyphenpenalty=10000", rev_tex)
        self.assertIn(r"\begin{minipage}[t]{\linewidth}", rev_tex)
        self.assertNotIn(r"(x)~=", rev_tex)

    def test_condense_theory_notes_for_in_class(self):
        """Verify verbose self-study notes are condensed to Core Definition, Key Rules, and DA Quick-Method."""
        verbose_theory = (
            "- **What It Is (From Scratch)**: A function links inputs to outputs. Every input produces a unique output. "
            "Think of a function like a reliable vending machine: when you press A1, you get one snack, never two snacks at once.\n"
            "- **Rule**: A relation R is a function iff every x has a unique y. Geometrically, this gives rise to the Vertical Line Test.\n"
            "- **Visual Intuition**: Picture sweeping a clear vertical ruler from left to right.\n"
            "- **Step-by-Step Method**:\n"
            "1. Solve explicitly for y.\n"
            "2. Check if isolating y introduces a \\pm sign.\n"
            "3. State whether vertical lines intersect once.\n"
            "- **Exam Action Trigger**: Look for phrases such as determine whether relation is a function.\n"
            "- **Common Trap & Self-Check**: Do not confuse vertical line test with horizontal line test."
        )
        condensed = pdf_generator.condense_theory_notes_for_in_class(verbose_theory)
        # Analogy stripped
        self.assertNotIn("vending machine", condensed)
        self.assertNotIn("sweeping a clear vertical ruler", condensed)
        self.assertNotIn("Exam Action Trigger", condensed)
        self.assertNotIn("Common Trap & Self-Check", condensed)
        # Core parts kept
        self.assertIn("Core Definition", condensed)
        self.assertIn("Key Rules", condensed)
        self.assertIn("DA Quick-Method", condensed)
        self.assertIn("1. Solve explicitly for y.", condensed)
        self.assertIn("2. Check if isolating y introduces a \\pm sign.", condensed)

    def test_bare_math_wrapping_in_text_mode(self):
        """Verify illegal LaTeX math commands and bare exponents in text mode are wrapped in \\ensuremath."""
        text = "Check if isolating y introduces a \\pm sign (e.g. y^2 = x \\implies y = \\pm\\sqrt{x}). (x, y) \\in R."
        sanitized = pdf_generator.sanitize_for_latex(text)
        self.assertIn(r"\ensuremath{\pm}", sanitized)
        self.assertIn(r"\ensuremath{y^2}", sanitized)
        self.assertIn(r"\ensuremath{\implies}", sanitized)
        self.assertIn(r"\ensuremath{\in}", sanitized)
        self.assertIn(r"\ensuremath{\pm\sqrt{x}}", sanitized)
        self.assertNotIn(r"\pm\sqrt{x})", sanitized)  # Must be wrapped

    def test_format_teacher_example_heading_no_duplicate_tier(self):
        """Verify format_teacher_example_heading does not produce duplicate tier labels."""
        h1 = pdf_generator.format_teacher_example_heading(1, "Practice (Identifying Functions from Equations)")
        self.assertEqual(h1, "Example 1: Practice (Identifying Functions from Equations)")
        h2 = pdf_generator.format_teacher_example_heading(2, "Further Practice (Graphical Justification using Vertical Line Test)")
        self.assertEqual(h2, "Example 2: Further Practice (Graphical Justification using Vertical Line Test)")
        h3 = pdf_generator.format_teacher_example_heading(1, "Applying: Maximising Enclosed Area")
        self.assertEqual(h3, "Example 1: Practice (Maximising Enclosed Area)")

    def test_format_latex_practice_solution(self):
        """Verify format_latex_practice_solution formats equation steps vertically down with unglued marks."""
        raw_sol = "(a) Difference of two squares: (x - 2y)(x + 2y) = 0 [1 mark].yields two straight lines: y = \\frac{1}{2}x and y = -\\frac{1}{2}x [1 mark]. (b) Fails VLT [1 mark]."
        formatted = pdf_generator.format_latex_practice_solution(raw_sol)
        self.assertIn(r"\textbf{\color{danavy}(a)}", formatted)
        self.assertIn(r"\textbf{\color{danavy}(b)}", formatted)
        self.assertIn(r"[1 mark]", formatted)
        self.assertNotIn(r"[1 mark].yields", formatted)

        # Chained implications
        chained_sol = "gradient: 3y = -kx + 7 \\implies m_2 = -\\frac{k}{3} [1 mark].condition: m_1 \\times m_2 = -1 \\implies 3 \\times (-\\frac{k}{3}) = -1 \\implies k = 1 [1 mark]."
        chained_fmt = pdf_generator.format_latex_practice_solution(chained_sol)
        self.assertIn(r"\implies", chained_fmt)
        self.assertIn(r"\par\vspace", chained_fmt)

    def test_sanitize_out_of_syllabus_abs_y(self):
        """Verify any questions or notes containing |y| are replaced with in-scope Stage 6 content."""
        sample_data = {
            "concepts": [
                {
                    "concept_name": "Concept of a function",
                    "practice_questions": [
                        {"text": "A relation is defined by $|x| + |y| = 4$. Sketch and prove whether it is a function.", "final_answer": "Not a function"},
                        {"text": "Find domain of $f(x) = \\sqrt{x-2}$.", "final_answer": "$x \\ge 2$"}
                    ],
                    "teacher_examples": [
                        {"problem_text": "Explain why $|y| = x$ is not a function."}
                    ],
                    "exam_hacks": [
                        {"hack_content": "Check for even powers like $y^2 = 4x$ or $|y| = x$."}
                    ]
                }
            ]
        }
        sanitized = pdf_generator.sanitize_out_of_syllabus_abs_y(sample_data)
        q1_text = sanitized["concepts"][0]["practice_questions"][0]["text"]
        self.assertNotIn(r"|y|", q1_text)
        self.assertIn("x^2 + y^2 = 25", q1_text)
        ex_text = sanitized["concepts"][0]["teacher_examples"][0]["problem_text"]
        self.assertNotIn(r"|y|", ex_text)
        hack_text = sanitized["concepts"][0]["exam_hacks"][0]["hack_content"]
        self.assertNotIn(r"|y|", hack_text)

    def test_columnsep_and_diagram_in_theory_booklet(self):
        """Verify columnsep is set to 0.85cm and linear TikZ diagram has exact intercepts."""
        tikz = pdf_generator.get_concept_fallback_tikz("linear functions, gradients & intercepts")
        self.assertIn(r"(0, c)", tikz)
        self.assertIn(r"\left(-\frac{c}{m}, 0\right)", tikz)
        self.assertIn(r"\theta", tikz)

        booklet_data = {
            "year_level": "Year 11 (Advanced) Maths",
            "topic": "Functions & Graphs",
            "concepts": [
                {
                    "concept_name": "Linear functions, gradients & intercepts",
                    "theory_content": "- **Core Definition**: A linear function produces a straight line.",
                    "practice_questions": [
                        {"text": "Find gradient of $3x - 4y + 12 = 0$.", "final_answer": "3/4", "worked_solution": "Rearrange: $4y = 3x + 12 \\implies y = \\frac{3}{4}x + 3$ [1 mark]."}
                    ]
                }
            ]
        }
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="student_class")
        self.assertNotIn(r"\begin{multicols}{2}", tex)
        self.assertIn(r"\needspace{4.2cm}", tex)

    def test_clean_set_notation(self):
        """Verify that clean_set_notation removes formal university set notation and translates to high school English."""
        vlt = r"Vertical Line Test: |{y : (c, y) \in f}| \le 1 \quad \forall c \in \mathbb{R}"
        self.assertEqual(
            pdf_generator.clean_set_notation(vlt),
            "Vertical Line Test: Any vertical line $x = c$ intersects the graph at most once"
        )

        fn_cond = r"Function condition: If $(x,y_1) \in f$ and $(x,y_2) \in f$, then $y_1 = y_2$"
        self.assertIn("Each $x$-value has at most one $y$-value", pdf_generator.clean_set_notation(fn_cond))

        forall_r = r"For all $x \in \mathbb{R}$, $f(x) \ge 0$"
        self.assertNotIn(r"\mathbb{R}", pdf_generator.clean_set_notation(forall_r))
        self.assertIn("For all real $x$", pdf_generator.clean_set_notation(forall_r))

    def test_clean_sigma_and_advanced_symbols(self):
        """Verify that symbols like sigma (\\sum, \\Sigma, ∑, Σ) are cleanly translated for Year 10 students."""
        # 1. Handshaking Lemma with unicode sigma
        lemma_unicode = "• Handshaking Lemma: ∑ deg(v) = 2e (e = total number of edges)"
        cleaned_unicode = pdf_generator.clean_set_notation(lemma_unicode)
        self.assertNotIn("∑", cleaned_unicode)
        self.assertIn(r"\text{Sum of degrees}", cleaned_unicode)

        # 2. Handshaking Lemma with LaTeX \sum in math mode
        lemma_latex = r"Handshaking Lemma: $\sum \deg(v) = 2E$"
        cleaned_latex = pdf_generator.clean_set_notation(lemma_latex)
        self.assertNotIn(r"\sum", cleaned_latex)
        self.assertIn(r"\text{Sum of degrees} = 2E", cleaned_latex)

        # 3. Display math in worked solutions
        sol_math = r"\[\sum \deg(v) = 14 + 4 = 18\]"
        cleaned_sol = pdf_generator.clean_set_notation(sol_math)
        self.assertNotIn(r"\sum", cleaned_sol)
        self.assertIn(r"\text{Sum of degrees}", cleaned_sol)

        # 4. Statistics formulas
        stats = r"Mean: \bar{x} = \frac{\sum fx}{\sum f}"
        cleaned_stats = pdf_generator.clean_set_notation(stats)
        self.assertNotIn(r"\sum", cleaned_stats)
        self.assertIn(r"\text{Sum of }", cleaned_stats)
        self.assertIn(r"\text{Total frequency } n", cleaned_stats)

        # 5. sanitize_for_latex integration
        raw_tex = r"Handshaking Lemma: $\sum \deg(v) = 2e$"
        sanitized = pdf_generator.sanitize_for_latex(raw_tex)
        self.assertNotIn(r"\sum", sanitized)
        self.assertIn(r"\text{Sum of degrees}", sanitized)

    def test_format_latex_practice_solution_no_ne_split(self):
        """Verify that format_latex_practice_solution does not corrupt or split \\ne into \\n + e."""
        raw = r"(b) For any x \ne 0, a vertical line x = c intersects the graph at two distinct points: (c, c) and (c, -c). [1 mark]"
        out = pdf_generator.format_latex_practice_solution(raw)
        self.assertNotIn("\ne 0", out)
        self.assertNotIn("\ne", out)
        self.assertIn(r"\textbf{\color{danavy}(b)}", out)
        self.assertIn("For any x", out)

    def test_get_topic_exam_download_filename(self):
        """Verify DA publication naming convention for End-of-Topic Mastery Exam downloads."""
        exam = {
            "title": "Year 11 Mathematics - Functions (End-of-Topic Mastery Exam)",
            "topic": "Functions",
            "year_level": "Year 11",
            "textbook": "CambridgeMATHS NSW"
        }
        tb = {"topic": "Functions", "textbook": "CambridgeMATHS NSW"}
        
        fn_stu = pdf_generator.get_topic_exam_download_filename(exam, mode="student", theory_booklet=tb)
        self.assertEqual(fn_stu, "Functions End-of-Topic Mastery Exam Student (Cambridge).pdf")
        self.assertNotIn("_", fn_stu)

        fn_tea = pdf_generator.get_topic_exam_download_filename(exam, mode="teacher", theory_booklet=tb)
        self.assertEqual(fn_tea, "Functions End-of-Topic Mastery Exam Teacher Solutions (Cambridge).pdf")
        self.assertNotIn("_", fn_tea)

    def test_get_worksheet_download_filename(self):
        """Verify DA publication naming convention for In-Class and Homework worksheets."""
        tb = {"topic": "Functions", "textbook": "CambridgeMATHS NSW"}
        ic_ws = {
            "title": "Year 11 Mathematics - Functions (In-Class Practice)",
            "topic": "Functions",
            "assessment_type": "in_class",
            "textbook": "CambridgeMATHS NSW"
        }
        hw_ws = {
            "title": "Year 11 Mathematics - Functions (Homework - Set 1)",
            "topic": "Functions",
            "assessment_type": "homework",
            "set_number": 1,
            "textbook": "CambridgeMATHS NSW"
        }

        # In-Class
        fn_ic_stu = pdf_generator.get_worksheet_download_filename(ic_ws, sheet_type="in_class", mode="student", theory_booklet=tb)
        self.assertEqual(fn_ic_stu, "Functions In-Class Exercise Student (Cambridge).pdf")
        self.assertNotIn("_", fn_ic_stu)

        fn_ic_tea = pdf_generator.get_worksheet_download_filename(ic_ws, sheet_type="in_class", mode="teacher", theory_booklet=tb)
        self.assertEqual(fn_ic_tea, "Functions In-Class Exercise Teacher Solutions (Cambridge).pdf")

        fn_ic_ans = pdf_generator.get_worksheet_download_filename(ic_ws, sheet_type="in_class", mode="answers", theory_booklet=tb)
        self.assertEqual(fn_ic_ans, "Functions In-Class Exercise Quick Answers (Cambridge).pdf")

        # Homework Set 1
        fn_hw_stu = pdf_generator.get_worksheet_download_filename(hw_ws, sheet_type="homework", mode="student", theory_booklet=tb)
        self.assertEqual(fn_hw_stu, "Functions Homework Set 1 Student (Cambridge).pdf")
        self.assertNotIn("_", fn_hw_stu)

        fn_hw_tea = pdf_generator.get_worksheet_download_filename(hw_ws, sheet_type="homework", mode="teacher", theory_booklet=tb)
        self.assertEqual(fn_hw_tea, "Functions Homework Set 1 Teacher Solutions (Cambridge).pdf")

        fn_hw_ans = pdf_generator.get_worksheet_download_filename(hw_ws, sheet_type="homework", mode="answers", theory_booklet=tb)
        self.assertEqual(fn_hw_ans, "Functions Homework Set 1 Quick Answers (Cambridge).pdf")

    def test_worksheet_charter_font_and_multipart_subparts(self):
        """Verify worksheet uses Charter font and splits multi-part questions into clean indented sub-items."""
        questions = [
            {
                "item_label": "3",
                "text": "A relation is defined by the equation $(x-3)^2 + y^2 = 16$. (a) By testing $x = 3$, demonstrate why this relation fails the vertical line test and is therefore not a function. (b) Split the relation into two separate equations, each defining $y$ as a single function of $x$, and state the domain for both functions in interval notation.",
                "marks": 3,
                "correct_answer": "(a) $y = \\pm 4$, two outputs. (b) $y = \\sqrt{16-(x-3)^2}$ and $y = -\\sqrt{16-(x-3)^2}$, domain $[-1, 7]$.",
                "solution_steps": "(a) Substitute $x=3$: $(3-3)^2 + y^2 = 16 \\implies y = \\pm 4$. Since a single input $x=3$ yields two distinct $y$-values, it fails the vertical line test. (b) $y^2 = 16 - (x-3)^2 \\implies y = \\pm \\sqrt{16-(x-3)^2}$. Domain is $[-1, 7]$."
            }
        ]
        tex = pdf_generator.build_latex_worksheet_source(
            title="Year 11 Maths - Functions",
            year_level="Year 11",
            topic="Functions",
            questions=questions,
            include_solutions=True,
            sheet_type="Topic Mastery Exam",
            font_theme="charter"
        )
        # 1. Verify Charter font
        self.assertIn(r"\usepackage{charter}", tex)
        # 2. Verify subpart splitting into enumerate
        self.assertIn(r"\begin{enumerate}[label=\textbf{(\alph*)}", tex)
        self.assertIn(r"demonstrate why this relation fails the vertical line test", tex)
        self.assertIn(r"Split the relation into two separate equations", tex)
        self.assertIn(r"\qmark{3}", tex)
        # 3. Verify answers and solutions format subparts
        self.assertIn(r"\textbf{(a)}", tex)
        self.assertIn(r"\textbf{(b)}", tex)

    def test_build_masterclass_theory_box_content_formatting(self):
        """Verify theory box uses The Big Idea heading, separate lines for formulas, and no Step repetition."""
        theory_content = (
            "- **The Big Idea (How to Think About It)**: An index is a shortcut counter for how many copies of a number you are multiplying.\n"
            "- **DA Master Method (The Ninja Recipe)**:\n"
            "[Step 1] - [Step 1: Big Numbers First] Multiply or divide the regular numerical coefficients normally.\n"
            "[Step 2] - [Step 2: Same Bases Only] Identify matching base pronumerals. Add or subtract indices.\n"
            "[Step 3] - [Step 3: Alphabetical Combine] Write variables in alphabetical order.\n"
            "- **The Examiner's Trap (Mark Protector)**: Students frequently add coefficients instead of multiplying them."
        )
        key_formulas = [
            "First Index Law (Multiplication): $a^m \\times a^n = a^{m+n}$ ($a = \\text{base}, m, n = \\text{indices}$)",
            "Second Index Law (Division): $a^m \\div a^n = a^{m-n}$ ($a \\neq 0$)",
            "Coefficients Rule: $c_1 a^m \\times c_2 a^n = (c_1 \\times c_2) a^{m+n}$"
        ]

        card_tex = pdf_generator.build_masterclass_theory_box_content(
            theory_content=theory_content,
            key_formulas=key_formulas,
            tutor_tips="Always separate coefficients from index laws.",
            concept_name="Index Laws",
            topic="Algebra",
            year_level="Year 9 5.3"
        )

        # 1. Verify heading is THE BIG IDEA (HOW TO THINK ABOUT IT)
        self.assertIn("THE BIG IDEA (HOW TO THINK ABOUT IT)", card_tex)
        self.assertNotIn("THE GOLDEN INTUITION", card_tex)

        # 2. Verify formulas are on separate lines with bullets and NOT glued with \qquad\qquad
        self.assertNotIn(r"\qquad\qquad", card_tex)
        self.assertIn(r"\ensuremath{\bullet}\ \textbf{First Index Law (Multiplication):}", card_tex)
        self.assertIn(r"\ensuremath{\bullet}\ \textbf{Second Index Law (Division):}", card_tex)
        self.assertIn(r"\ensuremath{\bullet}\ \textbf{Coefficients Rule:}", card_tex)
        self.assertIn(r"\\[0.09cm]", card_tex)

        # 3. Verify no repetition in steps ([Step 1] - [Step 1: ...])
        self.assertIn(r"\textbf{\color{dablue}[Step 1: Big Numbers First]} Multiply", card_tex)
        self.assertIn(r"\textbf{\color{dablue}[Step 2: Same Bases Only]} Identify", card_tex)
        self.assertIn(r"\textbf{\color{dablue}[Step 3: Alphabetical Combine]} Write", card_tex)
        self.assertNotIn(r"[Step 1] - [Step 1", card_tex)
        # 4. Verify ESSENTIAL FORMULAE heading (and no VARIABLE BLUEPRINT)
        self.assertIn("ESSENTIAL FORMULAE", card_tex)
        self.assertNotIn("VARIABLE BLUEPRINT", card_tex)

    def test_theory_box_angle_diagrams_and_single_line_steps(self):
        """Verify that geometric angle rules get side-by-side mini TikZ diagrams, and single-line method steps split cleanly onto new lines."""
        theory_content = (
            "- **The Big Idea (How to Think About It)**: Geometric proof is building an airtight chain of dominoes backed by geometric reasons in brackets.\n"
            "- **DA Master Method (The Ninja Recipe)**: [Step 1: Mark & Name] Mark known angles, parallel arrows, and equal side ticks on the diagram. [Step 2: Link with Reasons] Write statements step-by-step, appending an approved geometric reason in brackets. [Step 3: Conclude Target] State the final required result with hence or therefore.\n"
            "- **The Examiner's Trap (Mark Protector)**: Omitting parallel line names in angle reasons (e.g. writing just 'alternate angles' instead of 'alternate angles, AB || CD') forfeits marks."
        )
        key_formulas = [
            "Alternate Angles: $\\angle ABC = \\angle BCD$ (alternate angles, $AB \\parallel CD$, forming a 'Z' shape)",
            "Corresponding Angles: $\\angle EAB = \\angle ACD$ (corresponding angles, $AB \\parallel CD$, forming an 'F' shape)",
            "Co-interior Angles: $\\angle BAC + \\angle ACD = 180^\\circ$ (co-interior angles, $AB \\parallel CD$, forming a 'C' shape)",
            "Angle Sum of a Triangle: $\\angle A + \\angle B + \\angle C = 180^\\circ$ (angle sum of $\\triangle ABC$)",
            "Exterior Angle of a Triangle: $\\angle ACD = \\angle A + \\angle B$ (exterior angle equals sum of opposite interior)"
        ]

        card_tex = pdf_generator.build_masterclass_theory_box_content(
            theory_content=theory_content,
            key_formulas=key_formulas,
            tutor_tips="Always state parallel lines in geometric angle reasons.",
            concept_name="Angle Relationships & Geometric Deduction",
            topic="Geometry",
            year_level="Year 8"
        )

        # 1. Verify Card 2 heading is simplified
        self.assertIn("ESSENTIAL FORMULAE", card_tex)
        self.assertNotIn("VARIABLE BLUEPRINT", card_tex)

        # 2. Verify mini TikZ diagrams are generated for each angle rule
        self.assertIn(r"\begin{tikzpicture}", card_tex)
        self.assertIn(r"\hfill\parbox[c]{0.26\linewidth}{\centering", card_tex)
        self.assertIn(r"\parbox[c]{0.70\linewidth}", card_tex)
        # Verify specific angle diagrams are present
        self.assertIn(r"arc (180:239:0.35)", card_tex)  # Alternate angles Z arc
        self.assertIn(r"arc (0:59:0.35)", card_tex)    # Corresponding angles F arc
        self.assertIn(r"arc (0:-121:0.35)", card_tex)  # Co-interior angles C arc
        self.assertIn(r"arc (0:118:0.28)", card_tex)   # Exterior angle arc

        # 3. Verify single-line method steps are split into 3 distinct items joined by \\[0.09cm]
        self.assertIn(r"\textbf{\color{dablue}[Step 1: Mark \& Name]} Mark known", card_tex)
        self.assertIn(r"\textbf{\color{dablue}[Step 2: Link with Reasons]} Write statements", card_tex)
        self.assertIn(r"\textbf{\color{dablue}[Step 3: Conclude Target]} State the final", card_tex)
        # Verify line break separator between steps
        self.assertIn(r"\\[0.09cm]", card_tex)

    def test_subpart_roman_numerals_and_answer_sheet_centering(self):
        """Verify that nested roman numerals are formatted on separate lines, answer sheet coordinates are centered, and teacher answer key filenames are produced."""
        # 1. Test nested roman numerals in worksheet source
        q_text = (
            "(a) Express each of the following large numbers in scientific notation (A \\times 10^k, where 1 \\le A < 10): "
            "(i) 620 000 (ii) 450 000 000\n"
            "(b) Express 5.12 \\times 10^5 as an ordinary whole number."
        )
        sample_q = [{
            "num": 5,
            "text": q_text,
            "marks": 3,
            "tier": "Core Foundation"
        }]
        tex_out = pdf_generator.build_latex_worksheet_source(
            title="In-Class Practice",
            year_level="Year 9 5.3",
            topic="Scientific Notation",
            questions=sample_q,
            sheet_type="In-Class",
            include_solutions=False
        )
        # Must have outer enumerate for (a), (b)
        self.assertIn(r"\begin{enumerate}[label=\textbf{(\alph*)}", tex_out)
        # Must have nested enumerate for (i), (ii)
        self.assertIn(r"\begin{enumerate}[label=\textbf{(\roman*)}", tex_out)
        self.assertIn("620 000", tex_out)
        self.assertIn("450 000 000", tex_out)
        self.assertIn(r"\qmark{3}", tex_out)

        # 2. Test format_latex_question_with_subparts formats roman subparts in hung enumerate list
        lines = pdf_generator.format_latex_question_with_subparts(q_text, as_item=False)
        formatted_str = "\n".join(lines)
        self.assertIn(r"label=\textbf{(\roman*)}", formatted_str)
        self.assertIn("620 000", formatted_str)
        self.assertIn("450 000 000", formatted_str)

        # 3. Test ANSWER_SHEET_COLS exact horizontal centering
        self.assertEqual(pdf_generator.ANSWER_SHEET_COLS[0]["qn_x"], 36.1)
        self.assertEqual(pdf_generator.ANSWER_SHEET_COLS[1]["qn_x"], 209.8)
        self.assertEqual(pdf_generator.ANSWER_SHEET_COLS[2]["qn_x"], 383.7)

        # 4. Test build_latex_answer_sheet_overlay_source centering
        overlay = pdf_generator.build_latex_answer_sheet_overlay_source(
            labels=["1", "2"],
            answers=["$x = 5$", "$y = 10$"],
            total_pages=1,
            is_teacher=True,
            term=2,
            week=4
        )
        # Check node positions use centered coordinates
        self.assertIn("at (36.1, 673.71)", overlay)  # 687.91 - 14.20 = 673.71
        self.assertIn("at (123.6, 670.91)", overlay) # 687.91 - 17.00 = 670.91
        self.assertIn("at (305, 735) {2}", overlay)
        self.assertIn("at (365, 735) {4}", overlay)

        # 5. Test get_worksheet_download_filename with teacher_answers mode
        ws_dict = {
            "title": "Functions",
            "topic": "Functions",
            "sheet_type": "in_class",
            "textbook": "Cambridge"
        }
        fn_tea = pdf_generator.get_worksheet_download_filename(ws_dict, sheet_type="in_class", mode="teacher_answers")
        self.assertEqual(fn_tea, "Functions In-Class Exercise Teacher Answer Key (Cambridge).pdf")

        fn_hw_tea = pdf_generator.get_worksheet_download_filename(
            {"topic": "Functions", "sheet_type": "homework", "set_number": 2, "textbook": "Cambridge"},
            sheet_type="homework",
            mode="teacher_answers"
        )
        self.assertEqual(fn_hw_tea, "Functions Homework Set 2 Teacher Answer Key (Cambridge).pdf")

    def test_theory_box_spacing_and_embedded_diagrams(self):
        """Verify that theory/note boxes sit closer to concept titles and diagrams are embedded inside the box."""
        booklet_data = {
            "topic": "10. Network Concepts and Applications",
            "year_level": "Year 10",
            "concepts": [{
                "concept_name": "Network terminology: vertices, edges, loops & degrees",
                "theory_content": "- **The Big Idea**: A network is a map of connections between vertices.\n- **DA Master Method**: [Step 1: Count] Count nodes. [Step 2: Degrees] Calculate degree.\n- **The Examiner's Trap**: Loops add 2 to degree.",
                "key_formulas": ["Degree of Vertex: $\\deg(v)$", "Handshaking Lemma: $\\sum \\deg(v) = 2E$"],
                "tutor_tips": "A loop adds 2 to degree.",
                "teacher_examples": [{"example_num": 1, "title": "Ex 1", "problem_text": "P1", "worked_solution": "S1"}],
                "practice_questions": [{"question_num": 1, "question_text": "Q1", "solution": "A1"}]
            }]
        }

        # 1. Theory Booklet checks
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")
        
        # Verify tighter spacing after concept title and before box
        self.assertIn(r"\\[0.05cm]", tex)
        self.assertIn(r"\vspace{-0.22cm}", tex)
        self.assertNotIn(r"\\[0.25cm]\n\nopagebreak\n\vspace{-0.1cm}", tex)

        # Verify theorybox has before skip=1pt and after skip=6pt
        self.assertIn("before skip=1pt", tex)
        self.assertIn("after skip=6pt", tex)

        # Verify diagram is INSIDE \begin{theorybox} ... \end{theorybox}
        th_box_start = tex.find(r"\begin{theorybox}")
        th_box_end = tex.find(r"\end{theorybox}")
        self.assertGreater(th_box_start, 0)
        self.assertGreater(th_box_end, th_box_start)
        
        box_slice = tex[th_box_start:th_box_end]
        self.assertIn(r"VISUAL MODEL \& KEY DIAGRAM", box_slice)
        self.assertIn(r"\begin{tikzpicture}", box_slice)
        self.assertIn("Handshaking Lemma", box_slice)

        # Verify NO duplicate diagram outside the theory box
        after_box_slice = tex[th_box_end:tex.find(r"\subsection*{Teacher Demonstration Examples}")]
        self.assertNotIn(r"\begin{tikzpicture}", after_box_slice)

        # 2. Review Booklet checks
        rev_tex = pdf_generator.build_latex_review_booklet_source(booklet_data, mode="teacher")
        self.assertIn(r"\\[0.05cm]", rev_tex)
        self.assertIn(r"\vspace{-0.22cm}", rev_tex)
        self.assertIn("before skip=1pt", rev_tex)
        self.assertIn("after skip=6pt", rev_tex)
        rev_box_start = rev_tex.find(r"\begin{reviewbox}")
        rev_box_end = rev_tex.find(r"\end{reviewbox}")
        self.assertIn(r"\begin{tikzpicture}", rev_tex[rev_box_start:rev_box_end])

    def test_network_and_pythagoras_fallback_tikz(self):
        """Verify get_concept_fallback_tikz returns rich diagrams for networks, trees, and Pythagoras."""
        # Network terminology
        net_tikz = pdf_generator.get_concept_fallback_tikz("Network terminology: vertices, edges, loops & degrees", "Network Concepts")
        self.assertIn("Loop (+2 deg)", net_tikz)
        self.assertIn("Multiple Edge", net_tikz)
        self.assertIn("Handshaking Lemma", net_tikz)

        # Minimum Spanning Tree
        mst_tikz = pdf_generator.get_concept_fallback_tikz("Minimum Spanning Trees", "Network Concepts")
        self.assertIn("Minimum Spanning Tree (MST)", mst_tikz)
        self.assertIn("No Cycles", mst_tikz)

        # Pythagoras & Trigonometry
        pyth_tikz = pdf_generator.get_concept_fallback_tikz("Right-Angled Triangles & Pythagoras", "Trigonometry")
        self.assertIn("SOH CAH TOA", pyth_tikz)
        self.assertIn(r"c^2 = a^2 + b^2", pyth_tikz)

    def test_australian_english_spelling(self):
        """Verify Australian English spelling normalization and case preservation."""
        text = "Factorize the quadratic, find the center of the circle, and measure 10 meters."
        au = pdf_generator.enforce_australian_english_text(text)
        self.assertEqual(au, "Factorise the quadratic, find the centre of the circle, and measure 10 metres.")

        # Test case preservation
        self.assertEqual(pdf_generator.enforce_australian_english_text("FACTORIZATION"), "FACTORISATION")
        self.assertEqual(pdf_generator.enforce_australian_english_text("Rationalizing"), "Rationalising")
        self.assertEqual(pdf_generator.enforce_australian_english_text("minimize"), "minimise")
        self.assertEqual(pdf_generator.enforce_australian_english_text("labeled"), "labelled")
        self.assertEqual(pdf_generator.enforce_australian_english_text("behavior"), "behaviour")
        self.assertEqual(pdf_generator.enforce_australian_english_text("colors"), "colours")

        # Test LaTeX commands remain intact
        latex_text = r"\begin{center} The circle is centered at (0,0) \end{center}"
        latex_au = pdf_generator.enforce_australian_english_text(latex_text)
        self.assertIn(r"\begin{center}", latex_au)
        self.assertIn(r"\end{center}", latex_au)
        self.assertIn("centred", latex_au)

        # Test dictionary recursion
        data = {
            "title": "Factorizing Review",
            "steps": ["Step 1: Rationalize the denominator", "Step 2: Center the graph"]
        }
        au_dict = pdf_generator.enforce_australian_english_dict(data)
        self.assertEqual(au_dict["title"], "Factorising Review")
        self.assertEqual(au_dict["steps"][0], "Step 1: Rationalise the denominator")
        self.assertEqual(au_dict["steps"][1], "Step 2: Centre the graph")

    def test_currency_math_delimiter_bug_fix(self):
        """Verify comma-separated numbers in math do not get corrupted into currency dollars, eliminating spaces."""
        text = "Each $x$-value ($1, 2, 3, 4$) appears exactly once and corresponds to a single $y$-value"
        sanitized = pdf_generator.sanitize_for_latex(text)
        # Must not turn into \$1, 2, 3, 4$ which leaves unmatched closing dollar
        self.assertNotIn(r"\$1, 2, 3, 4$", sanitized)
        self.assertIn("appears exactly once and corresponds to a single", sanitized)

        # Stray dollar list ($1, 2, 3, 4)
        text_stray = "Each $x$-value ($1, 2, 3, 4) appears exactly once"
        sanitized_stray = pdf_generator.sanitize_for_latex(text_stray)
        self.assertNotIn(r"\$1, 2, 3, 4", sanitized_stray)
        self.assertIn("(1, 2, 3, 4)", sanitized_stray)

        # Verify genuine currency still works
        curr_text = "The item costs $500, with an extra fee of $75."
        curr_sanitized = pdf_generator.sanitize_for_latex(curr_text)
        self.assertIn(r"\$500", curr_sanitized)
        self.assertIn(r"\$75", curr_sanitized)

        # Test runaway math prose unwrap
        runaway_math = "$appears exactly once and corresponds to a single$"
        runaway_sanitized = pdf_generator.sanitize_for_latex(runaway_math)
        self.assertEqual(runaway_sanitized, "appears exactly once and corresponds to a single")

    def test_sketch_solution_fallback_diagram(self):
        """Verify that when a question asks to sketch, a high-quality TikZ solution diagram is provided."""
        # 1. Sideways parabola
        sideways_tikz = pdf_generator.get_sketch_solution_fallback_tikz(
            "Consider $y^2 = 4x$. (a) Sketch the graph and explain why it is not a function.",
            "A sideways parabola opening to the right."
        )
        self.assertIn(r"y^2 = 4x", sideways_tikz)
        self.assertIn("Test line: $x = 1$", sideways_tikz)
        self.assertIn("Vertical Line Test", sideways_tikz)
        self.assertIn("Restricted branch", sideways_tikz)

        # 2. Circle
        circle_tikz = pdf_generator.get_sketch_solution_fallback_tikz(
            "Sketch the circle $x^2 + y^2 = 16$ and verify whether it is a function.",
            "Fails the vertical line test"
        )
        self.assertIn(r"x^2 + y^2 = 16", circle_tikz)
        self.assertIn("Vertical Line Test", circle_tikz)

        # 3. Integration into theory booklet builder when AI provides empty solution_diagram_tikz
        booklet_data = {
            "topic": "Functions and Relations",
            "year_level": "Year 11",
            "concepts": [{
                "concept_name": "Relations vs Functions",
                "theory_content": "- **The Big Idea**: A relation connects $x$ and $y$.\n- **DA Master Method**: [Step 1: Check]\n- **The Examiner's Trap**: Fails VLT.",
                "key_formulas": ["VLT: Vertical line intersects at most once"],
                "teacher_examples": [{
                    "example_num": 2,
                    "title": "Applying: Sideways Parabola",
                    "problem_text": "Consider $y^2 = 4x$. (a) Sketch the graph and explain why it is not a function.",
                    "worked_solution": "Fails the vertical line test at $x=1$ with points $(1, 2)$ and $(1, -2)$.",
                    "solution_diagram_tikz": ""  # AI left it empty!
                }]
            }]
        }
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")
        # Ensure the fallback diagram was injected into the Model Whiteboard Solution
        solbox_start = tex.find(r"\begin{solutionbox}")
        solbox_end = tex.find(r"\end{solutionbox}")
        self.assertIn(r"\begin{tikzpicture}", tex[solbox_start:solbox_end])
        self.assertIn(r"y^2 = 4x", tex[solbox_start:solbox_end])

    def test_network_diagram_synthesis_and_solid_theorybox(self):
        """Verify network diagram synthesis from worded edge weights and solid theorybox definition."""
        # 1. Test standalone synthesis function
        worded_q = "A network has vertices $A, B, C, D$. Edges and weights are: $AB = 7, AC = 3, CB = 2, CD = 8, BD = 4$. Find the shortest path from $A$ to $D$."
        synth_tikz = pdf_generator.synthesize_network_diagram_from_text(worded_q)
        self.assertIsNotNone(synth_tikz)
        self.assertIn(r"\begin{tikzpicture}", synth_tikz)
        self.assertIn("(A)", synth_tikz)
        self.assertIn("(B)", synth_tikz)
        self.assertIn("(C)", synth_tikz)
        self.assertIn(r"\draw[edge] (A) -- (B)", synth_tikz)
        self.assertIn("{7}", synth_tikz)
        self.assertIn(r"\draw[edge] (A) -- (C)", synth_tikz)
        self.assertIn("{3}", synth_tikz)

        # 2. Test Theory Booklet integration
        booklet_data = {
            "topic": "Networks and Graph Theory",
            "year_level": "Year 11",
            "concepts": [{
                "concept_name": "Planar Graphs and Euler's Formula",
                "theory_content": "### The Big Idea\nA planar graph is a network.\n### DA Master Method\n- [Step 1: Check]\n- [Step 2: Calculate]\n### The Examiner's Trap\nDon't forget exterior.",
                "key_formulas": ["Euler's Formula: $v - e + f = 2$"],
                "teacher_examples": [],
                "practice_questions": [{
                    "question_num": 3,
                    "question_text": worded_q,
                    "final_answer": "9",
                    "solution": "3+2+4=9"
                }]
            }]
        }
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")

        # Verify solid theorybox without vanishing attach boxed title
        self.assertIn(r"\usepackage{etoolbox}", tex)
        self.assertIn("colbacktitle=danavy", tex)
        self.assertIn("coltitle=white", tex)
        self.assertIn("pad at break=2mm", tex)
        self.assertNotIn(r"attach boxed title to top left={yshift=-2mm, xshift=4mm}", tex[tex.find(r"\newtcolorbox{theorybox}"):tex.find(r"\newtcolorbox{solutionbox}")])

        # Verify Card 3 spacing uses \par\vspace to avoid bounding box overlap
        self.assertIn(r"\par\vspace{0.08cm}", tex)

        # Verify diagram synthesis was automatically injected for Question 3
        q3_pos = tex.find("A network has vertices")
        self.assertGreater(q3_pos, 0)
        after_q3 = tex[q3_pos:]
        self.assertIn(r"\begin{tikzpicture}", after_q3)
        self.assertIn("{7}", after_q3)

    def test_question_variety_and_diagram_synthesis(self):
        """Verify that practice questions have authentic variety: diagram questions receive diagrams while non-diagram formula drills remain text-only."""
        # 1. Non-diagram formula question returns None (preserving question variety)
        formula_q = "A connected planar graph has 7 vertices and 10 edges. Use Euler's formula to find the number of faces."
        self.assertIsNone(pdf_generator.synthesize_question_diagram(formula_q, topic="Networks"))

        # 2. Planar graph question referencing a diagram synthesizes a clean 5-vertex planar graph
        planar_q = "For the planar graph shown below, determine the number of faces."
        planar_tikz = pdf_generator.synthesize_question_diagram(planar_q, topic="Networks", concept_name="Planar Graphs")
        self.assertIsNotNone(planar_tikz)
        self.assertIn(r"\begin{tikzpicture}", planar_tikz)
        self.assertIn("(A)", planar_tikz)
        self.assertIn("(E)", planar_tikz)

        # 3. Right-angled triangle question referencing a diagram synthesizes right triangle TikZ
        trig_q = "In the right-angled triangle shown below, the hypotenuse is 13 cm and the base is 12 cm. Find the value of $x$."
        trig_tikz = pdf_generator.synthesize_question_diagram(trig_q, topic="Trigonometry", concept_name="Right-Angled Triangles")
        self.assertIsNotNone(trig_tikz)
        self.assertIn(r"\begin{tikzpicture}", trig_tikz)
        self.assertIn("13", trig_tikz)
        self.assertIn("12", trig_tikz)

        # 4. Parallel lines & transversal question referencing a diagram synthesizes parallel lines TikZ
        parallel_q = "In the figure shown below, lines $AB$ and $CD$ are parallel. Determine the angle marked $x$."
        parallel_tikz = pdf_generator.synthesize_question_diagram(parallel_q, topic="Geometry", concept_name="Parallel Lines")
        self.assertIsNotNone(parallel_tikz)
        self.assertIn(r"\begin{tikzpicture}", parallel_tikz)
        self.assertIn("dawine", parallel_tikz)

        # 5. Full Theory Booklet compilation with mixed question variety:
        # Q1: formula drill (no diagram)
        # Q2: planar graph (diagram synthesized)
        # Q3: algebraic calculation (no diagram)
        # Q4: worded network with edge weights (custom network synthesized)
        booklet_data = {
            "topic": "Networks and Graph Theory",
            "year_level": "Year 11",
            "concepts": [{
                "concept_name": "Planar Graphs and Networks",
                "theory_content": "### The Big Idea\nEuler formula.\n### DA Master Method\n- [Step 1: Count]\n### The Examiner's Trap\nCount exterior face.",
                "key_formulas": ["$V - E + F = 2$"],
                "teacher_examples": [],
                "practice_questions": [
                    {
                        "q_num": 1,
                        "text": formula_q,
                        "final_answer": "5",
                        "worked_solution": "F = 2 - V + E = 2 - 7 + 10 = 5"
                    },
                    {
                        "q_num": 2,
                        "text": planar_q,
                        "final_answer": "5",
                        "worked_solution": "Count the bounded regions plus exterior: 5 faces."
                    },
                    {
                        "q_num": 3,
                        "text": "Solve for $x$: $3x - 5 = 10$.",
                        "final_answer": "x = 5",
                        "worked_solution": "3x = 15, x = 5"
                    },
                    {
                        "q_num": 4,
                        "text": "A network has vertices $A, B, C, D$. Edges and weights are: $AB = 6, AC = 4, BC = 2, BD = 5, CD = 3$. Find the shortest path from $A$ to $D$.",
                        "final_answer": "7",
                        "worked_solution": "A -> C -> D = 4 + 3 = 7"
                    }
                ]
            }]
        }
        tex = pdf_generator.build_latex_theory_booklet_source(booklet_data, mode="teacher")

        # Q1 should NOT have a tikzpicture immediately following it
        pos_q1 = tex.find("A connected planar graph has 7 vertices")
        pos_q2 = tex.find("For the planar graph shown below")
        pos_q3 = tex.find("Solve for $x$")
        pos_q4 = tex.find("A network has vertices $A, B, C, D$. Edges and weights are: $AB = 6")

        self.assertGreater(pos_q1, 0)
        self.assertGreater(pos_q2, pos_q1)
        self.assertGreater(pos_q3, pos_q2)
        self.assertGreater(pos_q4, pos_q3)

        chunk_q1 = tex[pos_q1:pos_q2]
        self.assertNotIn(r"\begin{tikzpicture}", chunk_q1, "Q1 is a formula drill and should NOT have a diagram")

        chunk_q2 = tex[pos_q2:pos_q3]
        self.assertIn(r"\begin{tikzpicture}", chunk_q2, "Q2 refers to a planar graph diagram and MUST have a diagram")

        chunk_q3 = tex[pos_q3:pos_q4]
        self.assertNotIn(r"\begin{tikzpicture}", chunk_q3, "Q3 is an algebraic drill and should NOT have a diagram")

        chunk_q4 = tex[pos_q4:]
        self.assertIn(r"\begin{tikzpicture}", chunk_q4, "Q4 describes weighted edges and MUST have a diagram")

    def test_safe_print_handles_io_errors(self):
        """Verify safe_print swallows broken pipe / OSError without raising."""
        from unittest.mock import patch
        with patch("builtins.print", side_effect=OSError(5, "Input/output error")):
            # Should not raise exception
            pdf_generator.safe_print("Testing broken pipe suppression")

    def test_strip_all_tikz_diagrams(self):
        """Verify strip_all_tikz_diagrams cleanly removes Card 2.5 and adjustbox TikZ without syntax errors."""
        sample_tex = r"""\begin{theorybox}[Core]
\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{%
\textbf{\color{danavy}\sffamily\footnotesize \ensuremath{\blacktriangleright}\ VISUAL MODEL \& KEY DIAGRAM}\\[0.05cm]
{\centering
\begin{adjustbox}{max width=0.88\linewidth, max totalheight=3.4cm, keepaspectratio, center}
\begin{tikzpicture}
\node {Test Visual};
\end{tikzpicture}
\end{adjustbox}
\par}
}}
\end{theorybox}
\item Question with diagram
\begin{center}
\begin{adjustbox}{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}
\begin{tikzpicture}
\node {Question TikZ};
\end{tikzpicture}
\end{adjustbox}
\end{center}"""
        clean_tex = pdf_generator.strip_all_tikz_diagrams(sample_tex)
        self.assertNotIn("VISUAL MODEL", clean_tex)
        self.assertNotIn("tikzpicture", clean_tex)
        self.assertNotIn("adjustbox", clean_tex)
        self.assertIn(r"\begin{theorybox}[Core]", clean_tex)
        self.assertIn("Question with diagram", clean_tex)

    def test_practice_question_variety_guarantee(self):
        """Verify that visual concepts guarantee a balanced mix of diagram and non-diagram practice questions."""
        pqs = [
            {"q_num": 1, "text": "State the condition for a planar graph."},
            {"q_num": 2, "text": "Calculate the number of faces using Euler's formula."},
            {"q_num": 3, "text": "Explain why a graph with v = 4, e = 8 cannot be planar."},
            {"q_num": 4, "text": "Determine the number of bounded faces in the graph."}
        ]
        varied = pdf_generator.ensure_concept_practice_question_variety(pqs, "Planar Graphs", "Networks")
        self.assertEqual(len(varied), 4)
        # Q1 and Q3 remain non-diagram
        self.assertFalse(bool(varied[0].get("diagram_tikz")))
        self.assertFalse(bool(varied[2].get("diagram_tikz")))
        # Q2 and Q4 receive diagrams
        self.assertTrue(bool(varied[1].get("diagram_tikz")))
        self.assertTrue(bool(varied[3].get("diagram_tikz")))
        self.assertIn("planar graph shown below", varied[1].get("text", "").lower())
        self.assertIn("planar graph shown below", varied[3].get("text", "").lower())


    def test_stem_and_leaf_table_sanitization(self):
        """Verify that stem-and-leaf tables and Key lines are cleanly preserved without double wrapping or broken delimiters."""
        raw_markdown = """
| Stem | Leaf |
| :--- | :--- |
| 1 | 2 5 8 |
| 2 | 1 4 4 7 |
| 3 | 0 2 6 |
| 4 | 1 5 |
"""
        clean_md = pdf_generator.sanitize_for_latex(raw_markdown)
        self.assertEqual(clean_md.count(r"\begin{center}"), 1)
        self.assertEqual(clean_md.count(r"\end{center}"), 1)
        self.assertIn(r"\begin{tabular}{r|l}", clean_md)
        self.assertIn(r"\textbf{Stem} & \textbf{Leaf} \\", clean_md)
        self.assertNotIn(r"\begin{centre}", clean_md)

        raw_latex = r"""\begin{center}
\begin{tabular}{r|l}
\textbf{Stem} & \textbf{Leaf} \\
\hline
1 & 2 \quad 5 \quad 8 \\
2 & 1 \quad 4 \quad 4 \quad 7 \\
3 & 0 \quad 2 \quad 6 \\
4 & 1 \quad 5
\end{tabular}\\[0.15cm]
\textbf{Key:} $3 \mid 1 = 31$
\end{center}"""
        clean_tex = pdf_generator.sanitize_for_latex(raw_latex)
        self.assertEqual(clean_tex.count(r"\begin{center}"), 1)
        self.assertEqual(clean_tex.count(r"\end{center}"), 1)
        self.assertIn(r"\textbf{Key:} $3 \mid 1 = 31$", clean_tex)
        self.assertIn(r"\begin{tabular}{r|l}", clean_tex)
        self.assertNotIn(r"\begin{centre}", clean_tex)


if __name__ == "__main__":
    unittest.main()
