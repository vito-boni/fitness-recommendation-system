import os
import sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.program_generator import generate
base = dict(experience=1, days=3, session_minutes=60, primary_target=1, advanced_targets=[],
            target_body_parts=["chest","back","shoulders","legs","arms","core"], facilities=["1","2","3","4","5","6","7"],
            physical_condition="0", exercise_complexity="simple", weight=80, height=170, gender="L", age=30)
def run(title, **kw):
    prof = {**base, **kw}
    t=time.time(); r=generate(prof); dt=time.time()-t
    print("="*90); print(title, f"({dt:.2f}s)", "pool", r["meta"].get("exercise_pool"), "ranked", r["meta"].get("candidates_ranked"))
    for w in r["warnings"]: print("  [!]", w)
    for p in r["programs"]:
        print(f"  {p['name']}: {p['split']} | avg {p['avg_session_minutes']}m/{p['session_minutes_target']} | final {p['scores']['final']} | fill {p['scores']['time_fill']}")
    if not r["programs"]: print("  (tidak ada program)")
    return r
run("1 hari full-body pemula 45 mnt", days=1, session_minutes=40)
run("2 hari", days=2)
run("6 hari lanjutan 90 mnt", days=6, experience=4, session_minutes=90, primary_target=3)
run("5 hari exp2 hipertrofi", days=5, experience=2, primary_target=2, session_minutes=60)
run("bahu cedera", physical_condition="1", body_part="bahu", limitation="nyeri saat angkat lengan", days=3)
r=run("tidak dikenali", physical_condition="1", body_part="saraf", limitation="mati rasa", days=3)
run("jantung", physical_condition="1", body_part="internal tubuh", limitation="hipertensi", days=3, age=55)
run("hanya dumbbell target glutes legs", facilities=["1"], body_parts=None, target_body_parts=["legs"], days=3, experience=2)
run("hanya kardio (7)", facilities=["7"], days=3)
run("lengan saja, hanya mesin", facilities=["4"], target_body_parts=["arms"], days=3)
run("exp4 lanjutan semua alat 4 hari 90 mnt", experience=4, days=4, session_minutes=90, primary_target=4, advanced_targets=["Performa Atletik"], complexity="technical", exercise_complexity="technical")
# keberagaman & validasi aturan
import itertools
for days in range(1,7):
    r=generate({**base, "days":days, "experience":3, "session_minutes":60, "primary_target":2})
    names=[p["split"] for p in r["programs"]]
    over=[(p["name"],s["label"],s["total_minutes"]) for p in r["programs"] for s in p["sessions"] if s["total_minutes"]>60.01]
    print(days, names, "OVER:", over)
