import json
import unittest
from unittest.mock import MagicMock, patch
import ai_engine
import pdf_generator

class TestAiEngine(unittest.TestCase):
    def test_clean_json_response(self):
        markdown_json = "```json\n{\"title\": \"Math Worksheet\", \"total_marks\": 10}\n```"
        result = ai_engine.clean_json_response(markdown_json)
        self.assertEqual(result["title"], "Math Worksheet")
        self.assertEqual(result["total_marks"], 10)

    def test_clean_json_raw(self):
        raw_json = "{\"status\": \"ok\", \"count\": 5}"
        result = ai_engine.clean_json_response(raw_json)
        self.assertEqual(result["status"], "ok")

    def test_textbook_options_and_curricula_coverage(self):
        """Verify that all 6 active new-syllabus textbooks are registered and provide topics/subtopics, while Mathscape is deprecated from TEXTBOOK_OPTIONS."""
        expected_active_textbooks = [
            "CambridgeMATHS NSW",
            "Maths in Focus (Nelson Cengage)",
            "New Century Maths (Nelson Cengage)",
            "Jacaranda Maths Quest",
            "Australian Signpost Mathematics",
            "Oxford Maths NSW"
        ]
        for tb in expected_active_textbooks:
            self.assertIn(tb, ai_engine.TEXTBOOK_OPTIONS, f"{tb} must be in TEXTBOOK_OPTIONS")

        # Mathscape is deprecated from active options to prevent using legacy syllabus
        self.assertNotIn("Mathscape (Macmillan)", ai_engine.TEXTBOOK_OPTIONS)
        self.assertIn("Mathscape (Macmillan)", ai_engine.TEXTBOOK_CURRICULA)

        junior_years = ["Year 7", "Year 8", "Year 9", "Year 10"]
        senior_years = ["Year 11 (Advanced)", "Year 11 (Standard)", "Year 12 (Advanced)", "Year 12 (Extension 1)"]
        for tb in expected_active_textbooks:
            years_to_test = senior_years if tb == "Maths in Focus (Nelson Cengage)" else junior_years
            for yl in years_to_test:
                topics = ai_engine.get_topics_for_year(yl, textbook=tb)
                self.assertGreater(len(topics), 0, f"{tb} must have topics for {yl}")
                first_topic = topics[0]
                subs = ai_engine.get_curriculum_subtopics(yl, first_topic, textbook=tb)
                self.assertGreater(len(subs), 0, f"{tb} must have subtopics for {yl} - {first_topic}")

        # Verify Network Concepts is present in Year 10 for all junior textbooks
        for tb in ["CambridgeMATHS NSW", "New Century Maths (Nelson Cengage)", "Jacaranda Maths Quest", "Australian Signpost Mathematics", "Oxford Maths NSW"]:
            y10_topics = ai_engine.get_topics_for_year("Year 10", textbook=tb)
            has_network = any("network" in t.lower() for t in y10_topics)
            self.assertTrue(has_network, f"Year 10 for {tb} must include Network Concepts")

    def test_textbook_alias_matching(self):
        """Verify that aliases like 'Singpost', 'New Century', 'Maths Quest', 'Oxford', 'Mathscape' resolve correctly."""
        aliases = [
            ("Cambridge", "CambridgeMATHS NSW"),
            ("Maths in Focus", "Maths in Focus (Nelson Cengage)"),
            ("New Century", "New Century Maths (Nelson Cengage)"),
            ("Maths Quest", "Jacaranda Maths Quest"),
            ("Singpost", "Australian Signpost Mathematics"),
            ("Signpost", "Australian Signpost Mathematics"),
            ("Oxford", "Oxford Maths NSW"),
            ("Mathscape", "Mathscape (Macmillan)")
        ]
        for alias, target_name in aliases:
            curr = ai_engine.get_curriculum_dict(alias)
            target_curr = ai_engine.get_curriculum_dict(target_name)
            self.assertEqual(curr, target_curr, f"Alias '{alias}' should resolve to '{target_name}'")

    def test_theory_booklet_download_filename_format(self):
        """Verify downloaded files follow the user-specified naming template without underscores:
        e.g. Sequences & Series Theory Student (Cambridge).pdf
        """
        cases = [
            (
                {"topic": "Sequences & Series", "textbook": "CambridgeMATHS NSW"},
                "student",
                "Sequences & Series Theory Student with space (Cambridge).pdf"
            ),
            (
                {"topic": "Sequences & Series", "textbook": "CambridgeMATHS NSW"},
                "teacher",
                "Sequences & Series Theory Teacher (Cambridge).pdf"
            ),
            (
                {"topic": "6. Motion and Rates of Change", "textbook": "CambridgeMATHS NSW"},
                "teacher",
                "Motion and Rates of Change Theory Teacher (Cambridge).pdf"
            ),
            (
                {"topic": "1. Financial Mathematics", "textbook": "Maths in Focus (Nelson Cengage)"},
                "student",
                "Financial Mathematics Theory Student with space (Maths in Focus).pdf"
            ),
            (
                {"topic": "Algebra and Equations", "textbook": "New Century Maths (Nelson Cengage)"},
                "student",
                "Algebra and Equations Theory Student with space (New Century Maths).pdf"
            ),
            (
                {"topic": "Linear Relationships", "textbook": "Jacaranda Maths Quest"},
                "teacher",
                "Linear Relationships Theory Teacher (Maths Quest).pdf"
            ),
            (
                {"topic": "2D and 3D Space", "textbook": "Australian Signpost Mathematics"},
                "student",
                "2D and 3D Space Theory Student with space (Signpost).pdf"
            ),
            (
                {"topic": "Number and Calculations", "textbook": "Oxford Maths NSW"},
                "student",
                "Number and Calculations Theory Student with space (Oxford).pdf"
            ),
            (
                {"topic": "Whole Numbers and Operations", "textbook": "Mathscape (Macmillan)"},
                "teacher",
                "Whole Numbers and Operations Theory Teacher (Mathscape).pdf"
            ),
            (
                {"topic": "Sequences and Series", "textbook": "CambridgeMATHS NSW Stage 6"},
                "student_class",
                "Sequences and Series Theory Student no space (Cambridge).pdf"
            ),
            (
                {"topic": "Rates and Ratios", "textbook": "Maths in Focus (Nelson)"},
                "class",
                "Rates and Ratios Theory Student no space (Maths in Focus).pdf"
            )
        ]
        for booklet_data, mode, expected_filename in cases:
            fn = ai_engine.get_theory_booklet_download_filename(booklet_data, mode=mode)
            self.assertEqual(fn, expected_filename)
            self.assertNotIn("_", fn, f"Filename '{fn}' must not contain any underscores")

    def test_review_booklet_download_filename(self):
        """Verify that review booklet download filenames follow DA standards for teacher, student, and student_class."""
        cases = [
            (
                {"topic": "Sequences and Series", "textbook": "CambridgeMATHS Stage 6"},
                "teacher",
                "pdf",
                "Sequences and Series Review Teacher (Cambridge).pdf"
            ),
            (
                {"topic": "Sequences and Series", "textbook": "CambridgeMATHS Stage 6"},
                "student",
                "pdf",
                "Sequences and Series Review Student with space (Cambridge).pdf"
            ),
            (
                {"topic": "Sequences and Series", "textbook": "CambridgeMATHS Stage 6"},
                "student_class",
                "pdf",
                "Sequences and Series Review Student no space (Cambridge).pdf"
            ),
            (
                {"topic": "Trigonometry", "textbook": "Maths in Focus"},
                "class",
                "docx",
                "Trigonometry Review Student no space (Maths in Focus).docx"
            )
        ]
        for b_data, mode, ext, expected in cases:
            fn = ai_engine.get_review_booklet_download_filename(b_data, mode=mode, extension=ext)
            self.assertEqual(fn, expected)
            self.assertNotIn("_", fn, f"Filename '{fn}' must not contain any underscores")


    def test_curriculum_worksheet_nested_difficulty_prompt_logic(self):
        """Verify that generate_curriculum_worksheet supports Dict[str, Dict[str, int]] and builds correct allocations."""
        import inspect
        src = inspect.getsource(ai_engine.generate_curriculum_worksheet)
        
        # Test 1: Nested difficulty breakdown
        subtopics_detailed = {
            "1A Expanding brackets": {"Easy": 1, "Medium": 2, "Hard": 1, "Extremely Hard": 0},
            "1B Factoring": {"Easy": 0, "Medium": 1, "Hard": 2, "Extremely Hard": 1}
        }
        
        is_detailed = any(isinstance(v, dict) for v in subtopics_detailed.values())
        self.assertTrue(is_detailed)
        
        total_items = sum(
            sum(c.values()) if isinstance(c, dict) else int(c)
            for c in subtopics_detailed.values()
        )
        self.assertEqual(total_items, 8)
        
        # Test 2: Verify backward compatibility with flat dict
        subtopics_flat = {
            "1A Expanding brackets": 3,
            "1B Factoring": 2
        }
        is_detailed_flat = any(isinstance(v, dict) for v in subtopics_flat.values())
        self.assertFalse(is_detailed_flat)
        self.assertEqual(sum(subtopics_flat.values()), 5)

    def test_curriculum_worksheet_prompt_contains_difficulty_criteria(self):
        """Verify prompt template contains all 4 difficulty definitions and handles nested allocations."""
        import inspect
        src = inspect.getsource(ai_engine.generate_curriculum_worksheet)
        self.assertIn("DIFFICULTY LEVEL CRITERIA (MANDATORY):", src)
        self.assertIn("Easy (Commit to Memory): Foundational definitions", src)
        self.assertIn("Medium (Further Practice): Standard textbook exercises", src)
        self.assertIn("Hard (Application): Multi-step non-routine problem solving", src)
        self.assertIn("Extremely Hard (Thinking Creatively): Extension/Challenging exam question", src)
        self.assertIn("Past Exam (Exam Questions): Authentic NSW Stage 6", src)
        self.assertIn('"difficulty": "Easy"', src)

    def test_clean_topic_title(self):
        """Verify leading numbers are removed, 'and' is normalized to '&', and 2D/3D preserved."""
        cases = [
            ("1. Sequences and Series", "Sequences & Series"),
            ("14. Probability", "Probability"),
            ("6: Motion and Rates of Change", "Motion & Rates of Change"),
            ("2D and 3D Space", "2D & 3D Space"),
            ("Year 12 Mathematics - Sequences and Series", "Sequences & Series"),
            ("Sequences and Series — Homework", "Sequences & Series"),
            ("1. Sequences and Series — Homework", "Sequences & Series"),
            ("Chapter 3 - Polynomials", "Polynomials")
        ]
        for raw_topic, expected in cases:
            cleaned = ai_engine.clean_topic_title(raw_topic)
            self.assertEqual(cleaned, expected)

    def test_get_textbooks_for_year_filtering(self):
        """Verify Year 11 Standard excludes Australian Signpost, while Year 8 includes it."""
        y11_tbs = ai_engine.get_textbooks_for_year("Year 11 (Standard)")
        self.assertIn("CambridgeMATHS NSW", y11_tbs)
        self.assertIn("Maths in Focus (Nelson Cengage)", y11_tbs)
        self.assertNotIn("Australian Signpost Mathematics", y11_tbs)
        self.assertNotIn("Jacaranda Maths Quest", y11_tbs)
        self.assertNotIn("Oxford Maths NSW", y11_tbs)
        self.assertNotIn("Mathscape (Macmillan)", y11_tbs)

        y8_tbs = ai_engine.get_textbooks_for_year("Year 8")
        self.assertIn("Australian Signpost Mathematics", y8_tbs)
        self.assertIn("CambridgeMATHS NSW", y8_tbs)
        self.assertNotIn("Maths in Focus (Nelson Cengage)", y8_tbs)
        self.assertNotIn("Mathscape (Macmillan)", y8_tbs)
        self.assertEqual(len(y8_tbs), 5)

    def test_get_worksheet_download_filename(self):
        """Verify exact filename formatting without underscores."""
        fn_hw1 = ai_engine.get_worksheet_download_filename(
            topic="1. Sequences and Series",
            sheet_type="Homework",
            set_number=1
        )
        self.assertEqual(fn_hw1, "Sequences & Series HW Set 1.pdf")
        self.assertNotIn("_", fn_hw1)

        fn_hw2 = ai_engine.get_worksheet_download_filename(
            topic="1. Sequences and Series",
            sheet_type="Homework",
            set_number=2
        )
        self.assertEqual(fn_hw2, "Sequences & Series HW Set 2.pdf")

        fn_ans = ai_engine.get_worksheet_download_filename(
            topic="1. Sequences and Series",
            sheet_type="Homework",
            set_number=1,
            prefix="DA Answer Sheet"
        )
        self.assertEqual(fn_ans, "DA Answer Sheet Sequences & Series HW Set 1.pdf")

        fn_key = ai_engine.get_worksheet_download_filename(
            topic="1. Sequences and Series",
            sheet_type="Homework",
            set_number=1,
            prefix="Marking Key",
            extension="json"
        )
        self.assertEqual(fn_key, "Marking Key Sequences & Series HW Set 1.json")

        fn_inclass = ai_engine.get_worksheet_download_filename(
            topic="1. Sequences and Series",
            sheet_type="In-Class"
        )
        self.assertEqual(fn_inclass, "Sequences & Series In Class Worksheet.pdf")

    def test_get_api_key_isolation(self):
        """Verify API key resolution isolates explicit keys from environment keys."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"GEMINI_API_KEY": "master_env_secret"}):
            # Explicit non-empty key returns explicit key
            self.assertEqual(ai_engine.get_api_key("custom_tutor_key"), "custom_tutor_key")
            # Explicit empty key returns empty string (does NOT fall back to master env key)
            self.assertEqual(ai_engine.get_api_key(""), "")
            self.assertEqual(ai_engine.get_api_key("   "), "")
            # None falls back to env key (e.g. for CLI/scripts or admin default)
            self.assertEqual(ai_engine.get_api_key(None), "master_env_secret")

    def test_get_client_missing_key_raises(self):
        """Verify get_client raises clear ValueError when empty key is provided."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"GEMINI_API_KEY": "master_env_secret"}):
            with self.assertRaises(ValueError) as ctx:
                ai_engine.get_client("")
            self.assertIn("Google Gemini API Key is missing", str(ctx.exception))

    def test_theory_and_review_prompts_enforce_concise_tuition_notes(self):
        """Verify prompt templates mandate comprehensive self-learning, intuitive anti-textbook notes."""
        import inspect
        theory_src = inspect.getsource(ai_engine.generate_theory_booklet)
        self.assertIn("IN-CLASS CENTRE TEACHING (CONCISE, DIRECT & TO THE POINT)", theory_src)
        self.assertIn("CONCISE & TO THE POINT", theory_src)

        review_src = inspect.getsource(ai_engine.generate_review_booklet)
        self.assertIn("THOROUGH & ACCESSIBLE SELF-LEARNING REVISION NOTES", review_src)
        self.assertIn("COMPREHENSIVE SELF-LEARNING REVISION SUMMARY", review_src)
        self.assertIn("up to 50 questions", review_src)

    def test_format_combined_topics(self):
        """Test formatting single, pair, and multiple topics."""
        # Single string
        self.assertEqual(ai_engine.format_combined_topics("1. Algebraic Techniques"), "Algebraic Techniques")
        # List with 1 item
        self.assertEqual(ai_engine.format_combined_topics(["1. Algebraic Techniques"]), "Algebraic Techniques")
        # List with 2 items
        self.assertEqual(
            ai_engine.format_combined_topics(["1. Algebraic Techniques", "2. Equations and Inequalities"]),
            "Algebraic Techniques & Equations & Inequalities"
        )
        # List with 3 items
        self.assertEqual(
            ai_engine.format_combined_topics(["1. Algebra", "2. Geometry", "3. Trigonometry"]),
            "Algebra, Geometry & Trigonometry"
        )
        # Empty list
        self.assertEqual(ai_engine.format_combined_topics([]), "Mathematics")

    def test_generate_topic_review_booklet_alias_exists(self):
        """Verify the module alias generate_topic_review_booklet is exported in ai_engine."""
        self.assertTrue(hasattr(ai_engine, "generate_topic_review_booklet"))
        self.assertIs(ai_engine.generate_topic_review_booklet, ai_engine.generate_review_booklet)

    @patch("ai_engine.get_client")
    def test_generate_theory_booklet_with_multi_topics(self, mock_get_client):
        """Verify generate_theory_booklet accepts multiple topics as list and builds multi-topic prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"concepts": [{"name": "Linear Equations", "theory_content": "- **Core Concept**: Balance both sides.", "key_formulas": ["ax + b = 0"], "tutor_tips": "Check answers.", "teacher_examples": [], "practice_questions": []}]}'
        mock_response.usage_metadata.prompt_token_count = 500
        mock_response.usage_metadata.candidates_token_count = 200
        mock_response.usage_metadata.total_token_count = 700
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        topics = ["1. Algebraic Techniques", "2. Equations"]
        res = ai_engine.generate_theory_booklet(
            year_level="Year 9",
            topic=topics,
            subtopics=["[Algebraic Techniques] Expanding", "[Equations] Linear"],
            examples_per_concept=2,
            practice_per_concept=3,
            term=1,
            week=2,
            custom_instructions="Focus on HSC fundamentals",
            api_key="fake-key"
        )

        self.assertIn("Algebraic Techniques & Equations", res["title"])
        self.assertEqual(res["topic"], "Algebraic Techniques & Equations")
        self.assertEqual(res["year_level"], "Year 9")
        self.assertEqual(res["term"], 1)
        self.assertEqual(res["week"], 2)

        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][0]
        self.assertIn("Multi-Topic Booklet Coverage", prompt_sent)
        self.assertIn("Algebraic Techniques & Equations", prompt_sent)

    @patch("ai_engine.get_client")
    def test_generate_review_booklet_with_multi_topics_and_kwargs(self, mock_get_client):
        """Verify generate_review_booklet handles multi-topics and kwargs (selected_subtopics, questions_per_concept)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"concepts": [{"concept_name": "Integration", "revision_summary": "- **Core Definition**: Antiderivative.", "key_formulas": ["\\\\int x^n dx"], "tips_and_tricks": "Add + C", "common_pitfalls": ["Forgetting + C"], "mastery_examples": [], "review_questions": []}]}'
        mock_response.usage_metadata.prompt_token_count = 600
        mock_response.usage_metadata.candidates_token_count = 250
        mock_response.usage_metadata.total_token_count = 850
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        topics = ["Calculus", "Integration"]
        # Call via the aliased function with kwargs
        res = ai_engine.generate_topic_review_booklet(
            year_level="Year 12 (Advanced)",
            topic=topics,
            selected_subtopics=["[Calculus] Derivatives", "[Integration] Indefinite Integrals"],
            examples_per_concept=2,
            questions_per_concept=5,
            term=2,
            week=4,
            custom_instructions="Strict exam tips",
            api_key="fake-key"
        )

        self.assertIn("Calculus & Integration", res["title"])
        self.assertEqual(res["topic"], "Calculus & Integration")
        self.assertEqual(res["year_level"], "Year 12 (Advanced)")
        self.assertEqual(res["term"], 2)
        self.assertEqual(res["week"], 4)

        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][0]
        self.assertIn("Multi-Topic Booklet Coverage", prompt_sent)
        self.assertIn("Calculus & Integration", prompt_sent)

    def test_multi_topic_latex_pdf_generation_all_modes(self):
        """Verify multi-topic title with '&' builds valid LaTeX and compiles without syntax error."""
        multi_topic_booklet = {
            "title": "Year 10 - Algebraic Techniques & Linear Equations Theory Booklet",
            "year_level": "Year 10",
            "topic": "Algebraic Techniques & Linear Equations",
            "term": 1,
            "week": 3,
            "textbook": "CambridgeMATHS NSW",
            "concepts": [
                {
                    "name": "Expanding Brackets & Factorising",
                    "theory_content": "- **Core Concept**: Distributive law $a(b+c) = ab+ac$.\\n- **The Golden Rule**: Multiply outside term by each term inside.",
                    "key_formulas": ["$a(b+c) = ab + ac$"],
                    "tutor_tips": "Watch negative signs carefully.",
                    "teacher_examples": [
                        {
                            "example_num": 1,
                            "title": "Expanding Binomials",
                            "problem_text": "Expand and simplify: $(2x + 3)(x - 4)$",
                            "solution_text": "Step 1: FOIL method\\n$= 2x^2 - 8x + 3x - 12$\\n$= 2x^2 - 5x - 12$"
                        }
                    ],
                    "practice_questions": [
                        {
                            "question_num": 1,
                            "difficulty": "Easy",
                            "marks": 1,
                            "problem_text": "Expand $3(x - 5)$.",
                            "solution_text": "$= 3x - 15$",
                            "final_answer": "$3x - 15$"
                        }
                    ]
                }
            ]
        }

        # Test building LaTeX source for all 3 modes
        for mode in ["teacher", "student", "student_class"]:
            src = pdf_generator.build_latex_theory_booklet_source(multi_topic_booklet, mode=mode, term=1, week=3)
            self.assertIn("Algebraic Techniques \\& Linear Equations", src)
            if mode == "student_class":
                self.assertIn("THEORY STUDENT CLASS", src)

        # Test generating PDF bytes
        for mode in ["teacher", "student", "student_class"]:
            pdf_bytes = pdf_generator.generate_theory_booklet_pdf(multi_topic_booklet, mode=mode, term=1, week=3)
            self.assertIsNotNone(pdf_bytes)
            self.assertTrue(len(pdf_bytes) > 1000)

    def test_normalize_difficulty_all_tiers(self):
        """Verify normalize_difficulty maps various input strings to the 5 canonical pedagogical tiers."""
        self.assertEqual(ai_engine.normalize_difficulty("easy"), "Section 1 - Commit to Memory")
        self.assertEqual(ai_engine.normalize_difficulty("drilling"), "Section 1 - Commit to Memory")
        self.assertEqual(ai_engine.normalize_difficulty("commit to memory"), "Section 1 - Commit to Memory")
        self.assertEqual(ai_engine.normalize_difficulty("Level 1"), "Section 1 - Commit to Memory")

        self.assertEqual(ai_engine.normalize_difficulty("medium"), "Section 2 - Further Practice")
        self.assertEqual(ai_engine.normalize_difficulty("deeper understanding"), "Section 2 - Further Practice")
        self.assertEqual(ai_engine.normalize_difficulty("further practice"), "Section 2 - Further Practice")
        self.assertEqual(ai_engine.normalize_difficulty("Level 2"), "Section 2 - Further Practice")

        self.assertEqual(ai_engine.normalize_difficulty("hard"), "Section 3 - Application")
        self.assertEqual(ai_engine.normalize_difficulty("application"), "Section 3 - Application")
        self.assertEqual(ai_engine.normalize_difficulty("Level 3"), "Section 3 - Application")

        self.assertEqual(ai_engine.normalize_difficulty("challenging"), "Section 4 - Thinking Creatively")
        self.assertEqual(ai_engine.normalize_difficulty("extremely hard"), "Section 4 - Thinking Creatively")
        self.assertEqual(ai_engine.normalize_difficulty("thinking creatively"), "Section 4 - Thinking Creatively")
        self.assertEqual(ai_engine.normalize_difficulty("Level 4"), "Section 4 - Thinking Creatively")

        self.assertEqual(ai_engine.normalize_difficulty("exam"), "Section 5 - Exam Questions")
        self.assertEqual(ai_engine.normalize_difficulty("past exam"), "Section 5 - Exam Questions")
        self.assertEqual(ai_engine.normalize_difficulty("exam questions"), "Section 5 - Exam Questions")
        self.assertEqual(ai_engine.normalize_difficulty("Level 5"), "Section 5 - Exam Questions")

    @patch("ai_engine.get_client")
    def test_question_distribution_in_theory_and_review_prompts(self, mock_get_client):
        """Verify question_distribution and level_distribution are injected into prompts."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"concepts": []}'
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        custom_dist = {
            "Simultaneous Equations": {
                "Level 1 - Drilling": 3,
                "Level 2 - Deeper Understanding": 2,
                "Level 3 - Application": 2,
                "Level 4 - Challenging": 1,
                "Exam Style": 1
            }
        }

        # Theory booklet with custom distribution
        ai_engine.generate_theory_booklet(
            year_level="Year 9",
            topic="Linear Equations",
            subtopics=["Simultaneous Equations"],
            api_key="test_key",
            question_distribution=custom_dist
        )
        called_prompt_theory = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("Exact Question Tier Breakdown Per Subtopic", called_prompt_theory)
        self.assertIn("Level 1 - Drilling: 3 questions", called_prompt_theory)
        self.assertIn("Level 4 - Challenging: 1 question", called_prompt_theory)

        # Verify new pedagogical labels
        new_level_dist = {
            "Level 1 - Commit to Memory": 2,
            "Level 2 - Further Practice": 2,
            "Level 3 - Application": 1,
            "Level 4 - Thinking Creatively": 1,
            "Level 5 - Exam Questions": 1
        }
        ai_engine.generate_theory_booklet(
            year_level="Year 11 Advanced",
            topic="Functions & Graphs",
            subtopics=["Vertical Line Test"],
            api_key="test_key",
            level_distribution=new_level_dist
        )
        called_prompt_new = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("Level 1 - Commit to Memory: 2 questions", called_prompt_new)
        self.assertIn("Level 2 - Further Practice: 2 questions", called_prompt_new)
        self.assertIn("Level 4 - Thinking Creatively: 1 question", called_prompt_new)
        self.assertIn("Level 5 - Exam Questions: 1 question", called_prompt_new)

    @patch("ai_engine.get_client")
    def test_generate_remedial_worksheet_types(self, mock_get_client):
        """Verify generate_remedial_worksheet supports both 'Remedial' and 'Targeted NESA' worksheet types."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"questions": [{"item_label": "1", "text": "Solve 2x+1=5", "marks": 1, "subtopic": "Linear Equations", "solution_steps": "2x=4 => x=2", "correct_answer": "2"}], "marking_key": {"1": "2"}}'
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 1. Remedial Practice Worksheet
        remedial_res = ai_engine.generate_remedial_worksheet(
            student_name="Justin Lin",
            year_level="Year 10",
            weak_topics=["Linear Equations", "Quadratics"],
            num_questions=5,
            worksheet_type="Remedial",
            api_key="fake-key"
        )
        self.assertEqual(remedial_res["title"], "DA Tuition - Justin Lin Remedial Practice Worksheet")
        self.assertEqual(remedial_res["worksheet_type"], "Remedial")
        called_prompt_remedial = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("DA Tuition - Justin Lin Remedial Practice Worksheet", called_prompt_remedial)
        self.assertIn("Remedial Practice Worksheet", called_prompt_remedial)

        # 2. Targeted NESA Practice Worksheet
        nesa_res = ai_engine.generate_remedial_worksheet(
            student_name="Justin Lin",
            year_level="Year 10",
            weak_topics=["Linear Equations", "Quadratics"],
            num_questions=5,
            worksheet_type="Targeted NESA",
            api_key="fake-key"
        )
        self.assertEqual(nesa_res["title"], "DA Tuition - Justin Lin Targeted NESA Practice Worksheet")
        self.assertEqual(nesa_res["worksheet_type"], "Targeted NESA")
        called_prompt_nesa = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("DA Tuition - Justin Lin Targeted NESA Practice Worksheet", called_prompt_nesa)
        self.assertIn("Targeted NESA Practice Worksheet", called_prompt_nesa)

    def test_is_year_11_advanced(self):
        """Verify accurate identification of NSW Year 11 Mathematics Advanced."""
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 (Advanced)"))
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 Advanced"))
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 (Adv)"))
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 Adv"))
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 Maths"))
        self.assertTrue(ai_engine.is_year_11_advanced("Year 11 Mathematics"))

        # Negative checks: Extension, Standard, Year 12, Junior
        self.assertFalse(ai_engine.is_year_11_advanced("Year 11 (Extension)"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 11 (Extension 1)"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 11 Ext 1"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 11 (Standard)"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 11 Standard"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 12 (Advanced)"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 12 (Extension 1)"))
        self.assertFalse(ai_engine.is_year_11_advanced("Year 10"))

    def test_cambridge_curriculum_year_11_advanced_boundaries(self):
        """Verify Cambridge Year 11 Advanced strictly excludes Year 12 and Extension 1 subtopics."""
        c_y11 = ai_engine.CAMBRIDGE_CURRICULUM["Year 11 (Advanced)"]
        all_y11_subs = [sub.lower() for subs in c_y11.values() for sub in subs]

        # Must NOT contain Year 12 calculus rules (product/quotient/chain)
        self.assertFalse(any("product rule" in s for s in all_y11_subs))
        self.assertFalse(any("quotient rule" in s for s in all_y11_subs))
        self.assertFalse(any("chain rule" in s for s in all_y11_subs))

        # Must NOT contain Extension 1 polynomials (division, remainder/factor theorem, roots)
        self.assertFalse(any("polynomial division" in s for s in all_y11_subs))
        self.assertFalse(any("remainder and factor" in s for s in all_y11_subs))
        self.assertFalse(any("sum and product of roots" in s for s in all_y11_subs))

        # Must NOT contain Year 12 calculus chapters
        self.assertNotIn("10. The Rules of Differentiation", c_y11)
        self.assertNotIn("11. Exponential, Logarithmic and Trigonometric Calculus", c_y11)

        # Must have Introduction to Differentiation and Probability & Data
        self.assertIn("9. Introduction to Differentiation", c_y11)
        self.assertIn("10. Probability and Data Analysis", c_y11)

    def test_maths_in_focus_curriculum_year_11_advanced_boundaries(self):
        """Verify Maths in Focus Year 11 Advanced excludes Extension 1 compound & double angles."""
        m_y11 = ai_engine.MATHS_IN_FOCUS_CURRICULUM["Year 11 (Advanced)"]
        all_y11_subs = [sub.lower() for subs in m_y11.values() for sub in subs]

        # Must NOT contain Extension 1 compound/double angles
        self.assertFalse(any("compound angle" in s for s in all_y11_subs))
        self.assertFalse(any("double angle" in s for s in all_y11_subs))

        # Must have reciprocal trig ratios and trig equations in radians/degrees
        self.assertTrue(any("reciprocal" in s for s in all_y11_subs))
        self.assertTrue(any("solving trigonometric equations" in s for s in all_y11_subs))

    def test_stage6_syllabus_boundary_prompt(self):
        """Verify boundary prompt returns strict negative directives for Year 11 Advanced."""
        prompt = ai_engine.get_stage6_syllabus_boundary_prompt("Year 11 (Advanced)")
        self.assertIn("STRICT NSW NESA SYLLABUS BOUNDARY", prompt)
        self.assertIn("ZERO TOLERANCE LEAKAGE POLICY", prompt)
        self.assertIn("NO Integration", prompt)
        self.assertIn("NO Product Rule, Quotient Rule, or Chain Rule", prompt)
        self.assertIn("NO Arithmetic Sequences/Series", prompt)
        self.assertIn("NO Financial Mathematics", prompt)
        self.assertIn("NO Normal Distribution", prompt)
        self.assertIn("NO Mathematical Induction", prompt)
        self.assertIn("NO Vectors", prompt)
        self.assertIn("NO Networks", prompt)

        # Test Stage 5 (Year 10) directives
        prompt_y10 = ai_engine.get_stage6_syllabus_boundary_prompt("Year 10")
        self.assertIn("STAGE 5", prompt_y10)
        self.assertIn("STRICTLY NO CALCULUS", prompt_y10)
        self.assertIn("STRICTLY NO SIGMA / SUMMATION NOTATION", prompt_y10)
        self.assertIn("STRICTLY NO RADIANS", prompt_y10)

        # Test Stage 4 (Year 8) directives
        prompt_y8 = ai_engine.get_stage6_syllabus_boundary_prompt("Year 8")
        self.assertIn("STAGE 4", prompt_y8)
        self.assertIn("STRICTLY NO QUADRATICS", prompt_y8)
        self.assertIn("STRICTLY NO PYTHAGORAS", prompt_y8)
        self.assertIn("STRICTLY NO TRIGONOMETRY", prompt_y8)

        # Test Stage 6 Standard directives
        prompt_std = ai_engine.get_stage6_syllabus_boundary_prompt("Year 11 Standard")
        self.assertIn("STAGE 6 MATHEMATICS STANDARD", prompt_std)
        self.assertIn("STRICTLY NO CALCULUS", prompt_std)

    def test_audit_and_sanitize_year11_advanced_data(self):
        """Verify the post-generation auditor detects and flags forbidden out-of-syllabus terms across stages."""
        # Clean Year 11 data
        clean_data = {
            "title": "Year 11 Functions and Graphs",
            "year_level": "Year 11 (Advanced)",
            "questions": [
                {"text": "Find the vertex and axis of symmetry of $y = x^2 - 4x + 3$."}
            ]
        }
        audited_clean = ai_engine.audit_and_sanitize_year11_advanced_data(clean_data, "Year 11 (Advanced)")
        self.assertEqual(audited_clean["_syllabus_audit"]["status"], "passed")

        # Contaminated data with Year 12 integral and Extension 1 vectors
        contaminated_data = {
            "title": "Year 11 Practice",
            "year_level": "Year 11 (Advanced)",
            "questions": [
                {"text": "Evaluate $\\int_0^2 (3x^2 + 1) dx$ using the fundamental theorem of calculus."},
                {"text": "Given vector $\\mathbf{i} + 2\\mathbf{j}$, find the dot product."}
            ]
        }
        audited_contaminated = ai_engine.audit_and_sanitize_year11_advanced_data(contaminated_data, "Year 11 (Advanced)")
        self.assertEqual(audited_contaminated["_syllabus_audit"]["status"], "warning")
        violations = audited_contaminated["_syllabus_audit"]["violations_flagged"]
        self.assertTrue(any("Integral Calculus" in v for v in violations))
        self.assertTrue(any("Vectors" in v for v in violations))

        # Year 10 contaminated with calculus and sigma
        y10_contaminated = {
            "title": "Year 10 Networks",
            "year_level": "Year 10",
            "questions": [
                {"text": "Find the derivative $\\frac{dy}{dx}$."},
                {"text": "Calculate $\\sum x$."}
            ]
        }
        audited_y10 = ai_engine.audit_and_sanitize_year11_advanced_data(y10_contaminated, "Year 10")
        self.assertEqual(audited_y10["_syllabus_audit"]["status"], "warning")
        y10_violations = audited_y10["_syllabus_audit"]["violations_flagged"]
        self.assertTrue(any("Calculus" in v for v in y10_violations))
        self.assertTrue(any("Sigma Notation" in v for v in y10_violations))

    @patch("ai_engine.get_client")
    def test_exam_package_injects_year11_boundary_prompt(self, mock_get_client):
        """Verify generate_exam_package injects the Year 11 Advanced boundary prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"title": "Exam Pkg", "concepts": []}'
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        ai_engine.generate_exam_package(
            year_level="Year 11 (Advanced)",
            topic="Functions and Graphs",
            api_key="test-key"
        )
        called_prompt = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("STRICT NSW NESA SYLLABUS BOUNDARY & SCOPE DIRECTIVE FOR YEAR 11 MATHEMATICS ADVANCED", called_prompt)
        self.assertIn("ZERO TOLERANCE LEAKAGE POLICY", prompt := called_prompt)
        self.assertIn("NO Product Rule, Quotient Rule, or Chain Rule", prompt)

    @patch("ai_engine.get_client")
    def test_generate_topic_mastery_exam_and_concept_grading(self, mock_get_client):
        """Verify generate_topic_mastery_exam builds concept prompt and grade_student_submission populates concept tags."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "Year 10 5.3 Consumer Arithmetic - End-of-Topic Mastery Exam",
            "topic": "Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "sheet_type": "Topic Mastery Exam",
            "questions": [
                {
                    "item_label": "1", "marks": 1, "concept_name": "Concept 1: Simple Interest",
                    "cognitive_level": "Level 1 - Commit to Memory", "text": "What is I?", "correct_answer": "Prn"
                },
                {
                    "item_label": "2", "marks": 3, "concept_name": "Concept 2: Compound Interest",
                    "cognitive_level": "Level 2 - Exam Application", "text": "Calculate A.", "correct_answer": "1000"
                }
            ],
            "marking_key": {"1": "Prn", "2": "1000"}
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        sample_tb = {
            "id": 42,
            "title": "Year 10 Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "topic": "Consumer Arithmetic",
            "concepts": [
                {"name": "Concept 1: Simple Interest", "key_formulas": ["I = Prn"], "tutor_tips": "Flat rate only."},
                {"name": "Concept 2: Compound Interest", "key_formulas": ["A = P(1+r)^n"], "tutor_tips": "Watch compounding frequency."}
            ]
        }

        exam = ai_engine.generate_topic_mastery_exam(sample_tb, api_key="fake-key")
        self.assertEqual(exam["sheet_type"], "Topic Mastery Exam")
        self.assertEqual(exam["source_theory_id"], 42)
        self.assertEqual(len(exam["questions"]), 2)

        # Verify prompt instructed 100% concept coverage
        call_prompt = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("100% CONCEPT COVERAGE", call_prompt)
        self.assertIn("Concept 1: Simple Interest", call_prompt)
        self.assertIn("Concept 2: Compound Interest", call_prompt)

        # Verify grading with questions_metadata
        grade_response = MagicMock()
        grade_response.text = json.dumps({
            "extracted_name": "Alex Tan",
            "score": 1.0,
            "total_marks": 4.0,
            "accuracy_pct": 25.0,
            "mistakes": [
                {
                    "question_num": "2",
                    "marks_lost": 3.0,
                    "student_answer": "500",
                    "correct_answer": "1000",
                    "error_type": "Calculation"
                }
            ]
        })
        mock_client.models.generate_content.return_value = grade_response

        grading_result = ai_engine.grade_student_submission(
            student_pdf_bytes=b"%PDF-1.4...",
            marking_key={"1": "Prn", "2": "1000"},
            total_marks=4.0,
            questions_metadata=exam["questions"],
            api_key="fake-key"
        )
        self.assertEqual(len(grading_result["mistakes"]), 1)
        mistake = grading_result["mistakes"][0]
        # Should be auto-populated with concept_name and cognitive_level from metadata
        self.assertEqual(mistake["concept_name"], "Concept 2: Compound Interest")
        self.assertEqual(mistake["cognitive_level"], "Level 2 - Exam Application")

    @patch("ai_engine.get_client")
    def test_generate_topic_mastery_exam_more_than_four_questions(self, mock_get_client):
        """Verify generate_topic_mastery_exam supports >4 questions and concept_counts customization."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "Year 10 5.3 Consumer Arithmetic - End-of-Topic Mastery Exam",
            "topic": "Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "sheet_type": "Topic Mastery Exam",
            "questions": [
                {"item_label": str(i), "marks": 2, "concept_name": "Concept 1: Simple Interest", "text": f"Q{i}", "correct_answer": "ans"}
                for i in range(1, 13)
            ],
            "marking_key": {str(i): "ans" for i in range(1, 13)}
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        sample_tb = {
            "id": 42,
            "title": "Year 10 Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "topic": "Consumer Arithmetic",
            "concepts": [
                {"name": "Concept 1: Simple Interest", "key_formulas": ["I = Prn"], "tutor_tips": "Flat rate only."},
                {"name": "Concept 2: Compound Interest", "key_formulas": ["A = P(1+r)^n"], "tutor_tips": "Watch compounding frequency."}
            ]
        }

        # 1. Test with questions_per_concept = 6 (> 4 questions)
        exam = ai_engine.generate_topic_mastery_exam(sample_tb, api_key="fake-key", questions_per_concept=6)
        call_prompt = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("generate exactly 6 questions (total 12 questions)", call_prompt)
        self.assertIn('"total_items": 12', call_prompt)

        # 2. Test with concept_counts customization (e.g. 5 and 7 questions)
        exam2 = ai_engine.generate_topic_mastery_exam(
            sample_tb,
            api_key="fake-key",
            concept_counts={"Concept 1: Simple Interest": 5, "Concept 2: Compound Interest": 7}
        )
        call_prompt2 = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("Target: 5 questions", call_prompt2)
        self.assertIn("Target: 7 questions", call_prompt2)
        self.assertIn('"total_items": 12', call_prompt2)

    @patch("ai_engine.get_client")
    def test_generate_aligned_companion_worksheet_in_class(self, mock_get_client):
        """Verify In-Class companion worksheet generation with per-concept question counts."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "Year 10 Mathematics - Consumer Arithmetic (In-Class Practice)",
            "topic": "Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "sheet_type": "In-Class",
            "source_theory_id": 42,
            "assessment_type": "in_class",
            "total_items": 3,
            "questions": [
                {"item_label": "1", "marks": 2, "concept_name": "Concept 1: Simple Interest", "text": "Q1"},
                {"item_label": "2", "marks": 2, "concept_name": "Concept 1: Simple Interest", "text": "Q2"},
                {"item_label": "3", "marks": 3, "concept_name": "Concept 2: Compound Interest", "text": "Q3"}
            ],
            "marking_key": {"1": "A", "2": "B", "3": "C"}
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        sample_tb = {
            "id": 42,
            "title": "Year 10 Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "topic": "Consumer Arithmetic",
            "concepts": [
                {
                    "name": "Concept 1: Simple Interest",
                    "key_formulas": ["I = Prn"],
                    "tutor_tips": "Flat rate only.",
                    "teacher_examples": [{"problem_text": "Calculate simple interest on $5000 at 4% for 3 years."}]
                },
                {
                    "name": "Concept 2: Compound Interest",
                    "key_formulas": ["A = P(1+r)^n"],
                    "tutor_tips": "Watch compounding frequency.",
                    "teacher_examples": [{"problem_text": "Calculate compound amount for $5000 compounded quarterly."}]
                }
            ]
        }

        ic_ws = ai_engine.generate_aligned_companion_worksheet(
            theory_booklet=sample_tb,
            sheet_type="In-Class",
            concept_counts={"Concept 1: Simple Interest": 2, "Concept 2: Compound Interest": 1},
            api_key="fake-key"
        )
        self.assertEqual(ic_ws["sheet_type"], "In-Class")
        self.assertEqual(ic_ws["assessment_type"], "in_class")
        self.assertEqual(ic_ws["source_theory_id"], 42)

        call_prompt = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("IN-CLASS GUIDED WHITEBOARD PRACTICE", call_prompt)
        self.assertIn("Requested Questions: 2", call_prompt)
        self.assertIn("Requested Questions: 1", call_prompt)
        self.assertIn("TOTAL QUESTIONS TO GENERATE: EXACTLY 3", call_prompt)
        self.assertIn("Prototype Example 1: Calculate simple interest", call_prompt)

    @patch("ai_engine.get_client")
    def test_generate_aligned_companion_worksheet_homework(self, mock_get_client):
        """Verify Homework numerical twin companion worksheet generation with per-concept counts and set number."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "Year 10 Mathematics - Consumer Arithmetic (Homework - Set 2)",
            "topic": "Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "sheet_type": "Homework",
            "set_number": 2,
            "source_theory_id": 42,
            "assessment_type": "homework",
            "total_items": 5,
            "questions": [
                {"item_label": "1", "marks": 2, "concept_name": "Concept 1: Simple Interest", "text": "HQ1"}
            ],
            "marking_key": {"1": "Ans1"}
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        sample_tb = {
            "id": 42,
            "title": "Year 10 Consumer Arithmetic",
            "year_level": "Year 10 5.3",
            "topic": "Consumer Arithmetic",
            "concepts": [
                {
                    "name": "Concept 1: Simple Interest",
                    "key_formulas": ["I = Prn"],
                    "teacher_examples": [{"problem_text": "Ex1 Simple Interest"}]
                },
                {
                    "name": "Concept 2: Compound Interest",
                    "key_formulas": ["A = P(1+r)^n"],
                    "teacher_examples": [{"problem_text": "Ex2 Compound Interest"}]
                }
            ]
        }

        hw_ws = ai_engine.generate_aligned_companion_worksheet(
            theory_booklet=sample_tb,
            sheet_type="Homework",
            concept_counts={"Concept 1: Simple Interest": 3, "Concept 2: Compound Interest": 2},
            set_number=2,
            api_key="fake-key"
        )
        self.assertEqual(hw_ws["sheet_type"], "Homework")
        self.assertEqual(hw_ws["assessment_type"], "homework")
        self.assertEqual(hw_ws["set_number"], 2)
        self.assertEqual(hw_ws["source_theory_id"], 42)

        call_prompt = mock_client.models.generate_content.call_args[1]["contents"]
        self.assertIn("HOMEWORK NUMERICAL TWINS & MASTERY REINFORCEMENT (SET 2)", call_prompt)
        self.assertIn("Requested Questions: 3", call_prompt)
        self.assertIn("Requested Questions: 2", call_prompt)
        self.assertIn("TOTAL QUESTIONS TO GENERATE: EXACTLY 5", call_prompt)


if __name__ == "__main__":
    unittest.main()


