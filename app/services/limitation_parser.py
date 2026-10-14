"""
Parser keluhan fisik berbasis kata kunci (rule-based NLP, tanpa LLM).

Alur per kalimat (dipisah oleh titik / tanda tanya / tanda seru / baris baru / kata sambung "tapi"):
  1. Normalisasi teks & koreksi typo (elongasi huruf, ejaan fonetik, difflib fuzzy).
  2. Lapisan pra-pemeriksaan disambiguasi semantik (membedakan nyeri muskuloskeletal vs waspada sistemik/kardiovaskular).
  3. Cari kata KELUHAN (sakit, nyeri, cedera, kaku, ...) -> tingkat keparahan.
  4. Cari BAGIAN TUBUH (pergelangan tangan, betis, lutut, ...) -> area + sendi yang dibatasi.
  5. Cari KONDISI MEDIS (HNP, hipertensi, jantung, ...) -> berdiri sendiri.
  6. Keluhan + bagian tubuh => label otomatis, mis. "Sakit Betis (Area Tubuh Bawah)".
  7. Kalimat bernada negasi ("tidak sakit") diabaikan; "tidak bisa/susah" dihitung sebagai keluhan.
  8. Bila keluhan terlalu banyak / berisiko tinggi => rekomendasi rujukan ke Personal Trainer / tenaga medis.
"""

from functools import lru_cache
import difflib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ==============================================================================
# 1. KONSTANTA WILAYAH ANATOMI, SENDI, & TINGKAT KEPARAHAN
# ==============================================================================

REGIONS: Dict[str, str] = {
    "upper": "Area Tubuh Atas",
    "lower": "Area Tubuh Bawah",
    "trunk": "Area Batang Tubuh / Tulang Belakang",
    "systemic": "Kondisi Medis Spesifik / Sistemik",
}

JOINT_LABEL: Dict[str, str] = {
    "shoulder": "bahu",
    "knee": "lutut",
    "lower_back": "punggung bawah",
    "elbow": "siku",
    "wrist": "pergelangan tangan",
    "hip": "pinggul",
    "neck": "leher",
    "ankle": "pergelangan kaki",
}

SEVERITY_RANK: Dict[str, int] = {
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}

# ==============================================================================
# 2. KAMUS KELUHAN, BAGIAN TUBUH, & KONDISI MEDIS
# ==============================================================================

# Gejala / keluhan fisik: (daftar kata kunci, label, tingkat keparahan)
SYMPTOMS: List[Tuple[List[str], str, str]] = [
    (["pegal", "tegang"], "Pegal", "mild"),
    (["kaku", "stiff"], "Kaku", "mild"),
    (["linu"], "Linu", "mild"),
    (["sakit", "pain", "painful"], "Sakit", "moderate"),
    (["nyeri", "ache"], "Nyeri", "moderate"),
    (["ngilu"], "Ngilu", "moderate"),
    (["kesemutan"], "Kesemutan", "moderate"),
    (["bengkak", "swelling"], "Bengkak", "moderate"),
    (["radang", "inflamasi"], "Radang", "moderate"),
    (["terkilir", "keseleo", "sprain"], "Terkilir", "moderate"),
    (["ketarik", "tertarik", "strain"], "Tertarik", "moderate"),
    (["kram", "kejang otot", "spasme", "cramp"], "Kram", "moderate"),
    (["memar"], "Memar", "moderate"),
    (["lemah"], "Lemah", "moderate"),
    (["cedera", "cidera", "injury", "injured"], "Cedera", "moderate"),
    (["keterbatasan"], "Keterbatasan", "moderate"),
    (["keluhan"], "Keluhan", "mild"),
    (["patah", "retak", "fracture"], "Patah", "severe"),
    (["robek", "sobek", "torn"], "Robek", "severe"),
    (["dislokasi", "terkilir parah"], "Dislokasi", "severe"),
    (["operasi", "pasca operasi", "surgery"], "Pasca Operasi", "severe"),
    (["mati rasa", "numb"], "Mati Rasa", "severe"),
]

# Frasa kemampuan gerak yang menurun -> dihitung sebagai keluhan fungsional
ABILITY_PHRASES: List[str] = [
    "tidak bisa", "tidak dapat", "tidak kuat", "tidak mampu",
    "nggak bisa", "gak bisa", "ngga bisa",
    "susah", "sulit", "kesulitan", "cannot", "can't", "unable"
]

