import os
import sys
import unittest
import uuid

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "b-back")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from server import app


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

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


if __name__ == "__main__":
    unittest.main()
