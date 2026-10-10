import os
"""Uji aturan keras pada ratusan profil acak (bahan Bab 4.3.3 Pengujian Filter Keamanan)."""
import random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.program_generator import generate, load_catalog, JOINT_KEYWORDS

random.seed(7)
cat = {e["id"]: e for e in load_catalog()}
GROUPS = ["chest","back","shoulders","legs","arms","core"]
LIMITS = [("",""),("bahu","nyeri bahu"),("lutut","cedera lutut"),("punggung","hernia"),("siku","tendon siku"),
          ("pinggul","nyeri pinggul"),("leher","sakit leher"),("saraf","mati rasa"),("internal","hipertensi")]
N, viol, nprog, empty = 400, [], 0, 0
for i in range(N):
    phys = random.random() < 0.4
    bp, lim = random.choice(LIMITS) if phys else ("","")
    fac = random.sample(list("1234567"), random.randint(1,7))
    prof = dict(experience=random.randint(1,4), days=random.randint(1,6), session_minutes=random.choice([40,60,90,120]),
                primary_target=random.randint(1,4), advanced_targets=random.sample(["Fat Loss","Ketahanan Jantung","Kekuatan Absolut","Panjang umur / Healthy Aging","Performa Atletik"], random.randint(0,2)),
                target_body_parts=random.sample(GROUPS, random.randint(1,6)), facilities=fac, physical_condition="1" if phys else "0",
                body_part=bp, limitation=lim, exercise_complexity=random.choice(["simple","balanced","technical"]),
                weight=random.randint(45,130), height=random.randint(150,190), gender=random.choice("LP"), age=random.randint(17,65))
    r = generate(prof)
    if not r["programs"]: empty += 1
    excl = set(r["meta"].get("filter", {}).get("excluded_joints", []))
    maxd = r["meta"].get("filter", {}).get("max_diff", 3); maxi = r["meta"].get("filter", {}).get("max_impact", 3)
    fset = set(fac)
    for p in r["programs"]:
        nprog += 1
        def bad(msg): viol.append((i, p["name"], msg, prof))
        if len(p["sessions"]) != prof["days"]: bad("jumlah sesi != hari")
        for s in p["sessions"]:
            if s["total_seconds"] > prof["session_minutes"]*60 + 1: bad(f"waktu melebihi {s['total_minutes']}")
            names = [e["name"] for e in s["exercises"]]
            if len(names) != len(set(names)): bad("latihan duplikat dalam sesi")
            if len(names) > 9: bad("terlalu banyak latihan")
            for e in s["exercises"]:
                ex = cat[e["id"]]
                if not ex["fac"] <= fset: bad(f"alat tidak tersedia: {e['name']}")
                if ex["joints"] & excl: bad(f"sendi terlarang: {e['name']}")
                if ex["difficulty"] > maxd: bad(f"kesulitan > batas: {e['name']}")
                if ex["impact_level"] > maxi: bad(f"impact > batas: {e['name']}")
                if e["load_kg"] and ex["max_kg"] and e["load_kg"] > ex["max_kg"]: bad("beban > batas alat")
            if s["cardio_finisher"] and "7" not in fset: bad("kardio tanpa alat kardio")
print(f"profil: {N} | program dihasilkan: {nprog} | profil tanpa program: {empty} | pelanggaran: {len(viol)}")
for v in viol[:10]: print(v[:3])
