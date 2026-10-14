#!/usr/bin/env python3
"""
================================================================================
TEST SCRIPT: Bije's Gym Personalized Fitness Recommendation Pipeline Validation
Methodology: Content-Based Filtering & Weighted Cosine Similarity (2-Stage Architecture)
================================================================================
This script is a self-contained, completely runnable test and validation suite
that executes and verifies the full recommendation pipeline for:
"Web-Based Personalized Fitness Recommendation System Using Content-Based Filtering
and Weighted Cosine Similarity (Bije's Gym)"

It covers:
1. Candidate Repository (10 items: beginner to advanced, low impact to high intensity,
   hypertrophy, fat loss, cardiac-safe, joint-safe) and 2-Stage Pipeline Definition.
2. Test 1: Deterministic Safety Pre-Filtering Execution (PAR-Q+ cardiac/joint clearance).
3. Test 2: Mathematical Boundary & Edge Case Suite (zero-vectors, missing attributes,
   extreme outliers, deterministic tie-breaking logic).
4. Test 3: Attribute Weight Sensitivity Experiment (Equal, Goal-Dominant, Body-Comp-Dominant).
5. Test 4: Programmatic Precision@K Calculation against Expert Trainer Ground Truth.

Zero external dependencies (pure Python standard library).
================================================================================
"""

import math
import random
import time
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ==============================================================================
# SECTION 1: PIPELINE DEFINITION & MOCK REPOSITORY
# ==============================================================================

GOAL_CATEGORIES = ["Hypertrophy", "Fat Loss", "Strength", "General Health"]


@dataclass(frozen=True)
class WorkoutProgram:
    """Mock repository model representing candidate workout programs at Bije's Gym."""
    id: str
    name: str
    category: str
    experience_level: str          # 'Beginner', 'Intermediate', 'Advanced'
    intensity: str                 # 'Low', 'Moderate', 'High'
    impact_level: str              # 'Low', 'Moderate', 'High'
    is_cardiac_safe: bool          # PAR-Q+ cardiac clearance
    is_joint_safe: bool            # PAR-Q+ musculoskeletal clearance
    has_heavy_compounds: bool      # Axial compound lifts (Valsalva hemodynamic risk)
    target_ffmi: float             # Normalized FFMI affinity [0.0 - 1.0]
    target_bf: float               # Normalized Body Fat % affinity [0.0 - 1.0]
    target_wthr: float             # Normalized WHtR affinity [0.0 - 1.0]
    target_frequency: float        # Normalized weekly session target [0.0 - 1.0]
    primary_goal: str              # Dominant training objective
    goal_distribution: Dict[str, float]  # Continuous affinity across goal spectrum


@dataclass
class MemberPersona:
    """Member profile input representation capturing physiological metrics and safety flags."""
    user_id: str
    name: str
    age: int
    gender: str                    # 'M' or 'F'
    height_cm: float
    weight_kg: float
    waist_cm: Optional[float]
    body_fat_pct: Optional[float]
    workout_frequency: int         # Days per week (1 - 7)
    primary_goal: str              # 'Hypertrophy', 'Fat Loss', 'Strength', 'General Health'
    parq_cardiac: bool = False     # PAR-Q+ positive cardiac flag
    parq_joint: bool = False       # PAR-Q+ positive musculoskeletal joint flag
    experience_level: str = "Beginner"


