import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.program_generator import (
        EXPERIENCE_TIERS,
        OPPOSITION_MAP,
        Profile,
        _movement_balance,
        filter_exercises,
        generate,
        parse_experience_tier,
    )
except ImportError:
    from services.program_generator import (
        EXPERIENCE_TIERS,
        OPPOSITION_MAP,
        Profile,
        _movement_balance,
        filter_exercises,
        generate,
        parse_experience_tier,
    )


class ExperienceOverrideAndDynamicBiasTests(unittest.TestCase):
    def test_experience_tiers_parsing(self):
        """Verify all 6 tiers parse correctly from ints, strings, and slugs."""
        expected = {
            1: "Rookie",
            2: "Novice",
            3: "Intermediate",
            4: "Upper Intermediate",
            5: "Advanced",
            6: "Veteran",
        }
        for tier_num, tier_name in expected.items():
            self.assertEqual(parse_experience_tier(tier_num), tier_num)
            self.assertEqual(parse_experience_tier(tier_name), tier_num)
            self.assertEqual(parse_experience_tier(tier_name.lower()), tier_num)
            self.assertEqual(EXPERIENCE_TIERS[tier_num], tier_name)

            prof = Profile({"experience": tier_name})
            self.assertEqual(prof.experience, tier_num)
            self.assertEqual(prof.experience_level, tier_name)

        # Legacy backward compatibility
        self.assertEqual(parse_experience_tier("pemula"), 1)
        self.assertEqual(parse_experience_tier("dasar"), 2)
        self.assertEqual(parse_experience_tier("menengah"), 3)
        self.assertEqual(parse_experience_tier("lanjutan"), 5)

    def test_high_bmi_experienced_lifter_exempt_from_conservative_caps(self):
        """Verify high-muscularity lifters with Intermediate+ tier are exempted from conservative default caps."""
        # Muscular athlete: 115 kg, 173 cm, 15% body fat -> Lean mass = 97.75 kg, FFMI ~ 32.7
        experienced_profile = Profile({
            "experience": "Intermediate",
            "weight": 115,
            "height": 173,
            "body_fat_percent": 15,
            "gender": "L",
            "age": 25,
            "facilities": ["1", "2", "3", "4", "5", "6", "7"],
            "physical_condition": "0",
        })
        self.assertTrue(experienced_profile.is_experienced)
        self.assertFalse(experienced_profile.low_impact)
        # Reference weight should be active contractile lean mass (97.8 kg)
        self.assertAlmostEqual(experienced_profile.reference_weight, 97.8, places=1)
        self.assertGreater(experienced_profile.ffmi, 25.0)

        pool, warnings, meta = filter_exercises(experienced_profile)
        pool_ids = {ex["id"] for ex in pool}
        # Barbell Squat (impact 3, axial load) and Deadlift MUST be in pool
        self.assertIn("squat", pool_ids)
        self.assertIn("deadlift", pool_ids)
        self.assertIn("romanian_deadlift", pool_ids)
        self.assertEqual(meta["max_impact"], 3)

    def test_high_central_adiposity_novice_lifter_receives_conservative_safety_caps(self):
        """Verify high-central-adiposity Rookie/Novice receives conservative default safety caps."""
        novice_profile = Profile({
            "experience": "Novice",
            "weight": 115,
            "height": 173,
            "waist_cm": 115,  # WtHR = 0.665 >= 0.60 (central adiposity risk)
            "gender": "L",
            "age": 25,
            "facilities": ["1", "2", "3", "4", "5", "6", "7"],
            "physical_condition": "0",
        })
        self.assertFalse(novice_profile.is_experienced)
        self.assertTrue(novice_profile.low_impact)
        self.assertGreaterEqual(novice_profile.wthr, 0.60)

        pool, warnings, meta = filter_exercises(novice_profile)
        pool_ids = {ex["id"] for ex in pool}
        # Barbell Squat (impact 3) should be filtered out for novice safety under high central adiposity
        self.assertNotIn("squat", pool_ids)
        self.assertNotIn("deadlift", pool_ids)
        self.assertEqual(meta["max_impact"], 2)

    def test_high_bmi_experienced_not_defaulted_to_bodyweight_squats(self):
        """Verify high-BMI experienced lifter receives heavy Barbell Squat with proper load, not bodyweight."""
        result = generate({
            "experience": "Advanced",
            "days": 3,
            "session_minutes": 60,
            "primary_target": 3,  # Strength
            "gender": "L",
            "weight": 110,
            "height": 175,  # BMI ~ 35.9
            "facilities": ["1", "2", "3", "4", "5", "6", "7"],
            "physical_condition": "0",
        })
        self.assertTrue(result["programs"])
        all_exercises = [
            ex
            for prog in result["programs"]
            for sess in prog["sessions"]
            for ex in sess["exercises"]
        ]
        quad_exercises = [ex for ex in all_exercises if ex["muscle_key"] == "quads"]
        quad_names = {ex["name"] for ex in quad_exercises}

        # Must include Barbell Squat (or heavy loaded squat variant) and NOT be defaulted to Bodyweight Squat
        self.assertNotIn("Bodyweight Squat", quad_names)
        self.assertTrue(any("Squat" in name and ex["load_kg"] is not None and ex["load_kg"] >= 40
                            for ex in quad_exercises for name in [ex["name"]]))

    def test_dynamic_muscle_bias_skews_upper_day_for_back_and_arms(self):
        """Verify prioritizing Back & Arms dynamically allocates slots to priority groups and skips/minimizes chest."""
        result = generate({
            "experience": "Intermediate",
            "days": 4,  # Upper / Lower or similar
            "session_minutes": 60,
            "primary_target": 2,
            "gender": "L",
            "weight": 75,
            "height": 175,
            "focus_areas": ["back", "arms"],  # Prioritas: Back, Biceps, Triceps
            "facilities": ["1", "2", "3", "4", "5", "6", "7"],
            "physical_condition": "0",
        })
        self.assertTrue(result["programs"])
        program = result["programs"][0]

        # Find an Upper session
        upper_sessions = [s for s in program["sessions"] if "upper" in s["label"].lower() or "atas" in s["label"].lower()]
        if not upper_sessions:
            upper_sessions = program["sessions"]

        upper = upper_sessions[0]
        muscles_in_session = [ex["muscle_key"] for ex in upper["exercises"]]
        back_count = muscles_in_session.count("back")
        arm_count = muscles_in_session.count("biceps") + muscles_in_session.count("triceps")
        chest_count = muscles_in_session.count("chest")

        # Priority groups (Back & Arms) must dominate the exercise slots
        self.assertGreaterEqual(back_count + arm_count, 4)
        # Non-priority opposition (Chest) must be minimized or skipped entirely
        self.assertLessEqual(chest_count, 1)

    def test_movement_balance_does_not_penalize_priority_patterns(self):
        """Verify _movement_balance accommodates intentional pattern concentration when muscle focus is selected."""
        mock_sessions_priority_pull = [{
            "exercises": [
                {"name": "Bent Over Row", "pattern": "pull", "muscle_key": "back"},
                {"name": "Lat Pulldown", "pattern": "pull", "muscle_key": "back"},
                {"name": "Seated Cable Row", "pattern": "pull", "muscle_key": "back"},
                {"name": "Dumbbell Curl", "pattern": "pull", "muscle_key": "biceps"},
                {"name": "Tricep Pushdown", "pattern": "push", "muscle_key": "triceps"},
                {"name": "Lateral Raise", "pattern": "push", "muscle_key": "shoulders"},
            ]
        }]
        profile_with_back_arms = Profile({
            "experience": 3,
            "focus_areas": ["back", "arms"],
        })
        profile_balanced = Profile({
            "experience": 3,
        })

        # With back & arms focus, 4 pull exercises should receive full balance score (1.0)
        score_focused = _movement_balance(mock_sessions_priority_pull, profile_with_back_arms)
        self.assertEqual(score_focused, 1.0)

        # Without focus, rigid balance penalizes 4 repeated pull exercises
        score_balanced = _movement_balance(mock_sessions_priority_pull, profile_balanced)
        self.assertLess(score_balanced, 1.0)

    def test_ffmi_and_wthr_athletic_metrics_stack(self):
        """Verify modern athletic metrics (FFMI, WtHR, Lean Mass) calculate accurately and BMI is completely absent."""
        profile = Profile({
            "training_age_tier": "advanced",
            "weight": 85,
            "height": 180,
            "body_fat_percent": 12.0,
            "waist_cm": 78.0,
            "gender": "L",
            "age": 28,
        })
        # Fat Mass = 85 * 0.12 = 10.2 kg; Lean Mass = 74.8 kg
        self.assertAlmostEqual(profile.lean_mass, 74.8, places=1)
        self.assertAlmostEqual(profile.fat_mass, 10.2, places=1)
        # FFMI = 74.8 / (1.80^2) = 23.08 kg/m2
        self.assertAlmostEqual(profile.ffmi, 23.1, places=1)
        # WtHR = 78 / 180 = 0.433
        self.assertAlmostEqual(profile.wthr, 0.433, places=2)
        self.assertEqual(profile.training_age_tier, "advanced")
        self.assertEqual(profile.training_age_rank, 5)

        summary = profile.summary()
        self.assertIn("ffmi", summary)
        self.assertIn("norm_ffmi", summary)
        self.assertIn("wthr", summary)
        self.assertIn("lean_mass_kg", summary)
        self.assertIn("training_age_tier", summary)
        # Verify complete removal of BMI from profile summary
        self.assertNotIn("bmi", summary)
        self.assertNotIn("bmi_status", summary)
        self.assertNotIn("bmi_classification", summary)

    def test_training_age_load_scaling(self):
        """Verify Initial Working Load Estimation scales up with training age tiers."""
        rookie = Profile({"training_age_tier": "rookie", "weight": 75, "height": 175, "gender": "L"})
        advanced = Profile({"training_age_tier": "advanced", "weight": 75, "height": 175, "gender": "L"})
        veteran = Profile({"training_age_tier": "veteran", "weight": 75, "height": 175, "gender": "L"})

        self.assertLess(rookie.training_age_rank, advanced.training_age_rank)
        self.assertLess(advanced.training_age_rank, veteran.training_age_rank)

        # Advanced and Veteran have higher axial load capacity and initial working load
        res_rookie = generate({"training_age_tier": "rookie", "days": 3, "session_minutes": 60, "primary_target": 3, "gender": "L", "weight": 75, "height": 175})
        res_adv = generate({"training_age_tier": "advanced", "days": 3, "session_minutes": 60, "primary_target": 3, "gender": "L", "weight": 75, "height": 175})

        rookie_loads = [
            ex["load_kg"]
            for prog in res_rookie["programs"]
            for sess in prog["sessions"]
            for ex in sess["exercises"]
            if ex.get("load_kg") is not None
        ]
        adv_loads = [
            ex["load_kg"]
            for prog in res_adv["programs"]
            for sess in prog["sessions"]
            for ex in sess["exercises"]
            if ex.get("load_kg") is not None
        ]
        self.assertGreater(max(adv_loads), max(rookie_loads))


if __name__ == "__main__":
    unittest.main()