# Kata-kata penyangkal (negasi)
NEGATORS: List[str] = [
    "tidak ada", "tidak", "tak", "bukan", "tanpa",
    "nggak", "ngga", "gak", "belum", "bebas dari",
    "no", "not", "without"
]

# Bagian tubuh: (daftar kata kunci, label, area anatomis, himpunan sendi yang dibatasi)
# Frasa panjang diletakkan di awal agar diprioritaskan
BODY_PARTS: List[Tuple[List[str], str, str, Set[str]]] = [
    (["pergelangan tangan", "wrist"], "Pergelangan Tangan", "upper", {"wrist"}),
    (["telapak tangan", "jari tangan", "tangan", "jari", "hand", "finger"], "Tangan", "upper", {"wrist"}),
    (["lengan bawah", "forearm"], "Lengan Bawah", "upper", {"elbow", "wrist"}),
    (["siku", "elbow"], "Siku", "upper", {"elbow"}),
    (["lengan", "bisep", "biseps", "trisep", "triseps", "arm"], "Lengan", "upper", {"elbow"}),
    (["bahu", "pundak", "shoulder"], "Bahu", "upper", {"shoulder"}),
    (["dada", "chest"], "Dada", "upper", {"shoulder"}),
    (["leher", "servikal", "neck"], "Leher", "upper", {"neck"}),
    (["punggung atas", "upper back"], "Punggung Atas", "trunk", {"shoulder", "neck"}),
    (["punggung bawah", "pinggang", "lumbar", "lower back"], "Punggung Bawah", "trunk", {"lower_back"}),
    (["tulang belakang", "spine", "punggung", "back"], "Punggung", "trunk", {"lower_back"}),
    (["perut", "abdomen", "stomach"], "Perut", "trunk", {"lower_back"}),
    (["saraf", "nerve"], "Saraf", "trunk", {"lower_back"}),
    (["pinggul", "panggul", "selangkangan", "hip", "groin"], "Pinggul", "lower", {"hip"}),
    (["paha", "thigh", "hamstring", "quadriceps"], "Paha", "lower", {"hip", "knee"}),
    (["tempurung lutut", "lutut", "knee", "patella"], "Lutut", "lower", {"knee"}),
    (["betis", "calf"], "Betis", "lower", {"ankle"}),
    (["pergelangan kaki", "mata kaki", "engkel", "ankle"], "Pergelangan Kaki", "lower", {"ankle"}),
    (["tumit", "achilles", "heel"], "Tumit", "lower", {"ankle"}),
    (["telapak kaki", "jari kaki", "foot"], "Telapak Kaki", "lower", {"ankle"}),
    (["kaki", "tungkai", "leg"], "Kaki", "lower", {"ankle", "knee"}),
]

# Diagnosis spesifik yang sudah mencakup bagian tubuh + keluhan
CONDITIONS: List[Tuple[List[str], str, str, Set[str], str]] = [
    (["hnp", "saraf kejepit", "hernia", "ischias", "sciatica", "herniated"], "Saraf Kejepit / HNP", "trunk", {"lower_back"}, "severe"),
    (["skoliosis", "scoliosis"], "Skoliosis", "trunk", {"lower_back"}, "moderate"),
    (["osteoporosis"], "Osteoporosis", "trunk", {"lower_back", "hip"}, "moderate"),
    (["acl", "meniskus", "meniscus"], "Cedera Ligamen / Meniskus Lutut", "lower", {"knee"}, "severe"),
    (["rotator cuff"], "Rotator Cuff", "upper", {"shoulder"}, "severe"),
    (["tennis elbow", "tenis elbow", "golfer's elbow"], "Tennis / Golfer's Elbow", "upper", {"elbow"}, "moderate"),
    (["carpal tunnel"], "Carpal Tunnel", "upper", {"wrist"}, "moderate"),
    (["asam urat", "gout"], "Asam Urat", "lower", {"knee", "ankle"}, "moderate"),
]

# Kondisi medis umum / sistemik: risk "high" => wajib rujukan, "medium" => modifikasi beban kardio
SYSTEMIC: List[Tuple[List[str], str, str]] = [
    (["gagal jantung", "penyakit jantung", "jantung", "aritmia", "heart"], "Kondisi Jantung", "high"),
    (["stroke"], "Riwayat Stroke", "high"),
    (["hamil", "kehamilan", "pregnan"], "Kehamilan", "high"),
    (["epilepsi", "epilepsy"], "Epilepsi", "high"),
    (["gagal ginjal"], "Gagal Ginjal", "high"),
    (["hipertensi", "darah tinggi", "tekanan darah", "hypertension"], "Hipertensi", "medium"),
    (["asma", "asthma", "sesak napas", "sesak nafas", "sesak", "pernapasan"], "Gangguan Pernapasan", "medium"),
    (["diabetes", "kencing manis"], "Diabetes", "medium"),
    (["vertigo"], "Vertigo", "medium"),
    (["kolesterol"], "Kolesterol Tinggi", "medium"),
]

