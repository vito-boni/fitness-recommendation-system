import json
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.program_generator import generate
except ImportError:
    from services.program_generator import generate


def show(title, prof):
    t = time.time()
    r = generate(prof)
    dt = time.time() - t
    print("=" * 100)
    print(title, f"({dt:.2f}s)")
    for w in r["warnings"]:
        print("  [!]", w)
    for p in r["programs"]:
        print(
            f"\n{p['name']} | {p['frequency_days']}x | split: {p['split']} | "
            f"rata2 {p['avg_session_minutes']} mnt (target {p['session_minutes_target']}) | "
            f"mingguan {p['weekly_minutes']} mnt | skor {p['scores']}"
        )
        for s in p["sessions"]:
            extra = f" + kardio {s['cardio_block']['minutes']}m" if s.get("cardio_block") else ""
            print(f"  - {s['label']}: {s['total_minutes']} mnt, {len(s['exercises'])} latihan{extra}")
    return r


def test_generator_alice():
    alice = dict(
        experience=2,
        days=3,
        session_minutes=60,
        primary_target=2,
        advanced_targets=["Fat Loss", "Bentuk Tubuh Ideal"],
        target_body_parts=["full_body", "chest", "back", "shoulders", "legs", "arms", "core"],
        facilities=["1", "2", "3", "4", "5", "6", "7"],
        physical_condition="0",
        exercise_complexity="balanced",
        weight=61,
        height=168,
        gender="P",
        age=26,
    )
    result = generate(alice)
    assert len(result["programs"]) > 0
    assert result["programs"][0]["frequency_days"] == 3


def test_generator_vito():
    vito = dict(
        experience=3,
        days=4,
        session_minutes=120,
        primary_target=4,
        advanced_targets=[],
        target_body_parts=["chest", "back", "shoulders", "legs", "arms", "core"],
        facilities=["4"],
        physical_condition="0",
        exercise_complexity="balanced",
        weight=115,
        height=173,
        gender="L",
        age=22,
    )
    result = generate(vito)
    assert len(result["programs"]) > 0
    assert result["programs"][0]["frequency_days"] == 4


if __name__ == "__main__":
    alice = dict(
        experience=2,
        days=3,
        session_minutes=60,
        primary_target=2,
        advanced_targets=["Fat Loss", "Bentuk Tubuh Ideal"],
        target_body_parts=["full_body", "chest", "back", "shoulders", "legs", "arms", "core"],
        facilities=["1", "2", "3", "4", "5", "6", "7"],
        physical_condition="0",
        exercise_complexity="balanced",
        weight=61,
        height=168,
        gender="P",
        age=26,
    )
    r = show("ALICE (exp2, 3 hari, 60 mnt, semua alat)", alice)
    vito = dict(
        experience=3,
        days=4,
        session_minutes=120,
        primary_target=4,
        advanced_targets=[],
        target_body_parts=["chest", "back", "shoulders", "legs", "arms", "core"],
        facilities=["4"],
        physical_condition="0",
        exercise_complexity="balanced",
        weight=115,
        height=173,
        gender="L",
        age=22,
    )
    show("VITO (exp3, 4 hari, 120 mnt, hanya mesin)", vito)
