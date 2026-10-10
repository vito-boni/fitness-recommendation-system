import unittest

from services.program_generator import (
    Profile,
    base_prescription,
    exercise_seconds,
    filter_exercises,
    generate,
    load_catalog,
)


class RestAdjustmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = {exercise["name"]: exercise for exercise in load_catalog()}

    def rest(self, target, exercise_name, advanced_targets=()):
        profile = Profile({
            "primary_target": target,
            "experience": 2,
            "advanced_targets": list(advanced_targets),
        })
        return base_prescription(self.catalog[exercise_name], profile, True)["rest"]

    def test_hypertrophy_rest_increases_by_five_seconds(self):
        self.assertEqual(self.rest(2, "Chest Press"), 95)

    def test_strength_rest_increases_by_ten_seconds(self):
        self.assertEqual(self.rest(3, "Chest Press"), 115)

    def test_strength_goal_uses_strength_rest_for_low_rep_lift(self):
        self.assertEqual(
            self.rest(2, "Bench Press", ["Kekuatan Absolut"]),
            160,
        )

    def test_general_fitness_rest_is_unchanged(self):
        self.assertEqual(self.rest(1, "Chest Press"), 60)

    def test_low_estimated_strength_excludes_barbell_curl_for_beginner(self):
        beginner = Profile({
            "experience": 2,
            "primary_target": 2,
            "gender": "P",
            "weight": 60,
            "height": 165,
            "facilities": ["1", "2", "3", "4"],
        })
        pool, warnings, meta = filter_exercises(beginner)
        exercise_ids = {exercise["id"] for exercise in pool}
        self.assertNotIn("barbell_curl", exercise_ids)
        self.assertIn("dumbbell_curl", exercise_ids)
        self.assertIn("barbell_curl", meta["excluded_load"])
        self.assertTrue(any("estimasi beban awalnya terlalu berat" in warning for warning in warnings))

    def test_experience_increases_load_eligibility(self):
        experienced = Profile({
            "experience": 4,
            "primary_target": 2,
            "gender": "L",
            "weight": 60,
            "height": 165,
            "facilities": ["1", "2", "3", "4"],
        })
        pool, _, meta = filter_exercises(experienced)
        exercise_ids = {exercise["id"] for exercise in pool}
        self.assertIn("barbell_curl", exercise_ids)
        self.assertNotIn("barbell_curl", meta["excluded_load"])

    def test_generated_program_uses_load_suitable_curl_variants(self):
        def generate_for(gender, experience):
            return generate({
                "experience": experience,
                "days": 3,
                "session_minutes": 60,
                "primary_target": 2,
                "gender": gender,
                "weight": 60,
                "height": 165,
                "target_body_parts": ["arms", "chest", "back", "legs"],
                "facilities": ["1", "2", "3", "4", "5", "6", "7"],
                "physical_condition": "0",
            })["programs"][0]

        beginner_woman = generate_for("P", 2)
        woman_curls = [
            exercise
            for session in beginner_woman["sessions"]
            for exercise in session["exercises"]
            if "curl" in exercise["name"].lower()
        ]
        self.assertNotIn("Barbell Curl", [exercise["name"] for exercise in woman_curls])
        self.assertTrue(woman_curls)
        self.assertTrue(all(exercise["load_kg"] < 20 for exercise in woman_curls))

        experienced_man = generate_for("L", 4)
        man_curls = [
            exercise
            for session in experienced_man["sessions"]
            for exercise in session["exercises"]
            if "curl" in exercise["name"].lower()
        ]
        self.assertIn("Barbell Curl", [exercise["name"] for exercise in man_curls])

    def test_extra_rest_is_counted_between_sets(self):
        exercise = self.catalog["Chest Press"]
        original = exercise_seconds(exercise, 3, 10, None, 90)
        adjusted = exercise_seconds(exercise, 3, 10, None, 95)
        self.assertEqual(adjusted - original, 10)

    def test_exercise_count_is_capped_based_on_session_length(self):
        for duration, maximum in ((60, 8), (90, 10), (120, 10)):
            with self.subTest(duration=duration):
                result = generate({
                    "experience": 4,
                    "days": 3,
                    "session_minutes": duration,
                    "primary_target": 3,
                    "target_body_parts": ["chest", "back", "legs", "shoulders", "arms"],
                    "facilities": ["1", "2", "3", "4", "5", "6", "7"],
                    "physical_condition": "0",
                })
                self.assertTrue(result["programs"])
                for program in result["programs"]:
                    for session in program["sessions"]:
                        self.assertLessEqual(len(session["exercises"]), maximum)


if __name__ == "__main__":
    unittest.main()
