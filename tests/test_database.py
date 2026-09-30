import unittest
import os
import database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.original_db = database.DB_FILE
        database.DB_FILE = os.path.join(os.path.dirname(__file__), "test_da_tuition.db")
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.init_db()

    def tearDown(self):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.DB_FILE = self.original_db

    def test_class_and_roll_flow(self):
        class_id = database.create_class("Year 10 Advanced - Sat 10am", "Year 10", "Mr. David", "Sat 10:00 - 12:00")
        self.assertGreater(class_id, 0)

        students = ["Ryan Huynh", "Emily Chen", "Alex Smith"]
        added = database.add_students_to_class(class_id, students)
        self.assertEqual(added, 3)

        roll = database.get_class_students(class_id)
        self.assertEqual(len(roll), 3)
        self.assertIn("Emily Chen", roll)

    def test_worksheet_and_submission_flow(self):
        class_id = database.create_class("Year 8 Math - Sun 2pm", "Year 8", "Ms. Sarah", "Sun 14:00 - 16:00")
        
        qs = [
            {"num": 1, "text": "Simplify 2x + 3x", "answer": "5x", "topic": "Algebra", "subtopic": "Collecting Terms"},
            {"num": 2, "text": "Solve 2x = 10", "answer": "5", "topic": "Algebra", "subtopic": "Linear Equations"}
        ]
        key = {"1": "5x", "2": "5"}
        ws_id = database.save_worksheet("Term 1 Week 1 Homework", 1, 1, "Year 8", "Algebra", "Medium", qs, key)
        self.assertGreater(ws_id, 0)

        mistakes = [
            {
                "question_num": "2",
                "topic": "Algebra",
                "subtopic": "Linear Equations",
                "status": "Incorrect",
                "marks_lost": 1.0,
                "student_answer": "20",
                "correct_answer": "5",
                "error_type": "Calculation"
            }
        ]
        sub_id = database.save_submission(
            worksheet_id=ws_id,
            student_name="Alex Smith",
            raw_file_name="Alex_Homework.pdf",
            score=1.0,
            total_marks=2.0,
            accuracy_pct=50.0,
            pdf_report_path="reports/Alex_Report.pdf",
            summary_text="Good effort on basic terms.",
            mistakes=mistakes,
            class_id=class_id
        )
        self.assertGreater(sub_id, 0)

        history = database.get_student_history("Alex Smith")
        self.assertEqual(len(history), 1)

        sub = database.get_submission_by_id(sub_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["student_name"], "Alex Smith")
        self.assertEqual(sub["score"], 1.0)
        self.assertEqual(sub["total_marks"], 2.0)

        sub_mistakes = database.get_submission_mistakes(sub_id)
        self.assertEqual(len(sub_mistakes), 1)
        self.assertEqual(sub_mistakes[0]["question_num"], "2")
        self.assertEqual(sub_mistakes[0]["correct_answer"], "5")

        summary = database.get_submissions_summary(class_id=class_id)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["class_name"], "Year 8 Math - Sun 2pm")

    def test_generated_homework_is_saved_once_for_marking(self):
        worksheet = {
            "id": 1790699533,  # An older session's timestamp was not a database ID.
            "title": "Year 11 (Extension) - Permutations Homework Set 3",
            "term": 3,
            "week": 8,
            "year_level": "Year 11 (Extension)",
            "topic": "Permutations",
            "difficulty": "Mixed",
            "sheet_type": "Homework",
            "set_number": 3,
            "questions": [{"item_label": "1", "text": "How many arrangements?", "marks": 1}],
            "marking_key": {"1": "24"},
        }
        saved_id = database.ensure_generated_worksheet_saved(worksheet)
        worksheet["id"] = saved_id
        self.assertEqual(database.ensure_generated_worksheet_saved(worksheet), saved_id)
        matches = [w for w in database.get_worksheets() if w["id"] == saved_id]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["assessment_type"], "homework")
        self.assertEqual(matches[0]["set_number"], 3)
        self.assertEqual(database.get_worksheet_by_id(saved_id)["marking_key"], {"1": "24"})

    def test_missing_mistake_question_label_is_resolved_from_marking_key(self):
        ws_id = database.save_worksheet(
            "Permutations Homework Set 1", 1, 1, "Year 11 (Extension)",
            "Permutations", "Mixed", [], {"10": "72", "11": "144", "12": "14,400"}
        )
        sub_id = database.save_submission(
            worksheet_id=ws_id,
            student_name="Testing 3",
            raw_file_name="Testing Combined.pdf",
            score=13.5,
            total_marks=18.0,
            accuracy_pct=75.0,
            pdf_report_path="reports/Testing_3.pdf",
            mistakes=[{
                "question_num": "",
                "correct_answer": "14,400",
                "student_answer": "wrong",
                "marks_lost": 1.5,
            }],
        )

        mistakes = database.get_submission_mistakes(sub_id)
        self.assertEqual(mistakes[0]["question_num"], "12")

    def test_delete_unmarked_worksheet(self):
        ws_id = database.save_worksheet("Old worksheet", 1, 1, "Year 8", "Algebra", "Easy", [], {})
        self.assertTrue(database.delete_worksheet(ws_id))
        self.assertIsNone(database.get_worksheet_by_id(ws_id))
        self.assertFalse(database.delete_worksheet(ws_id))

    def test_delete_preserves_marked_worksheet_and_submission(self):
        ws_id = database.save_worksheet("Marked worksheet", 1, 1, "Year 8", "Algebra", "Easy", [], {})
        sub_id = database.save_submission(
            worksheet_id=ws_id, student_name="Alex Smith", raw_file_name="answer.pdf",
            score=1, total_marks=2, accuracy_pct=50, pdf_report_path="report.pdf",
            summary_text="Reviewed", mistakes=[]
        )
        with self.assertRaisesRegex(ValueError, "marked submission"):
            database.delete_worksheet(ws_id)
        self.assertIsNotNone(database.get_worksheet_by_id(ws_id))
        self.assertIsNotNone(database.get_submission_by_id(sub_id))

    def test_delete_single_submission_preserves_worksheet(self):
        ws_id = database.save_worksheet("Testing worksheet", 1, 1, "Year 8", "Algebra", "Easy", [], {})
        sub_id = database.save_submission(
            worksheet_id=ws_id, student_name="Testing Student", raw_file_name="test.pdf",
            score=0, total_marks=2, accuracy_pct=0, pdf_report_path="report.pdf",
            summary_text="Retry", mistakes=[{"question_num": "1", "status": "Incorrect", "marks_lost": 1}]
        )
        self.assertTrue(database.delete_submission(sub_id))
        self.assertIsNone(database.get_submission_by_id(sub_id))
        self.assertEqual(database.get_submission_mistakes(sub_id), [])
        self.assertIsNotNone(database.get_worksheet_by_id(ws_id))
        self.assertFalse(database.delete_submission(sub_id))

    def test_user_authentication(self):
        # Default seeded users
        bunsea = database.authenticate_user("bunsea", "password123")
        self.assertIsNotNone(bunsea)
        self.assertEqual(bunsea["username"], "bunsea")
        self.assertEqual(bunsea["role"], "admin")
        self.assertNotIn("password_hash", bunsea)
        self.assertNotIn("salt", bunsea)

        david = database.authenticate_user("tutor_david", "password123")
        self.assertIsNotNone(david)
        self.assertEqual(david["role"], "tutor")

        # Wrong password
        wrong = database.authenticate_user("bunsea", "wrongpass")
        self.assertIsNone(wrong)

        # Nonexistent user
        nonexistent = database.authenticate_user("ghost_tutor", "password123")
        self.assertIsNone(nonexistent)

    def test_tutor_class_isolation(self):
        # Create tutor 1 and tutor 2
        t1_id = database.create_user("tutor_alice", "pass123", "Ms. Alice", "tutor")
        t2_id = database.create_user("tutor_bob", "pass123", "Mr. Bob", "tutor")

        # Create classes for each tutor
        c1_id = database.create_class("Alice Class Year 7", "Year 7", "Ms. Alice", "Mon 4pm", tutor_id=t1_id)
        c2_id = database.create_class("Bob Class Year 9", "Year 9", "Mr. Bob", "Wed 5pm", tutor_id=t2_id)

        # Alice should only see her own class
        alice_classes = database.get_classes_for_user(t1_id, "tutor")
        self.assertEqual(len(alice_classes), 1)
        self.assertEqual(alice_classes[0]["id"], c1_id)

        # Bob should only see his own class
        bob_classes = database.get_classes_for_user(t2_id, "tutor")
        self.assertEqual(len(bob_classes), 1)
        self.assertEqual(bob_classes[0]["id"], c2_id)

        # Admin should see both classes (and any seeded defaults)
        admin_classes = database.get_classes_for_user(1, "admin")
        admin_class_ids = [c["id"] for c in admin_classes]
        self.assertIn(c1_id, admin_class_ids)
        self.assertIn(c2_id, admin_class_ids)

    def test_student_roster_privacy(self):
        t1_id = database.create_user("tutor_clara", "pass123", "Ms. Clara", "tutor")
        t2_id = database.create_user("tutor_dan", "pass123", "Mr. Dan", "tutor")

        c1 = database.create_class("Clara Class", "Year 10", "Ms. Clara", tutor_id=t1_id)
        c2 = database.create_class("Dan Class", "Year 11", "Mr. Dan", tutor_id=t2_id)

        database.add_students_to_class(c1, ["Student Clara 1", "Student Clara 2"])
        database.add_students_to_class(c2, ["Student Dan 1", "Student Dan 2"])

        # Clara should only see her students
        clara_students = [s["name"] for s in database.get_students_for_user(t1_id, "tutor")]
        self.assertIn("Student Clara 1", clara_students)
        self.assertIn("Student Clara 2", clara_students)
        self.assertNotIn("Student Dan 1", clara_students)
        self.assertNotIn("Student Dan 2", clara_students)

        # Dan should only see his students
        dan_students = [s["name"] for s in database.get_students_for_user(t2_id, "tutor")]
        self.assertIn("Student Dan 1", dan_students)
        self.assertNotIn("Student Clara 1", dan_students)

        # Admin sees all students
        admin_students = [s["name"] for s in database.get_students_for_user(1, "admin")]
        self.assertIn("Student Clara 1", admin_students)
        self.assertIn("Student Dan 1", admin_students)

    def test_class_access_security(self):
        t1_id = database.create_user("tutor_eva", "pass123", "Ms. Eva", "tutor")
        t2_id = database.create_user("tutor_frank", "pass123", "Mr. Frank", "tutor")

        c1 = database.create_class("Eva Class", "Year 12", "Ms. Eva", tutor_id=t1_id)

        # Eva owns c1 -> True
        self.assertTrue(database.can_user_access_class(t1_id, "tutor", c1))

        # Frank does NOT own c1 -> False
        self.assertFalse(database.can_user_access_class(t2_id, "tutor", c1))

        # Admin always has access -> True
        self.assertTrue(database.can_user_access_class(999, "admin", c1))

    def test_submission_analytics_scoping(self):
        t1_id = database.create_user("tutor_gina", "pass123", "Ms. Gina", "tutor")
        t2_id = database.create_user("tutor_harry", "pass123", "Mr. Harry", "tutor")

        c1 = database.create_class("Gina Class", "Year 9", tutor_id=t1_id)
        c2 = database.create_class("Harry Class", "Year 10", tutor_id=t2_id)

        database.save_submission(
            worksheet_id=None,
            student_name="Gina Student",
            raw_file_name="gina.pdf",
            score=9.0, total_marks=10.0, accuracy_pct=90.0,
            pdf_report_path="",
            class_id=c1
        )
        database.save_submission(
            worksheet_id=None,
            student_name="Harry Student",
            raw_file_name="harry.pdf",
            score=5.0, total_marks=10.0, accuracy_pct=50.0,
            pdf_report_path="",
            class_id=c2
        )

        # Gina should only see her class submission
        gina_subs = database.get_submissions_summary(user_id=t1_id, role="tutor")
        self.assertEqual(len(gina_subs), 1)
        self.assertEqual(gina_subs[0]["student_name"], "Gina Student")

        # Harry should only see his class submission
        harry_subs = database.get_submissions_summary(user_id=t2_id, role="tutor")
        self.assertEqual(len(harry_subs), 1)
        self.assertEqual(harry_subs[0]["student_name"], "Harry Student")

        # Admin sees both
        admin_subs = database.get_submissions_summary(user_id=1, role="admin")
        self.assertEqual(len(admin_subs), 2)

    def test_lesson_cover_sheet_crud_and_scoping(self):
        t1 = database.create_user("tutor_katie", "pass123", "Ms. Katie", "tutor")
        t2 = database.create_user("tutor_leo", "pass123", "Mr. Leo", "tutor")

        c1 = database.create_class("Katie Year 11", "Year 11", tutor_id=t1)
        c2 = database.create_class("Leo Year 12", "Year 12", tutor_id=t2)

        sheet1_id = database.create_lesson_cover_sheet({
            "student_name": "Marcus Vance",
            "class_id": c1,
            "tutor_id": t1,
            "term": 1,
            "week": 3,
            "lesson_date": "2026-03-10",
            "subject": "Maths",
            "topic": "Vectors in 2D",
            "subtopic": "Dot Product & Orthogonality",
            "syllabus_outcomes": "ME-V1",
            "materials_used": ["DA Topic Booklet", "Exam Papers"],
            "mastery_data": [
                {"concept": "Dot Product Formula", "level": "Independent"},
                {"concept": "Proving Orthogonal Vectors", "level": "Exam Ready"}
            ],
            "root_cause_tags": ["Careless / Algebraic Slip"],
            "specific_stumbling_block": "Negative sign expansion in 3D dot product",
            "intervention_tags": ["Visual / Geometric Sketch", "Stepped Algorithm"],
            "score_engagement": 5,
            "score_confidence": 4,
            "score_independence": 4,
            "tutor_observations": "Great focus, solved multi-step proofs well.",
            "attention_flag": "all_clear",
            "homework_assigned": "Exercise 4B Q1-8",
            "homework_due": "2026-03-17",
            "target_accuracy": "90%",
            "next_lesson_priority": "Vector Projections",
            "parent_soundbite": "Marcus mastered perpendicular vector proofs; next week we tackle projections.",
            "student_clarity": "Crystal Clear",
            "student_support": "Very Supported",
            "student_questions": "Always (100%)",
            "student_difficulty": "Sweet Spot",
            "student_confidence_shift": "Higher",
            "student_request_note": "More 3D projection questions"
        })
        self.assertGreater(sheet1_id, 0)

        # Retrieve and verify deserialized JSON
        sheet1 = database.get_lesson_cover_sheet_by_id(sheet1_id)
        self.assertIsNotNone(sheet1)
        self.assertEqual(sheet1["student_name"], "Marcus Vance")
        self.assertEqual(len(sheet1["mastery_data"]), 2)
        self.assertEqual(sheet1["mastery_data"][0]["concept"], "Dot Product Formula")
        self.assertIn("Visual / Geometric Sketch", sheet1["intervention_tags"])

        # Create sheet for tutor 2
        sheet2_id = database.create_lesson_cover_sheet({
            "student_name": "Samantha Wu",
            "class_id": c2,
            "tutor_id": t2,
            "topic": "Differential Calculus",
            "score_engagement": 4,
            "score_confidence": 3,
            "score_independence": 3,
            "attention_flag": "homework_missing",
            "attention_notes": "Did not complete homework due to sports gala."
        })
        self.assertGreater(sheet2_id, 0)

        # Scoping: Katie should only see Marcus
        katie_sheets = database.get_lesson_cover_sheets(user_id=t1, role="tutor")
        self.assertEqual(len(katie_sheets), 1)
        self.assertEqual(katie_sheets[0]["student_name"], "Marcus Vance")

        # Scoping: Leo should only see Samantha
        leo_sheets = database.get_lesson_cover_sheets(user_id=t2, role="tutor")
        self.assertEqual(len(leo_sheets), 1)
        self.assertEqual(leo_sheets[0]["student_name"], "Samantha Wu")

        # Admin sees both
        admin_sheets = database.get_lesson_cover_sheets(user_id=1, role="admin")
        self.assertEqual(len(admin_sheets), 2)

    def test_student_longitudinal_metrics(self):
        t1 = database.create_user("tutor_maya", "pass123", "Ms. Maya", "tutor")
        c1 = database.create_class("Maya Class", "Year 11", tutor_id=t1)

        # Lesson 1
        database.create_lesson_cover_sheet({
            "student_name": "Oliver Twist",
            "class_id": c1,
            "tutor_id": t1,
            "term": 1,
            "week": 1,
            "lesson_date": "2026-02-01",
            "topic": "Surds & Indices",
            "root_cause_tags": ["Prerequisite Foundation Gap"],
            "score_engagement": 3,
            "score_confidence": 2,
            "score_independence": 2,
            "attention_flag": "deficit_remedial",
            "attention_notes": "Year 9 index law gaps",
            "parent_soundbite": "Reviewed basic index laws with heavy scaffolding.",
            "student_clarity": "Mostly Clear",
            "student_difficulty": "Overwhelming"
        })

        # Lesson 2
        database.create_lesson_cover_sheet({
            "student_name": "Oliver Twist",
            "class_id": c1,
            "tutor_id": t1,
            "term": 1,
            "week": 2,
            "lesson_date": "2026-02-08",
            "topic": "Surds & Rationalising",
            "root_cause_tags": ["Prerequisite Foundation Gap", "Careless / Algebraic Slip"],
            "score_engagement": 4,
            "score_confidence": 4,
            "score_independence": 3,
            "attention_flag": "all_clear",
            "parent_soundbite": "Oliver gained solid confidence rationalising surds.",
            "student_clarity": "Crystal Clear",
            "student_difficulty": "Sweet Spot"
        })

        # Lesson 3
        database.create_lesson_cover_sheet({
            "student_name": "Oliver Twist",
            "class_id": c1,
            "tutor_id": t1,
            "term": 1,
            "week": 3,
            "lesson_date": "2026-02-15",
            "topic": "Algebraic Proofs",
            "root_cause_tags": ["Careless / Algebraic Slip"],
            "score_engagement": 5,
            "score_confidence": 5,
            "score_independence": 4,
            "attention_flag": "all_clear",
            "parent_soundbite": "Oliver worked independently on rigorous surd proofs!",
            "student_clarity": "Crystal Clear",
            "student_difficulty": "Sweet Spot"
        })

        metrics = database.get_student_longitudinal_metrics("Oliver Twist")
        self.assertEqual(metrics["total_lessons"], 3)
        self.assertEqual(metrics["avg_engagement"], 4.0) # (3+4+5)/3
        self.assertAlmostEqual(metrics["avg_confidence"], 3.67, places=2) # (2+4+5)/3
        self.assertEqual(metrics["avg_independence"], 3.0) # (2+3+4)/3
        self.assertEqual(metrics["latest_soundbite"], "Oliver worked independently on rigorous surd proofs!")
        self.assertEqual(len(metrics["attention_flags"]), 1) # only lesson 1 had deficit_remedial
        self.assertEqual(metrics["root_cause_freq"]["Prerequisite Foundation Gap"], 2)
        self.assertEqual(metrics["root_cause_freq"]["Careless / Algebraic Slip"], 2)
        self.assertEqual(len(metrics["chronological_scores"]), 3)

    def test_create_user_with_api_key_and_lookup(self):
        """Verify user creation with API key, case-insensitive username lookup, and password updating."""
        uid = database.create_user(
            username="Tutor_Emma",
            password="securePassword123",
            display_name="Ms. Emma Watson",
            role="tutor",
            api_key="AIzaSyTestApiKey123"
        )
        self.assertGreater(uid, 0)

        # Lookup by username (case-insensitive)
        u1 = database.get_user_by_username("tutor_emma")
        self.assertIsNotNone(u1)
        self.assertEqual(u1["username"], "tutor_emma")
        self.assertEqual(u1["display_name"], "Ms. Emma Watson")
        self.assertEqual(u1["api_key"], "AIzaSyTestApiKey123")
        self.assertEqual(u1["role"], "tutor")

        # Lookup non-existent
        self.assertIsNone(database.get_user_by_username("non_existent_tutor"))

        # Test password update
        database.update_user_password(uid, "newPassword456")
        self.assertIsNone(database.authenticate_user("tutor_emma", "securePassword123"))
        authed = database.authenticate_user("tutor_emma", "newPassword456")
        self.assertIsNotNone(authed)

    def test_topic_assessment_matrix_and_theory_linked_exams(self):
        """Verify linking an end-of-topic exam to a theory booklet and generating the Topic Assessment Matrix."""
        # 1. Create a Theory Booklet with 3 concepts
        tb_content = {
            "title": "Year 10 5.3 Consumer Arithmetic",
            "concepts": [
                {"name": "Concept 1: Simple Interest", "theory_content": "Formula I = Prn"},
                {"name": "Concept 2: Compound Interest", "theory_content": "Formula A = P(1+r)^n"},
                {"name": "Concept 3: Depreciation", "theory_content": "Formula S = V0(1-r)^n"}
            ]
        }
        tb_id = database.save_theory_booklet("Year 10 Consumer Arithmetic", 1, 1, "Year 10 5.3", "Consumer Arithmetic", tb_content)
        self.assertGreater(tb_id, 0)

        # 2. Save an End-of-Topic Mastery Exam linked to this Theory Booklet
        qs = [
            {"item_label": "1", "marks": 2, "concept_name": "Concept 1: Simple Interest", "cognitive_level": "Level 1"},
            {"item_label": "2", "marks": 3, "concept_name": "Concept 1: Simple Interest", "cognitive_level": "Level 2"},
            {"item_label": "3", "marks": 3, "concept_name": "Concept 2: Compound Interest", "cognitive_level": "Level 2"},
            {"item_label": "4", "marks": 4, "concept_name": "Concept 2: Compound Interest", "cognitive_level": "Level 3"},
            {"item_label": "5", "marks": 3, "concept_name": "Concept 3: Depreciation", "cognitive_level": "Level 2"}
        ]
        key = {"1": "100", "2": "250", "3": "1200", "4": "5600", "5": "8900"}
        ws_id = database.save_worksheet(
            title="Year 10 Consumer Arithmetic - End-of-Topic Mastery Exam",
            term=1, week=1, year_level="Year 10 5.3", topic="Consumer Arithmetic",
            difficulty="Mixed", questions=qs, marking_key=key,
            source_theory_id=tb_id, assessment_type="topic_exam"
        )
        self.assertGreater(ws_id, 0)

        # Check linked exams query
        linked = database.get_theory_linked_exams(tb_id)
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["id"], ws_id)
        self.assertEqual(linked[0]["assessment_type"], "topic_exam")

        # 3. Simulate submissions for 2 students
        # Student A: Masters Concept 1 and 3, but fails Concept 2 (lost 5 marks on Q3 and Q4)
        database.save_submission(
            worksheet_id=ws_id, student_name="Student A", raw_file_name="sub_a.pdf",
            score=10.0, total_marks=15.0, accuracy_pct=66.7, pdf_report_path="reports/a.pdf",
            mistakes=[
                {"question_num": "3", "concept_name": "Concept 2: Compound Interest", "cognitive_level": "Level 2", "marks_lost": 2.0},
                {"question_num": "4", "concept_name": "Concept 2: Compound Interest", "cognitive_level": "Level 3", "marks_lost": 3.0}
            ]
        )

        # Student B: Also struggles with Concept 2 (lost 4 marks on Q4)
        database.save_submission(
            worksheet_id=ws_id, student_name="Student B", raw_file_name="sub_b.pdf",
            score=11.0, total_marks=15.0, accuracy_pct=73.3, pdf_report_path="reports/b.pdf",
            mistakes=[
                {"question_num": "4", "concept_name": "Concept 2: Compound Interest", "cognitive_level": "Level 3", "marks_lost": 4.0}
            ]
        )

        # 4. Generate Topic Assessment Matrix
        matrix = database.get_topic_assessment_matrix(ws_id)
        self.assertEqual(matrix["student_count"], 2)
        self.assertEqual(len(matrix["concepts_tested"]), 3)
        self.assertTrue(matrix["theory_coverage"]["is_complete"])
        self.assertEqual(matrix["theory_coverage"]["coverage_pct"], 100.0)

        # Verify Concept 2 has lower cohort average and triggers teaching gap alert
        c2_avg = matrix["cohort_concept_averages"]["Concept 2: Compound Interest"]["average_pct"]
        self.assertLess(c2_avg, 65.0)
        self.assertTrue(matrix["cohort_concept_averages"]["Concept 2: Compound Interest"]["is_gap"])
        self.assertEqual(len(matrix["teaching_gaps"]), 1)
        self.assertEqual(matrix["teaching_gaps"][0]["concept_name"], "Concept 2: Compound Interest")

    def test_get_theory_linked_worksheets(self):
        # 1. Save Theory Booklet
        tb_id = database.save_theory_booklet(
            title="Year 10 Coordinate Geometry Theory",
            term=1, week=2, year_level="Year 10", topic="Coordinate Geometry",
            content={"topic": "Coordinate Geometry", "concepts": [{"name": "Midpoint"}]}
        )

        # 2. Save In-Class Worksheet
        ic_id = database.save_worksheet(
            title="Year 10 - Coordinate Geometry (In-Class)",
            term=1, week=2, year_level="Year 10", topic="Coordinate Geometry",
            difficulty="Graduated", questions=[{"item_label": "1", "text": "Q1"}],
            marking_key={"1": "A"}, source_theory_id=tb_id, assessment_type="in_class"
        )

        # 3. Save Homework Worksheet Set 1
        hw_id = database.save_worksheet(
            title="Year 10 - Coordinate Geometry (Homework - Set 1)",
            term=1, week=2, year_level="Year 10", topic="Coordinate Geometry",
            difficulty="Balanced", questions=[{"item_label": "1", "text": "HQ1"}],
            marking_key={"1": "B"}, set_number=1, source_theory_id=tb_id, assessment_type="homework"
        )

        # 4. Save Topic Exam
        exam_id = database.save_worksheet(
            title="Year 10 - Coordinate Geometry (Mastery Exam)",
            term=1, week=2, year_level="Year 10", topic="Coordinate Geometry",
            difficulty="Tiered", questions=[{"item_label": "1", "text": "EQ1"}],
            marking_key={"1": "C"}, source_theory_id=tb_id, assessment_type="topic_exam"
        )

        # 5. Test filtering by assessment_type
        all_linked = database.get_theory_linked_worksheets(tb_id)
        self.assertEqual(len(all_linked), 3)

        ic_linked = database.get_theory_linked_worksheets(tb_id, assessment_type="in_class")
        self.assertEqual(len(ic_linked), 1)
        self.assertEqual(ic_linked[0]["id"], ic_id)

        hw_linked = database.get_theory_linked_worksheets(tb_id, assessment_type="homework")
        self.assertEqual(len(hw_linked), 1)
        self.assertEqual(hw_linked[0]["id"], hw_id)

        exam_linked = database.get_theory_linked_worksheets(tb_id, assessment_type="topic_exam")
        self.assertEqual(len(exam_linked), 1)
        self.assertEqual(exam_linked[0]["id"], exam_id)

    def test_init_db_idempotency_and_concurrency(self):
        """Verify calling init_db repeatedly and concurrently does not raise IntegrityError on users table."""
        import threading

        # Sequential repeated calls with force=True
        for _ in range(5):
            database.init_db(force=True)

        # Verify admin user is still present and valid
        bunsea = database.get_user_by_username("bunsea")
        self.assertIsNotNone(bunsea)
        self.assertEqual(bunsea["role"], "admin")

        # Concurrent multithreaded calls
        errors = []
        def run_init():
            try:
                database.init_db(force=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=run_init) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent init_db raised errors: {errors}")

if __name__ == "__main__":
    unittest.main()