# Ambang rujukan Personal Trainer / Tenaga Medis
REFERRAL_MAX_JOINTS: int = 3          # >= 3 jenis sendi berbeda terbatas
REFERRAL_MAX_SEVERE: int = 2          # >= 2 keluhan berstatus berat

# ==============================================================================
# 3. PRA-PEMROSESAN TEKS & KOREKSI TYPO (FONETIK & FUZZY)
# ==============================================================================

INDONESIAN_SPELLING_VARIANTS: Dict[str, str] = {
    # f/v -> p loanwords & common colloquial spelling variants
    r"\bpernafasan\b": "pernapasan",
    r"\bnafas\b": "napas",
    r"\bsyaraf\b": "saraf",
    r"\bcidera\b": "cedera",
    r"\bpingang\b": "pinggang",
    r"\bkesleo\b": "keseleo",
    r"\bpegel\b": "pegal",
    r"\bencok\b": "asam urat",
    r"\bkramm+\b": "kram",
    r"\bpusing\b": "vertigo",
}

# Pola regex variasi ejaan terkompilasi di tingkat modul
_COMPILED_SPELLING_VARIANTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern), replacement)
    for pattern, replacement in INDONESIAN_SPELLING_VARIANTS.items()
]

# Kosakata kata tunggal (panjang >= 4) yang diekstrak sekali dari semua tabel kamus
_DOMAIN_VOCABULARY: Set[str] = set()
for _table in (CONDITIONS, SYSTEMIC, BODY_PARTS, SYMPTOMS):
    for _entry in _table:
        for _keyword in _entry[0]:
            for _word in _keyword.split():
                if len(_word) >= 4:
                    _DOMAIN_VOCABULARY.add(_word)

_DOMAIN_VOCAB_LIST: List[str] = sorted(_DOMAIN_VOCABULARY)

# Pola regex umum yang digunakan berulang
_RE_ELONGATION: re.Pattern = re.compile(r"(.)\1{2,}")
_RE_TRAILING_CONSONANTS: re.Pattern = re.compile(r"([bcdfghjklmnpqrstvwxyz])\1+\b")
_RE_MULTIPLE_SPACES: re.Pattern = re.compile(r"\s+")
_RE_ALPHANUMERIC: re.Pattern = re.compile(r"[^a-z0-9]")
_RE_CLAUSE_SPLIT: re.Pattern = re.compile(r"[.!?;\n]+")
_RE_CONJUNCTION_SPLIT: re.Pattern = re.compile(r"\b(?:tapi|tetapi|namun|but)\b", flags=re.IGNORECASE)

# Pola regex untuk lapisan disambiguasi
_RE_CHEST: re.Pattern = re.compile(r"\b(dada|chest)\b")
_RE_ABDOMEN: re.Pattern = re.compile(r"\b(perut|abdomen|ulu\s+hati|lambung)\b")
_RE_AMBIGUOUS_KEYWORDS: re.Pattern = re.compile(r"\b(dada|chest|perut|abdomen|ulu\s+hati|lambung)\b")


@lru_cache(maxsize=512)
def _pattern(keyword: str) -> re.Pattern:
    """Mengompilasi dan meng-cache pola regex batas kata untuk kata kunci pencarian."""
    body = r"\s+".join(re.escape(part) for part in keyword.split())
    tail = r"(?![a-z])" if len(keyword) <= 4 else r"[a-z]*"
    return re.compile(r"(?<![a-z])" + body + tail)


def normalize_text(text: str) -> str:
    """Normalisasi fonetik, penyingkatan huruf berulang, dan pembersihan spasi."""
    if not text:
        return ""
    normalized = text.lower().strip()
    # 1. Kompresi karakter berulang (sakiiit -> sakit, pegasaal -> pegal)
    normalized = _RE_ELONGATION.sub(r"\1", normalized)
    # 2. Kompresi konsonan ganda di akhir kata (sakitt -> sakit, lututt -> lutut)
    normalized = _RE_TRAILING_CONSONANTS.sub(r"\1", normalized)
    # 3. Penggantian variasi ejaan standar menggunakan pola terkompilasi
    for compiled_pattern, replacement in _COMPILED_SPELLING_VARIANTS:
        normalized = compiled_pattern.sub(replacement, normalized)
    return _RE_MULTIPLE_SPACES.sub(" ", normalized)


