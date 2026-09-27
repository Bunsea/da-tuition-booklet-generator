import unittest
import os
import database
import ai_engine
import cloud_sync

class TestGeminiCostAndInstructions(unittest.TestCase):
    def setUp(self):
        self.original_db = database.DB_FILE
        database.DB_FILE = os.path.join(os.path.dirname(__file__), "test_cost_instructions.db")
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.init_db()

    def tearDown(self):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.DB_FILE = self.original_db

    def test_gemini_cost_estimation(self):
        # Gemini 3.8 Flash USD calculation: $0.75 / 1M in, $3.75 / 1M out
        expected_38_usd = (1000 / 1_000_000 * 0.75) + (2000 / 1_000_000 * 3.75)
        cost_38_usd = ai_engine.estimate_gemini_cost(1000, 2000, model="gemini-3.8-flash", currency="USD")
        self.assertAlmostEqual(cost_38_usd, round(expected_38_usd, 6), places=5)

        # Gemini 3.8 Flash AUD calculation: default currency is AUD (1.55x USD)
        cost_38_aud = ai_engine.estimate_gemini_cost(1000, 2000, model="gemini-3.8-flash")
        expected_38_aud = expected_38_usd * ai_engine.USD_TO_AUD_RATE
        self.assertAlmostEqual(cost_38_aud, round(expected_38_aud, 5), places=5)

        # Default model is gemini-3.8-flash
        cost_default = ai_engine.estimate_gemini_cost(1000, 2000)
        self.assertEqual(cost_default, cost_38_aud)

        # Gemini 2.5 Flash: $0.30 / 1M in, $2.50 / 1M out
        cost_25 = ai_engine.estimate_gemini_cost(1000, 2000, model="gemini-2.5-flash")
        expected_25 = ((1000 / 1_000_000 * 0.30) + (2000 / 1_000_000 * 2.50)) * ai_engine.USD_TO_AUD_RATE
        self.assertAlmostEqual(cost_25, round(expected_25, 5), places=5)

        # Gemini 2.5 Flash-Lite: $0.10 / 1M in, $0.40 / 1M out
        cost_lite = ai_engine.estimate_gemini_cost(1000, 2000, model="gemini-2.5-flash-lite")
        expected_lite = ((1000 / 1_000_000 * 0.10) + (2000 / 1_000_000 * 0.40)) * ai_engine.USD_TO_AUD_RATE
        self.assertAlmostEqual(cost_lite, round(expected_lite, 5), places=5)

    def test_worksheet_instructions_and_cost_db(self):
        ws_id = database.save_worksheet(
            title="Year 11 Polynomials Homework Set 1",
            term=1,
            week=2,
            year_level="Year 11 Advanced",
            topic="Polynomials",
            difficulty="Hard",
            questions=[{"item_label": "1", "text": "Find roots", "correct_answer": "x=2"}],
            marking_key={"1": "x=2"},
            set_number=1,
            custom_instructions="Focus heavily on polynomial division and remainder theorem.",
            cost=0.0084,
            model="gemini-3.8-flash",
            tokens=3450
        )
        self.assertGreater(ws_id, 0)

        saved = database.get_worksheet_by_id(ws_id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("custom_instructions"), "Focus heavily on polynomial division and remainder theorem.")
        self.assertEqual(saved.get("cost"), 0.0084)
        self.assertEqual(saved.get("model"), "gemini-3.8-flash")
        self.assertEqual(saved.get("tokens"), 3450)

        # Update instructions
        ok = database.update_worksheet_instructions(ws_id, "Updated: Include cubic factoring.")
        self.assertTrue(ok)
        updated = database.get_worksheet_by_id(ws_id)
        self.assertEqual(updated.get("custom_instructions"), "Updated: Include cubic factoring.")

    def test_theory_and_review_booklet_instructions_db(self):
        # Theory booklet
        tb_content = {
            "title": "Year 10 Linear Relationships",
            "custom_instructions": "Include gradient-intercept and point-gradient form.",
            "meta_cost": 0.0125,
            "model_used": "gemini-3.8-flash",
            "meta_tokens": 5200,
            "concepts": [{"name": "Gradient Formula"}]
        }
        tb_id = database.save_theory_booklet("Year 10 Linear Relationships", 1, 1, "Year 10", "Linear Relationships", tb_content)
        self.assertGreater(tb_id, 0)

        tb_saved = database.get_theory_booklet_by_id(tb_id)
        self.assertEqual(tb_saved["content"]["custom_instructions"], "Include gradient-intercept and point-gradient form.")

        # Update theory booklet instructions
        ok_tb = database.update_theory_booklet_instructions(tb_id, "Updated: Focus on perpendicular lines.")
        self.assertTrue(ok_tb)
        tb_updated = database.get_theory_booklet_by_id(tb_id)
        self.assertEqual(tb_updated["content"]["custom_instructions"], "Updated: Focus on perpendicular lines.")

        # Review booklet
        rb_content = {
            "title": "Year 12 Calculus Review",
            "custom_instructions": "Focus on chain rule pitfalls and optimisation word problems.",
            "meta_cost": 0.0150,
            "model_used": "gemini-3.8-flash",
            "meta_tokens": 6100,
            "concepts": [{"name": "Optimisation"}]
        }
        rb_id = database.save_review_booklet("Year 12 Calculus Review", 2, 4, "Year 12 Advanced", "Calculus", rb_content)
        self.assertGreater(rb_id, 0)

        rb_saved = database.get_review_booklet_by_id(rb_id)
        self.assertEqual(rb_saved["content"]["custom_instructions"], "Focus on chain rule pitfalls and optimisation word problems.")

        # Update review booklet instructions
        ok_rb = database.update_review_booklet_instructions(rb_id, "Updated: Add related rates problems.")
        self.assertTrue(ok_rb)
        rb_updated = database.get_review_booklet_by_id(rb_id)
        self.assertEqual(rb_updated["content"]["custom_instructions"], "Updated: Add related rates problems.")

    def test_cloud_sync_cost_helper(self):
        exam_with_cost = {"cost": 0.0055, "model": "gemini-3.8-flash"}
        cost, model = cloud_sync._get_exam_cost_info(exam_with_cost)
        self.assertEqual(cost, 0.0055)
        self.assertEqual(model, "gemini-3.8-flash")

        # Estimation fallback
        exam_est = {"num_questions": 12}
        est_cost, est_model = cloud_sync._get_exam_cost_info(exam_est)
        self.assertGreater(est_cost, 0.0)
        self.assertEqual(est_model, "gemini-3.8-flash")

    def test_cloud_sync_resilient_missing_column(self):
        class MockStorageFile:
            def upload(self, path, data, opts=None):
                return {"path": path}
            def get_public_url(self, path):
                return f"https://mock.supabase.co/storage/{path}"

        class MockStorage:
            def from_(self, bucket):
                return MockStorageFile()

        class MockTable:
            def __init__(self):
                self.calls = 0
                self.inserted_payloads = []

            def insert(self, payload):
                self.calls += 1
                self.inserted_payloads.append(dict(payload))
                if "answers" in payload:
                    raise Exception("{'message': \"Could not find the 'answers' column of 'saved_exams' in the schema cache\", 'code': 'PGRST204', 'hint': None, 'details': None}")
                return self

            def execute(self):
                return type('MockResponse', (), {'data': [{'id': 1}]})()

        mock_table = MockTable()
        mock_client = type('MockClient', (), {
            'storage': MockStorage(),
            'table': lambda self, name: mock_table
        })()

        orig_get_client = cloud_sync.get_supabase_client
        try:
            cloud_sync.get_supabase_client = lambda: mock_client
            ok, msg = cloud_sync.save_exam_to_cloud(
                subject="Year 10 Maths",
                year_level="Year 10",
                topic="Trigonometry",
                teacher_name="DA Tutor",
                pdf_bytes=b"%PDF-test",
                answers_text="1. A, 2. B",
                cost=0.045
            )
            self.assertTrue(ok)
            self.assertEqual(mock_table.calls, 2)
            self.assertNotIn("answers", mock_table.inserted_payloads[-1])
            self.assertIn("Successfully saved", msg)
        finally:
            cloud_sync.get_supabase_client = orig_get_client

if __name__ == "__main__":
    unittest.main()
