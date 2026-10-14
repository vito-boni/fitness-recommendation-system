"""
Generator program latihan: Content-Based Filtering + Cosine Similarity.

Alur:
  1. Normalisasi profil dari asesmen (data dasar, komposisi tubuh, kardio, antropometri opsional,
     tujuan spesifik -> target utama otomatis, fokus otot opsional, modalitas, keluhan fisik).
  2. Filter keras (aturan): kompleksitas gerak, keterbatasan fisik (parser keluhan), dampak, beban awal.
  3. Skor tiap latihan = cosine(vektor preferensi profil, vektor fitur latihan).
     Vektor preferensi dipengaruhi kompleksitas gerak, target, dan rasio antropometri (jika diisi).
  4. Enumerasi kombinasi blok split sesuai jumlah hari, dipangkas aturan,
     lalu diberi skor (cosine paparan otot, kecocokan frekuensi, pemulihan).
  5. Tiap kandidat diisi latihan resistance sampai waktu sesi mendekati target (durasi sesi
     hanya untuk Resistance Training; Cardio dan Mobility adalah blok tambahan di luar durasi).
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

try:
    from app.services.limitation_parser import JOINT_LABEL, parse_limitations, referral_message
except ImportError:
    from services.limitation_parser import JOINT_LABEL, parse_limitations, referral_message

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
# Fokus otot opsional (pilihan member) -> otot yang diprioritaskan
FOCUS_TO_MUSCLES = {
    "chest": ["chest"], "back": ["back"], "shoulders": ["shoulders"], "glutes": ["glutes"],
    "thighs": ["quads", "hamstrings"], "arms": ["biceps", "triceps"], "calves": ["calves"], "core": ["core"],
}
FOCUS_LABEL = {"chest": "Dada", "back": "Punggung", "shoulders": "Bahu", "glutes": "Glutes",
               "thighs": "Paha", "arms": "Lengan", "calves": "Betis", "core": "Core"}
LEGACY_GROUP_TO_FOCUS = {"chest": ["chest"], "back": ["back"], "shoulders": ["shoulders"],
                         "legs": ["thighs", "glutes", "calves"], "arms": ["arms"], "core": ["core"]}
FOCUS_WEIGHT = 2.5          # bobot otot fokus pada vektor target split (otot lain = 1.0)

# Pemetaan kelompok otot oposisi (antagonis) untuk pemecahan simetri kaku template split
OPPOSITION_MAP = {
    "back": {"chest"},
    "chest": {"back"},
    "biceps": {"triceps"},
    "triceps": {"biceps"},
    "quads": {"hamstrings", "glutes"},
    "hamstrings": {"quads"},
    "glutes": {"quads"},
    "core": set(),
    "calves": set(),
    "shoulders": set(),
}

# Training Age Tiers: rookie, novice, intermediate, upper_intermediate, advanced, veteran
TRAINING_AGE_TIERS = (
    "rookie",
    "novice",
    "intermediate",
    "upper_intermediate",
    "advanced",
    "veteran",
)

TRAINING_AGE_RANK = {
    "rookie": 1,
    "novice": 2,
    "intermediate": 3,
    "upper_intermediate": 4,
    "advanced": 5,
    "veteran": 6,
}

TRAINING_AGE_LABELS = {
    "rookie": "Rookie (< 6 bulan latihan konsisten)",
    "novice": "Novice (6–12 bulan latihan terstruktur)",
    "intermediate": "Intermediate (1–2 tahun latihan progresif)",
    "upper_intermediate": "Upper Intermediate (2–4 tahun latihan terencana)",
    "advanced": "Advanced (4–7 tahun adaptasi lanjutan)",
    "veteran": "Veteran (> 7 tahun penguasaan beban tingkat tinggi)",
}

# Multiplier untuk Initial Working Load Heuristic berbasis Training Age (menggantikan asumsi berat badan mentah)
TRAINING_AGE_LOAD_MULT = {
    "rookie": 1.0,
    "novice": 1.35,
    "intermediate": 1.85,
    "upper_intermediate": 2.30,
    "advanced": 2.75,
    "veteran": 3.20,
}

TRAINING_AGE_SAFETY_DIFF = {
    "rookie": 2,
    "novice": 3,
    "intermediate": 3,
    "upper_intermediate": 3,
    "advanced": 3,
    "veteran": 3,
}

TRAINING_AGE_VOLUME_CAP = {
    "rookie": 6.0,
    "novice": 8.0,
    "intermediate": 10.0,
    "upper_intermediate": 11.0,
    "advanced": 12.0,
    "veteran": 12.0,
}

TRAINING_AGE_EXPOSURE_CAP = {
    "rookie": 3,
    "novice": 3,
    "intermediate": 4,
    "upper_intermediate": 4,
    "advanced": 5,
    "veteran": 5,
}

TRAINING_AGE_SPEC_MAX = {
    "rookie": 0,
    "novice": 1,
    "intermediate": 2,
    "upper_intermediate": 2,
    "advanced": 3,
    "veteran": 3,
}

# Aliases dan normalisasi enum Training Age Tier
TRAINING_AGE_ALIASES = {
    "rookie": "rookie",
    "1": "rookie",
    "pemula": "rookie",
    "novice": "novice",
    "2": "novice",
    "dasar": "novice",
    "intermediate": "intermediate",
    "3": "intermediate",
    "menengah": "intermediate",
    "upper_intermediate": "upper_intermediate",
    "upper intermediate": "upper_intermediate",
    "upper-intermediate": "upper_intermediate",
    "4": "upper_intermediate",
    "advanced": "advanced",
    "5": "advanced",
    "lanjutan": "advanced",
    "veteran": "veteran",
    "6": "veteran",
}


def parse_training_age_tier(val, default="rookie"):
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        idx = int(val)
        if 1 <= idx <= 6:
            return TRAINING_AGE_TIERS[idx - 1]
        return default
    s = str(val).strip().lower().replace("-", "_")
    return TRAINING_AGE_ALIASES.get(s, default)


# Kompatibilitas mundur dengan kode yang memanggil parse_experience_tier
EXPERIENCE_TIERS = {
    1: "Rookie",
    2: "Novice",
    3: "Intermediate",
    4: "Upper Intermediate",
    5: "Advanced",
    6: "Veteran",
}

def parse_experience_tier(val, default=1):
    tier = parse_training_age_tier(val, None)
    if tier is not None:
        return TRAINING_AGE_RANK[tier]
    return default

RESISTANCE_ROLES = ("main", "accessory", "core")

# ---- bobot skor akhir (dipakai juga untuk analisis sensitivitas, Bab 4.3.2) ----
WEIGHTS = {"split_cosine": 0.35, "freq_fit": 0.20, "recovery": 0.15,
           "exercise_cos": 0.15, "time_fill": 0.05, "movement_balance": 0.10}
DIVERSITY_PENALTY = 0.15

MIN_SESSION_MINUTES = 30
MAX_SESSION_MINUTES = 120           # di atas ini cenderung junk volume (Zając et al., 2015)
WARMUP_SEC = 300
COOLDOWN_SEC = 300
TIME_TOLERANCE_SEC = 240            # sesi boleh kurang maksimal 4 menit dari target
SETUP_SEC = {1: 30, 2: 60, 3: 90}   # waktu pindah/siap alat dari kolom `setup`
TRANSITION_SEC = 45                 # perpindahan antar latihan, termasuk persiapan area/alat
FATIGUE_BUFFER = 0.15                # buffer terhadap waktu kerja untuk perlambatan akibat kelelahan
MAX_SESSION_EXERCISES = 6
MAX_PATTERN_EXERCISES = 4
SESSION_VOLUME_CAP = {1: 6.0, 2: 8.0, 3: 10.0, 4: 10.0, 5: 12.0, 6: 12.0}  # effective sets per muscle per session
EXP_MULT = {1: 1.0, 2: 1.4, 3: 1.9, 4: 2.3, 5: 2.7, 6: 3.1}               # pengalaman -> estimasi beban awal
FEMALE_FACTOR = 0.65
EXPOSURE_CAP = {1: 3, 2: 3, 3: 4, 4: 4, 5: 5, 6: 5}      # paparan maksimal per otot per minggu
SPECIALIZATION_MAX = {1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
SPECIALIZATION_BLOCKS = {"chest", "back", "shoulders_arms", "glutes", "quads_hams", "core"}
IDEAL_FREQ = 2.0

# Kompleksitas gerak menentukan tingkat kesulitan maksimum; pengalaman hanya batas keselamatan.
COMPLEXITY_MAX_DIFF = {"simple": 1, "balanced": 2, "technical": 3}
SAFETY_MAX_DIFF = {1: 2, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3}

# Tujuan spesifik -> target utama otomatis (1 = kebugaran, 2 = hipertrofi, 3 = kekuatan, 4 = power)
GOAL_TARGET = {"Fat Loss": 1, "Ketahanan Jantung": 1, "Panjang umur / Healthy Aging": 1,
               "Bentuk Tubuh Ideal": 2, "Kekuatan Absolut": 3, "Performa Atletik": 4}
PRIMARY_LABEL = {1: "Kebugaran & Metabolik Dasar", 2: "Pembentukan Otot (Hipertrofi)",
                 3: "Pembentukan Otot & Kekuatan", 4: "Kekuatan, Power & Performa Atletik"}

# Komposisi tubuh: batas atas tiap tingkat lemak tubuh (%) per gender (level 1..6)
BF_CUTOFFS = {"L": [13, 17, 24, 30, 39], "P": [20, 24, 31, 39, 44]}
BF_LABEL = {0: "Tidak diketahui", 1: "Rendah", 2: "Cukup rendah", 3: "Rata-rata",
            4: "Cukup tinggi", 5: "Tinggi", 6: "Obesitas"}
CARDIO_LABEL = {1: "Rendah / mudah lelah", 2: "Sedang / normal", 3: "Baik / terlatih"}

# Antropometri opsional: field -> (kode, min, maks, label)
ANTHRO_FIELDS = {
    "waist_cm": ("waist", 40, 200, "Lingkar Perut"),
    "hip_cm": ("hip", 50, 200, "Lingkar Pinggul"),
    "shoulder_width_cm": ("shoulder", 30, 80, "Lebar Bahu"),
    "arm_length_cm": ("arm", 40, 110, "Panjang Lengan"),
    "leg_length_cm": ("leg", 50, 130, "Panjang Tungkai"),
    "inside_foot_length_cm": ("inseam", 40, 110, "Panjang Kaki Bagian Dalam"),
    "torso_length_cm": ("torso", 30, 90, "Panjang Torso"),
}
# Ambang rasio (pendek, panjang). Nilai acuan populasi; dapat disetel untuk analisis sensitivitas.
ANTHRO_NORMS = {
    "leg_ratio": (0.50, 0.545),          # tungkai / tinggi badan
    "inseam_ratio": (0.43, 0.47),        # panjang kaki dalam / tinggi badan
    "leg_torso": (1.60, 1.90),           # tungkai / torso
    "arm_ratio": (0.42, 0.46),           # lengan / tinggi badan
    "shoulder_ratio": {"L": (0.25, 0.29), "P": (0.23, 0.27)},   # lebar bahu / tinggi badan
    "whtr": 0.5,                         # lingkar perut / tinggi badan
    "whr": {"L": 0.90, "P": 0.85},       # lingkar perut / lingkar pinggul
}
# Kategori biomekanik latihan (kolom `biomech` pada katalog)
BIOMECH_TAGS = ("barbell_squat", "upright_squat", "hinge", "long_rom_press", "stable_press", "neutral")

UNILATERAL = {"Dumbbell Row", "Dumbbell Lunge", "Walking Lunge", "Reverse Lunge", "Split Squat",
              "Dumbbell Bulgarian Split Squat", "Side Plank", "Dumbbell Concentration Curl",
              "Dumbbell Tricep Kickback", "Cable Kickback", "Cable Lateral Raise",
              # mobilitas: dilakukan per sisi
              "Thoracic Rotation (Open Book)", "Overhead Lat Stretch", "Cross-Body Shoulder Stretch",
              "Neck Side Stretch", "Biceps Wall Stretch", "Wrist Flexor Stretch", "Overhead Triceps Stretch",
              "Standing Quad Stretch", "Kneeling Hip Flexor Stretch", "Lying Hamstring Stretch",
              "Figure-4 Glute Stretch", "Calf Wall Stretch", "Lying Knee-to-Chest Stretch"}

MOBILITY_SETS = 2
MOBILITY_HOLD_SEC = 40
MOBILITY_TRANSITION_SEC = 15
MOBILITY_MIN_SEC = 8 * 60
MOBILITY_MAX_SEC = 12 * 60
CONDITIONING_EXCLUDED = {"Squat Jump", "Jumping Jack"}


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
            r["biomech"] = (r.get("biomech") or "neutral").strip() or "neutral"
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


def derive_primary_target(goals):
    """Target utama otomatis dari tujuan spesifik: ambil tingkat tertinggi yang dipilih."""
    return max((GOAL_TARGET.get(g, 0) for g in goals), default=0) or None


# Pemetaan persentase lemak tubuh atletik acuan untuk indeks pilihan member (bila tidak memasukkan angka persis)
BF_INDEX_TO_PCT = {
    "L": {1: 11.0, 2: 15.5, 3: 20.5, 4: 27.5, 5: 35.0, 6: 42.0},
    "P": {1: 18.0, 2: 22.5, 3: 28.0, 4: 35.5, 5: 42.0, 6: 48.0},
}


def classify_ffmi(ffmi, gender="L"):
    """Klasifikasi Fat-Free Mass Index (FFMI) untuk menilai tingkat hipertrofi & kekokohan struktural."""
    if not ffmi or ffmi <= 0:
        return "Belum ada data"
    is_female = (gender == "P")
    if is_female:
        if ffmi < 15.0:
            return "Massa Otot Rendah"
        if ffmi < 17.0:
            return "Normal / Kekokohan Rata-Rata"
        if ffmi < 19.5:
            return "Atletis & Terlatih"
        if ffmi < 22.0:
            return "Perkembangan Otot Sangat Baik"
        return "Tingkat Elit / Atletik Unggul"
    else:
        if ffmi < 18.0:
            return "Massa Otot Rendah"
        if ffmi < 20.0:
            return "Normal / Kekokohan Rata-Rata"
        if ffmi < 22.0:
            return "Atletis & Terlatih"
        if ffmi < 25.0:
            return "Perkembangan Otot Sangat Baik (Hipertrofi Prima)"
        return "Tingkat Elit Natural (Binaraga / Kekuatan Puncak)"


def classify_wthr(wthr):
    """Klasifikasi Waist-to-Height Ratio (WtHR) untuk evaluasi adipositas sentral tanpa bias timbangan."""
    if wthr is None:
        return "Tidak ada data lingkar perut"
    if wthr < 0.40:
        return "Sangat Ramping (Adipositas Sentral Minimal)"
    if wthr < 0.50:
        return "Optimal (Profil Metabolik Sehat & Seimbang)"
    if wthr < 0.60:
        return "Peningkatan Lemak Sentral (Prioritas Metabolik Aktif)"
    return "Adipositas Sentral Tinggi (Prioritas Kardiorespirasi & Proteksi Sendi)"


def estimate_body_fat_deurenberg(weight_kg, height_cm, age=None, gender="L"):
    """Estimasi fallback persentase lemak tubuh berbasis formula Deurenberg et al. (1991).

    Digunakan ketika member memilih 'Lewat dulu' pada opsi persentase lemak tubuh.
    """
    weight = max(0.0, float(weight_kg or 0))
    height_m = max(0.0, float(height_cm or 0)) / 100.0
    sex = gender if gender in ("L", "P") else "L"
    if height_m <= 0 or weight <= 0:
        return 18.0 if sex == "L" else 25.0
    bmi = weight / (height_m ** 2)
    age_val = float(age) if (age is not None and float(age or 0) > 0) else 25.0
    sex_val = 1.0 if sex == "L" else 0.0
    est = 1.20 * bmi + 0.23 * age_val - 10.8 * sex_val - 5.4
    return round(max(5.0, min(55.0, est)), 1)


def calculate_body_composition(weight_kg, height_cm, body_fat_pct=None, waist_cm=None, gender="L", age=None):
    """Engine Komposisi Tubuh Atletik Modern: FFMI & WtHR dengan fallback formula bila lemak tubuh dilewati."""
    weight = max(0.0, float(weight_kg or 0))
    height = max(0.0, float(height_cm or 0))
    sex = gender if gender in ("L", "P") else "L"

    is_precise = False
    # Penentuan persentase lemak tubuh: jika diberikan angka persis (>0), gunakan langsung;
    # jika berupa indeks tier lama (1..6), petakan ke nilai persentase median atletik;
    # jika kosong / 'Lewat dulu', gunakan estimasi formula Deurenberg et al. (1991).
    if body_fat_pct is not None and str(body_fat_pct).strip() not in ("", "0", "null", "None"):
        val = float(body_fat_pct)
        if 1 <= val <= 6 and val == int(val):
            bf = BF_INDEX_TO_PCT[sex].get(int(val), 18.0 if sex == "L" else 25.0)
        else:
            bf = max(3.0, min(60.0, val))
            is_precise = True
    else:
        bf = estimate_body_fat_deurenberg(weight, height, age, sex)

    height_m = height / 100.0 if height > 0 else 0
    fat_mass_kg = weight * (bf / 100.0) if weight > 0 else 0
    lean_mass_kg = max(0.0, weight - fat_mass_kg)

    if height_m > 0 and lean_mass_kg > 0:
        ffmi = lean_mass_kg / (height_m ** 2)
        norm_ffmi = ffmi + 6.1 * (1.80 - height_m)
    else:
        ffmi = 0.0
        norm_ffmi = 0.0

    wthr = (float(waist_cm) / height) if (waist_cm and float(waist_cm) > 0 and height > 0) else None

    # Tingkat kategori lemak tubuh 1..6 untuk jeda istirahat recovery
    cuts = BF_CUTOFFS.get(sex, BF_CUTOFFS["L"])
    bf_level = 1 + sum(1 for c in cuts if bf > c)

    return {
        "lean_mass_kg": round(lean_mass_kg, 1),
        "fat_mass_kg": round(fat_mass_kg, 1),
        "body_fat_percent": round(bf, 1),
        "is_body_fat_estimated": not is_precise,
        "bf_level": bf_level,
        "ffmi": round(ffmi, 1),
        "norm_ffmi": round(norm_ffmi, 1),
        "wthr": round(wthr, 3) if wthr is not None else None,
        "ffmi_classification": classify_ffmi(ffmi, sex),
        "wthr_classification": classify_wthr(wthr),
    }


def analyze_anthropometry(d, height, gender, aesthetic):
    """Hitung rasio tubuh dari ukuran opsional lalu terjemahkan menjadi bobot preferensi latihan."""
    res = {"provided": False, "measures": {}, "ignored": [], "ratios": {}, "findings": [], "applied": [],
           "biomech": {tag: 1.0 for tag in BIOMECH_TAGS}, "muscle_weights": {}, "metabolic_priority": False}
    for field, (code, low, high, label) in ANTHRO_FIELDS.items():
        raw = d.get(field)
        if raw in (None, ""):
            continue
        value = _num(raw, 0)
        if value <= 0:
            continue
        if low <= value <= high:
            res["measures"][code] = value
        else:
            res["ignored"].append(label)
    m = res["measures"]
    if not m:
        return res
    res["provided"] = True
    bm = res["biomech"]
    sex = gender if gender in ("L", "P") else "L"
    emphasis = 1.25 if aesthetic else 1.15

    def scale(tag, factor):
        bm[tag] = round(min(1.6, max(0.3, bm[tag] * factor)), 3)

    leg_status = None
    if m.get("leg") and m.get("torso"):
        ratio = m["leg"] / m["torso"]
        low, high = ANTHRO_NORMS["leg_torso"]
        res["ratios"]["tungkai_torso"] = round(ratio, 2)
        leg_status = "long" if ratio >= high else "short" if ratio <= low else "average"
    elif m.get("leg") and height:
        ratio = m["leg"] / height
        low, high = ANTHRO_NORMS["leg_ratio"]
        res["ratios"]["tungkai_tinggi"] = round(ratio, 3)
        leg_status = "long" if ratio >= high else "short" if ratio <= low else "average"
    elif m.get("inseam") and height:
        ratio = m["inseam"] / height
        low, high = ANTHRO_NORMS["inseam_ratio"]
        res["ratios"]["kaki_dalam_tinggi"] = round(ratio, 3)
        leg_status = "long" if ratio >= high else "short" if ratio <= low else "average"
    if leg_status == "long":
        scale("barbell_squat", 0.35)
        scale("upright_squat", 1.55)
        scale("hinge", 0.7)
        res["findings"].append("Tungkai relatif panjang terhadap badan.")
        res["applied"].append("Squat barbell diturunkan prioritasnya; squat tegak (hack squat, leg press, goblet) "
                              "dan variasi mesin dinaikkan agar punggung bawah dan lutut tidak terbebani berlebih.")
    elif leg_status == "short":
        scale("barbell_squat", 1.55)
        scale("upright_squat", 0.7)
        scale("hinge", 1.25)
        res["findings"].append("Tungkai relatif pendek terhadap badan.")
        res["applied"].append("Squat dan hinge barbell lebih menguntungkan secara leverage sehingga prioritasnya dinaikkan.")

    if m.get("arm") and height:
        ratio = m["arm"] / height
        low, high = ANTHRO_NORMS["arm_ratio"]
        res["ratios"]["lengan_tinggi"] = round(ratio, 3)
        if ratio >= high:
            scale("long_rom_press", 0.45)
            scale("stable_press", 1.45)
            scale("hinge", 1.35)
            res["findings"].append("Lengan relatif panjang.")
            res["applied"].append("Bench press barbell (jangkauan gerak panjang) diturunkan; dumbbell dan mesin press "
                                  "dinaikkan. Gerakan menarik (deadlift, row) lebih diuntungkan leverage lengan.")
        elif ratio <= low:
            scale("long_rom_press", 1.45)
            scale("stable_press", 0.75)
            scale("hinge", 0.7)
            res["findings"].append("Lengan relatif pendek.")
            res["applied"].append("Press barbell lebih efisien (jangkauan gerak pendek) sehingga dinaikkan; "
                                  "gerakan menarik dari lantai diturunkan.")

    if m.get("shoulder") and height:
        ratio = m["shoulder"] / height
        low, high = ANTHRO_NORMS["shoulder_ratio"][sex]
        res["ratios"]["bahu_tinggi"] = round(ratio, 3)
        if ratio <= low:
            res["muscle_weights"]["shoulders"] = emphasis
            res["muscle_weights"]["back"] = emphasis
            res["findings"].append("Bahu relatif sempit terhadap tinggi badan.")
            res["applied"].append("Bahu dan punggung diberi prioritas lebih agar proporsi tubuh atas lebih seimbang (V-taper).")
        elif ratio >= high:
            res["findings"].append("Bahu relatif lebar terhadap tinggi badan.")

    if m.get("waist") and height:
        whtr = m["waist"] / height
        res["ratios"]["perut_tinggi"] = round(whtr, 3)
        if whtr >= ANTHRO_NORMS["whtr"]:
            res["metabolic_priority"] = True
            res["findings"].append("Rasio lingkar perut terhadap tinggi badan di atas 0,5 (lemak sentral meningkat).")
    if m.get("waist") and m.get("hip"):
        whr = m["waist"] / m["hip"]
        res["ratios"]["perut_pinggul"] = round(whr, 3)
        if whr >= ANTHRO_NORMS["whr"][sex]:
            res["metabolic_priority"] = True
            res["findings"].append("Rasio perut-pinggul di atas batas sehat.")
    if res["metabolic_priority"]:
        res["applied"].append("Prioritas metabolik aktif: durasi blok Cardio (bila dipilih) ditambah dan "
                              "disarankan menambahkan Cardio ke program.")
    return res


class Profile:
    def __init__(self, d):
        raw_tier = (d.get("training_age_tier") or d.get("experience_tier")
                    or d.get("experience") or d.get("experience_level"))
        self.training_age_tier = parse_training_age_tier(raw_tier, "rookie")
        self.training_age_rank = TRAINING_AGE_RANK[self.training_age_tier]
        self.experience = self.training_age_rank
        self.experience_level = EXPERIENCE_TIERS[self.training_age_rank]

        self.days = min(6, max(1, int(_num(d.get("days"), 3))))
        self.session_minutes = min(MAX_SESSION_MINUTES,
                                   max(MIN_SESSION_MINUTES, int(_num(d.get("session_minutes"), 60))))
        self.advanced = set(_list(d.get("advanced_targets")))
        explicit = int(_num(d.get("primary_target"), 0))
        derived = derive_primary_target(self.advanced)
        if 1 <= explicit <= 4:
            self.primary_target, self.primary_source = explicit, "manual"
        elif derived:
            self.primary_target, self.primary_source = derived, "goals"
        else:
            self.primary_target, self.primary_source = 2, "default"

        self.focus = self._focus_from(d)
        self.focus_muscles = {m for f in self.focus for m in FOCUS_TO_MUSCLES[f]}
        self.modalities = {x for x in _list(d.get("modalities")) if x in ("cardio", "mobility")}

        # Bije's Gym menyediakan semua peralatan; `facilities` hanya dipakai bila dikirim eksplisit (pengujian).
        fac = set(_list(d.get("facilities")))
        if "8" in fac or not fac:
            fac = {"1", "2", "3", "4", "5", "6", "7"}
        self.facilities = fac - {"8"}

        self.physical = str(d.get("physical_condition", "0")) in ("1", "true", "True")
        story = d.get("limitation_story")
        if story is None:
            story = " ".join(str(d.get(k) or "") for k in ("body_part", "limitation", "other_note"))
        self.limit_text = str(story or "").strip()
        self.limits = parse_limitations(self.limit_text if self.physical else "")

        self.complexity = d.get("exercise_complexity", "balanced")
        if self.complexity not in ("simple", "balanced", "technical"):
            self.complexity = {"Sederhana & aman": "simple", "Sederhana & praktis": "simple",
                               "Teknis tinggi / kompleks": "technical",
                               "Teknis & kompleks": "technical"}.get(self.complexity, "balanced")

        self.weight = _num(d.get("weight") or d.get("weight_kg"), 0)
        self.height = _num(d.get("height") or d.get("height_cm"), 0)
        self.gender = d.get("gender") or ""
        self.age = int(_num(d.get("age"), 0))
        self.waist = _num(d.get("waist_cm") or d.get("waist"), 0)

        raw_bf = d.get("body_fat_percent") if d.get("body_fat_percent") is not None else d.get("body_fat")
        self.comp = calculate_body_composition(self.weight, self.height, raw_bf, self.waist, self.gender, self.age)
        self.lean_mass = self.comp["lean_mass_kg"]
        self.fat_mass = self.comp["fat_mass_kg"]
        self.body_fat_percent = self.comp["body_fat_percent"]
        self.bf_level = self.comp["bf_level"]
        self.ffmi = self.comp["ffmi"]
        self.norm_ffmi = self.comp["norm_ffmi"]
        self.wthr = self.comp["wthr"]
        self.ffmi_classification = self.comp["ffmi_classification"]
        self.wthr_classification = self.comp["wthr_classification"]

        self.cardio_level = min(3, max(1, int(_num(d.get("cardio_endurance"), 2))))
        self.anthro = analyze_anthropometry(d, self.height, self.gender, self.goal_flags["aesthetic"])

    @property
    def is_experienced(self):
        """Training Age Tier: intermediate, upper_intermediate, advanced, veteran."""
        return self.training_age_rank >= 3

    @staticmethod
    def _focus_from(d):
        raw = [f for f in _list(d.get("focus_areas")) if f in FOCUS_TO_MUSCLES]
        if not raw and d.get("target_body_parts") is not None:
            legacy = [p for p in _list(d.get("target_body_parts")) if p != "full_body"]
            if legacy and not set(LEGACY_GROUP_TO_FOCUS) <= set(legacy):
                for group in legacy:
                    raw.extend(LEGACY_GROUP_TO_FOCUS.get(group, []))
        return list(dict.fromkeys(raw))

    @property
    def reference_weight(self):
        """Berat acuan struktural untuk estimasi beban awal berbasis Lean Mass (otot aktif)."""
        return self.lean_mass if self.lean_mass > 0 else (self.weight or 60.0)

    @property
    def goal_flags(self):
        a = self.advanced
        return {
            "fat_loss": "Fat Loss" in a,
            "cardio": "Ketahanan Jantung" in a,
            "strength": "Kekuatan Absolut" in a or self.primary_target >= 3,
            "aging": "Panjang umur / Healthy Aging" in a,
            "athletic": "Performa Atletik" in a or self.primary_target == 4,
            "aesthetic": "Bentuk Tubuh Ideal" in a,
        }

    @property
    def cardio_caution(self):
        return self.physical and self.limits["cardio_caution"]

    @property
    def low_impact(self):
        # Evaluasi dampak rendah berbasis WtHR (adipositas sentral nyata), kondisi fisik medis, atau usia lanjut.
        # Bebas dari bias timbangan BMI (mencegah atlet berotot berat di-default ke low-impact).
        central_adiposity_risk = (self.wthr is not None and self.wthr >= 0.60 and not self.is_experienced)
        return (self.physical or self.age >= 50 or self.goal_flags["aging"]
                or self.cardio_level == 1 or central_adiposity_risk)

    @property
    def recovery_bonus(self):
        """Tambahan jeda antar set (detik): adipositas sentral tinggi (WtHR), kardio rendah, atau kondisi medis."""
        bonus = 0
        if (self.wthr is not None and self.wthr >= 0.55) or self.bf_level >= 4:
            bonus += 15
        if self.cardio_level == 1:
            bonus += 15
        if self.cardio_caution:
            bonus += 15
        return min(30, bonus)

    def muscle_priority(self, muscle):
        if muscle in self.focus_muscles:
            weight = FOCUS_WEIGHT
        elif any(muscle in OPPOSITION_MAP.get(pm, set()) for pm in self.focus_muscles):
            weight = 0.5
        else:
            weight = 1.0
        return weight * self.anthro["muscle_weights"].get(muscle, 1.0)

    def summary(self):
        return {
            "ffmi": self.ffmi,
            "norm_ffmi": self.norm_ffmi,
            "ffmi_classification": self.ffmi_classification,
            "lean_mass_kg": self.lean_mass,
            "fat_mass_kg": self.fat_mass,
            "body_fat_percent": self.body_fat_percent,
            "is_body_fat_estimated": self.comp.get("is_body_fat_estimated", False),
            "wthr": self.wthr,
            "wthr_classification": self.wthr_classification,
            "training_age_tier": self.training_age_tier,
            "training_age_label": TRAINING_AGE_LABELS[self.training_age_tier],
            "training_age_rank": self.training_age_rank,
            "experience_level": self.training_age_tier,
            "experience_tier": self.training_age_rank,
            "cardio_level": self.cardio_level,
            "cardio_label": CARDIO_LABEL[self.cardio_level],
            "recovery_bonus_sec": self.recovery_bonus,
            "primary_target": self.primary_target,
            "primary_target_label": PRIMARY_LABEL[self.primary_target],
            "primary_target_source": self.primary_source,
            "focus": [FOCUS_LABEL[f] for f in self.focus],
            "modalities": ["resistance", *sorted(self.modalities)],
            "anthropometry": {k: self.anthro[k] for k in
                              ("provided", "ratios", "findings", "applied", "ignored", "metabolic_priority")},
        }


def _estimated_load_before_rounding(ex, reps, profile):
    unit = ex["load_unit"]
    if unit in ("bodyweight", "time") or ex["load_ratio"] == 0:
        return None

    # Mesin beban awal atletik: berbasis Lean Mass (otot aktif) & Training Age Tier
    lean_engine = profile.lean_mass or profile.weight or 60.0
    tier_mult = TRAINING_AGE_LOAD_MULT.get(profile.training_age_tier, 1.0)

    # Robustness scaling berbasis FFMI (semakin kokoh struktur otot, semakin efisien transfer gaya)
    ffmi_baseline = 17.0 if profile.gender == "P" else 20.0
    ffmi_scaler = max(0.85, min(1.35, profile.ffmi / ffmi_baseline)) if profile.ffmi > 0 else 1.0

    load = ex["load_ratio"] * lean_engine * tier_mult * ffmi_scaler
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
def filter_exercises(profile):
    warnings = []
    tier = profile.training_age_tier
    if profile.complexity == "simple":
        max_diff = 1
    elif profile.complexity == "balanced":
        max_diff = 2 if tier in ("rookie", "novice") else 3
    else:
        max_diff = TRAINING_AGE_SAFETY_DIFF.get(tier, 3)
    max_impact = 3
    excluded_joints = set()
    lim = profile.limits
    if profile.low_impact:
        max_impact = 2
    if profile.physical:
        excluded_joints = set(lim["excluded_joints"])
        if lim["items"]:
            warnings.append("Keluhan yang terdeteksi: " + "; ".join(lim["labels"]) + ".")
            if "lower" in lim["regions"]:
                max_impact = min(max_impact, 2)
            if lim["has_severe"]:
                max_diff = min(max_diff, 2)
                warnings.append("Terdapat keluhan berat (mis. patah, robek, pasca operasi). Pastikan Anda sudah "
                                "mendapat izin dokter atau Personal Trainer sebelum memulai program.")
        if lim["unrecognized"]:
            warnings.append("Sebagian kalimat keluhan tidak dikenali sistem: "
                            + "; ".join(u["sentence"] for u in lim["unrecognized"])
                            + ". Tulis bagian tubuh dan keluhannya, mis. \"Sakit lutut.\"")
        if not lim["items"] and (lim["unrecognized"] or not profile.limit_text):
            max_diff = min(max_diff, 2)
            excluded_joints.add("lower_back")
            warnings.append("Keterbatasan fisik tidak dikenali otomatis oleh sistem, sehingga pemilihan latihan "
                            "dibuat lebih konservatif. Konsultasikan program dengan trainer sebelum dimulai.")
        if lim["cardio_caution"]:
            max_diff = min(max_diff, 2)
            max_impact = 2
            warnings.append("Kondisi yang Anda sebutkan memerlukan pertimbangan medis. Konsultasikan dengan dokter "
                            "sebelum memulai program ini; latihan berdampak tinggi dan beban sangat berat dihindari.")
        if excluded_joints:
            warnings.append("Latihan yang membebani " + ", ".join(JOINT_LABEL[j] for j in sorted(excluded_joints))
                            + " tidak dimasukkan ke program (termasuk pemanasan, kardio, dan mobilitas).")
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

# Kompleksitas gerak -> preferensi kesulitan, waktu persiapan alat, dan kelas alat (bebas/terpandu/bodyweight)
COMPLEXITY_DIFF = {"simple": [1.0, 0.5, 0.1], "balanced": [0.8, 1.0, 0.5], "technical": [0.4, 0.8, 1.0]}
COMPLEXITY_SETUP = {"simple": [1.0, 0.6, 0.1], "balanced": [0.8, 1.0, 0.6], "technical": [0.4, 0.8, 1.0]}
COMPLEXITY_EQUIP = {"simple": [0.4, 1.0, 0.8], "balanced": [0.8, 1.0, 0.6], "technical": [1.0, 0.6, 0.5]}


def exercise_features(ex):
    return [f"d{ex['difficulty']}", f"i{ex['impact_level']}", f"s{ex['setup']}",
            "compound" if ex["movement_type"] == "compound" else "isolation",
            EQUIP_CLASS.get(ex["equipment"], "bw"),
            f"bm_{ex['biomech']}"]


def profile_vector(profile):
    """Vektor preferensi profil member (bobot per fitur latihan)."""
    d = list(COMPLEXITY_DIFF[profile.complexity])
    s = list(COMPLEXITY_SETUP[profile.complexity])
    eq = list(COMPLEXITY_EQUIP[profile.complexity])
    low_impact = profile.low_impact
    if low_impact:
        i = [1.0, 0.3, 0.0]
        eq[0] *= 0.8
    elif profile.primary_target == 4 or profile.goal_flags["athletic"]:
        i = [0.6, 0.9, 1.0]
    else:
        i = [0.8, 1.0, 0.6]
    if profile.session_minutes <= 45:
        s = [a * b for a, b in zip(s, [1.0, 0.8, 0.5])]
    flags = profile.goal_flags
    iso = {1: 0.6, 2: 1.0, 3: 0.6, 4: 0.4}[profile.primary_target] + (0.2 if flags["aesthetic"] else 0.0)
    comp = 1.0 + (0.2 if (flags["fat_loss"] or flags["cardio"]) else 0.0)
    w = {}
    for k, v in zip(["d1", "d2", "d3"], d):
        w[k] = v
    for k, v in zip(["i1", "i2", "i3"], i):
        w[k] = v
    for k, v in zip(["s1", "s2", "s3"], s):
        w[k] = v
    w.update({"compound": comp, "isolation": iso, "free": eq[0], "guided": eq[1], "bw": eq[2]})
    for tag in BIOMECH_TAGS:
        w[f"bm_{tag}"] = profile.anthro["biomech"][tag]
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


def split_label(block_order):
    """Label split mengikuti urutan sesi yang benar-benar ditampilkan."""
    blocks = load_blocks()["blocks"]
    return " / ".join(blocks[key]["label"] for key in block_order)


def rank_combos(profile, pools, top_k=60):
    data = load_blocks()
    units = _units()
    expos = {k: _block_exposure(b, pools) for k, b in data["blocks"].items()}
    # Fokus otot hanya menambah prioritas; program tetap menutup seluruh tubuh bila memungkinkan.
    D = [profile.muscle_priority(m) for m in MUSCLES]
    # otot yang tidak mungkin dilatih dengan batasan ini tidak diwajibkan
    reachable = {m for m in MUSCLES if any(expos[b][m] > 0 for b in expos)}
    required_big = [m for m in MAJOR if m in reachable]
    required_sel = {m for m in MUSCLES if m in reachable}
    unreachable_sel = sorted(m for m in MUSCLES if m not in reachable)
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
                opps = {opp for pm in profile.focus_muscles for opp in OPPOSITION_MAP.get(pm, set()) if opp not in profile.focus_muscles}
                thr_of = (lambda m: 0.0 if m in opps else (1.0 if m in MAJOR else 0.5)) if tier == 0 else (lambda m: 0.0 if m in opps else 0.5)
                if any(Ed[m] < thr_of(m) - 1e-9 for m in required_sel):
                    continue
                req_big_target = [m for m in required_big if m not in opps]
                cov_big = sum(1 for m in req_big_target if Ed[m] >= (1.0 if tier == 0 else 0.5))
                if profile.experience <= 2 or profile.primary_target == 1:
                    if cov_big < len(req_big_target):
                        continue
                elif profile.days >= 2 and cov_big < min(4, len(req_big_target)):
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
        if profile.days > 1:
            order, (pen, worst) = best_order(blocks, expos)
            if profile.days >= 4 and worst >= 0.75:
                continue
            rec = 1 - pen
        else:
            order, rec = list(blocks), 1.0
            order.sort(key=lambda b: ["upper", "push", "full_body", "chest", "shoulders_arms", "back", "pull",
                                      "lower", "legs", "quads_hams", "glutes", "core"].index(b)
                       if b in ["upper", "push", "full_body", "chest", "shoulders_arms", "back", "pull",
                                "lower", "legs", "quads_hams", "glutes", "core"] else 99)
        base = WEIGHTS["split_cosine"] * cs + WEIGHTS["freq_fit"] * fit + WEIGHTS["recovery"] * rec
        cands.append({"combo": combo, "label": split_label(order), "order": order, "cos": cs, "fit": fit,
                      "recovery": rec, "base": base, "exposure": dict(zip(MUSCLES, E))})
    cands.sort(key=lambda c: -c["base"])
    return cands[:top_k], unreachable_sel, tier_used, sorted(required_sel)


# --------------------------------------------------------------------------
# Preskripsi, beban, waktu
# --------------------------------------------------------------------------
def _is_heavy(ex):
    return ex["equipment"] == "barbell" and ex["movement_type"] == "compound" and ex["role"] == "main"


def _base_prescription(ex, profile, is_main):
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
    # Fat loss memperpendek jeda hanya bila pemulihan member tidak terganggu (lemak tinggi / kardio rendah).
    if fl["fat_loss"] and not profile.recovery_bonus:
        p["rest"] = max(30, p["rest"] - 15)
    if p["reps"] is not None:
        if p["reps"] <= 8:
            p["rest"] += 10
        elif t in (2, 3, 4):
            p["rest"] += 5
    p["seconds"] = None
    return p


def base_prescription(ex, profile, is_main):
    """Preskripsi dasar + tambahan jeda pemulihan (lemak tubuh tinggi / kardio rendah / kondisi medis)."""
    p = _base_prescription(ex, profile, is_main)
    p["rest"] += profile.recovery_bonus
    return p


def exercise_seconds(ex, sets, reps, seconds, rest):
    work = sets * (seconds if seconds else reps * ex["sec_per_rep"])
    if ex["unilateral"]:
        work *= 2
    work_with_fatigue = work * (1 + FATIGUE_BUFFER)
    rest_time = max(0, sets - 1) * rest
    setup_time = SETUP_SEC.get(ex["setup"], 30)
    return int(round(work_with_fatigue + rest_time + setup_time + TRANSITION_SEC))


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


def exercise_line(ex, sets, reps, seconds, rest, profile, similarity):
    """Satu baris latihan siap tampil (dipakai generator dan fitur tukar latihan)."""
    sec = exercise_seconds(ex, sets, reps, seconds, rest)
    load_kg, load_txt = estimate_load(ex, reps, profile)
    return {
        "id": ex["id"], "name": ex["name"], "muscle": MUSCLE_LABEL.get(ex["primary_muscle"], ex["primary_muscle"]),
        "muscle_key": ex["primary_muscle"], "pattern": ex["pattern"], "equipment": ex["equipment"],
        "sets": sets, "reps": reps, "seconds_per_set": seconds,
        "sec_per_rep": ex["sec_per_rep"] or None, "rest_sec": rest, "unilateral": ex["unilateral"],
        "setup_seconds": SETUP_SEC.get(ex["setup"], 30),
        "load_kg": load_kg, "load_text": load_txt, "est_seconds": sec,
        "est_text": fmt_mmss(sec), "similarity": round(similarity, 3),
    }


# --------------------------------------------------------------------------
# Penyusunan sesi
# --------------------------------------------------------------------------
def _tokens(name):
    return set(re.findall(r"[a-z]+", name.lower()))


def _too_similar(a, b):
    return len(_tokens(a["name"]) & _tokens(b["name"])) >= 2


def _effective_set_volume(chosen):
    """Count direct work plus conservative fractional volume for common synergists."""
    volume = {}
    for item in chosen:
        ex = item["ex"]
        muscle = ex["primary_muscle"]
        sets = item["sets"]
        contributions = {muscle: 1.0}
        pattern = ex["pattern"]

        if pattern == "push":
            secondary = {
                "chest": {"shoulders": 0.5, "triceps": 0.5},
                "shoulders": {"chest": 0.25, "triceps": 0.5},
                "triceps": {"chest": 0.25, "shoulders": 0.25},
            }
        elif pattern == "pull":
            secondary = {
                "back": {"biceps": 0.5, "shoulders": 0.25},
                "biceps": {"back": 0.25},
                "shoulders": {"back": 0.25},
            }
        elif pattern == "legs":
            secondary = {
                "quads": {"glutes": 0.5, "hamstrings": 0.25},
                "hamstrings": {"glutes": 0.25, "quads": 0.25},
                "glutes": {"hamstrings": 0.25, "quads": 0.25},
            }
        else:
            secondary = {}

        contributions.update(secondary.get(muscle, {}))
        for affected_muscle, fraction in contributions.items():
            if affected_muscle in MUSCLES:
                volume[affected_muscle] = volume.get(affected_muscle, 0.0) + sets * fraction
    return volume


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
        self.used_mobility = {}
        self.volume_cap = SESSION_VOLUME_CAP[profile.experience]

        # Pola gerak prioritas dari fokus otot
        self.priority_patterns = set()
        if self.p.focus_muscles:
            if any(m in ("back", "biceps") for m in self.p.focus_muscles):
                self.priority_patterns.add("pull")
            if any(m in ("chest", "triceps") for m in self.p.focus_muscles):
                self.priority_patterns.add("push")
            if any(m in ("quads", "hamstrings", "glutes", "calves") for m in self.p.focus_muscles):
                self.priority_patterns.add("legs")

        # Otot oposisi terhadap fokus otot pilihan member
        self.opposition_muscles = set()
        for pm in self.p.focus_muscles:
            for opp in OPPOSITION_MAP.get(pm, set()):
                if opp not in self.p.focus_muscles:
                    self.opposition_muscles.add(opp)

    def can_add(self, chosen, ex, sets):
        if len(chosen) >= MAX_SESSION_EXERCISES:
            return False
        pattern = ex["pattern"]
        if pattern in ("push", "pull", "legs") and sum(
            item["ex"]["pattern"] == pattern for item in chosen
        ) >= MAX_PATTERN_EXERCISES:
            return False

        trial = [*chosen, {"ex": ex, "sets": sets}]
        return all(value <= self.volume_cap + 1e-9
                   for value in _effective_set_volume(trial).values())

    def can_increase(self, chosen, item):
        item["sets"] += 1
        allowed = all(value <= self.volume_cap + 1e-9
                      for value in _effective_set_volume(chosen).values())
        item["sets"] -= 1
        return allowed

    def _dynamic_slots_for_block(self, block):
        """Alokasi slot dinamis: otot fokus mendapat alokasi volume/slot lebih besar,
        sedangkan otot oposisi non-prioritas diminimalkan atau dilewati (skipped)
        untuk memecah simetri kaku split template.
        """
        default_slots = block["slots"]
        p = self.p
        if not p.focus_muscles:
            return default_slots

        block_muscles = set(block["muscles"])
        priority_in_block = [m for m in MUSCLES if m in p.focus_muscles and m in block_muscles]
        if not priority_in_block:
            return default_slots

        opposition_in_block = {m for m in self.opposition_muscles if m in block_muscles}
        slot_map = {s["muscle"]: {"main": s["main"], "acc": s["acc"]} for s in default_slots}

        priority_slots = []
        neutral_slots = []
        opposition_slots = []

        # 1. Otot prioritas: alokasikan slot & volume lebih banyak
        for m in priority_in_block:
            base_main = slot_map.get(m, {}).get("main", 0)
            base_acc = slot_map.get(m, {}).get("acc", 0)
            if m in MAJOR:
                new_main = max(2, base_main + 1)
                new_acc = max(1, base_acc + 1)
            else:
                new_main = max(1, base_main)
                new_acc = max(2, base_acc + 1)
            priority_slots.append({"muscle": m, "main": new_main, "acc": new_acc})

        # 2. Otot netral non-prioritas (mis. shoulders bila back & arms yang dipilih)
        for s in default_slots:
            m = s["muscle"]
            if m in priority_in_block or m in opposition_in_block:
                continue
            neutral_slots.append({"muscle": m, "main": min(1, s["main"]), "acc": min(1, s["acc"])})

        # 3. Otot oposisi non-prioritas (mis. chest jika back & arms diprioritaskan)
        # Minimalkan atau lewati (0 main, 0 acc) agar tidak memaksakan simetri kaku
        total_prio = sum(s["main"] + s["acc"] for s in priority_slots)
        for m in opposition_in_block:
            if total_prio >= 4:
                new_main, new_acc = 0, 0
            else:
                new_main, new_acc = 0, 1
            if new_main > 0 or new_acc > 0:
                opposition_slots.append({"muscle": m, "main": new_main, "acc": new_acc})

        return [*priority_slots, *neutral_slots, *opposition_slots]

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

    def pick_conditioning(self, chosen):
        cands = []
        for ex in self.pool:
            if ex["role"] != "conditioning" or ex["name"] in CONDITIONING_EXCLUDED:
                continue
            if any(c["ex"]["id"] == ex["id"] or _too_similar(c["ex"], ex) for c in chosen):
                continue
            score = self.cos[ex["id"]] - 0.12 * self.used.get(ex["id"], 0)
            cands.append((score, ex["name"], ex))
        if not cands:
            return None
        cands.sort(key=lambda t: (-t[0], t[1]))
        return cands[0][2]

    def build(self, block_key, budget_sec, session_index=0):
        block = load_blocks()["blocks"][block_key]
        p = self.p
        chosen = []

        def add(ex, is_main):
            pr = base_prescription(ex, p, is_main)
            while pr["sets"] >= 2:
                if self.can_add(chosen, ex, pr["sets"]):
                    chosen.append({"ex": ex, "main": is_main, **pr})
                    return
                pr["sets"] -= 1

        # 1) Alokasi slot dinamis sesuai bias otot prioritas
        dynamic_slots = self._dynamic_slots_for_block(block)
        for slot in dynamic_slots:
            m = slot["muscle"]
            main_roles = ("main",) if m != "core" else ("core",)
            acc_roles = ("accessory",) if m != "core" else ("core",)
            n_main, n_acc = slot["main"], slot["acc"]
            for _ in range(n_main):
                ex = self.pick(m, main_roles, chosen) or self.pick(m, ("main", "accessory", "core"), chosen)
                if ex:
                    add(ex, True)
            for _ in range(n_acc):
                ex = self.pick(m, acc_roles, chosen) or self.pick(m, ("main", "accessory", "core"), chosen)
                if ex:
                    add(ex, False)
        # latihan power untuk target 4 / performa atletik
        if p.goal_flags["athletic"] and p.experience >= 3 and "quads" in block["muscles"]:
            sj = next((e for e in self.pool if e["name"] == "Squat Jump"), None)
            if sj and not any(c["ex"]["id"] == sj["id"] for c in chosen):
                for sets in range(4, 1, -1):
                    if self.can_add(chosen, sj, sets):
                        chosen.append({"ex": sj, "main": False, "sets": sets, "reps": 5, "seconds": None,
                                       "rest": 90 + p.recovery_bonus, "max_sets": 4})
                        break
        # finisher metabolik untuk tujuan Fat Loss / Ketahanan Jantung (bila kondisi jantung mengizinkan)
        if (p.goal_flags["fat_loss"] or p.goal_flags["cardio"]) and p.cardio_level >= 2 and not p.cardio_caution:
            conditioning = self.pick_conditioning(chosen)
            if conditioning:
                add(conditioning, False)

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
        guard = 0
        while guard < 200:
            guard += 1
            remaining = budget_sec - total()
            if remaining <= 90:
                break
            moved = False
            # (a) tambah set latihan utama sampai batas "target" (maks 4)
            for c in chosen:
                if c["main"] and c["sets"] < min(4, c["max_sets"]) and not c["seconds"] \
                        and self.can_increase(chosen, c):
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
                if len(chosen) >= min(limit, MAX_SESSION_EXERCISES):
                    return False
                muscles = [m for m in block["muscles"] if m in self.by_muscle] or ["core"]
                muscles = [m for m in muscles if m.split("(")[0] in MUSCLES]
                tm = p.focus_muscles
                opps = self.opposition_muscles
                allowed_muscles = [m for m in muscles if m not in opps] or muscles
                counts = {m: sum(1 for c in chosen if c["ex"]["primary_muscle"] == m) for m in allowed_muscles}
                order = sorted(allowed_muscles, key=lambda m: (counts[m] - (2.0 if m in tm else 0), m))
                for m in order:
                    ex = self.pick(m, ("main", "accessory", "core"), chosen)
                    if not ex:
                        continue
                    is_main = ex["role"] == "main"
                    pr = base_prescription(ex, p, is_main)
                    if not self.can_add(chosen, ex, pr["sets"]):
                        continue
                    dt = exercise_seconds(ex, pr["sets"], pr["reps"], pr["seconds"], pr["rest"])
                    if dt <= remaining:
                        chosen.append({"ex": ex, "main": is_main, **pr})
                        return True
                return False
            if add_extra(6):
                continue
            for c in chosen:
                if not c["main"] and c["sets"] < c["max_sets"] and not c["seconds"] \
                        and self.can_increase(chosen, c):
                    dt = exercise_seconds(c["ex"], c["sets"] + 1, c["reps"], c["seconds"], c["rest"]) - \
                         exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"])
                    if dt <= remaining:
                        c["sets"] += 1
                        moved = True
                        break
            if moved:
                continue
            if add_extra(MAX_SESSION_EXERCISES):
                continue
            for c in chosen:
                if c["main"] and c["sets"] < c["max_sets"] and not c["seconds"] \
                        and self.can_increase(chosen, c):
                    dt = exercise_seconds(c["ex"], c["sets"] + 1, c["reps"], c["seconds"], c["rest"]) - \
                         exercise_seconds(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"])
                    if dt <= remaining:
                        c["sets"] += 1
                        moved = True
                        break
            if moved:
                continue
            break

        for c in chosen:
            self.used[c["ex"]["id"]] = self.used.get(c["ex"]["id"], 0) + 1
        return self._render(block_key, block, chosen, session_index)

    # ---- pemanasan / pendinginan: hanya memakai alat yang lolos filter keamanan ----
    def _cardio_equipment(self):
        order = (["static_bike", "elliptical", "treadmill"] if self.p.low_impact
                 else ["treadmill", "static_bike", "elliptical"])
        available = {e["id"]: e for e in self.pool if e["role"] == "cardio"}
        return next((available[i] for i in order if i in available), None)

    def _warmup_cooldown(self):
        machine = self._cardio_equipment()
        if machine:
            warm = {"name": f"{machine['name']} (intensitas ringan-sedang)", "purpose": "Pemanasan",
                    "est_seconds": WARMUP_SEC, "est_text": "5 menit"}
            cool = {"name": f"{machine['name']} (intensitas sangat ringan)", "purpose": "Pendinginan",
                    "est_seconds": COOLDOWN_SEC, "est_text": "5 menit"}
            return warm, cool
        if any(e["name"] == "Jumping Jack" for e in self.pool):
            warm_name = "Jumping Jack & mobilitas sendi"
        else:
            warm_name = "Jalan di tempat & gerak sendi ringan (hindari area yang nyeri)"
        warm = {"name": warm_name, "purpose": "Pemanasan", "est_seconds": WARMUP_SEC, "est_text": "5 menit"}
        cool = {"name": "Peregangan statis ringan (hindari area yang nyeri)", "purpose": "Pendinginan",
                "est_seconds": COOLDOWN_SEC, "est_text": "5 menit"}
        return warm, cool

    # ---- blok tambahan di luar durasi sesi resistance ----
    def _cardio_block(self, session_index):
        p = self.p
        if "cardio" not in p.modalities:
            return None
        options = sorted((e for e in self.pool if e["role"] == "cardio"),
                         key=lambda e: (e["impact_level"], e["difficulty"], e["name"]))
        if not options:
            return None
        if p.low_impact or p.cardio_level == 1:
            ex = options[0]
        else:
            ex = options[session_index % len(options)]
        flags = p.goal_flags
        minutes = 10 + (5 if flags["fat_loss"] else 0) + (5 if flags["cardio"] else 0) \
            + (5 if p.anthro["metabolic_priority"] else 0)
        minutes = min(minutes, 15 if (p.cardio_level == 1 or p.cardio_caution) else 20)
        if p.cardio_level == 1 or p.cardio_caution:
            intensity = "Zona 1-2 (ringan, masih bisa berbicara penuh)"
        elif p.cardio_level == 3 and flags["cardio"] and p.experience >= 2:
            intensity = "Interval: 1 menit cepat, 2 menit santai"
        else:
            intensity = "Zona 2 (sedang, masih bisa berbicara)"
        seconds = minutes * 60
        return {"id": ex["id"], "name": ex["name"], "minutes": minutes, "intensity": intensity,
                "est_seconds": seconds, "est_text": fmt_mmss(seconds)}

    def _mobility_block(self, chosen):
        p = self.p
        if "mobility" not in p.modalities:
            return None
        options = [e for e in self.pool if e["role"] == "mobility"]
        if not options:
            return None
        sets_by_muscle = {}
        for c in chosen:
            muscle = c["ex"]["primary_muscle"]
            sets_by_muscle[muscle] = sets_by_muscle.get(muscle, 0) + c["sets"]
        picked, total = [], 0

        def cost(ex):
            return MOBILITY_SETS * MOBILITY_HOLD_SEC * (2 if ex["unilateral"] else 1) + MOBILITY_TRANSITION_SEC

        def take(ex):
            nonlocal total
            if ex in picked or total + cost(ex) > MOBILITY_MAX_SEC:
                return False
            picked.append(ex)
            total += cost(ex)
            return True

        for muscle in sorted(sets_by_muscle, key=lambda m: -sets_by_muscle[m]):
            if total >= MOBILITY_MIN_SEC:
                break
            cands = sorted((e for e in options if e["primary_muscle"] == muscle),
                           key=lambda e: (self.used_mobility.get(e["id"], 0), e["name"]))
            if cands:
                take(cands[0])
        if total < MOBILITY_MIN_SEC:
            general = sorted((e for e in options if e["id"] in ("cat_cow", "childs_pose", "figure_four_stretch",
                                                               "thoracic_rotation", "lying_knee_to_chest")),
                             key=lambda e: (self.used_mobility.get(e["id"], 0), e["name"]))
            for ex in general:
                if total >= MOBILITY_MIN_SEC:
                    break
                take(ex)
        if not picked:
            return None
        lines = []
        for ex in picked:
            self.used_mobility[ex["id"]] = self.used_mobility.get(ex["id"], 0) + 1
            lines.append({"id": ex["id"], "name": ex["name"],
                          "muscle": MUSCLE_LABEL.get(ex["primary_muscle"], ex["primary_muscle"]),
                          "sets": MOBILITY_SETS, "seconds_per_set": MOBILITY_HOLD_SEC,
                          "unilateral": ex["unilateral"], "est_seconds": cost(ex)})
        return {"exercises": lines, "est_seconds": total, "minutes": round(total / 60, 1),
                "est_text": fmt_mmss(total)}

    def _render(self, block_key, block, chosen, session_index):
        p = self.p
        lines = []
        exs_total = 0
        for c in chosen:
            line = exercise_line(c["ex"], c["sets"], c["reps"], c["seconds"], c["rest"], p, self.cos[c["ex"]["id"]])
            exs_total += line["est_seconds"]
            lines.append(line)
        warm, cool = self._warmup_cooldown()
        cardio = self._cardio_block(session_index)
        mobility = self._mobility_block(chosen)
        total = WARMUP_SEC + exs_total + COOLDOWN_SEC
        addon_sec = (cardio["est_seconds"] if cardio else 0) + (mobility["est_seconds"] if mobility else 0)
        return {"block": block_key, "label": block["label"], "warmup": warm, "exercises": lines,
                "cooldown": cool, "cardio_block": cardio, "mobility_block": mobility,
                "effective_sets": {MUSCLE_LABEL[m]: round(value, 1)
                                   for m, value in _effective_set_volume(chosen).items()},
                "total_seconds": total, "total_minutes": round(total / 60, 1),
                "addon_seconds": addon_sec, "total_with_addons_minutes": round((total + addon_sec) / 60, 1)}


# --------------------------------------------------------------------------
# API utama
# --------------------------------------------------------------------------
def _weekly_overlap(a, b):
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0


def _movement_balance(sessions, profile=None):
    """Penalize a session for concentrating too many exercises in one movement pattern.
    Jika user memilih fokus otot prioritas (mis. Back & Arms -> pull pattern),
    konsentrasi pola tersebut diperbolehkan dan tidak dipenalti secara kaku.
    """
    priority_patterns = set()
    if profile and profile.focus_muscles:
        if any(m in ("back", "biceps") for m in profile.focus_muscles):
            priority_patterns.add("pull")
        if any(m in ("chest", "triceps") for m in profile.focus_muscles):
            priority_patterns.add("push")
        if any(m in ("quads", "hamstrings", "glutes", "calves") for m in profile.focus_muscles):
            priority_patterns.add("legs")

    scores = []
    for session in sessions:
        patterns = [exercise["pattern"] for exercise in session["exercises"]
                    if exercise["pattern"] in ("push", "pull", "legs")]
        if not patterns:
            continue
        counts = {}
        for pattern in patterns:
            counts[pattern] = counts.get(pattern, 0) + 1
        repeated = sum(max(0, count - (4 if pattern in priority_patterns else 2)) for pattern, count in counts.items())
        scores.append(max(0.0, 1 - repeated / len(patterns)))
    return sum(scores) / len(scores) if scores else 1.0


def _limitation_meta(profile):
    lim = profile.limits
    return {"labels": lim["labels"], "items": lim["items"], "excluded_joints": lim["excluded_joints"],
            "unrecognized": lim["unrecognized"], "negated": lim["negated"], "regions": lim["regions"]}


def _referral_result(profile, warnings, extra_reason=None, filt=None):
    meta = {"profile": profile.summary(), "limitations": _limitation_meta(profile)}
    if filt is not None:
        meta["filter"] = filt
    return {"programs": [], "warnings": warnings,
            "referral": referral_message(profile.limits, extra_reason), "meta": meta}


def generate(profile_dict, top_n=3):
    profile = Profile(profile_dict)
    if profile.physical and profile.limits["referral"]["required"]:
        return _referral_result(profile, [])
    pool, warnings, filt = filter_exercises(profile)

    def no_program(reason):
        if profile.physical:
            return _referral_result(profile, warnings, reason, filt)
        return {"programs": [], "warnings": warnings + [reason],
                "meta": {"filter": filt, "profile": profile.summary()}}

    resistance = [ex for ex in pool if ex["role"] in RESISTANCE_ROLES]
    if not resistance:
        return no_program("Tidak ada latihan yang cocok dengan batasan Anda.")
    pools = {}
    for ex in resistance:
        pools.setdefault(ex["primary_muscle"], []).append(ex)
    cands, unreachable, tier, required_sel = rank_combos(profile, pools)
    if unreachable:
        warnings.append("Latihan untuk " + ", ".join(MUSCLE_LABEL[m] for m in unreachable) +
                        " tidak tersedia dengan batasan yang dipilih.")
    if not cands:
        return no_program("Tidak ditemukan kombinasi split yang memenuhi aturan.")
    if tier > 0:
        warnings.append(f"Dengan {profile.days} hari latihan per minggu, tidak semua bagian tubuh "
                        "bisa dilatih secara penuh. Program disusun semaksimal mungkin; tambah hari latihan "
                        "bila ingin cakupan lebih lengkap.")
    wvec = profile_vector(profile)
    budget = profile.session_minutes * 60 - WARMUP_SEC - COOLDOWN_SEC

    built = []
    for cand in cands:
        sb = SessionBuilder(profile, pool, wvec)
        sessions = [sb.build(b, budget, idx) for idx, b in enumerate(cand["order"])]
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
        movement_balance = _movement_balance(sessions, profile)
        if profile.focus_muscles:
            focus_ex_count = sum(1 for s in sessions for e in s["exercises"] if e.get("muscle_key") in profile.focus_muscles)
            total_ex_count = sum(len(s["exercises"]) for s in sessions) or 1
            focus_satisfaction = focus_ex_count / total_ex_count
            w_balance = 0.02
            w_focus = 0.15
            final = (cand["base"] + WEIGHTS["exercise_cos"] * ex_cos
                     + WEIGHTS["time_fill"] * time_fill
                     + w_balance * movement_balance
                     + w_focus * focus_satisfaction)
        else:
            final = (cand["base"] + WEIGHTS["exercise_cos"] * ex_cos
                     + WEIGHTS["time_fill"] * time_fill
                     + WEIGHTS["movement_balance"] * movement_balance)
        built.append({**cand, "sessions": sessions, "ex_cos": ex_cos, "time_fill": time_fill,
                      "movement_balance": movement_balance, "final": final})
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

    # Pastikan program terurut tegas dari skor kecocokan tertinggi ke terendah (Top 1, Top 2, Top 3)
    selected.sort(key=lambda b: -b["final"])

    if not selected:
        return no_program("Tidak dapat menyusun sesi yang memenuhi batasan Anda.")
    best_avg = max(sum(x["total_minutes"] for x in b["sessions"]) / len(b["sessions"]) for b in selected)
    if profile.session_minutes - best_avg > 8:
        warnings.append(f"Dengan fasilitas dan batasan yang dipilih, rata-rata durasi sesi program yang "
                        f"direkomendasikan sekitar {int(best_avg)} menit (target {profile.session_minutes} menit). "
                        "Beberapa sesi dapat lebih panjang atau lebih pendek; program tetap mengikuti batas waktu Anda.")
    flags = profile.goal_flags
    wants_cardio = flags["fat_loss"] or flags["cardio"] or profile.anthro["metabolic_priority"]
    if wants_cardio and "cardio" not in profile.modalities:
        warnings.append("Saran: tujuan dan data tubuh Anda akan terbantu dengan Cardio. "
                        "Aktifkan opsi Cardio pada preferensi modalitas untuk menambahkan blok kardio di luar durasi sesi.")
    if profile.recovery_bonus:
        warnings.append(f"Jeda antar set ditambah {profile.recovery_bonus} detik karena kondisi pemulihan Anda "
                        "(lemak tubuh tinggi, ketahanan kardio rendah, atau kondisi medis).")
    focus = [FOCUS_LABEL[f] for f in profile.focus] or ["Seimbang (seluruh tubuh)"]
    programs = []
    for i, b in enumerate(selected):
        weekly = sum(s["total_seconds"] for s in b["sessions"])
        weekly_addon = sum(s["addon_seconds"] for s in b["sessions"])
        programs.append({
            "name": f"Program {chr(65 + i)}",
            "frequency_days": profile.days,
            "session_minutes_target": profile.session_minutes,
            "avg_session_minutes": round(sum(s["total_minutes"] for s in b["sessions"]) / len(b["sessions"]), 1),
            "weekly_minutes": round(weekly / 60),
            "weekly_addon_minutes": round(weekly_addon / 60),
            "split": b["label"],
            "focus": focus,
            "primary_target_label": PRIMARY_LABEL[profile.primary_target],
            "modalities": ["resistance", *sorted(profile.modalities)],
            "sessions": b["sessions"],
            "time_model": {"fatigue_buffer": FATIGUE_BUFFER, "transition_sec": TRANSITION_SEC,
                           "warmup_sec": WARMUP_SEC, "cooldown_sec": COOLDOWN_SEC},
            "scores": {"final": round(b["final"], 3), "split_cosine": round(b["cos"], 3),
                       "freq_fit": round(b["fit"], 3), "recovery": round(b["recovery"], 3),
                       "exercise_cosine_mean": round(b["ex_cos"], 3), "time_fill": round(b["time_fill"], 3),
                       "movement_balance": round(b["movement_balance"], 3)},
            "exposure": {MUSCLE_LABEL[m]: v for m, v in b["exposure"].items() if v > 0},
            "uncovered_targets": [MUSCLE_LABEL[m] for m in required_sel if b["exposure"][m] < 0.5],
        })
    return {"programs": programs, "warnings": warnings,
            "meta": {"filter": filt, "candidates_ranked": len(cands), "exercise_pool": len(pool),
                     "weights": WEIGHTS,
                     "profile": profile.summary(),
                     "limitations": _limitation_meta(profile),
                     "time_model": {
                         "setup_seconds_by_level": SETUP_SEC,
                         "transition_seconds_per_exercise": TRANSITION_SEC,
                         "work_fatigue_buffer_percent": int(FATIGUE_BUFFER * 100),
                         "warmup_seconds": WARMUP_SEC,
                         "cooldown_seconds": COOLDOWN_SEC,
                     },
                     "limits": {
                         "max_exercises_per_session": MAX_SESSION_EXERCISES,
                         "max_effective_sets_per_muscle": SESSION_VOLUME_CAP[profile.experience],
                         "max_exercises_per_movement_pattern": MAX_PATTERN_EXERCISES,
                         "session_minutes_range": [MIN_SESSION_MINUTES, MAX_SESSION_MINUTES],
                     }}}