def get_mock_program_repository() -> List[WorkoutProgram]:
    """
    Defines 10 diverse candidate programs:
    - Beginner to Advanced experience levels
    - Low-impact to High-intensity workouts
    - Hypertrophy, Fat Loss, Powerlifting Strength, and Cardiac/Joint-Safe Rehab
    """
    return [
        WorkoutProgram(
            id="PROG-01",
            name="Cardiac-Safe Low-Impact Mobility & Cardio",
            category="Cardiac/Rehab",
            experience_level="Beginner",
            intensity="Low",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.20,
            target_bf=0.65,
            target_wthr=0.60,
            target_frequency=0.33,  # ~3 days/week
            primary_goal="General Health",
            goal_distribution={"General Health": 0.85, "Fat Loss": 0.15, "Hypertrophy": 0.0, "Strength": 0.0},
        ),
        WorkoutProgram(
            id="PROG-02",
            name="Rehab Joint-Friendly Machine Circuit",
            category="Cardiac/Rehab",
            experience_level="Beginner",
            intensity="Low",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.25,
            target_bf=0.50,
            target_wthr=0.50,
            target_frequency=0.33,  # ~3 days/week
            primary_goal="General Health",
            goal_distribution={"General Health": 0.80, "Hypertrophy": 0.10, "Fat Loss": 0.10, "Strength": 0.0},
        ),
        WorkoutProgram(
            id="PROG-03",
            name="Foundational Full-Body Dumbbell Routine",
            category="Hypertrophy",
            experience_level="Beginner",
            intensity="Moderate",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.40,
            target_bf=0.45,
            target_wthr=0.45,
            target_frequency=0.33,  # ~3 days/week
            primary_goal="Hypertrophy",
            goal_distribution={"Hypertrophy": 0.50, "General Health": 0.30, "Strength": 0.20, "Fat Loss": 0.0},
        ),
        WorkoutProgram(
            id="PROG-04",
            name="Fat Loss HIIT & Metabolic Circuit",
            category="Fat Loss",
            experience_level="Intermediate",
            intensity="High",
            impact_level="High",
            is_cardiac_safe=False,
            is_joint_safe=False,
            has_heavy_compounds=False,
            target_ffmi=0.35,
            target_bf=0.80,
            target_wthr=0.70,
            target_frequency=0.50,  # ~4 days/week
            primary_goal="Fat Loss",
            goal_distribution={"Fat Loss": 0.85, "General Health": 0.10, "Hypertrophy": 0.05, "Strength": 0.0},
        ),
        WorkoutProgram(
            id="PROG-05",
            name="Hypertrophy Push-Pull-Legs (PPL)",
            category="Hypertrophy",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Moderate",
            is_cardiac_safe=False,
            is_joint_safe=True,
            has_heavy_compounds=True,
            target_ffmi=0.75,
            target_bf=0.25,
            target_wthr=0.35,
            target_frequency=0.83,  # ~6 days/week
            primary_goal="Hypertrophy",
            goal_distribution={"Hypertrophy": 0.85, "Strength": 0.15, "Fat Loss": 0.0, "General Health": 0.0},
        ),
        WorkoutProgram(
            id="PROG-06",
            name="Upper / Lower Strength & Size",
            category="Strength",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Moderate",
            is_cardiac_safe=False,
            is_joint_safe=True,
            has_heavy_compounds=True,
            target_ffmi=0.70,
            target_bf=0.30,
            target_wthr=0.38,
            target_frequency=0.67,  # ~5 days/week
            primary_goal="Strength",
            goal_distribution={"Strength": 0.55, "Hypertrophy": 0.45, "Fat Loss": 0.0, "General Health": 0.0},
        ),
        WorkoutProgram(
            id="PROG-07",
            name="Heavy Duty Advanced Powerlifting",
            category="Strength",
            experience_level="Advanced",
            intensity="High",
            impact_level="High",
            is_cardiac_safe=False,
            is_joint_safe=False,
            has_heavy_compounds=True,
            target_ffmi=0.90,
            target_bf=0.20,
            target_wthr=0.30,
            target_frequency=0.67,  # ~5 days/week
            primary_goal="Strength",
            goal_distribution={"Strength": 0.85, "Hypertrophy": 0.15, "Fat Loss": 0.0, "General Health": 0.0},
        ),
        WorkoutProgram(
            id="PROG-08",
            name="Glute & Core Focused Body Sculpt",
            category="Hypertrophy",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.50,
            target_bf=0.40,
            target_wthr=0.40,
            target_frequency=0.50,  # ~4 days/week
            primary_goal="Hypertrophy",
            goal_distribution={"Hypertrophy": 0.65, "Fat Loss": 0.25, "General Health": 0.10, "Strength": 0.0},
        ),
        WorkoutProgram(
            id="PROG-09",
            name="High-Density Conditioning & Tabata",
            category="Fat Loss",
            experience_level="Advanced",
            intensity="High",
            impact_level="High",
            is_cardiac_safe=False,
            is_joint_safe=False,
            has_heavy_compounds=False,
            target_ffmi=0.50,
            target_bf=0.75,
            target_wthr=0.65,
            target_frequency=0.67,  # ~5 days/week
            primary_goal="Fat Loss",
            goal_distribution={"Fat Loss": 0.80, "General Health": 0.15, "Strength": 0.05, "Hypertrophy": 0.0},
        ),
        WorkoutProgram(
            id="PROG-10",
            name="Bodyweight Calisthenics & Core Control",
            category="General Health",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.55,
            target_bf=0.30,
            target_wthr=0.35,
            target_frequency=0.50,  # ~4 days/week
            primary_goal="General Health",
            goal_distribution={"General Health": 0.50, "Hypertrophy": 0.30, "Strength": 0.20, "Fat Loss": 0.0},
        ),
    ]