def fuzzy_correct_tokens(text: str, cutoff: float = 0.82) -> str:
    """Koreksi typo kata tunggal menggunakan difflib terhadap domain vocabulary."""
    tokens = text.split()
    corrected = []
    for token in tokens:
        clean_token = _RE_ALPHANUMERIC.sub("", token)
        if len(clean_token) >= 4 and clean_token not in _DOMAIN_VOCABULARY:
            match = difflib.get_close_matches(clean_token, _DOMAIN_VOCAB_LIST, n=1, cutoff=cutoff)
            if match:
                token = token.replace(clean_token, match[0])
        corrected.append(token)
    return " ".join(corrected)


def _find(text: str, keywords: List[str], consumed: List[Tuple[int, int]]) -> List[Tuple[int, str]]:
    """Cari kemunculan kata kunci yang belum terpakai (rentang tidak tumpang tindih)."""
    hits = []
    for kw in sorted(keywords, key=len, reverse=True):
        for m in _pattern(kw).finditer(text):
            span = (m.start(), m.end())
            if any(span[0] < c[1] and c[0] < span[1] for c in consumed):
                continue
            consumed.append(span)
            hits.append((m.start(), kw))
    return hits


def split_clauses(text: str) -> List[str]:
    """Pecah teks menjadi kalimat/klausa. Titik adalah pemisah utama."""
    clean_text = (text or "").replace("\r", "\n")
    parts = _RE_CLAUSE_SPLIT.split(clean_text)
    clauses = []
    for part in parts:
        for sub in _RE_CONJUNCTION_SPLIT.split(part):
            clean_sub = sub.strip(" ,-\t")
            if clean_sub:
                clauses.append(clean_sub)
    return clauses


def _negated(clause: str, first_signal_pos: int) -> bool:
    """Mengecek apakah ada kata negasi sebelum posisi kemunculan kata kunci keluhan."""
    before = clause[:first_signal_pos]
    return any(_pattern(n).search(before) for n in NEGATORS)


# ==============================================================================
# 4. LAPISAN DISAMBIGUASI SEMANTIK (INTERCEPTOR DADA & PERUT)
# ==============================================================================

MUSCULAR_MODIFIERS: Set[str] = {
    "otot", "musculus", "doms", "pegal", "kram", "kaku",
    "ketarik", "tertarik", "tegang", "habis latihan", "habis workout", "habis gym",
    "pasca latihan", "latihan", "bench press", "sit up", "squat", "deadlift"
}

VISCERAL_RED_FLAGS: Set[str] = {
    "sesak", "tembus", "menjalar", "tertekan", "ditekan", "berat",
    "panas", "terbakar", "berdebar", "mual", "muntah", "keringat dingin",
    "melilit", "menusuk", "ulu hati", "lambung", "jantung"
}

_EXPLICIT_MUSCULAR_PHRASES: Tuple[str, ...] = (
    "habis latihan", "habis workout", "habis gym", "pasca latihan",
    "nyeri otot", "otot dada", "otot perut"
)

_EXPLICIT_VISCERAL_PHRASES: Tuple[str, ...] = (
    "ulu hati", "sesak napas", "sesak nafas", "keringat dingin", "tembus ke belakang"
)


