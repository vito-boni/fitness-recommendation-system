import os
import sys
import unittest
import uuid

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app

app = create_app({"TESTING": True})


def is_db_available():
    try:
        from app.config.db import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = is_db_available()


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_parse_limitations_endpoint_offline(self):
        parse_res = self.client.post(
            "/api/recommendations/limitations/parse",
            json={"text": "Sakit saat menekuk pergelangan tangan. Sakit bagian betis."},
        )
        self.assertEqual(parse_res.status_code, 200)
        parsed = parse_res.get_json()
        self.assertIn("Sakit Pergelangan Tangan (Area Tubuh Atas)", parsed["labels"])
        self.assertIn("Sakit Betis (Area Tubuh Bawah)", parsed["labels"])

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_register_and_login_flow(self):
        username = f"alice_backend_test_{uuid.uuid4().hex[:8]}"
        password = "secret123"

        register_response = self.client.post(
            "/api/auth/register",
            json={"name": "Alice Backend", "username": username, "password": password},
        )
        self.assertEqual(register_response.status_code, 201, register_response.get_data(as_text=True))

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login_response.status_code, 200, login_response.get_data(as_text=True))

        data = login_response.get_json()
        self.assertEqual(data["user"]["username"], username)

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_profile_update(self):
        username = f"profile_backend_test_{uuid.uuid4().hex[:8]}"
        password = "secret456"

        self.client.post(
            "/api/auth/register",
            json={"name": "Profile Tester", "username": username, "password": password},
        )

        response = self.client.put(
            f"/api/profile/{username}",
            json={
                "age": 28,
                "gender": "P",
                "height_cm": 168,
                "weight_kg": 60,
                "body_fat_percent": 22,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        profile = self.client.get(f"/api/profile/{username}")
        self.assertEqual(profile.status_code, 200, profile.get_data(as_text=True))
        payload = profile.get_json()
        self.assertEqual(payload["username"], username)

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_limitations_parse_and_recommendations_endpoints(self):
        username = f"rec_backend_test_{uuid.uuid4().hex[:8]}"
        password = "secret789"
        self.client.post(
            "/api/auth/register",
            json={"name": "Rec Tester", "username": username, "password": password},
        )

        parse_res = self.client.post(
            "/api/recommendations/limitations/parse",
            json={"text": "Sakit saat menekuk pergelangan tangan. Sakit bagian betis."},
        )
        self.assertEqual(parse_res.status_code, 200, parse_res.get_data(as_text=True))
        parsed = parse_res.get_json()
        self.assertIn("Sakit Pergelangan Tangan (Area Tubuh Atas)", parsed["labels"])
        self.assertIn("Sakit Betis (Area Tubuh Bawah)", parsed["labels"])

        gen_res = self.client.post(
            "/api/recommendations/generate",
            json={
                "gender": "L",
                "age": 24,
                "height": 175,
                "weight": 75,
                "body_fat": 4,
                "cardio_endurance": 1,
                "leg_length_cm": 91,
                "torso_length_cm": 47,
                "days": 3,
                "session_minutes": 60,
                "experience": 2,
                "exercise_complexity": "simple",
                "advanced_targets": ["Bentuk Tubuh Ideal", "Fat Loss"],
                "focus_areas": ["chest", "glutes"],
                "modalities": ["cardio", "mobility"],
                "physical_condition": "1",
                "limitation_story": "Sakit saat menekuk pergelangan tangan.",
            },
        )
        self.assertEqual(gen_res.status_code, 200, gen_res.get_data(as_text=True))
        gen_data = gen_res.get_json()
        self.assertTrue(gen_data["programs"])
        self.assertEqual(gen_data["meta"]["profile"]["recovery_bonus_sec"], 30)

        alt_res = self.client.get("/api/recommendations/alternatives")
        self.assertEqual(alt_res.status_code, 200, alt_res.get_data(as_text=True))
        alt_data = alt_res.get_json()
        self.assertIn("chest", alt_data["alternatives"])

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_profile_update_recalculates_body_composition(self):
        username = f"comp_test_{uuid.uuid4().hex[:8]}"
        password = "secretPassword1"
        self.client.post(
            "/api/auth/register",
            json={"name": "Comp Tester", "username": username, "password": password},
        )

        response = self.client.put(
            f"/api/profile/{username}",
            json={
                "age": 25,
                "gender": "L",
                "height_cm": 180,
                "weight_kg": 80,
                "body_fat_percent": 15,
                "waist_cm": 82,
                "training_age_tier": "intermediate",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data.get("ffmi"))
        self.assertGreater(float(data["ffmi"]), 20.0)
        self.assertAlmostEqual(float(data["wthr"]), 82 / 180, places=2)
        self.assertEqual(data["training_age_tier"], "intermediate")

        prof = self.client.get(f"/api/profile/{username}")
        self.assertEqual(prof.status_code, 200)
        prof_data = prof.get_json()
        self.assertAlmostEqual(float(prof_data["ffmi"]), float(data["ffmi"]), places=1)
        self.assertAlmostEqual(float(prof_data["wthr"]), float(data["wthr"]), places=2)

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_recommendations_strictly_descending_order(self):
        username = f"sort_test_{uuid.uuid4().hex[:8]}"
        password = "secretPassword2"
        self.client.post(
            "/api/auth/register",
            json={"name": "Sort Tester", "username": username, "password": password},
        )

        gen_res = self.client.post(
            "/api/recommendations/generate",
            json={
                "gender": "L",
                "age": 26,
                "height": 175,
                "weight": 72,
                "days": 4,
                "session_minutes": 60,
                "training_age_tier": "intermediate",
                "advanced_targets": ["Bentuk Tubuh Ideal", "Fat Loss"],
                "focus_areas": ["back", "arms"],
            },
        )
        self.assertEqual(gen_res.status_code, 200)
        programs = gen_res.get_json()["programs"]
        self.assertGreaterEqual(len(programs), 2)
        scores = [p["scores"]["final"] for p in programs]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(programs[0]["name"], "Program A")

    @unittest.skipUnless(DB_AVAILABLE, "MySQL database not available")
    def test_permanent_account_deletion_flow(self):
        username = f"delete_me_{uuid.uuid4().hex[:8]}"
        password = "deleteSecret123"
        self.client.post(
            "/api/auth/register",
            json={"name": "Delete Me", "username": username, "password": password},
        )

        self.client.put(
            f"/api/profile/{username}",
            json={"age": 30, "gender": "L", "height_cm": 175, "weight_kg": 75},
        )

        del_res = self.client.delete(f"/api/profile/{username}")
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.get_json()
        self.assertIn("berhasil dihapus", del_data["message"].lower())

        get_res = self.client.get(f"/api/profile/{username}")
        self.assertEqual(get_res.status_code, 401)

        login_res = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login_res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
