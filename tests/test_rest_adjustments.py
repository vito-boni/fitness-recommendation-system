import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.program_generator import (
        FATIGUE_BUFFER,
        MAX_SESSION_EXERCISES,
        Profile,
        SESSION_VOLUME_CAP,
        SETUP_SEC,
        TRANSITION_SEC,
        base_prescription,
        exercise_seconds,
        filter_exercises,
        generate,
        load_catalog,
    )
except ImportError:
    from services.program_generator import (
        FATIGUE_BUFFER,
        MAX_SESSION_EXERCISES,
        Profile,
        SESSION_VOLUME_CAP,
        SETUP_SEC,
        TRANSITION_SEC,
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

    def test_barbell_curl_is_not_in_catalog(self):
        # Sengaja dihapus dari katalog: tidak masuk akal direkomendasikan ke pemula.
        self.assertNotIn("Barbell Curl", self.catalog)

    def test_low_estimated_strength_excludes_ez_bar_curl_for_beginner(self):
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
        self.assertNotIn("ez_bar_curl", exercise_ids)
        self.assertIn("dumbbell_curl", exercise_ids)
        self.assertIn("ez_bar_curl", meta["excluded_load"])
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
        self.assertIn("ez_bar_curl", exercise_ids)
        self.assertNotIn("ez_bar_curl", meta["excluded_load"])

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
            })["programs"]

        def arm_curls(programs):
            return [
                exercise
                for program in programs
                for session in program["sessions"]
                for exercise in session["exercises"]
                if "curl" in exercise["name"].lower() and exercise["muscle_key"] == "biceps"
            ]

        beginner_woman = arm_curls(generate_for("P", 2))
        self.assertTrue(beginner_woman)
        self.assertNotIn("EZ Bar Curl", [exercise["name"] for exercise in beginner_woman])
        self.assertTrue(all(exercise["load_kg"] is None or exercise["load_kg"] < 10 or
                            exercise["equipment"] in ("cable", "machine") for exercise in beginner_woman))

        experienced_man = arm_curls(generate_for("L", 4))
        self.assertTrue(experienced_man)
        self.assertNotIn("Barbell Curl", [exercise["name"] for exercise in experienced_man])
        self.assertIn("EZ Bar Curl", [exercise["name"] for exercise in experienced_man])

    def test_extra_rest_is_counted_between_sets(self):
        exercise = self.catalog["Chest Press"]
        original = exercise_seconds(exercise, 3, 10, None, 90)
        adjusted = exercise_seconds(exercise, 3, 10, None, 95)
        self.assertEqual(adjusted - original, 10)

    def test_estimated_duration_includes_transitions_and_fatigue_buffer(self):
        exercise = self.catalog["Chest Press"]
        sets, reps, rest = 3, 10, 90
        work = sets * reps * exercise["sec_per_rep"]
        expected = round(
            work * (1 + FATIGUE_BUFFER)
            + (sets - 1) * rest
            + SETUP_SEC[exercise["setup"]]
            + TRANSITION_SEC
        )
        self.assertEqual(exercise_seconds(exercise, sets, reps, None, rest), expected)

    def test_session_limits_and_split_labels_match_generated_sessions(self):
        experience = 1
        result = generate({
            "experience": experience,
            "days": 3,
            "session_minutes": 60,
            "primary_target": 1,
            "target_body_parts": ["chest", "back", "shoulders", "legs", "arms", "core"],
            "facilities": ["1", "2", "3", "4", "5", "6", "7"],
            "physical_condition": "0",
        })

        self.assertTrue(result["programs"])
        self.assertEqual(result["meta"]["limits"]["max_exercises_per_session"], MAX_SESSION_EXERCISES)
        for program in result["programs"]:
            self.assertEqual(
                program["split"],
                " / ".join(session["label"] for session in program["sessions"]),
            )
            for session in program["sessions"]:
                self.assertLessEqual(len(session["exercises"]), MAX_SESSION_EXERCISES)
                self.assertLessEqual(
                    session["total_seconds"],
                    program["session_minutes_target"] * 60,
                )
                for effective_sets in session["effective_sets"].values():
                    self.assertLessEqual(
                        effective_sets,
                        SESSION_VOLUME_CAP[experience],
                    )

    def test_exercise_count_is_capped_for_every_session_length(self):
        for duration in (60, 90, 120):
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
                        self.assertLessEqual(len(session["exercises"]), MAX_SESSION_EXERCISES)

    def test_duration_warning_describes_average_not_maximum_session(self):
        result = generate({
            "experience": 3,
            "days": 4,
            "session_minutes": 120,
            "primary_target": 3,
            "target_body_parts": ["chest", "back", "legs", "arms"],
            "facilities": ["1", "2", "3", "4", "5", "6"],
            "physical_condition": "0",
        })

        warning = next(
            warning for warning in result["warnings"]
            if "rata-rata durasi sesi program yang direkomendasikan" in warning
        )
        expected_average = max(
            sum(session["total_minutes"] for session in program["sessions"])
            / len(program["sessions"])
            for program in result["programs"]
        )
        self.assertIn(f"sekitar {int(expected_average)} menit", warning)
        self.assertIn("Beberapa sesi dapat lebih panjang atau lebih pendek", warning)

    def test_anthropometry_differentiates_same_basic_profile(self):
        base = {
            "experience": 3,
            "days": 3,
            "session_minutes": 60,
            "gender": "L",
            "age": 24,
            "height": 175,
            "weight": 75,
            "body_fat": 2,
            "cardio_endurance": 2,
            "exercise_complexity": "balanced",
            "advanced_targets": ["Bentuk Tubuh Ideal"],
            "modalities": ["resistance"],
            "physical_condition": "0",
        }
        short_limbed = generate({
            **base,
            "leg_length_cm": 79,
            "torso_length_cm": 56,
            "arm_length_cm": 68,
            "shoulder_width_cm": 48,
        })
        long_limbed = generate({
            **base,
            "leg_length_cm": 92,
            "torso_length_cm": 46,
            "arm_length_cm": 81,
            "shoulder_width_cm": 37,
        })

        def top_exercises(res):
            return {
                ex["name"]
                for s in res["programs"][0]["sessions"]
                for ex in s["exercises"]
            }

        ex_short = top_exercises(short_limbed)
        ex_long = top_exercises(long_limbed)
        self.assertNotEqual(ex_short, ex_long)
        self.assertTrue(long_limbed["meta"]["profile"]["anthropometry"]["findings"])

    def test_recovery_bonus_increases_rest_for_high_body_fat_and_low_cardio(self):
        normal = Profile({
            "primary_target": 2,
            "experience": 2,
            "body_fat": 2,
            "cardio_endurance": 2,
        })
        high_bf_low_cardio = Profile({
            "primary_target": 2,
            "experience": 2,
            "body_fat": 4,
            "cardio_endurance": 1,
        })
        rest_normal = base_prescription(self.catalog["Chest Press"], normal, True)["rest"]
        rest_adjusted = base_prescription(self.catalog["Chest Press"], high_bf_low_cardio, True)["rest"]
        self.assertEqual(rest_adjusted - rest_normal, 30)

    def test_specific_goals_derive_primary_target_automatically(self):
        res_basic = generate({
            "experience": 2,
            "days": 3,
            "session_minutes": 45,
            "advanced_targets": ["Fat Loss", "Ketahanan Jantung"],
        })
        self.assertEqual(res_basic["meta"]["profile"]["primary_target"], 1)

        res_power = generate({
            "experience": 3,
            "days": 3,
            "session_minutes": 60,
            "advanced_targets": ["Performa Atletik"],
        })
        self.assertEqual(res_power["meta"]["profile"]["primary_target"], 4)

    def test_cardio_and_mobility_addons_sit_outside_resistance_session_duration(self):
        res = generate({
            "experience": 2,
            "days": 3,
            "session_minutes": 45,
            "advanced_targets": ["Bentuk Tubuh Ideal"],
            "modalities": ["resistance", "cardio", "mobility"],
        })
        session = res["programs"][0]["sessions"][0]
        self.assertLessEqual(session["total_minutes"], 45)
        self.assertIsNotNone(session["cardio_block"])
        self.assertIsNotNone(session["mobility_block"])
        self.assertGreater(session["addon_seconds"], 0)
        self.assertEqual(
            session["total_with_addons_minutes"],
            round((session["total_seconds"] + session["addon_seconds"]) / 60, 1),
        )

    def test_sentence_limitation_parser_and_referral_threshold(self):
        single = generate({
            "experience": 2,
            "days": 3,
            "session_minutes": 45,
            "physical_condition": "1",
            "limitation_story": "Sakit saat menekuk pergelangan tangan. Sakit bagian betis.",
        })
        self.assertIsNone(single.get("referral"))
        labels = single["meta"]["limitations"]["labels"]
        self.assertIn("Sakit Pergelangan Tangan (Area Tubuh Atas)", labels)
        self.assertIn("Sakit Betis (Area Tubuh Bawah)", labels)

        severe_multi = generate({
            "experience": 2,
            "days": 3,
            "session_minutes": 45,
            "physical_condition": "1",
            "limitation_story": (
                "Sakit parah di bahu kanan saat diangkat. "
                "Nyeri tajam pada punggung bawah. "
                "Cedera lutut kiri bengkak."
            ),
        })
        self.assertTrue(severe_multi["referral"]["required"])
        self.assertEqual(severe_multi["programs"], [])
        self.assertIn("Personal Trainer", severe_multi["referral"]["message"])


if __name__ == "__main__":
    unittest.main()

