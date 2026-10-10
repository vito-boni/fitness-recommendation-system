import os
import json, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.program_generator import generate

def show(title, prof):
    t = time.time(); r = generate(prof); dt = time.time() - t
    print("="*100); print(title, f"({dt:.2f}s)")
    for w in r["warnings"]: print("  [!]", w)
    for p in r["programs"]:
        print(f"\n{p['name']} | {p['frequency_days']}x | split: {p['split']} | rata2 {p['avg_session_minutes']} mnt (target {p['session_minutes_target']}) | mingguan {p['weekly_minutes']} mnt | skor {p['scores']}")
        for s in p["sessions"]:
            print(f"  - {s['label']}: {s['total_minutes']} mnt, {len(s['exercises'])} latihan" + (f" + kardio {s['cardio_finisher']['minutes']}m" if s['cardio_finisher'] else ""))
    return r

alice = dict(experience=2, days=3, session_minutes=60, primary_target=2, advanced_targets=["Fat Loss","Bentuk Tubuh Ideal"],
             target_body_parts=["full_body","chest","back","shoulders","legs","arms","core"], facilities=["1","2","3","4","5","6","7"],
             physical_condition="0", exercise_complexity="balanced", weight=61, height=168, gender="P", age=26)
r = show("ALICE (exp2, 3 hari, 60 mnt, semua alat)", alice)
vito = dict(experience=3, days=4, session_minutes=120, primary_target=4, advanced_targets=[],
            target_body_parts=["chest","back","shoulders","legs","arms","core"], facilities=["4"],
            physical_condition="0", exercise_complexity="balanced", weight=115, height=173, gender="L", age=22)
show("VITO (exp3, 4 hari, 120 mnt, hanya mesin)", vito)
json.dump(r, open("/tmp/alice.json","w"), ensure_ascii=False, indent=1)