def disambiguate_clause(clause: str, original: str) -> Optional[Dict[str, Any]]:
    """Interceptor sebelum pencarian kamus umum untuk mendisambiguasi dada & perut:
    - Dada: Muskuloskeletal (Pectoralis strain/DOMS) vs Kardiovaskular (Angina/Iskemia)
    - Perut: Muskuloskeletal (Abdominal wall DOMS) vs Viseral/Pencernaan (Ulu hati/Kolik)
    """
    has_chest = bool(_RE_CHEST.search(clause))
    has_abdomen = bool(_RE_ABDOMEN.search(clause))

    if not (has_chest or has_abdomen):
        return None

    tokens = set(clause.split())
    has_muscular = bool(tokens & MUSCULAR_MODIFIERS) or any(
        phrase in clause for phrase in _EXPLICIT_MUSCULAR_PHRASES
    )
    has_visceral = bool(tokens & VISCERAL_RED_FLAGS) or any(
        phrase in clause for phrase in _EXPLICIT_VISCERAL_PHRASES
    )

    if has_chest:
        if has_muscular and not has_visceral:
            return {
                "sentence": original,
                "label": "Nyeri Otot Dada",
                "symptom": "Nyeri Otot",
                "severity": "mild" if ("pegal" in tokens or "doms" in tokens) else "moderate",
                "kind": "complaint",
                "area_key": "upper",
                "area": REGIONS["upper"],
                "joints": ["shoulder"],
                "risk": None,
                "disambiguation": "musculoskeletal",
            }
        else:
            return {
                "sentence": original,
                "label": "Nyeri Dada (Waspada Kardiovaskular)",
                "symptom": "Nyeri Dada",
                "severity": "severe",
                "kind": "systemic",
                "area_key": "systemic",
                "area": REGIONS["systemic"],
                "joints": [],
                "risk": "high",
                "disambiguation": "systemic_cardiac",
            }

    if has_abdomen:
        if has_muscular and not has_visceral and "ulu hati" not in clause and "lambung" not in clause:
            return {
                "sentence": original,
                "label": "Pegal/Kram Otot Perut",
                "symptom": "Pegal Otot",
                "severity": "mild" if "pegal" in tokens else "moderate",
                "kind": "complaint",
                "area_key": "trunk",
                "area": REGIONS["trunk"],
                "joints": ["lower_back"],
                "risk": None,
                "disambiguation": "musculoskeletal",
            }
        else:
            return {
                "sentence": original,
                "label": "Keluhan Perut / Viseral (Pencernaan / Ulu Hati)",
                "symptom": "Nyeri Viseral",
                "severity": "moderate",
                "kind": "systemic",
                "area_key": "systemic",
                "area": REGIONS["systemic"],
                "joints": [],
                "risk": "medium",
                "disambiguation": "visceral_gastro",
            }

    return None


# ==============================================================================
# 5. FUNGSI UTAMA PARSER KELUHAN FISIK
# ==============================================================================

def parse_limitations(text: str) -> Dict[str, Any]:
    """Menganalisis teks cerita keluhan fisik member dan memetakannya ke entitas pembatasan."""
    items: List[Dict[str, Any]] = []
    unrecognized: List[Dict[str, str]] = []
    negated: List[str] = []
    seen: Set[Tuple[str, str]] = set()

    def add(item: Dict[str, Any]) -> None:
        key = (item["label"], item["area_key"])
        if key in seen:
            return
        seen.add(key)
        items.append(item)

    for original in split_clauses(text):
        clause = normalize_text(original)
        clause = fuzzy_correct_tokens(clause)
        consumed: List[Tuple[int, int]] = []

        # 1. Lapisan Pra-Pemeriksaan Disambiguasi (Semantic Interceptor)
        intercepted = disambiguate_clause(clause, original)
        if intercepted:
            kw_match = _RE_AMBIGUOUS_KEYWORDS.search(clause)
            sig_pos = kw_match.start() if kw_match else len(clause)
            if _negated(clause, sig_pos):
                negated.append(original)
            else:
                add(intercepted)
            continue

        # 2. Deteksi Kamus Umum
        condition_hits = []
        for keywords, label, region, joints, severity in CONDITIONS:
            for pos, _ in _find(clause, keywords, consumed):
                condition_hits.append((pos, label, region, joints, severity))

        systemic_hits = []
        for keywords, label, risk in SYSTEMIC:
            for pos, _ in _find(clause, keywords, consumed):
                systemic_hits.append((pos, label, risk))

        part_hits = []
        for keywords, label, region, joints in BODY_PARTS:
            for pos, _ in _find(clause, keywords, consumed):
                part_hits.append((pos, label, region, joints))

        symptom_hits = []
        for keywords, label, severity in SYMPTOMS:
            for pos, _ in _find(clause, keywords, consumed):
                symptom_hits.append((pos, label, severity))

        ability = any(_pattern(p).search(clause) for p in ABILITY_PHRASES)
        if ability and not symptom_hits:
            symptom_hits.append((0, "Keterbatasan Gerak", "moderate"))
            ability_only = True
        else:
            ability_only = False

        signals = [h[0] for h in condition_hits + systemic_hits + symptom_hits]
        if not (signals or part_hits):
            unrecognized.append({
                "sentence": original,
                "reason": "Tidak ditemukan kata keluhan maupun bagian tubuh."
            })
            continue

        if signals and _negated(clause, min(signals)) and not ability:
            negated.append(original)
            continue

        produced = False
        for _, label, region, joints, severity in condition_hits:
            add({
                "sentence": original, "label": label, "symptom": None, "severity": severity,
                "kind": "condition", "area_key": region, "area": REGIONS[region],
                "joints": sorted(joints), "risk": None
            })
            produced = True

        for _, label, risk in systemic_hits:
            add({
                "sentence": original, "label": label, "symptom": None,
                "severity": "severe" if risk == "high" else "moderate", "kind": "systemic",
                "area_key": "systemic", "area": REGIONS["systemic"], "joints": [], "risk": risk
            })
            produced = True

        if symptom_hits and part_hits:
            symptom_hits.sort(key=lambda h: (-SEVERITY_RANK[h[2]], h[0]))
            _, symptom, severity = symptom_hits[0]
            for _, part, region, joints in sorted(part_hits):
                add({
                    "sentence": original, "label": f"{symptom} {part}", "symptom": symptom,
                    "severity": severity, "kind": "complaint", "area_key": region,
                    "area": REGIONS[region], "joints": sorted(joints), "risk": None
                })
                produced = True
        elif not produced:
            if part_hits:
                unrecognized.append({
                    "sentence": original,
                    "reason": "Bagian tubuh terdeteksi, tetapi belum ada kata keluhan (mis. sakit, nyeri, cedera)."
                })
            elif symptom_hits and not ability_only:
                unrecognized.append({
                    "sentence": original,
                    "reason": "Keluhan terdeteksi, tetapi bagian tubuhnya belum disebutkan."
                })
            else:
                unrecognized.append({
                    "sentence": original,
                    "reason": "Bagian tubuh yang dimaksud belum disebutkan."
                })

    return _summarize(items, unrecognized, negated)


