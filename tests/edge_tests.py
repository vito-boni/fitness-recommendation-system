import itertools
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

base = dict(
    experience=1,
    days=3,
    session_minutes=60,
    primary_target=1,
    advanced_targets=[],
    target_body_parts=["chest", "back", "shoulders", "legs", "arms", "core"],
    facilities=["1", "2", "3", "4", "5", "6", "7"],
    physical_condition="0",
    exercise_complexity="simple",
    weight=80,
    height=170,
    gender="L",
    age=30,
)


def run_case(title, **kw):
    prof = {**base, **kw}
    t = time.time()
    r = generate(prof)
    dt = time.time() - t
    print("=" * 90)
    print(
        title,
        f"({dt:.2f}s)",
        "pool",
        r["meta"].get("exercise_pool"),
        "ranked",
        r["meta"].get("candidates_ranked"),
    )
    for w in r["warnings"]:
        print("  [!]", w)
    for p in r["programs"]:
        print(
            f"  {p['name']}: {p['split']} | "
            f"avg {p['avg_session_minutes']}m/{p['session_minutes_target']} | "
            f"final {p['scores']['final']} | fill {p['scores']['time_fill']}"
        )
    return r


def test_edge_cases():
    r1 = run_case("1 hari full-body pemula 45 mnt", days=1, session_minutes=40)
    assert len(r1["programs"]) > 0

    r2 = run_case("2 hari", days=2)
    assert len(r2["programs"]) > 0

    r6 = run_case("6 hari lanjutan 90 mnt", days=6, experience=4, session_minutes=90, primary_target=3)
    assert len(r6["programs"]) > 0

    r5 = run_case("5 hari exp2 hipertrofi", days=5, experience=2, primary_target=2, session_minutes=60)
    assert len(r5["programs"]) > 0

    rbahu = run_case("bahu cedera", physical_condition="1", body_part="bahu", limitation="nyeri saat angkat lengan", days=3)
    assert len(rbahu["programs"]) > 0

    rsaraf = run_case("tidak dikenali", physical_condition="1", body_part="saraf", limitation="mati rasa", days=3)
    assert "programs" in rsaraf

    rjantung = run_case("jantung", physical_condition="1", body_part="internal tubuh", limitation="hipertensi", days=3, age=55)
    assert len(rjantung["programs"]) > 0

    rdb = run_case("hanya dumbbell target glutes legs", facilities=["1"], body_parts=None, target_body_parts=["legs"], days=3, experience=2)
    assert len(rdb["programs"]) > 0

    rkardio = run_case("hanya kardio (7)", facilities=["7"], days=3)
    assert "programs" in rkardio

    rmesin = run_case("lengan saja, hanya mesin", facilities=["4"], target_body_parts=["arms"], days=3)
    assert len(rmesin["programs"]) > 0

    rexp4 = run_case("exp4 lanjutan semua alat 4 hari 90 mnt", experience=4, days=4, session_minutes=90, primary_target=4, advanced_targets=["Performa Atletik"], complexity="technical", exercise_complexity="technical")
    assert len(rexp4["programs"]) > 0

    for days in range(1, 7):
        r = generate({**base, "days": days, "experience": 3, "session_minutes": 60, "primary_target": 2})
        assert len(r["programs"]) > 0


if __name__ == "__main__":
    test_edge_cases()