class BijeRecommendationEngine:
    """
    2-Stage Recommendation Engine Implementation:
      Stage 1: Deterministic Safety Filter (PAR-Q+ Contraindication Elimination)
      Stage 2: Weighted Cosine Similarity (Normalized Physical + Goal Feature Vectors)
    """

    @staticmethod
    def extract_user_feature_vector(persona: MemberPersona) -> Tuple[List[float], float]:
        """
        Extracts and normalizes user profile into a coordinate vector:
        [ffmi_norm, bf_norm, wthr_norm, freq_norm, g_hyp, g_fat, g_str, g_gen]
        Handles missing optional attributes gracefully via neutral domain imputation (0.50).
        """
        h_m = persona.height_cm / 100.0 if persona.height_cm > 0 else 1.70

        # 1. FFMI (Fat-Free Mass Index) Normalization: range [14.0, 28.0]
        if persona.body_fat_pct is not None and persona.weight_kg > 0 and h_m > 0:
            lean_mass_kg = persona.weight_kg * (1.0 - (persona.body_fat_pct / 100.0))
            raw_ffmi = lean_mass_kg / (h_m ** 2)
            ffmi_norm = max(0.0, min(1.0, (raw_ffmi - 14.0) / 14.0))
            bf_norm = max(0.0, min(1.0, (persona.body_fat_pct - 5.0) / 40.0))
        else:
            ffmi_norm = 0.50
            bf_norm = 0.50

        # 2. WHtR (Waist-to-Height Ratio) Normalization: range [0.35, 0.75]
        if persona.waist_cm is not None and persona.height_cm > 0:
            raw_wthr = persona.waist_cm / persona.height_cm
            wthr_norm = max(0.0, min(1.0, (raw_wthr - 0.35) / 0.40))
        else:
            wthr_norm = 0.50

        # 3. Workout Frequency Normalization: range [1, 7] days -> [0.0, 1.0]
        freq_norm = max(0.0, min(1.0, (persona.workout_frequency - 1) / 6.0))

        # 4. Primary Goal One-Hot Vector (Hypertrophy, Fat Loss, Strength, General Health)
        goal_vec = [1.0 if g == persona.primary_goal else 0.0 for g in GOAL_CATEGORIES]

        vector = [ffmi_norm, bf_norm, wthr_norm, freq_norm] + goal_vec
        return vector, freq_norm

    @staticmethod
    def extract_program_feature_vector(program: WorkoutProgram) -> List[float]:
        """Maps program parameters to the normalized feature coordinate space."""
        goal_vec = [program.goal_distribution.get(g, 0.0) for g in GOAL_CATEGORIES]
        return [
            program.target_ffmi,
            program.target_bf,
            program.target_wthr,
            program.target_frequency,
        ] + goal_vec

    @staticmethod
    def stage_1_safety_filter(
        catalog: List[WorkoutProgram],
        persona: MemberPersona
    ) -> Tuple[List[WorkoutProgram], List[Tuple[WorkoutProgram, str]]]:
        """
        Stage 1: Deterministic Safety Filter.
        Eliminates contraindicated programs if PAR-Q+ cardiac/joint flags are positive.
        """
        safe_programs: List[WorkoutProgram] = []
        rejected_programs: List[Tuple[WorkoutProgram, str]] = []

        for p in catalog:
            violations = []

            # PAR-Q+ Cardiac Contraindication Screening
            if persona.parq_cardiac:
                if not p.is_cardiac_safe:
                    violations.append("Violates PAR-Q+ cardiac clearance (is_cardiac_safe=False)")
                if p.intensity == "High":
                    violations.append("High cardiovascular strain (>85% HRmax)")
                if p.has_heavy_compounds:
                    violations.append("Heavy axial compound lifts (Valsalva hemodynamic risk)")

            # PAR-Q+ Musculoskeletal / Joint Screening
            if persona.parq_joint:
                if not p.is_joint_safe:
                    violations.append("Violates PAR-Q+ joint clearance (is_joint_safe=False)")
                if p.impact_level == "High":
                    violations.append("High musculoskeletal impact / ballistic plyometrics")

            if violations:
                rejected_programs.append((p, "; ".join(violations)))
            else:
                safe_programs.append(p)

        return safe_programs, rejected_programs

    @staticmethod
    def stage_2_weighted_cosine_similarity(
        u_vec: List[float],
        v_vec: List[float],
        weights: Dict[str, float]
    ) -> float:
        """
        Stage 2: Weighted Cosine Similarity.
        Formula:
            Sim(u, v; w) = (sum w_i * u_i * v_i) / (sqrt(sum w_i * u_i^2) * sqrt(sum w_i * v_i^2))
        Safely returns 0.0 on zero-vectors to prevent ZeroDivisionError.
        """
        # Map 5 attribute weights across the 8-dimensional coordinate space
        w_expanded = [
            weights["ffmi"],
            weights["bf"],
            weights["wthr"],
            weights["freq"],
            weights["goal"],
            weights["goal"],
            weights["goal"],
            weights["goal"],
        ]

        numerator = sum(w * u * v for w, u, v in zip(w_expanded, u_vec, v_vec))
        norm_u_sq = sum(w * (u ** 2) for w, u in zip(w_expanded, u_vec))
        norm_v_sq = sum(w * (v ** 2) for w, v in zip(w_expanded, v_vec))

        if norm_u_sq <= 0.0 or norm_v_sq <= 0.0:
            return 0.0

        similarity = numerator / (math.sqrt(norm_u_sq) * math.sqrt(norm_v_sq))
        return max(0.0, min(1.0, similarity))

    @classmethod
    def recommend(
        cls,
        catalog: List[WorkoutProgram],
        persona: MemberPersona,
        weights: Dict[str, float],
        top_k: int = 3
    ) -> Tuple[List[Tuple[WorkoutProgram, float]], List[WorkoutProgram], List[Tuple[WorkoutProgram, str]]]:
        """
        Executes the full 2-stage recommendation pipeline and produces ranked Top-K items.
        Deterministic Cascade Tie-Breaking:
          1. Similarity score (descending, rounded to 4 decimal places)
          2. Frequency Delta: abs(program.target_frequency - user_freq_norm) (ascending)
          3. Program ID: alphabetical ascending
        """
        safe_candidates, rejected = cls.stage_1_safety_filter(catalog, persona)
        u_vec, user_freq_norm = cls.extract_user_feature_vector(persona)

        scored_candidates: List[Tuple[WorkoutProgram, float]] = []
        for p in safe_candidates:
            v_vec = cls.extract_program_feature_vector(p)
            score = cls.stage_2_weighted_cosine_similarity(u_vec, v_vec, weights)
            scored_candidates.append((p, score))

        scored_candidates.sort(
            key=lambda item: (
                -round(item[1], 4),
                abs(item[0].target_frequency - user_freq_norm),
                item[0].id
            )
        )

        return scored_candidates[:top_k], safe_candidates, rejected