def _summarize(
    items: List[Dict[str, Any]],
    unrecognized: List[Dict[str, str]],
    negated: List[str]
) -> Dict[str, Any]:
    """Meringkas hasil ekstraksi keluhan dan menghitung ambang batas rujukan."""
    joints = sorted({j for it in items for j in it["joints"]})
    regions = sorted({it["area_key"] for it in items if it["area_key"] != "systemic"})
    medium_systemic = any(it["risk"] == "medium" for it in items)
    high_systemic = [it["label"] for it in items if it["risk"] == "high"]
    severe = [it["label"] for it in items if it["severity"] == "severe" and it["kind"] != "systemic"]

    reasons = []
    if high_systemic:
        reasons.append("Terdapat kondisi medis berisiko tinggi: " + ", ".join(high_systemic) + ".")
    if len(joints) >= REFERRAL_MAX_JOINTS:
        reasons.append("Terdapat pembatasan pada " + str(len(joints)) + " sendi berbeda ("
                       + ", ".join(JOINT_LABEL[j] for j in joints) + ").")
    elif {"upper", "lower", "trunk"} <= set(regions):
        reasons.append("Keluhan tersebar pada tubuh bagian atas, bawah, dan tulang belakang sekaligus.")
    if len(severe) >= REFERRAL_MAX_SEVERE:
        reasons.append("Terdapat beberapa keluhan berat: " + ", ".join(severe) + ".")

    return {
        "items": items,
        "labels": [f"{it['label']} ({it['area']})" for it in items],
        "excluded_joints": joints,
        "regions": regions,
        "cardio_caution": medium_systemic or bool(high_systemic),
        "has_severe": bool(severe),
        "unrecognized": unrecognized,
        "negated": negated,
        "referral": {"required": bool(reasons), "reasons": reasons},
    }


def referral_message(parsed: Dict[str, Any], extra_reason: Optional[str] = None) -> Dict[str, Any]:
    """Teks kesimpulan rujukan untuk ditampilkan ke member."""
    reasons = list(parsed["referral"]["reasons"])
    if extra_reason:
        reasons.append(extra_reason)
    labels = ", ".join(parsed["labels"]) or "keluhan yang Anda tuliskan"
    return {
        "required": True,
        "reasons": reasons,
        "complaints": parsed["labels"],
        "message": (
            "Berdasarkan analisis keluhan Anda (" + labels + "), sistem menyimpulkan bahwa kondisi fisik "
            "Anda memerlukan evaluasi langsung. Demi keselamatan, sistem tidak menyusun program otomatis. "
            "Silakan konsultasikan dengan Personal Trainer Bije's Gym atau tenaga medis, lalu bawa "
            "ringkasan keluhan ini sebagai bahan diskusi."
        ),
    }
