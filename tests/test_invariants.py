"""Uji aturan keras pada ratusan profil acak (bahan Bab 4.3.3 Pengujian Filter Keamanan)."""
import os
import random
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.program_generator import (
        MAX_PATTERN_EXERCISES,
        MAX_SESSION_EXERCISES,
        SESSION_VOLUME_CAP,
        generate,
        load_catalog,
    )
except ImportError:
    from services.program_generator import (
        MAX_PATTERN_EXERCISES,
        MAX_SESSION_EXERCISES,
        SESSION_VOLUME_CAP,
        generate,
        load_catalog,
    )


def test_invariants_random_profiles():
    random.seed(7)
    cat = {e["id"]: e for e in load_catalog()}
    focus_list = ["chest", "back", "shoulders", "glutes", "thighs", "arms", "calves", "core"]
    goals_list = [
        "Fat Loss",
        "Bentuk Tubuh Ideal",
        "Ketahanan Jantung",
        "Kekuatan Absolut",
        "Panjang umur / Healthy Aging",
        "Performa Atletik",
    ]
    stories_list = [
        "",
        "Sakit bahu.",
        "Cedera lutut.",
        "Nyeri punggung bawah, hernia.",
        "Nyeri siku. Sakit saat menekuk pergelangan tangan.",
        "Nyeri pinggul.",
        "Sakit leher.",
        "Saraf kejepit.",
        "Saya punya hipertensi.",
        "Sakit bagian betis.",
        "Kaku di pergelangan kaki. Sakit lutut.",
    ]
    n_iterations, viol, nprog, empty, referrals = 100, [], 0, 0, 0

    for i in range(n_iterations):
        phys = random.random() < 0.4
        story = random.choice(stories_list) if phys else ""
        experience = random.randint(1, 4)
        anthro = {}
        if random.random() < 0.5:
            h = random.randint(150, 190)
            anthro = dict(
                waist_cm=random.randint(60, 120),
                hip_cm=random.randint(80, 125),
                shoulder_width_cm=random.randint(36, 56),
                arm_length_cm=round(h * random.uniform(0.40, 0.48)),
                leg_length_cm=round(h * random.uniform(0.48, 0.56)),
                torso_length_cm=round(h * random.uniform(0.27, 0.34)),
            )
        prof = dict(
            experience=experience,
            days=random.randint(1, 6),
            session_minutes=random.choice([40, 60, 90, 120]),
            advanced_targets=random.sample(goals_list, random.randint(1, 3)),
            focus_areas=random.sample(focus_list, random.randint(0, 3)),
            modalities=random.sample(["cardio", "mobility"], random.randint(0, 2)),
            physical_condition="1" if phys else "0",
            limitation_story=story,
            exercise_complexity=random.choice(["simple", "balanced", "technical"]),
            cardio_endurance=random.randint(1, 3),
            body_fat=random.randint(0, 5),
            weight=random.randint(45, 130),
            height=random.randint(150, 190),
            gender=random.choice("LP"),
            age=random.randint(17, 65),
            **anthro,
        )
        r = generate(prof)
        if not r["programs"]:
            empty += 1
            if r.get("referral"):
                referrals += 1
            continue
        excl = set(r["meta"].get("filter", {}).get("excluded_joints", []))
        maxd = r["meta"].get("filter", {}).get("max_diff", 3)
        maxi = r["meta"].get("filter", {}).get("max_impact", 3)
        mods = set(prof["modalities"])
        for p in r["programs"]:
            nprog += 1

            def bad(msg):
                viol.append((i, p["name"], msg, prof))

            if len(p["sessions"]) != prof["days"]:
                bad("jumlah sesi != hari")
            for s in p["sessions"]:
                if s["total_seconds"] > prof["session_minutes"] * 60 + 1:
                    bad(f"waktu melebihi {s['total_minutes']}")
                names = [e["name"] for e in s["exercises"]]
                if len(names) != len(set(names)):
                    bad("latihan duplikat dalam sesi")
                if len(names) > MAX_SESSION_EXERCISES:
                    bad("terlalu banyak latihan")
                if any(value > SESSION_VOLUME_CAP[experience] for value in s["effective_sets"].values()):
                    bad("batas effective sets per otot terlampaui")
                pattern_counts = {}
                for exercise in s["exercises"]:
                    if exercise["pattern"] in ("push", "pull", "legs"):
                        pattern_counts[exercise["pattern"]] = pattern_counts.get(exercise["pattern"], 0) + 1
                if any(count > MAX_PATTERN_EXERCISES for count in pattern_counts.values()):
                    bad("terlalu banyak latihan dengan pola gerak sama")
                checked = list(s["exercises"])
                if s["cardio_block"]:
                    if "cardio" not in mods:
                        bad("blok kardio tanpa pilihan kardio")
                    checked.append(s["cardio_block"])
                if s["mobility_block"]:
                    if "mobility" not in mods:
                        bad("blok mobilitas tanpa pilihan mobilitas")
                    checked.extend(s["mobility_block"]["exercises"])
                    if s["mobility_block"]["est_seconds"] > 12 * 60:
                        bad("blok mobilitas > 12 menit")
                if "cardio" in mods and not s["cardio_block"] and any(
                    e["role"] == "cardio"
                    and not (e["joints"] & excl)
                    and e["difficulty"] <= maxd
                    and e["impact_level"] <= maxi
                    for e in cat.values()
                ):
                    bad("blok kardio hilang padahal ada alat yang aman")
                for e in checked:
                    ex = cat[e["id"]]
                    if ex["joints"] & excl:
                        bad(f"sendi terlarang: {e['name']}")
                    if ex["difficulty"] > maxd:
                        bad(f"kesulitan > batas: {e['name']}")
                    if ex["impact_level"] > maxi:
                        bad(f"impact > batas: {e['name']}")
                    if e.get("load_kg") and ex["max_kg"] and e["load_kg"] > ex["max_kg"]:
                        bad("beban > batas alat")
                for part in (s["warmup"], s["cooldown"]):
                    for ex in cat.values():
                        if ex["role"] == "cardio" and part["name"].startswith(ex["name"]) and (
                            ex["joints"] & excl or ex["impact_level"] > maxi
                        ):
                            bad(f"pemanasan/pendinginan melanggar filter: {part['name']}")

    assert len(viol) == 0, f"Found {len(viol)} rule violations: {viol[:5]}"


if __name__ == "__main__":
    test_invariants_random_profiles()
    print("All invariants passed successfully!")
