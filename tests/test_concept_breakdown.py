import unittest
import os
import json
import database
import pdf_generator

class TestConceptBreakdown(unittest.TestCase):
    def setUp(self):
        self.original_db = database.DB_FILE
        database.DB_FILE = os.path.join(os.path.dirname(__file__), "test_concept_breakdown.db")
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.init_db()

    def tearDown(self):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.DB_FILE = self.original_db

    def test_submission_and_student_concept_breakdown(self):
        # 1. Create a worksheet with questions assigned to concepts
        ws_id = database.save_worksheet(
            title="Year 10 Coordinate Geometry Set 1",
            term=1,
            week=2,
            year_level="Year 10",
            topic="Coordinate Geometry",
            difficulty="Medium",
            questions=[
                {"item_label": "1", "concept_name": "Distance Formula", "text": "Find distance", "correct_answer": "5"},
                {"item_label": "2", "concept_name": "Distance Formula", "text": "Perimeter", "correct_answer": "12"},
                {"item_label": "3", "concept_name": "Midpoint Formula", "text": "Find midpoint", "correct_answer": "(2, 3)"},
                {"item_label": "4", "concept_name": "Gradient & Parallel Lines", "text": "Find gradient", "correct_answer": "2"}
            ],
            marking_key={"1": "5", "2": "12", "3": "(2, 3)", "4": "2"},
            set_number=1
        )
        self.assertGreater(ws_id, 0)

        # 2. Save submission with mistakes on Q2 and Q3
        sub_id = database.save_submission(
            worksheet_id=ws_id,
            student_name="Alice Smith",
            raw_file_name="alice_hw.pdf",
            score=2.0,
            total_marks=4.0,
            accuracy_pct=50.0,
            pdf_report_path="reports/alice.pdf",
            summary_text="Good effort, review perimeter arithmetic and midpoint.",
            mistakes=[
                {
                    "question_num": "2",
                    "topic": "Coordinate Geometry",
                    "concept_name": "Distance Formula",
                    "status": "Incorrect",
                    "marks_lost": 1.0,
                    "student_answer": "11",
                    "correct_answer": "12",
                    "error_type": "Calculation Error"
                },
                {
                    "question_num": "3",
                    "topic": "Coordinate Geometry",
                    "concept_name": "Midpoint Formula",
                    "status": "Incorrect",
                    "marks_lost": 1.0,
                    "student_answer": "(2, 1)",
                    "correct_answer": "(2, 3)",
                    "error_type": "Calculation Error"
                }
            ]
        )
        self.assertGreater(sub_id, 0)

        # 3. Test get_submission_concept_breakdown
        breakdown = database.get_submission_concept_breakdown(sub_id)
        self.assertEqual(len(breakdown), 3)

        b_map = {b["concept_name"]: b for b in breakdown}
        self.assertIn("Distance Formula", b_map)
        self.assertIn("Midpoint Formula", b_map)
        self.assertIn("Gradient & Parallel Lines", b_map)

        # Distance Formula: 2 designated questions (1, 2), 1 correct, 1 incorrect -> 50% (Weakness)
        dist = b_map["Distance Formula"]
        self.assertEqual(dist["total_questions"], 2)
        self.assertEqual(dist["correct_count"], 1)
        self.assertEqual(dist["incorrect_count"], 1)
        self.assertEqual(dist["accuracy_pct"], 50.0)
        self.assertEqual(dist["status"], "Weakness")
        self.assertEqual(dist["questions_designated"], ["1", "2"])

        # Midpoint Formula: 1 designated question (3), 0 correct, 1 incorrect -> 0% (Weakness)
        mid = b_map["Midpoint Formula"]
        self.assertEqual(mid["total_questions"], 1)
        self.assertEqual(mid["correct_count"], 0)
        self.assertEqual(mid["incorrect_count"], 1)
        self.assertEqual(mid["status"], "Weakness")

        # Gradient & Parallel Lines: 1 designated question (4), 1 correct, 0 incorrect -> 100% (Strength)
        grad = b_map["Gradient & Parallel Lines"]
        self.assertEqual(grad["total_questions"], 1)
        self.assertEqual(grad["correct_count"], 1)
        self.assertEqual(grad["incorrect_count"], 0)
        self.assertEqual(grad["accuracy_pct"], 100.0)
        self.assertEqual(grad["status"], "Strength")

        # 4. Test student concept mastery matrix
        matrix = database.get_student_concept_mastery_matrix("Alice Smith")
        self.assertEqual(len(matrix), 3)

        # 5. Test PDF report generation with concept breakdown
        pdf_bytes = pdf_generator.generate_student_report_pdf(
            student_name="Alice Smith",
            term_week_header="Term 1 Week 2: Coordinate Geometry",
            score=2.0,
            total_marks=4.0,
            accuracy_pct=50.0,
            mistakes=database.get_submission_mistakes(sub_id),
            concept_breakdown=breakdown
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_subpart_mistake_matching_and_ordering(self):
        # Test question ordering across Sets and Sections
        unordered_qs = [
            {"item_label": "1", "subtopic": "Topic A", "difficulty": "Easy", "text": "Q1"},
            {"item_label": "2", "subtopic": "Topic B", "difficulty": "Easy", "text": "Q2"},
            {"item_label": "3", "subtopic": "Topic A", "difficulty": "Medium", "text": "Q3"},
            {"item_label": "4", "subtopic": "Topic B", "difficulty": "Medium", "text": "Q4"},
        ]
        ordered = pdf_generator.order_and_renumber_worksheet_questions(unordered_qs)
        # Should be ordered: Topic A (Easy), Topic A (Medium), Topic B (Easy), Topic B (Medium)
        self.assertEqual([q["item_label"] for q in ordered], ["1", "2", "3", "4"])
        self.assertEqual([q["text"] for q in ordered], ["Q1", "Q3", "Q2", "Q4"])

        # Test subpart mistake matching (e.g. Qn 2(a), 2(b))
        ws_id = database.save_worksheet(
            title="Subpart Test Worksheet",
            topic="Combinatorics",
            year_level="Year 11",
            term=1,
            week=1,
            difficulty="Medium",
            questions=[
                {"item_label": "1", "concept_name": "Permutations", "text": "Q1"},
                {"item_label": "2", "concept_name": "Combinations", "text": "Q2"}
            ],
            marking_key={"1": "10", "2": "20"},
            set_number=1
        )

        sub_id = database.save_submission(
            worksheet_id=ws_id,
            student_name="Bob Jones",
            raw_file_name="bob.pdf",
            score=1.0,
            total_marks=2.0,
            accuracy_pct=50.0,
            pdf_report_path="bob_report.pdf",
            summary_text="Good effort",
            mistakes=[
                {"question_num": "Qn 2(a)", "concept_name": "Combinations", "status": "Incorrect", "marks_lost": 1.0}
            ]
        )

        breakdown = database.get_submission_concept_breakdown(sub_id)
        b_map = {b["concept_name"]: b for b in breakdown}
        self.assertEqual(b_map["Combinations"]["accuracy_pct"], 0.0)
        self.assertEqual(b_map["Combinations"]["status"], "Weakness")
        self.assertEqual(b_map["Permutations"]["accuracy_pct"], 100.0)
        self.assertEqual(b_map["Permutations"]["status"], "Strength")

    def test_delete_worksheet_and_theory_booklet(self):
        # 1. Unmarked worksheet delete
        ws_id1 = database.save_worksheet(
            title="Temp Unmarked Worksheet",
            topic="Geometry",
            year_level="Year 9",
            term=2,
            week=3,
            difficulty="Easy",
            questions=[{"item_label": "1", "text": "Q1"}],
            marking_key={"1": "A"}
        )
        self.assertEqual(database.get_worksheet_submission_count(ws_id1), 0)
        self.assertTrue(database.delete_worksheet(ws_id1, force=False))
        self.assertIsNone(database.get_worksheet_by_id(ws_id1))

        # 2. Marked worksheet delete with force=False raising ValueError
        ws_id2 = database.save_worksheet(
            title="Temp Marked Worksheet",
            topic="Geometry",
            year_level="Year 9",
            term=2,
            week=3,
            difficulty="Easy",
            questions=[{"item_label": "1", "text": "Q1"}],
            marking_key={"1": "A"}
        )
        database.save_submission(
            worksheet_id=ws_id2,
            student_name="Test Student",
            raw_file_name="test.pdf",
            score=1.0,
            total_marks=1.0,
            accuracy_pct=100.0,
            pdf_report_path="test.pdf",
            summary_text="Done",
            mistakes=[]
        )
        self.assertEqual(database.get_worksheet_submission_count(ws_id2), 1)
        with self.assertRaises(ValueError):
            database.delete_worksheet(ws_id2, force=False)
        
        # 3. Force delete of marked worksheet succeeds
        self.assertTrue(database.delete_worksheet(ws_id2, force=True))
        self.assertIsNone(database.get_worksheet_by_id(ws_id2))

        # 4. Theory booklet delete
        tb_id = database.save_theory_booklet(
            title="Temp Theory Booklet",
            term=1,
            week=1,
            year_level="Year 11",
            topic="Algebra",
            content={"concepts": []}
        )
        self.assertIsNotNone(database.get_theory_booklet_by_id(tb_id))
        database.delete_theory_booklet(tb_id)
        self.assertIsNone(database.get_theory_booklet_by_id(tb_id))

if __name__ == "__main__":
    unittest.main()

