"""
Generator program latihan: Content-Based Filtering + Cosine Similarity.

Alur:
  1. Normalisasi profil dari asesmen.
  2. Filter keras (aturan): fasilitas, kesulitan vs pengalaman, keterbatasan fisik.
  3. Skor tiap latihan = cosine(vektor preferensi profil, vektor fitur latihan).
  4. Enumerasi kombinasi blok split sesuai jumlah hari, dipangkas aturan,
     lalu diberi skor (cosine paparan otot, kecocokan frekuensi, pemulihan).
  5. Tiap kandidat diisi latihan sampai waktu sesi mendekati target.
  6. Top-N dipilih dengan penalti kemiripan (supaya tidak kembar).
Tidak ada LLM: semua pilihan latihan berasal dari katalog.
"""
import csv
import itertools
import json
import math
import os
import re
from functools import lru_cache

DATA_DIR = os.environ.get("BIJES_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

MUSCLES = ["chest", "back", "shoulders", "biceps", "triceps",
           "quads", "hamstrings", "glutes", "calves", "core"]
MAJOR = ["chest", "back", "shoulders", "quads", "hamstrings", "glutes"]
MUSCLE_LABEL = {
    "chest": "Dada", "back": "Punggung", "shoulders": "Bahu", "biceps": "Biseps",
    "triceps": "Triseps", "quads": "Paha depan", "hamstrings": "Paha belakang",
    "glutes": "Glutes", "calves": "Betis", "core": "Core",
    "full_body": "Seluruh tubuh", "cardio": "Kardio",
}
GROUP_TO_MUSCLES = {
    "chest": ["chest"], "back": ["back"], "shoulders": ["shoulders"],
    "legs": ["quads", "hamstrings", "glutes", "calves"],
    "arms": ["biceps", "triceps"], "core": ["core"], "cardio": [],
}
GROUP_LABEL = {"chest": "Dada", "back": "Punggung", "shoulders": "Bahu", "legs": "Kaki",
               "arms": "Lengan", "core": "Core", "cardio": "Kardio"}

# ---- bobot skor akhir (dipakai juga untuk analisis sensitivitas, Bab 4.3.2) ----
WEIGHTS = {"split_cosine": 0.40, "freq_fit": 0.20, "recovery": 0.15,
           "exercise_cos": 0.15, "time_fill": 0.10}
DIVERSITY_PENALTY = 0.15

WARMUP_SEC = 300
COOLDOWN_SEC = 300
TIME_TOLERANCE_SEC = 240            # sesi boleh kurang maksimal 4 menit dari target
SETUP_SEC = {1: 30, 2: 60, 3: 90}   # waktu pindah/siap alat dari kolom `setup`
MAX_EXERCISES = 8
MAX_EXERCISES_CAP = 10

EXP_MULT = {1: 1.0, 2: 1.4, 3: 1.9, 4: 2.4}
FEMALE_FACTOR = 0.65
EXPOSURE_CAP = {1: 3, 2: 3, 3: 4, 4: 4}      # paparan maksimal per otot per minggu
SPECIALIZATION_MAX = {1: 0, 2: 1, 3: 2, 4: 2}
SPECIALIZATION_BLOCKS = {"chest", "back", "shoulders_arms", "glutes", "quads_hams", "core"}
IDEAL_FREQ = 2.0

UNILATERAL = {"Dumbbell Row", "Dumbbell Lunge", "Walking Lunge", "Reverse Lunge", "Split Squat",
              "Dumbbell Bulgarian Split Squat", "Side Plank", "Dumbbell Concentration Curl",
              "Dumbbell Tricep Kickback", "Cable Kickback", "Cable Lateral Raise"}

# kata kunci keterbatasan -> sendi (id/en)
JOINT_KEYWORDS = {
    "shoulder": ["bahu", "pundak", "shoulder", "rotator"],
    "knee": ["lutut", "knee", "acl", "meniskus", "meniscus"],
    "lower_back": ["punggung", "pinggang", "back", "hernia", "hnp", "saraf kejepit", "skoliosis",
                   "tulang belakang", "lumbar", "ischias", "sciatica"],
    "elbow": ["siku", "elbow", "tendon", "tenis elbow"],
    "wrist": ["pergelangan tangan", "wrist", "carpal", "tangan"],
    "hip": ["pinggul", "panggul", "hip", "paha atas"],
    "neck": ["leher", "neck", "servikal"],
    "ankle": ["pergelangan kaki", "ankle", "tumit", "achilles", "betis"],
}
CARDIO_CAUTION_KEYWORDS = ["jantung", "hipertensi", "darah tinggi", "asma", "diabetes", "hamil",
                           "heart", "hypertension", "pregnan", "pernapasan", "stroke", "kolesterol"]

JOINT_LABEL = {"shoulder": "bahu", "knee": "lutut", "lower_back": "punggung bawah", "elbow": "siku",
               "wrist": "pergelangan tangan", "hip": "pinggul", "neck": "leher", "ankle": "pergelangan kaki"}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_catalog():
    rows = []
    with open(os.path.join(DATA_DIR, "exercises_v2.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["difficulty"] = int(r["difficulty"])
            r["impact_level"] = int(r["impact_level"])
            r["setup"] = int(r["setup"])
            r["load_ratio"] = float(r["load_ratio"] or 0)
            r["sec_per_rep"] = float(r["sec_per_rep"] or 0)
            r["timed_default_sec"] = int(float(r["timed_default_sec"] or 0))
            r["max_kg"] = float(r["max_kg"]) if r["max_kg"] else None
            r["fac"] = {x for x in r["facility_req"].split("|") if x}
            r["joints"] = {x for x in r["joint_stress"].split("|") if x}
            r["unilateral"] = r["name"] in UNILATERAL
            rows.append(r)
    return rows


@lru_cache(maxsize=1)
def load_blocks():
    with open(os.path.join(DATA_DIR, "split_blocks.json"), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Profil
# --------------------------------------------------------------------------
def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _list(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v.strip():
        try:
            p = json.loads(v)
            return [str(x) for x in p] if isinstance(p, list) else []
        except json.JSONDecodeError:
            return []
    return []


class Profile:
    def __init__(self, d):
        self.experience = min(4, max(1, int(_num(d.get("experience"), 1))))
        self.days = min(6, max(1, int(_num(d.get("days"), 3))))
        self.session_minutes = max(30, int(_num(d.get("session_minutes"), 60)))
        self.primary_target = min(4, max(1, int(_num(d.get("primary_target"), 2))))
        self.advanced = set(_list(d.get("advanced_targets")))
        parts = [p for p in _list(d.get("target_body_parts")) if p != "full_body"]
        self.body_parts = parts or ["chest", "back", "shoulders", "legs", "arms", "core"]
        fac = set(_list(d.get("facilities")))
        if "8" in fac or not fac:
            fac = {"1", "2", "3", "4", "5", "6", "7"}
        self.facilities = fac - {"8"}
        self.physical = str(d.get("physical_condition", "0")) in ("1", "true", "True")
        self.limit_text = " ".join(str(d.get(k) or "") for k in ("body_part", "limitation", "other_note")).lower()
        self.complexity = d.get("exercise_complexity", "balanced")
        if self.complexity not in ("simple", "balanced", "technical"):
            self.complexity = {"Sederhana & aman": "simple", "Teknis tinggi / kompleks": "technical"}.get(
                self.complexity, "balanced")
        self.weight = _num(d.get("weight"), 0)
        self.height = _num(d.get("height"), 0)
        self.gender = d.get("gender") or ""
        self.age = int(_num(d.get("age"), 0))

    @property
    def bmi(self):
        return self.weight / ((self.height / 100) ** 2) if self.weight and self.height else 0

    @property
    def reference_weight(self):
        """Berat acuan untuk estimasi beban: dibatasi pada berat IMT 25 agar tidak melambung."""
        if not self.weight:
            return 0
        if self.height:
            return min(self.weight, 25 * (self.height / 100) ** 2)
        return self.weight

    @property
    def goal_flags(self):
        a = self.advanced
        return {
            "fat_loss": "Fat Loss" in a,
            "cardio": "Ketahanan Jantung" in a,
            "strength": "Kekuatan Absolut" in a or self.primary_target >= 3,
            "aging": "Panjang umur / Healthy Aging" in a,
            "athletic": "Performa Atletik" in a or self.primary_target == 4,
        }

    def target_muscles(self):
        s = set()
        for g in self.body_parts:
            s.update(GROUP_TO_MUSCLES.get(g, []))
        return s


def _estimated_load_before_rounding(ex, reps, profile):
    unit = ex["load_unit"]
    if unit in ("bodyweight", "time") or ex["load_ratio"] == 0:
        return None
    ref = profile.reference_weight
    if not ref:
        return None
    load = ex["load_ratio"] * ref * EXP_MULT[profile.experience]
    if profile.gender == "P":
        load *= FEMALE_FACTOR
    if profile.age >= 50:
        load *= 0.85
    if reps:
        if reps <= 5:
            load *= 1.15
        elif reps >= 15:
            load *= 0.8
        elif reps >= 12:
            load *= 0.9
    return load


# --------------------------------------------------------------------------
# Filter keras
# --------------------------------------------------------------------------
def _kw_match(text, kw):
    pat = r"\b" + re.escape(kw) + (r"\b" if len(kw) <= 4 else "")
    return re.search(pat, text) is not None


def filter_exercises(profile):
    warnings, excluded_joints = [], set()
    max_diff = {1: 1, 2: 2, 3: 3, 4: 3}[profile.experience]
    if profile.complexity == "technical":
        max_diff = min(3, max_diff + 1)
    if profile.complexity == "simple":
        max_diff = max(1, max_diff - 1) if profile.experience >= 3 else max_diff
    max_impact = 3
    cardio_caution = any(_kw_match(profile.limit_text, k) for k in CARDIO_CAUTION_KEYWORDS)
    low_impact = profile.physical or profile.age >= 50 or profile.bmi >= 35 or profile.goal_flags["aging"]
    if low_impact:
        max_impact = 2
    if profile.physical:
        for joint, kws in JOINT_KEYWORDS.items():
            if any(_kw_match(profile.limit_text, k) for k in kws):
                excluded_joints.add(joint)
        if not excluded_joints and not cardio_caution:
            max_diff = min(max_diff, 2)
            excluded_joints.add("lower_back")
            warnings.append("Keterbatasan fisik tidak dikenali otomatis oleh sistem, sehingga pemilihan latihan "
                            "dibuat lebih konservatif. Konsultasikan program dengan trainer sebelum dimulai.")
        if cardio_caution:
            max_diff = min(max_diff, 2)
            max_impact = 2
            warnings.append("Kondisi yang Anda sebutkan memerlukan pertimbangan medis. Konsultasikan dengan dokter "
                            "sebelum memulai program ini; latihan berdampak tinggi dan beban sangat berat dihindari.")
        if excluded_joints:
            warnings.append("Latihan yang membebani " + ", ".join(JOINT_LABEL[j] for j in sorted(excluded_joints))
                            + " tidak dimasukkan ke program.")
    pool = []
    excluded_load = []
    for ex in load_catalog():
        if not ex["fac"] <= profile.facilities:
            continue
        if ex["difficulty"] > max_diff or ex["impact_level"] > max_impact:
            continue
        if ex["joints"] & excluded_joints:
            continue
        minimum_load = {"barbell": 20, "ez_bar": 10}.get(ex["equipment"])
        if minimum_load is not None:
            prescription = base_prescription(ex, profile, ex["role"] == "main")
            estimated_load = _estimated_load_before_rounding(ex, prescription["reps"], profile)
            if estimated_load is not None and estimated_load < minimum_load:
                excluded_load.append(ex["id"])
                continue
        pool.append(ex)
    if excluded_load:
        warnings.append(
            "Latihan barbell atau EZ bar yang estimasi beban awalnya terlalu berat untuk profil Anda "
            "tidak disarankan; sistem akan memilih variasi yang lebih ringan bila tersedia."
        )
    return pool, warnings, {
        "max_diff": max_diff,
        "max_impact": max_impact,
        "excluded_joints": sorted(excluded_joints),
        "excluded_load": excluded_load,
    }


# --------------------------------------------------------------------------
# Cosine similarity: profil vs latihan
# --------------------------------------------------------------------------
EQUIP_CLASS = {"barbell": "free", "dumbbell": "free", "ez_bar": "free", "kettlebell": "free",
               "machine": "guided", "cable": "guided", "smith": "guided",
               "bodyweight": "bw", "battle_rope": "bw", "cardio": "bw"}


def exercise_features(ex):
    return [f"d{ex['difficulty']}", f"i{ex['impact_level']}", f"s{ex['setup']}",
            "compound" if ex["movement_type"] == "compound" else "isolation",
            EQUIP_CLASS.get(ex["equipment"], "bw")]


def profile_vector(profile):
    """Vektor preferensi profil member (bobot per fitur latihan)."""
    d = {1: [1.0, 0.2, 0.0], 2: [0.6, 1.0, 0.2], 3: [0.4, 0.8, 0.8], 4: [0.3, 0.7, 1.0]}[profile.experience]
    cm = {"simple": [1.0, 0.7, 0.3], "balanced": [1.0, 1.0, 1.0], "technical": [0.7, 1.0, 1.3]}[profile.complexity]
    d = [a * b for a, b in zip(d, cm)]
    low_impact = profile.physical or profile.age >= 50 or profile.bmi >= 35 or profile.goal_flags["aging"]
    if low_impact:
        i = [1.0, 0.3, 0.0]
    elif profile.primary_target == 4 or profile.goal_flags["athletic"]:
        i = [0.6, 0.9, 1.0]
    else:
        i = [0.8, 1.0, 0.6]
    s = [1.0, 0.5, 0.1] if (profile.experience == 1 or profile.session_minutes <= 45) else [0.8, 1.0, 0.8]
    iso = {1: 0.6, 2: 1.0, 3: 0.6, 4: 0.4}[profile.primary_target]
    comp = 1.0 + (0.2 if profile.goal_flags["fat_loss"] else 0.0)
    if profile.experience == 1 or low_impact:
        eq = [0.5, 1.0, 0.7]          # free, guided, bw
    elif profile.experience >= 3:
        eq = [1.0, 0.8, 0.5]
    else:
        eq = [0.8, 1.0, 0.6]
    w = {}
    for k, v in zip(["d1", "d2", "d3"], d):
        w[k] = v
    for k, v in zip(["i1", "i2", "i3"], i):
        w[k] = v
    for k, v in zip(["s1", "s2", "s3"], s):
        w[k] = v
    w.update({"compound": comp, "isolation": iso, "free": eq[0], "guided": eq[1], "bw": eq[2]})
    return w


def cosine_profile_exercise(wvec, ex):
    feats = exercise_features(ex)
    dot = sum(wvec.get(f, 0.0) for f in feats)
    n_u = math.sqrt(sum(v * v for v in wvec.values()))
    n_e = math.sqrt(len(feats))
    return dot / (n_u * n_e) if n_u else 0.0


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------------------
# Kombinasi split
# --------------------------------------------------------------------------
def _units():
    data = load_blocks()
    units = [{"key": k, "label": b["label"], "days": 1, "blocks": [k]} for k, b in data["blocks"].items()]
    units += [{"key": k, "label": b["label"], "days": b["days"], "blocks": list(b["blocks"])}
              for k, b in data["bundles"].items()]
    return units


def _block_exposure(block, pools):
    e = {m: 0.0 for m in MUSCLES}
    for slot in block["slots"]:
        m = slot["muscle"]
        if not pools.get(m):
            continue
        if slot["main"] > 0:
            e[m] = max(e[m], 1.0)
        elif slot["acc"] > 0:
            e[m] = max(e[m], 0.5)
    return e


def enumerate_combos(days, profile, units):
    out = []
    cap_spec = SPECIALIZATION_MAX[profile.experience]

    def rec(start, remaining, chosen):
        if remaining == 0:
            out.append(tuple(chosen))
            return
        for i in range(start, len(units)):
            u = units[i]
            if u["days"] > remaining:
                continue
            chosen.append(i)
            rec(i, remaining - u["days"], chosen)
            chosen.pop()

    rec(0, days, [])
    res = []
    for c in out:
        blocks = [b for i in c for b in units[i]["blocks"]]
        if sum(1 for b in blocks if b in SPECIALIZATION_BLOCKS) > cap_spec:
            continue
        # hari khusus Core hanya masuk akal untuk sesi singkat
        if "core" in blocks and profile.session_minutes > 45:
            continue
        res.append((c, blocks))
    return res


def _day_muscles(expo):
    return {m for m, v in expo.items() if v >= 1.0}


def best_order(blocks, expos):
    """Urutan hari yang meminimalkan tumpang tindih otot pada hari berurutan."""
    best, best_pen = list(blocks), None
    seen = set()
    for perm in itertools.permutations(range(len(blocks))):
        key = tuple(blocks[i] for i in perm)
        if key in seen:
            continue
        seen.add(key)
        pen = 0.0
        worst = 0.0
        for a, b in zip(key, key[1:]):
            A, B = _day_muscles(expos[a]), _day_muscles(expos[b])
            u = len(A | B)
            j = len(A & B) / u if u else 0
            pen += j
            worst = max(worst, j)
        pen = pen / max(1, len(key) - 1)
        if best_pen is None or pen < best_pen[0] - 1e-9:
            best, best_pen = list(key), (pen, worst)
    return best, best_pen or (0.0, 0.0)


def split_label(units, combo):
    # paket (Upper-Lower, Push-Pull-Legs) ditampilkan lebih dulu
    names = [units[i]["label"] for i in sorted(combo, key=lambda i: (-units[i]["days"], i))]
    out, seen = [], {}
    for n in names:
        seen[n] = seen.get(n, 0) + 1
    for n, c in seen.items():
        out.append(f"{n} x{c}" if c > 1 else n)
    return ", ".join(out)


def rank_combos(profile, pools, top_k=60):
    data = load_blocks()
    units = _units()
    expos = {k: _block_exposure(b, pools) for k, b in data["blocks"].items()}
    target = profile.target_muscles()
    D = [1.0 if m in target else 0.5 for m in MUSCLES]
    # otot yang tidak mungkin dilatih dengan fasilitas ini tidak diwajibkan
    reachable = {m for m in MUSCLES if any(expos[b][m] > 0 for b in expos)}
    required_big = [m for m in MAJOR if m in reachable]
    required_sel = {m for m in target if m in reachable}
    unreachable_sel = sorted(m for m in target if m not in reachable)
    cap = EXPOSURE_CAP[profile.experience]
    all_combos = enumerate_combos(profile.days, profile, units)

    def collect(tier):
        res = {}
        for combo, blocks in all_combos:
            E = [0.0] * len(MUSCLES)
            for b in blocks:
                for j, m in enumerate(MUSCLES):
                    E[j] += expos[b][m]
            if any(e > cap + 1e-9 for e in E):
                continue
            Ed = dict(zip(MUSCLES, E))
            if tier <= 1:
                thr_of = (lambda m: 1.0 if m in MAJOR else 0.5) if tier == 0 else (lambda m: 0.5)
                if any(Ed[m] < thr_of(m) - 1e-9 for m in required_sel):
                    continue
                cov_big = sum(1 for m in required_big if Ed[m] >= (1.0 if tier == 0 else 0.5))
                if profile.experience <= 2 or profile.primary_target == 1:
                    if cov_big < len(required_big):
                        continue
                elif profile.days >= 2 and cov_big < min(4, len(required_big)):
                    continue
            cs = cosine(E, D)
            fit = sum(D[j] * max(0.0, 1 - abs(E[j] - IDEAL_FREQ) / IDEAL_FREQ) for j in range(len(MUSCLES))) / sum(D)
            key = tuple(sorted(blocks))
            # kombinasi yang sama (mis. Push+Pull+Legs vs Push-Pull-Legs): pakai label paket
            if key not in res or len(combo) < len(res[key][0]):
                res[key] = (combo, blocks, cs, fit, E)
        return list(res.values())

    tier_used = 0
    scored = []
    for tier in (0, 1, 2):
        scored = collect(tier)
        tier_used = tier
        if scored:
            break
    # skor murah dahulu, pemulihan dihitung untuk kandidat teratas saja
    scored.sort(key=lambda t: -(WEIGHTS["split_cosine"] * t[2] + WEIGHTS["freq_fit"] * t[3]))
    cands = []
    for combo, blocks, cs, fit, E in scored[:400]:
        if profile.days >= 4:
            order, (pen, worst) = best_order(blocks, expos)
            if worst >= 0.75:
                continue
            rec = 1 - pen
        else:
            order, rec = list(blocks), 1.0
            order.sort(key=lambda b: ["upper", "push", "full_body", "chest", "shoulders_arms", "back", "pull",
                                      "lower", "legs", "quads_hams", "glutes", "core"].index(b)
                       if b in ["upper", "push", "full_body", "chest", "shoulders_arms", "back", "pull",
                                "lower", "legs", "quads_hams", "glutes", "core"] else 99)
        base = WEIGHTS["split_cosine"] * cs + WEIGHTS["freq_fit"] * fit + WEIGHTS["recovery"] * rec
        cands.append({"combo": combo, "label": split_label(units, combo), "order": order, "cos": cs, "fit": fit,
                      "recovery": rec, "base": base, "exposure": dict(zip(MUSCLES, E))})
    cands.sort(key=lambda c: -c["base"])
    return cands[:top_k], unreachable_sel, tier_used, sorted(required_sel)


# --------------------------------------------------------------------------
# Preskripsi, beban, waktu
# --------------------------------------------------------------------------
def _is_heavy(ex):
    return ex["equipment"] == "barbell" and ex["movement_type"] == "compound" and ex["role"] == "main"


def base_prescription(ex, profile, is_main):
    t = profile.primary_target
    exp = profile.experience
    fl = profile.goal_flags
    if ex["timed_default_sec"] and ex["role"] not in ("cardio",):
        sec = ex["timed_default_sec"] * (1.5 if exp >= 3 else 1.0)
        return {"sets": 2 if exp == 1 else 3, "reps": None, "seconds": int(sec), "rest": 45, "max_sets": 4}
    if ex["role"] == "core":
        return {"sets": 3, "reps": 15 if ex["equipment"] == "bodyweight" else 12, "seconds": None,
                "rest": 45, "max_sets": 4}
    if is_main:
        if t == 1:
            p = {"sets": 2 if exp == 1 else 3, "reps": 12, "rest": 60}
        elif t == 2:
            p = {"sets": 3, "reps": 10, "rest": 90}
        elif t == 3:
            p = {"sets": 4, "reps": 6, "rest": 150} if _is_heavy(ex) else {"sets": 3, "reps": 8, "rest": 105}
        else:
            p = {"sets": 5, "reps": 4, "rest": 180} if _is_heavy(ex) else {"sets": 4, "reps": 6, "rest": 120}
        if exp == 1:
            p["sets"] = min(p["sets"], 3)
        if fl["strength"] and t < 3 and _is_heavy(ex):
            p.update({"reps": 6, "rest": 150})
        p["max_sets"] = 5 if t >= 3 else 4
    else:
        p = {"sets": 2 if (t == 1 or exp == 1) else 3, "reps": 15 if t == 1 else 12,
             "rest": 45 if t == 1 else 60, "max_sets": 4}
    if fl["fat_loss"]:
        p["rest"] = max(30, p["rest"] - 15)
    if p["reps"] is not None:
        if p["reps"] <= 8:
            p["rest"] += 10
        elif t in (2, 3, 4):
            p["rest"] += 5
    p["seconds"] = None
    return p


def exercise_seconds(ex, sets, reps, seconds, rest):
    work = sets * (seconds if seconds else reps * ex["sec_per_rep"])
    if ex["unilateral"]:
        work *= 2
    return int(round(work + max(0, sets - 1) * rest + SETUP_SEC.get(ex["setup"], 30)))


def estimate_load(ex, reps, profile):
    """Estimasi beban kerja awal (kg). Mengembalikan (angka|None, teks)."""
    unit = ex["load_unit"]
    if unit in ("bodyweight", "time") or ex["load_ratio"] == 0:
        return None, "Beban tubuh"
    load = _estimated_load_before_rounding(ex, reps, profile)
    if load is None:
        return None, "Sesuaikan kemampuan"
    eq = ex["equipment"]
    if eq == "kettlebell":
        load = min([6, 8, 10], key=lambda x: abs(x - load))
    elif eq == "dumbbell":
        load = max(5.0, round(load / 2.5) * 2.5)
    elif eq == "barbell":
        load = max(20.0, round(load / 5) * 5)
    elif eq == "ez_bar":
        load = max(10.0, round(load / 5) * 5)
    else:
        load = max(5.0, round(load / 5) * 5)
    if ex["max_kg"]:
        load = min(load, ex["max_kg"])
    txt = f"{load:g} kg" + ("/tangan" if unit == "per_hand" else "")
    return load, txt


def fmt_mmss(sec):
    sec = int(round(sec))
    m, s = divmod(sec, 60)
    if m and s:
        return f"{m} menit {s} detik"
    if m:
        return f"{m} menit"
    return f"{s} detik"


# --------------------------------------------------------------------------
# Penyusunan sesi
# --------------------------------------------------------------------------
def _tokens(name):
    return set(re.findall(r"[a-z]+", name.lower()))


def _too_similar(a, b):
    return len(_tokens(a["name"]) & _tokens(b["name"])) >= 2


class SessionBuilder:
    def __init__(self, profile, pool, wvec):
        self.p = profile
        self.pool = pool
        self.w = wvec
        self.cos = {ex["id"]: cosine_profile_exercise(wvec, ex) for ex in pool}
        self.by_muscle = {}
        for ex in pool:
            self.by_muscle.setdefault(ex["primary_muscle"], []).append(ex)
        self.used = {}      # id -> berapa kali dipakai pada hari lain (variasi mingguan)
        self.max_ex = MAX_EXERCISES_CAP if profile.session_minutes >= 90 else MAX_EXERCISES

    def pick(self, muscle, roles, chosen, exclude_ids=()):
        cands = []
        for ex in self.by_muscle.get(muscle, []):
            if ex["role"] not in roles or ex["id"] in exclude_ids:
                continue
            if any(c["ex"]["id"] == ex["id"] or _too_similar(c["ex"], ex) for c in chosen):
                continue
            score = self.cos[ex["id"]] - 0.12 * self.used.get(ex["id"], 0)
            cands.append((score, ex["name"], ex))
        if not cands:
            return None
        cands.sort(key=lambda t: (-t[0], t[1]))
        return cands[0][2]

    def build(self, block_key, budget_sec, order_hint=None):
        block = load_blocks()["blocks"][block_key]
        p = self.p
        chosen = []

        def add(ex, is_main):
            pr = base_prescription(ex, p, is_main)
            chosen.append({"ex": ex, "main": is_main, **pr})

        # 1) isi slot sesuai prioritas
        for slot in block["slots"]:
            m = slot["muscle"]
            main_roles = ("main",) if m != "core" else ("core",)
            acc_roles = ("accessory",) if m != "core" else ("core",)
            for _ in range(slot["main"]):
                ex = self.pick(m, main_roles, chosen) or self.pick(m, ("main", "accessory", "core"), chosen)
                if ex:
                    add(ex, True)
            for _ in range(slot["acc"]):
                ex = self.pick(m, acc_roles, chosen) or self.pick(m, ("main", "accessory", "core"), chosen)
                if ex:
                    add(ex, False)
        # latihan power untuk target 4 / performa atletik
        if p.goal_flags["athletic"] and p.experience >= 3 and "quads" in block["muscles"]:
            sj = next((e for e in self.pool if e["name"] == "Squat Jump"), None)
            if sj and not any(c["ex"]["id"] == sj["id"] for c in chosen):
                chosen.append({"ex": sj, "main": False, "sets": 4, "reps": 5, "seconds": None,
                               "rest": 90, "max_sets": 4})

        def total():
            return sum(exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"]) for c in chosen)

        # 2) pangkas bila melebihi
        while chosen and total() > budget_sec:
            reduced = False
            for c in chosen:
                if c["sets"] > 2:
                    c["sets"] -= 1
                    reduced = True
                    if total() <= budget_sec:
                        break
            if total() <= budget_sec:
                break
            if not reduced:
                chosen.pop()
        # 3) tumbuhkan bila kurang
        cardio_extra = None
        guard = 0
        while guard < 200:
            guard += 1
            remaining = budget_sec - total() - (cardio_extra["sec"] if cardio_extra else 0)
            if remaining <= 90:
                break
            moved = False
            # (a) tambah set latihan utama sampai batas "target" (maks 4)
            for c in chosen:
                if c["main"] and c["sets"] < min(4, c["max_sets"]) and not c["seconds"]:
                    dt = exercise_seconds(c["ex"], c["sets"] + 1, c["reps"], c["seconds"], c["rest"]) - \
                         exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"])
                    if dt <= remaining:
                        c["sets"] += 1
                        moved = True
                        break
            if moved:
                continue
            # (b) tambah latihan sampai 6, lalu (c) set aksesori, (d) latihan sampai batas
            def add_extra(limit):
                if len(chosen) >= limit:
                    return False
                muscles = [m for m in block["muscles"] if m in self.by_muscle] or ["core"]
                muscles = [m for m in muscles if m.split("(")[0] in MUSCLES]
                tm = p.target_muscles()
                counts = {m: sum(1 for c in chosen if c["ex"]["primary_muscle"] == m) for m in muscles}
                order = sorted(muscles, key=lambda m: (counts[m] - (0.5 if m in tm else 0), m))
                for m in order:
                    ex = self.pick(m, ("main", "accessory", "core"), chosen)
                    if not ex:
                        continue
                    is_main = ex["role"] == "main"
                    pr = base_prescription(ex, p, is_main)
                    dt = exercise_seconds(ex, pr["sets"], pr["reps"], pr["seconds"], pr["rest"])
                    if dt <= remaining:
                        chosen.append({"ex": ex, "main": is_main, **pr})
                        return True
                return False
            if add_extra(6):
                continue
            for c in chosen:
                if not c["main"] and c["sets"] < c["max_sets"] and not c["seconds"]:
                    dt = exercise_seconds(c["ex"], c["sets"] + 1, c["reps"], c["seconds"], c["rest"]) - \
                         exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"])
                    if dt <= remaining:
                        c["sets"] += 1
                        moved = True
                        break
            if moved:
                continue
            if add_extra(self.max_ex):
                continue
            for c in chosen:
                if c["main"] and c["sets"] < c["max_sets"] and not c["seconds"]:
                    dt = exercise_seconds(c["ex"], c["sets"] + 1, c["reps"], c["seconds"], c["rest"]) - \
                         exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"])
                    if dt <= remaining:
                        c["sets"] += 1
                        moved = True
                        break
            if moved:
                continue
            # (e) kardio penutup bila ada alat kardio
            if "7" in p.facilities and remaining >= 300 and cardio_extra is None:
                mins = int(min(15, remaining // 60))
                cardio_extra = {"sec": mins * 60, "minutes": mins}
                continue
            break

        for c in chosen:
            self.used[c["ex"]["id"]] = self.used.get(c["ex"]["id"], 0) + 1
        return self._render(block_key, block, chosen, cardio_extra)

    def _render(self, block_key, block, chosen, cardio_extra):
        p = self.p
        has_cardio = "7" in p.facilities
        lines = []
        exs_total = 0
        for c in chosen:
            ex = c["ex"]
            sec = exercise_seconds(ex, c["sets"], c["reps"], c["seconds"], c["rest"])
            exs_total += sec
            load_kg, load_txt = estimate_load(ex, c["reps"], p)
            lines.append({
                "id": ex["id"], "name": ex["name"], "muscle": MUSCLE_LABEL.get(ex["primary_muscle"], ex["primary_muscle"]),
                "muscle_key": ex["primary_muscle"], "equipment": ex["equipment"],
                "sets": c["sets"], "reps": c["reps"], "seconds_per_set": c["seconds"],
                "sec_per_rep": ex["sec_per_rep"] or None, "rest_sec": c["rest"], "unilateral": ex["unilateral"],
                "load_kg": load_kg, "load_text": load_txt, "est_seconds": sec,
                "est_text": fmt_mmss(sec), "similarity": round(self.cos[ex["id"]], 3),
            })
        extra_sec = cardio_extra["sec"] if cardio_extra else 0
        cardio_line = None
        if cardio_extra:
            cardio_line = {"name": "Treadmill (Zone 2)", "minutes": cardio_extra["minutes"],
                           "est_seconds": cardio_extra["sec"], "est_text": fmt_mmss(cardio_extra["sec"])}
        warm = {"name": "Treadmill (Zone 3)" if has_cardio else "Jumping Jack & mobilitas sendi",
                "purpose": "Pemanasan", "est_seconds": WARMUP_SEC, "est_text": "5 menit"}
        cool = {"name": "Treadmill (Zone 1)" if has_cardio else "Peregangan statis",
                "purpose": "Pendinginan", "est_seconds": COOLDOWN_SEC, "est_text": "5 menit"}
        total = WARMUP_SEC + exs_total + extra_sec + COOLDOWN_SEC
        return {"block": block_key, "label": block["label"], "warmup": warm, "exercises": lines,
                "cardio_finisher": cardio_line, "cooldown": cool,
                "total_seconds": total, "total_minutes": round(total / 60, 1)}


# --------------------------------------------------------------------------
# API utama
# --------------------------------------------------------------------------
def _weekly_overlap(a, b):
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0


def generate(profile_dict, top_n=3):
    profile = Profile(profile_dict)
    pool, warnings, filt = filter_exercises(profile)
    if not pool:
        return {"programs": [], "warnings": warnings + ["Tidak ada latihan yang cocok dengan fasilitas dan batasan Anda."],
                "meta": {"filter": filt}}
    pools = {}
    for ex in pool:
        pools.setdefault(ex["primary_muscle"], []).append(ex)
    cands, unreachable, tier, required_sel = rank_combos(profile, pools)
    if unreachable:
        warnings.append("Latihan untuk " + ", ".join(MUSCLE_LABEL[m] for m in unreachable) +
                        " tidak tersedia dengan fasilitas atau batasan yang dipilih.")
    if not cands:
        return {"programs": [], "warnings": warnings + ["Tidak ditemukan kombinasi split yang memenuhi aturan."],
                "meta": {"filter": filt}}
    if tier > 0:
        warnings.append(f"Dengan {profile.days} hari latihan per minggu, tidak semua bagian tubuh target bisa dilatih "
                        "secara penuh. Program disusun semaksimal mungkin; tambah hari latihan bila ingin cakupan lebih lengkap.")
    wvec = profile_vector(profile)
    budget = profile.session_minutes * 60 - WARMUP_SEC - COOLDOWN_SEC

    built = []
    for cand in cands:
        sb = SessionBuilder(profile, pool, wvec)
        sessions = [sb.build(b, budget) for b in cand["order"]]
        sessions = [s for s in sessions if s["exercises"]]
        if len(sessions) != len(cand["order"]):
            continue
        target_sec = profile.session_minutes * 60
        fills = []
        for s in sessions:
            over = max(0, s["total_seconds"] - target_sec)
            under = max(0, target_sec - s["total_seconds"] - TIME_TOLERANCE_SEC)
            fills.append(max(0.0, 1 - (over + under) / target_sec * 4))
        time_fill = sum(fills) / len(fills)
        sims = [e["similarity"] for s in sessions for e in s["exercises"]]
        ex_cos = sum(sims) / len(sims)
        final = cand["base"] + WEIGHTS["exercise_cos"] * ex_cos + WEIGHTS["time_fill"] * time_fill
        built.append({**cand, "sessions": sessions, "ex_cos": ex_cos, "time_fill": time_fill, "final": final})
    built.sort(key=lambda b: -b["final"])

    selected = []
    pool_left = list(built)
    while pool_left and len(selected) < top_n:
        def adj(b):
            pen = max((_weekly_overlap(b["order"], s["order"]) for s in selected), default=0)
            return b["final"] - DIVERSITY_PENALTY * pen
        pool_left.sort(key=lambda b: -adj(b))
        pick = pool_left.pop(0)
        if any(sorted(pick["order"]) == sorted(s["order"]) for s in selected):
            continue
        selected.append(pick)

    if selected:
        best_avg = max(sum(x["total_minutes"] for x in b["sessions"]) / len(b["sessions"]) for b in selected)
        if profile.session_minutes - best_avg > 8:
            warnings.append(f"Dengan fasilitas dan batasan yang dipilih, sesi terpanjang yang bisa disusun sekitar "
                            f"{int(best_avg)} menit (target {profile.session_minutes} menit). Program tetap mengikuti "
                            "batas waktu Anda, hanya saja tidak terisi penuh.")
    if profile.session_minutes > 120:
        warnings.append("Sesi di atas 120 menit biasanya menurunkan kualitas latihan. Pertimbangkan menambah hari "
                        "latihan atau mempersingkat sesi.")
    focus = [GROUP_LABEL[g] for g in profile.body_parts if g in GROUP_LABEL]
    if set(profile.body_parts) >= {"chest", "back", "shoulders", "legs", "arms", "core"}:
        focus = ["Full-body"]
    programs = []
    for i, b in enumerate(selected):
        weekly = sum(s["total_seconds"] for s in b["sessions"])
        programs.append({
            "name": f"Program {chr(65 + i)}",
            "frequency_days": profile.days,
            "session_minutes_target": profile.session_minutes,
            "avg_session_minutes": round(sum(s["total_minutes"] for s in b["sessions"]) / len(b["sessions"]), 1),
            "weekly_minutes": round(weekly / 60),
            "split": b["label"],
            "focus": focus,
            "sessions": b["sessions"],
            "scores": {"final": round(b["final"], 3), "split_cosine": round(b["cos"], 3),
                       "freq_fit": round(b["fit"], 3), "recovery": round(b["recovery"], 3),
                       "exercise_cosine_mean": round(b["ex_cos"], 3), "time_fill": round(b["time_fill"], 3)},
            "exposure": {MUSCLE_LABEL[m]: v for m, v in b["exposure"].items() if v > 0},
            "uncovered_targets": [MUSCLE_LABEL[m] for m in required_sel if b["exposure"][m] < 0.5],
        })
    return {"programs": programs, "warnings": warnings,
            "meta": {"filter": filt, "candidates_ranked": len(cands), "exercise_pool": len(pool),
                     "weights": WEIGHTS}}