# ==============================================================================
# SECTION 2: UNITTEST TEST CASES
# ==============================================================================

class TestBijeGymRecommendationPipeline(unittest.TestCase):
    """Automated test cases verifying all 5 aspects of the recommendation pipeline."""

    def setUp(self):
        self.catalog = get_mock_program_repository()
        self.equal_weights = {
            "ffmi": 0.20,
            "bf": 0.20,
            "wthr": 0.20,
            "freq": 0.20,
            "goal": 0.20,
        }

    # --------------------------------------------------------------------------
    # PIPELINE DEFINITION & MOCK REPOSITORY INTEGRITY
    # --------------------------------------------------------------------------
    def test_01_pipeline_definition_and_mock_repository(self):
        """Verifies candidate program repository bounds, diversity, and feature vector integrity."""
        print("\n" + "=" * 80)
        print("TEST 0: PIPELINE DEFINITION & MOCK REPOSITORY INTEGRITY")
        print("=" * 80)

        # 1. Exactly 10 items
        self.assertEqual(len(self.catalog), 10, "Repository must contain exactly 10 programs.")

        # 2. Diversity coverage
        levels = {p.experience_level for p in self.catalog}
        intensities = {p.intensity for p in self.catalog}
        goals = {p.primary_goal for p in self.catalog}
        self.assertTrue({"Beginner", "Intermediate", "Advanced"}.issubset(levels))
        self.assertTrue({"Low", "Moderate", "High"}.issubset(intensities))
        self.assertTrue({"Hypertrophy", "Fat Loss", "Strength", "General Health"}.issubset(goals))

        # 3. Cardiac and compound presence
        self.assertTrue(any(p.is_cardiac_safe for p in self.catalog))
        self.assertTrue(any(not p.is_cardiac_safe for p in self.catalog))
        self.assertTrue(any(p.has_heavy_compounds for p in self.catalog))

        # 4. Feature vector bounds in [0.0, 1.0]
        for p in self.catalog:
            vec = BijeRecommendationEngine.extract_program_feature_vector(p)
            self.assertEqual(len(vec), 8, f"Program {p.id} vector must be 8-dimensional.")
            for dim_idx, val in enumerate(vec):
                self.assertTrue(
                    0.0 <= val <= 1.0,
                    f"Program {p.id} feature dim {dim_idx} out of range [0.0, 1.0]: {val}"
                )
            self.assertAlmostEqual(
                sum(p.goal_distribution.values()), 1.0, places=2,
                msg=f"Program {p.id} goal distribution must sum to 1.0"
            )

        # Print catalog table
        print(f"{'ID':<8} | {'Program Name':<42} | {'Exp':<12} | {'Intensity':<9} | {'Cardiac':<7} | {'Compounds'}")
        print("-" * 96)
        for p in self.catalog:
            c_safe = "Safe" if p.is_cardiac_safe else "Alert"
            comp = "Yes" if p.has_heavy_compounds else "No"
            print(f"{p.id:<8} | {p.name:<42} | {p.experience_level:<12} | {p.intensity:<9} | {c_safe:<7} | {comp}")
        print("-" * 96)
        print(">>> [PASS] Mock repository and 2-stage pipeline definitions successfully verified.\n")

    # --------------------------------------------------------------------------
    # TEST 1: SAFETY PRE-FILTERING EXECUTION
    # --------------------------------------------------------------------------
    def test_02_safety_prefiltering_execution(self):
        """Executes Stage 1 safety filter on a persona with positive cardiac flags and asserts elimination."""
        print("\n" + "=" * 80)
        print("TEST 1: SAFETY PRE-FILTERING EXECUTION (CARDIAC CONTRAINDICATION PROTOCOL)")
        print("=" * 80)

        # Test persona with positive cardiac flags
        cardiac_persona = MemberPersona(
            user_id="USER-CARDIO-01",
            name="Pak Hendro Wijaya (Cardiovascular Risk Persona)",
            age=54,
            gender="M",
            height_cm=168.0,
            weight_kg=78.0,
            waist_cm=92.0,
            body_fat_pct=28.0,
            workout_frequency=3,
            primary_goal="General Health",
            parq_cardiac=True,      # POSITIVE CARDIAC FLAG
            parq_joint=False,
            experience_level="Beginner",
        )

        print("[1] Verified Input Persona:")
        print(f"    Name                 : {cardiac_persona.name}")
        print(f"    Age / Gender         : {cardiac_persona.age} y.o. / {cardiac_persona.gender}")
        print(f"    PAR-Q+ Cardiac Flag  : POSITIVE [Alert: Angina / Hypertension History]")
        print(f"    PAR-Q+ Joint Flag    : NEGATIVE [Musculoskeletal Clearance Clear]")
        print(f"    Primary Training Goal: {cardiac_persona.primary_goal}")
        print(f"    Weekly Availability  : {cardiac_persona.workout_frequency} days/week")

        top_recs, safe_progs, rejected = BijeRecommendationEngine.recommend(
            self.catalog, cardiac_persona, self.equal_weights, top_k=3
        )

        print(f"\n[2] Filtered Candidates ({len(rejected)} Programs Eliminated Prior to Similarity Computation):")
        for p, reason in rejected:
            print(f"    [CONTRAINDICATED] {p.id:<8} {p.name:<38} -> {reason}")

        print(f"\n[3] Passed Safe Candidates ({len(safe_progs)} Programs Eligible for Similarity Scoring):")
        for p in safe_progs:
            print(f"    [CLEARED]        {p.id:<8} {p.name:<38} | Intensity: {p.intensity:<8} | Compounds: {p.has_heavy_compounds}")

        # Assertions: All heavy compound and high-intensity programs are strictly stripped out
        rejected_ids = {p.id for p, _ in rejected}
        safe_ids = {p.id for p in safe_progs}

        self.assertIn("PROG-04", rejected_ids, "PROG-04 (High intensity HIIT) must be filtered out.")
        self.assertIn("PROG-05", rejected_ids, "PROG-05 (Heavy compound PPL) must be filtered out.")
        self.assertIn("PROG-06", rejected_ids, "PROG-06 (Heavy compound Upper/Lower) must be filtered out.")
        self.assertIn("PROG-07", rejected_ids, "PROG-07 (High intensity powerlifting) must be filtered out.")
        self.assertIn("PROG-09", rejected_ids, "PROG-09 (High intensity Tabata) must be filtered out.")

        for p in safe_progs:
            self.assertTrue(p.is_cardiac_safe, f"{p.id} failed: is_cardiac_safe must be True.")
            self.assertNotEqual(p.intensity, "High", f"{p.id} failed: intensity cannot be High.")
            self.assertFalse(p.has_heavy_compounds, f"{p.id} failed: heavy compounds must be False.")

        print(f"\n[4] Final Safe Output (Top-3 Recommendations via Weighted Cosine):")
        for rank, (p, sim) in enumerate(top_recs, start=1):
            print(f"    Rank #{rank}: {p.id} - {p.name:<40} | Similarity Score: {sim:.4f}")

        self.assertEqual(len(top_recs), 3)
        self.assertTrue(all(p.id in safe_ids for p, _ in top_recs))
        print(">>> [PASS] Safety pre-filtering verified: 100% of contraindicated programs eliminated.\n")

    # --------------------------------------------------------------------------
    # TEST 2: MATHEMATICAL BOUNDARY & EDGE CASE SUITE
    # --------------------------------------------------------------------------
    def test_03_mathematical_boundary_and_edge_case_suite(self):
        """Verifies zero-vectors, missing optional attributes, extreme outliers, and deterministic tie-breaking."""
        print("\n" + "=" * 80)
        print("TEST 2: MATHEMATICAL BOUNDARY & EDGE CASE SUITE")
        print("=" * 80)

        # 1. Zero-Vector Test (Avoid Division-by-Zero)
        zero_vec_u = [0.0] * 8
        zero_vec_v = [0.0] * 8
        sim_zero = BijeRecommendationEngine.stage_2_weighted_cosine_similarity(
            zero_vec_u, zero_vec_v, self.equal_weights
        )
        self.assertEqual(sim_zero, 0.0, "Cosine of zero-vectors must return 0.0.")
        self.assertFalse(math.isnan(sim_zero), "Zero-vector computation must not return NaN.")
        print("[1] Zero-Vector Division-by-Zero Check: PASSED (Returned 0.0000, ZeroDivisionError Safely Caught)")

        # 2. Missing Optional Attributes (Imputation Integrity)
        missing_persona = MemberPersona(
            user_id="USER-MISSING",
            name="Incomplete Data Persona",
            age=30,
            gender="L",
            height_cm=170.0,
            weight_kg=70.0,
            waist_cm=None,         # Missing WHtR
            body_fat_pct=None,     # Missing Body Fat %
            workout_frequency=3,
            primary_goal="General Health",
        )
        u_vec, _ = BijeRecommendationEngine.extract_user_feature_vector(missing_persona)
        self.assertFalse(any(math.isnan(x) for x in u_vec), "Extracted vector must not contain NaN.")
        self.assertEqual(u_vec[1], 0.50, "Missing BF% must default to neutral 0.50.")
        self.assertEqual(u_vec[2], 0.50, "Missing waist/WHtR must default to neutral 0.50.")

        top_recs_missing, _, _ = BijeRecommendationEngine.recommend(
            self.catalog, missing_persona, self.equal_weights
        )
        self.assertEqual(len(top_recs_missing), 3)
        self.assertTrue(all(0.0 <= score <= 1.0 for _, score in top_recs_missing))
        print("[2] Missing Attributes Imputation Check: PASSED (Neutral Defaults 0.50 Assigned Without Error)")

        # 3. Extreme Outliers Test (High FFMI + Low BF% vs. Low FFMI + High BF%)
        athletic_outlier = MemberPersona(
            user_id="OUTLIER-ATHLETIC",
            name="Competitive Natural Bodybuilder",
            age=27,
            gender="M",
            height_cm=180.0,
            weight_kg=105.0,
            waist_cm=74.0,
            body_fat_pct=4.0,       # Extremely low body fat
            workout_frequency=6,
            primary_goal="Hypertrophy",
        )
        vec_athletic, _ = BijeRecommendationEngine.extract_user_feature_vector(athletic_outlier)
        self.assertAlmostEqual(vec_athletic[0], 1.0, places=2, msg="FFMI >= 28.0 must be clipped to 1.0")
        self.assertAlmostEqual(vec_athletic[1], 0.0, places=2, msg="BF% <= 5.0% must be clipped to 0.0")

        obese_outlier = MemberPersona(
            user_id="OUTLIER-OBESE",
            name="Severe Obesity Profile",
            age=50,
            gender="F",
            height_cm=152.0,
            weight_kg=120.0,
            waist_cm=130.0,
            body_fat_pct=56.0,      # Extremely high body fat
            workout_frequency=2,
            primary_goal="Fat Loss",
        )
        vec_obese, _ = BijeRecommendationEngine.extract_user_feature_vector(obese_outlier)
        self.assertAlmostEqual(vec_obese[1], 1.0, places=2, msg="BF% >= 45.0% must be clipped to 1.0")
        self.assertAlmostEqual(vec_obese[2], 1.0, places=2, msg="WHtR >= 0.75 must be clipped to 1.0")
        print("[3] Extreme Outliers Boundary Check: PASSED (Clipped to [0.0, 1.0] Without Overflow or Underflow)")

        # 4. Deterministic Tie-Breaking Logic
        # Construct two identical program clones with exact identical similarity scores
        clone_a = WorkoutProgram(
            id="PROG-TIE-A",
            name="Deterministic Tie Candidate A",
            category="Hypertrophy",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.50,
            target_bf=0.40,
            target_wthr=0.40,
            target_frequency=0.50,
            primary_goal="Hypertrophy",
            goal_distribution={"Hypertrophy": 1.0, "Fat Loss": 0.0, "Strength": 0.0, "General Health": 0.0},
        )
        clone_b = WorkoutProgram(
            id="PROG-TIE-B",
            name="Deterministic Tie Candidate B",
            category="Hypertrophy",
            experience_level="Intermediate",
            intensity="Moderate",
            impact_level="Low",
            is_cardiac_safe=True,
            is_joint_safe=True,
            has_heavy_compounds=False,
            target_ffmi=0.50,
            target_bf=0.40,
            target_wthr=0.40,
            target_frequency=0.50,
            primary_goal="Hypertrophy",
            goal_distribution={"Hypertrophy": 1.0, "Fat Loss": 0.0, "Strength": 0.0, "General Health": 0.0},
        )

        tie_persona = MemberPersona(
            user_id="TIE-TESTER",
            name="Tie Breaker Tester",
            age=25,
            gender="M",
            height_cm=175.0,
            weight_kg=75.0,
            waist_cm=80.0,
            body_fat_pct=15.0,
            workout_frequency=4,
            primary_goal="Hypertrophy",
        )

        # Shuffle input order 30 times and verify identical ranking order every single time
        tie_candidate_pool = [clone_b, clone_a]
        shuffled_outcomes = []
        for seed_idx in range(30):
            rng = random.Random(seed_idx)
            pool_shuffled = list(tie_candidate_pool)
            rng.shuffle(pool_shuffled)
            recs, _, _ = BijeRecommendationEngine.recommend(
                pool_shuffled, tie_persona, self.equal_weights, top_k=2
            )
            shuffled_outcomes.append(tuple(p.id for p, _ in recs))

        # Must always produce PROG-TIE-A before PROG-TIE-B
        deterministic_order = ("PROG-TIE-A", "PROG-TIE-B")
        self.assertTrue(
            all(outcome == deterministic_order for outcome in shuffled_outcomes),
            "Deterministic tie-breaking failed: Ordering varied across randomized permutations!"
        )
        print(f"[4] Deterministic Tie-Breaking Check: PASSED (30/30 Shuffles Invariant -> PROG-TIE-A < PROG-TIE-B)")
        print(">>> [PASS] All mathematical boundary and edge cases executed successfully.\n")

    # --------------------------------------------------------------------------
    # TEST 3: ATTRIBUTE WEIGHT SENSITIVITY EXPERIMENT
    # --------------------------------------------------------------------------
    def test_04_attribute_weight_sensitivity_experiment(self):
        """Executes 3 distinct weight configurations on 3 benchmark personas and prints ASCII rank shift table."""
        print("\n" + "=" * 80)
        print("TEST 3: ATTRIBUTE WEIGHT SENSITIVITY EXPERIMENT (RANK SHIFT ANALYSIS)")
        print("=" * 80)

        benchmarks = [
            MemberPersona(
                user_id="BM-1",
                name="Siti (Hypertrophy Bodybuilder)",
                age=26,
                gender="F",
                height_cm=168.0,
                weight_kg=62.0,
                waist_cm=70.0,
                body_fat_pct=13.0,
                workout_frequency=5,
                primary_goal="Hypertrophy",
            ),
            MemberPersona(
                user_id="BM-2",
                name="Agus (Weight Loss & Metabolic)",
                age=34,
                gender="M",
                height_cm=175.0,
                weight_kg=95.0,
                waist_cm=108.0,
                body_fat_pct=34.0,
                workout_frequency=3,
                primary_goal="Fat Loss",
            ),
            MemberPersona(
                user_id="BM-3",
                name="Dewi (Healthy Lifestyle & Stamina)",
                age=29,
                gender="F",
                height_cm=160.0,
                weight_kg=56.0,
                waist_cm=75.0,
                body_fat_pct=22.0,
                workout_frequency=3,
                primary_goal="General Health",
            ),
        ]

        weight_profiles = {
            "Equal": {
                "ffmi": 0.20, "bf": 0.20, "wthr": 0.20, "freq": 0.20, "goal": 0.20
            },
            "Goal-Dominant": {
                "ffmi": 0.10, "bf": 0.10, "wthr": 0.10, "freq": 0.10, "goal": 0.60
            },
            "Body-Comp-Dominant": {
                "ffmi": 0.30, "bf": 0.30, "wthr": 0.25, "freq": 0.075, "goal": 0.075
            },
        }

        print("+" + "-" * 118 + "+")
        print(f"| {'ATTRIBUTE WEIGHT SENSITIVITY MATRIX (TOP-3 RECOMMENDATIONS & RANK SHIFTS)':<116} |")
        print("+" + "-" * 32 + "+" + "-" * 27 + "+" + "-" * 27 + "+" + "-" * 28 + "+")
        print(f"| {'Benchmark Persona':<30} | {'Equal (20% All)':<25} | {'Goal-Dominant (60% Goal)':<25} | {'BodyComp-Dominant (85% BC)':<26} |")
        print("+" + "-" * 32 + "+" + "-" * 27 + "+" + "-" * 27 + "+" + "-" * 28 + "+")

        rank_shift_observed = False

        for b in benchmarks:
            rec_eq, _, _ = BijeRecommendationEngine.recommend(self.catalog, b, weight_profiles["Equal"], top_k=3)
            rec_gd, _, _ = BijeRecommendationEngine.recommend(self.catalog, b, weight_profiles["Goal-Dominant"], top_k=3)
            rec_bc, _, _ = BijeRecommendationEngine.recommend(self.catalog, b, weight_profiles["Body-Comp-Dominant"], top_k=3)

            ids_eq = [p.id for p, _ in rec_eq]
            ids_gd = [p.id for p, _ in rec_gd]
            ids_bc = [p.id for p, _ in rec_bc]

            if ids_eq != ids_gd or ids_eq != ids_bc or ids_gd != ids_bc:
                rank_shift_observed = True

            col1_lines = [f"{rank}. {p.id} ({sim:.3f})" for rank, (p, sim) in enumerate(rec_eq, 1)]
            col2_lines = [f"{rank}. {p.id} ({sim:.3f})" for rank, (p, sim) in enumerate(rec_gd, 1)]
            col3_lines = [f"{rank}. {p.id} ({sim:.3f})" for rank, (p, sim) in enumerate(rec_bc, 1)]

            print(f"| {b.name:<30} | {col1_lines[0]:<25} | {col2_lines[0]:<25} | {col3_lines[0]:<26} |")
            print(f"| {'[Goal: ' + b.primary_goal + ']':<30} | {col1_lines[1]:<25} | {col2_lines[1]:<25} | {col3_lines[1]:<26} |")
            print(f"| {'':<30} | {col1_lines[2]:<25} | {col2_lines[2]:<25} | {col3_lines[2]:<26} |")
            print("+" + "-" * 32 + "+" + "-" * 27 + "+" + "-" * 27 + "+" + "-" * 28 + "+")

        self.assertTrue(rank_shift_observed, "Weight adjustments must cause observable rank shifts across benchmark personas.")
        print(">>> [PASS] Attribute weight sensitivity experiment successfully executed.\n")

    # --------------------------------------------------------------------------
    # TEST 4: PRECISION@K CALCULATION
    # --------------------------------------------------------------------------
    def test_05_precision_at_k_calculation(self):
        """Calculates Precision@1 and Precision@3 programmatically against expert trainer ground truth labels."""
        print("\n" + "=" * 80)
        print("TEST 4: PRECISION@K EVALUATION (EXPERT TRAINER GROUND TRUTH BENCHMARK)")
        print("=" * 80)

        eval_personas: List[Tuple[MemberPersona, Set[str]]] = [
            (
                MemberPersona(
                    user_id="EVAL-1",
                    name="Budi (Cardiac Rehab Senior)",
                    age=58,
                    gender="M",
                    height_cm=168.0,
                    weight_kg=72.0,
                    waist_cm=88.0,
                    body_fat_pct=24.0,
                    workout_frequency=3,
                    primary_goal="General Health",
                    parq_cardiac=True,
                ),
                {"PROG-01", "PROG-02", "PROG-03"}  # Low-impact mobility, joint circuit, foundational
            ),
            (
                MemberPersona(
                    user_id="EVAL-2",
                    name="Rian (Advanced Hypertrophy)",
                    age=25,
                    gender="M",
                    height_cm=178.0,
                    weight_kg=82.0,
                    waist_cm=78.0,
                    body_fat_pct=12.0,
                    workout_frequency=6,
                    primary_goal="Hypertrophy",
                ),
                {"PROG-05", "PROG-06", "PROG-07"}  # PPL, Upper/Lower, Powerlifting
            ),
            (
                MemberPersona(
                    user_id="EVAL-3",
                    name="Maya (Metabolic Fat Loss)",
                    age=31,
                    gender="F",
                    height_cm=162.0,
                    weight_kg=72.0,
                    waist_cm=86.0,
                    body_fat_pct=33.0,
                    workout_frequency=4,
                    primary_goal="Fat Loss",
                ),
                {"PROG-04", "PROG-08", "PROG-09"}  # HIIT Circuit, Glute Sculpt, Tabata Conditioning
            ),
            (
                MemberPersona(
                    user_id="EVAL-4",
                    name="Doni (Knee & Joint Protection)",
                    age=42,
                    gender="M",
                    height_cm=172.0,
                    weight_kg=76.0,
                    waist_cm=84.0,
                    body_fat_pct=20.0,
                    workout_frequency=3,
                    primary_goal="General Health",
                    parq_joint=True,
                ),
                {"PROG-01", "PROG-02", "PROG-10"}  # Joint friendly machines, calisthenics, mobility
            ),
            (
                MemberPersona(
                    user_id="EVAL-5",
                    name="Siti (Female Body Sculpt)",
                    age=23,
                    gender="F",
                    height_cm=165.0,
                    weight_kg=58.0,
                    waist_cm=68.0,
                    body_fat_pct=22.0,
                    workout_frequency=4,
                    primary_goal="Hypertrophy",
                ),
                {"PROG-03", "PROG-05", "PROG-08"}  # Glute & Core Sculpt, Dumbbell Routine, PPL
            ),
        ]

        p1_scores: List[float] = []
        p3_scores: List[float] = []

        print(f"{'Persona Evaluated':<30} | {'Top-3 Predicted':<25} | {'Ground Truth':<25} | {'P@1':<8} | {'P@3':<8}")
        print("-" * 105)

        for persona, ground_truth in eval_personas:
            recs, _, _ = BijeRecommendationEngine.recommend(
                self.catalog, persona, self.equal_weights, top_k=3
            )
            pred_ids = [p.id for p, _ in recs]
            top_1_id = pred_ids[0] if pred_ids else None

            # Programmatic Precision@1: 1.0 if Top-1 in GT else 0.0
            p1 = 1.0 if top_1_id in ground_truth else 0.0
            p1_scores.append(p1)

            # Programmatic Precision@3: (hits in Top-3) / 3.0
            hits = len(set(pred_ids) & ground_truth)
            p3 = hits / 3.0
            p3_scores.append(p3)

            pred_str = ", ".join(pred_ids)
            gt_str = ", ".join(sorted(list(ground_truth)))
            print(f"{persona.name:<30} | {pred_str:<25} | {gt_str:<25} | {p1 * 100:>6.1f}% | {p3 * 100:>6.1f}%")

        mean_precision_1 = (sum(p1_scores) / len(p1_scores)) * 100.0
        mean_precision_3 = (sum(p3_scores) / len(p3_scores)) * 100.0

        print("-" * 105)
        print(f"Overall Mean Precision@1 : {mean_precision_1:.2f}%")
        print(f"Overall Mean Precision@3 : {mean_precision_3:.2f}%")

        self.assertGreaterEqual(mean_precision_1, 80.0, "Mean Precision@1 must exceed 80% benchmark.")
        self.assertGreaterEqual(mean_precision_3, 80.0, "Mean Precision@3 must exceed 80% benchmark.")
        print(">>> [PASS] Precision@K metrics programmatically validated against trainer benchmark.\n")


# ==============================================================================
# SECTION 3: SEQUENTIAL TEST EXECUTION RUNNER & REPORT
# ==============================================================================

def execute_validation_suite() -> int:
    """Executes all test routines sequentially and prints an organized test report."""
    print("\n" + "#" * 80)
    print("#  BIJE'S GYM RECOMMENDATION SYSTEM - COMPREHENSIVE TEST EXECUTION HARNESS")
    print("#  Methodology: Content-Based Filtering & Weighted Cosine Similarity")
    print("#" * 80)

    start_time = time.time()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBijeGymRecommendationPipeline)
    runner = unittest.TextTestRunner(verbosity=0)
    test_result = runner.run(suite)
    elapsed_time = time.time() - start_time

    print("=" * 80)
    print("                     TEST EXECUTION SUMMARY REPORT")
    print("=" * 80)
    total_tests = test_result.testsRun
    total_errors = len(test_result.errors)
    total_failures = len(test_result.failures)
    total_passed = total_tests - total_errors - total_failures

    print(f"Overall Test Suite Status : {'PASSED (SUCCESS)' if test_result.wasSuccessful() else 'FAILED'}")
    print(f"Total Test Cases Executed : {total_tests}")
    print(f"Passed Test Cases         : {total_passed} [100%]")
    print(f"Failed Test Cases         : {total_failures}")
    print(f"Error Exceptions          : {total_errors}")
    print(f"Execution Duration        : {elapsed_time:.3f} seconds")
    print("=" * 80)

    if test_result.wasSuccessful():
        print(">>> ALL 5 RECOMMENDATION PIPELINE VALIDATION SUITES PASSED SUCCESSFULLY.")
    else:
        print(">>> ONE OR MORE TEST ROUTINES FAILED. CHECK DETAILED LOGS ABOVE.")
    print("=" * 80 + "\n")

    return 0 if test_result.wasSuccessful() else 1


if __name__ == "__main__":
    import sys
    sys.exit(execute_validation_suite())
