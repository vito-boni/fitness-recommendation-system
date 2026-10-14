/* ===============================================================
   Bije's Gym - Asesmen & Rekomendasi Program Latihan
   Rekomendasi disusun oleh backend (POST /api/recommendations/generate):
   filter aturan + Content-Based Filtering (Cosine Similarity).
   File ini mengurus form, pratinjau otomatis (metrik atletik FFMI & WtHR,
   target utama otomatis, deteksi keluhan per kalimat), validasi,
   pemanggilan API, dan tampilan rencana latihan.
================================================================ */
const form = document.getElementById("recommendationForm");
const result = document.getElementById("recommendationList");
const physicalDetails = document.getElementById("physicalDetails");
const athleticMetricsBox = document.getElementById("athleticMetricsBox");
const ffmiValue = document.getElementById("ffmiValue");
const wthrChip = document.getElementById("wthrChip");
const wthrValue = document.getElementById("wthrValue");
const athleticStatusText = document.getElementById("athleticStatusText");
const leanMassText = document.getElementById("leanMassText");
const fatMassText = document.getElementById("fatMassText");
const derivedTargetLabel = document.getElementById("derivedTargetLabel");
const derivedTargetDesc = document.getElementById("derivedTargetDesc");
const limitationStoryInput = document.getElementById("limitationStory");
const limitationPreview = document.getElementById("limitationPreview");
const limitationPreviewBody = document.getElementById("limitationPreviewBody");

const API_BASE = "";

const MIN_DAYS = 1, MAX_DAYS = 6;
const MIN_MINUTES = 30, MAX_MINUTES = 120;

let storedSession = null;
let storedProfile = {};

const GOAL_TARGET_MAP = {
    "Kesehatan Jasmani": 1,  
    "Fat Loss": 1,
    "Ketahanan Jantung": 1,
    "Panjang umur": 1,
    "Bentuk Tubuh Ideal": 2,
    "Kekuatan Absolut": 3,
    "Performa Atletik": 4
};

const PRIMARY_TARGET_INFO = {
    1: {
        label: "Kebugaran & Metabolik Dasar",
        desc: "Fokus pada kebugaran umum, pembakaran kalori, ketahanan kardiorespirasi, dan mobilitas yang aman."
    },
    2: {
        label: "Pembentukan Otot (Hipertrofi)",
        desc: "Fokus pada hipertrofi dan proporsi estetika tubuh melalui kombinasi gerakan majemuk dan isolasi."
    },
    3: {
        label: "Pembentukan Otot & Kekuatan",
        desc: "Fokus pada peningkatan beban progresif (strength) dan kepadatan massa otot."
    },
    4: {
        label: "Otot, Kekuatan, Power & Performa Atletik",
        desc: "Fokus pada kekuatan maksimal, daya ledak (power), dan kapasitas atletik."
    }
};

const LEGACY_GROUP_TO_FOCUS = {
    chest: ["chest"],
    back: ["back"],
    shoulders: ["shoulders"],
    legs: ["thighs", "glutes", "calves"],
    arms: ["arms"],
    core: ["core"]
};

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/* ---------------------------------------------------------------
   Isi ulang form dari profil tersimpan
---------------------------------------------------------------- */
function parseStoredArray(value) {
    if (Array.isArray(value)) return value.map(String);
    if (typeof value !== "string" || !value) return [];
    try {
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch (error) {
        console.warn("Data pilihan tersimpan tidak valid:", error.message);
        return [];
    }
}

function normalizeStoredBodyFat(raw) {
    if (raw === null || raw === undefined || raw === "") return "";
    const num = Number(raw);
    if (Number.isFinite(num) && num > 0) return String(num);
    return "";
}

function buildLegacyLimitationStory(profile) {
    if (profile.limitation_story && String(profile.limitation_story).trim()) {
        return String(profile.limitation_story).trim();
    }
    const parts = [profile.body_part, profile.limitation, profile.other_note]
        .map((x) => String(x || "").trim())
        .filter(Boolean);
    return parts.join(". ");
}

function applyProfileDefaults() {
    const profileFields = {
        memberName: storedProfile.name || storedSession?.name || "",
        age: storedProfile.age ?? "",
        gender: storedProfile.gender ?? "",
        height: storedProfile.height_cm ?? "",
        weight: storedProfile.weight_kg ?? "",
        bodyFat: normalizeStoredBodyFat(storedProfile.body_fat_percent),
        cardioEndurance: storedProfile.cardio_endurance ? String(storedProfile.cardio_endurance) : "2",
        waist: storedProfile.waist_cm ?? "",
        hip: storedProfile.hip_cm ?? "",
        shoulder: storedProfile.shoulder_width_cm ?? "",
        armLength: storedProfile.arm_length_cm ?? "",
        legLength: storedProfile.leg_length_cm ?? "",
        insideFootLength: storedProfile.inside_foot_length_cm ?? "",
        torsoLength: storedProfile.torso_length_cm ?? "",
        limitationStory: buildLegacyLimitationStory(storedProfile)
    };

    Object.entries(profileFields).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value !== "") {
            el.value = value;
        }
    });

    const expValue = String(storedProfile.training_age_tier || storedProfile.experience_level || "").toLowerCase();
    if (expValue) {
        document.querySelectorAll('input[name="experience"]').forEach((input) => {
            const val = String(input.value).toLowerCase();
            input.checked = (val === expValue) ||
                (expValue === "1" && val === "rookie") ||
                (expValue === "2" && val === "novice") ||
                (expValue === "3" && val === "intermediate") ||
                (expValue === "4" && val === "upper_intermediate") ||
                (expValue === "5" && val === "advanced") ||
                (expValue === "6" && val === "veteran");
        });
    }
    document.querySelectorAll('input[name="physicalCondition"]').forEach((input) => {
        input.checked = String(input.value) === String(storedProfile.physical_condition ?? "");
    });

    const savedDays = Number(storedProfile.weekly_frequency);
    if (daysInput && Number.isInteger(savedDays) && savedDays >= MIN_DAYS && savedDays <= MAX_DAYS) {
        daysInput.value = savedDays;
    }
    const savedMinutes = Number(storedProfile.session_duration);
    if (minutesInput && Number.isFinite(savedMinutes) && savedMinutes >= MIN_MINUTES) {
        minutesInput.value = Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, savedMinutes));
    }

    const savedAdvanced = parseStoredArray(storedProfile.target_advanced);
    document.querySelectorAll('input[name="advancedTarget"]').forEach((input) => {
        input.checked = savedAdvanced.includes(input.value);
    });

    let savedFocus = parseStoredArray(storedProfile.focus_areas);
    if (!savedFocus.length && storedProfile.target_body_parts) {
        const legacyParts = parseStoredArray(storedProfile.target_body_parts).filter((p) => p !== "full_body");
        if (legacyParts.length && legacyParts.length < 6) {
            legacyParts.forEach((g) => {
                (LEGACY_GROUP_TO_FOCUS[g] || []).forEach((f) => {
                    if (!savedFocus.includes(f)) savedFocus.push(f);
                });
            });
        }
    }
    document.querySelectorAll('input[name="focusArea"]').forEach((input) => {
        input.checked = savedFocus.includes(input.value);
    });

    const savedModalities = parseStoredArray(storedProfile.modalities);
    document.querySelectorAll('input[name="modality"]').forEach((input) => {
        input.checked = savedModalities.includes(input.value);
    });

    const complexityValues = {
        "Sederhana & praktis": "simple",
        "Seimbang": "balanced",
        "Teknis tinggi / kompleks": "technical",
    };
    const complexityEl = document.getElementById("exerciseComplexity");
    if (complexityEl) {
        complexityEl.value =
            complexityValues[storedProfile.exercise_complexity] || storedProfile.exercise_complexity || "balanced";
    }
    physicalDetails.classList.toggle("visible", String(storedProfile.physical_condition) === "1");

    const hasBodyFat = storedProfile.body_fat_percent !== undefined &&
                       storedProfile.body_fat_percent !== "" &&
                       storedProfile.body_fat_percent !== null &&
                       Number(storedProfile.body_fat_percent) > 0;
    const bodyFatToggle = document.querySelectorAll('input[name="bodyFatToggle"]');
    if (bodyFatToggle.length) {
        const selectedBf = hasBodyFat ? "1" : "0";
        bodyFatToggle.forEach((radio) => {
            radio.checked = radio.value === selectedBf;
        });
        const bfPanel = document.getElementById("bodyFatFields");
        if (bfPanel) {
            bfPanel.hidden = selectedBf !== "1";
            bfPanel.classList.toggle("visible", selectedBf === "1");
        }
    }

    const hasAnthropometry = [
        storedProfile.waist_cm, storedProfile.hip_cm, storedProfile.shoulder_width_cm,
        storedProfile.arm_length_cm, storedProfile.leg_length_cm,
        storedProfile.inside_foot_length_cm, storedProfile.torso_length_cm
    ].some((value) => value !== undefined && value !== "" && value !== null && Number(value) > 0);

    const anthropometryToggle = document.querySelectorAll('input[name="anthropometryToggle"]');
    if (anthropometryToggle.length) {
        const selected = hasAnthropometry ? "1" : "0";
        anthropometryToggle.forEach((radio) => {
            radio.checked = radio.value === selected;
        });
        const panel = document.getElementById("anthropometryFields");
        if (panel) {
            panel.hidden = selected !== "1";
            panel.classList.toggle("visible", selected === "1");
        }
    }

    updateAthleticMetrics();
    updateDerivedPrimaryTarget();
    if (String(storedProfile.physical_condition) === "1" && limitationStoryInput?.value.trim()) {
        scheduleLimitationPreview();
    }
}

/* ---------------------------------------------------------------
   Pembacaan input
---------------------------------------------------------------- */
const daysInput = document.getElementById("weeklyFrequency");
const minutesInput = document.getElementById("sessionDuration");

function readDays() {
    const value = Number(daysInput?.value);
    return Number.isInteger(value) && value >= MIN_DAYS && value <= MAX_DAYS ? value : 0;
}

function readMinutes() {
    const value = Number(minutesInput?.value);
    return Number.isFinite(value) && value >= MIN_MINUTES && value <= MAX_MINUTES ? Math.round(value) : 0;
}

function getExerciseComplexityValue() {
    return document.getElementById("exerciseComplexity")?.value || "balanced";
}

function getExerciseComplexityLabel() {
    const labelMap = {
        simple: "Sederhana & aman",
        balanced: "Seimbang",
        technical: "Teknis tinggi / kompleks"
    };
    const value = getExerciseComplexityValue();
    return labelMap[value] || value;
}

function getSelectedSpecificGoals() {
    return [...document.querySelectorAll('input[name="advancedTarget"]:checked')].map((input) => input.value);
}

function computeDerivedPrimaryTarget(goals) {
    let best = 0;
    goals.forEach((goal) => {
        const target = GOAL_TARGET_MAP[goal] || 0;
        if (target > best) best = target;
    });
    return best;
}

function updateDerivedPrimaryTarget() {
    if (!derivedTargetLabel || !derivedTargetDesc) return;
    const goals = getSelectedSpecificGoals();
    const target = computeDerivedPrimaryTarget(goals);
    if (!target) {
        derivedTargetLabel.textContent = "Pilih minimal 1 tujuan spesifik";
        derivedTargetDesc.textContent = "Target utama ditentukan otomatis berdasarkan tujuan spesifik yang Anda pilih.";
        return;
    }
    const info = PRIMARY_TARGET_INFO[target];
    derivedTargetLabel.textContent = info.label;
    derivedTargetDesc.textContent = `${info.desc} (Berdasarkan pilihan: ${goals.join(", ")})`;
}

/* ---------------------------------------------------------------
   Input angka (umur, tinggi, berat) dan rentang (hari, menit)
---------------------------------------------------------------- */
function clampNumericInput(input, min, max, step) {
    if (!input || input.value === "") return;

    let value = Number(input.value);
    if (!Number.isFinite(value)) {
        value = min;
    }

    if (step && step > 0) {
        value = Math.round(value / step) * step;
        value = Number(value.toFixed(1));
    }

    value = Math.min(Math.max(value, min), max);
    input.value = value;
}

const ageInput = document.getElementById("age");
const heightInput = document.getElementById("height");
const weightInput = document.getElementById("weight");
const genderSelect = document.getElementById("gender");
const bodyFatInput = document.getElementById("bodyFat");
const cardioSelect = document.getElementById("cardioEndurance");

[
    { input: ageInput, min: 1, max: 99, step: 1 },
    { input: heightInput, min: 1, max: 250, step: 1 },
    { input: weightInput, min: 1, max: 220, step: 0.1 },
    { input: bodyFatInput, min: 1, max: 79, step: 0.1 }
].forEach(({ input, min, max, step }) => {
    if (!input) return;

    clampNumericInput(input, min, max, step);

    input.addEventListener("input", () => {
        clampNumericInput(input, min, max, step);
        updateAthleticMetrics();
    });

    input.addEventListener("change", () => {
        clampNumericInput(input, min, max, step);
        updateAthleticMetrics();
    });
});

[genderSelect, cardioSelect].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", updateAthleticMetrics);
});

const waistInput = document.getElementById("waist");
if (waistInput) {
    waistInput.addEventListener("input", updateAthleticMetrics);
    waistInput.addEventListener("change", updateAthleticMetrics);
}

[
    { input: daysInput, min: MIN_DAYS, max: MAX_DAYS, step: 1 },
    { input: minutesInput, min: MIN_MINUTES, max: MAX_MINUTES, step: 1 }
].forEach(({ input, min, max, step }) => {
    if (!input) return;
    input.addEventListener("change", () => {
        clampNumericInput(input, min, max, step);
        if (validationHasRun) updateUnfilledState();
    });
    input.addEventListener("input", () => {
        if (validationHasRun) updateUnfilledState();
    });
});

/* ---------------------------------------------------------------
   Komposisi Tubuh Atletik Modern (FFMI & WtHR)
---------------------------------------------------------------- */
const BF_INDEX_TO_PCT = {
    L: { 1: 11.0, 2: 15.5, 3: 20.5, 4: 27.5, 5: 35.0, 6: 42.0 },
    P: { 1: 18.0, 2: 22.5, 3: 28.0, 4: 35.5, 5: 42.0, 6: 48.0 }
};

function estimateBodyFatDeurenberg(bmi, age, gender) {
    if (!bmi || bmi <= 0) return gender === "P" ? 25.0 : 18.0;
    const ageVal = age && age > 0 ? age : 25;
    const sexVal = gender === "P" ? 0 : 1;
    const est = 1.20 * bmi + 0.23 * ageVal - 10.8 * sexVal - 5.4;
    return Math.max(5.0, Math.min(55.0, Number(est.toFixed(1))));
}

function classifyFfmi(ffmi, gender) {
    if (!ffmi || ffmi <= 0) return "Belum ada data";
    const isFemale = gender === "P";
    if (isFemale) {
        if (ffmi < 15.0) return "Di Bawah Rata-Rata";
        if (ffmi < 17.0) return "Rata-Rata";
        if (ffmi < 19.5) return "Berotot";
        if (ffmi < 22.0) return "Sangat Berotot";
        return "Potensi Genetik Maksimal";
    }
    if (ffmi < 18.0) return "Di Bawah Rata-Rata";
    if (ffmi < 20.0) return "Rata-Rata";
    if (ffmi < 22.0) return "Berotot";
    if (ffmi < 25.0) return "Sangat Berotot";
    return "Potensi Genetik Maksimal";
}

function classifyWthr(wthr) {
    if (!wthr || wthr <= 0) return "";
    if (wthr < 0.40) return "Sangat Ramping (Adipositas Sentral Minimal)";
    if (wthr < 0.50) return "Optimal Sehat (Rasio Perut Seimbang)";
    if (wthr < 0.60) return "Peningkatan Lemak Sentral (Prioritas Metabolik)";
    return "Adipositas Sentral Tinggi (Proteksi Sendi & Kardio)";
}

function updateAthleticMetrics() {
    if (!athleticMetricsBox) return;
    const heightCm = Number(heightInput?.value || 0);
    const weightKg = Number(weightInput?.value || 0);
    const age = Number(ageInput?.value || 0);
    const gender = genderSelect?.value || "L";
    const waistCm = Number(document.getElementById("waist")?.value || 0);
    const cardioLevel = Number(cardioSelect?.value || 2);

    const useBodyFat = document.querySelector('input[name="bodyFatToggle"]:checked')?.value === "1";
    const rawBf = useBodyFat ? bodyFatInput?.value : "";

    if (!heightCm || !weightKg || heightCm <= 0 || weightKg <= 0) {
        athleticMetricsBox.hidden = true;
        ffmiValue.textContent = "0.0";
        if (wthrChip) wthrChip.hidden = true;
        athleticStatusText.textContent = "Menunggu data dasar lengkap";
        leanMassText.textContent = "Massa Bebas Lemak: - kg";
        fatMassText.textContent = "Massa Lemak: - kg";
        return;
    }

    const heightM = heightCm / 100;
    const sex = gender === "P" ? "P" : "L";
    let bfPercent;
    let isEstimated = false;

    if (useBodyFat && rawBf !== "" && rawBf !== undefined && rawBf !== null) {
        const val = Number(rawBf);
        if (Number.isFinite(val) && val > 0) {
            bfPercent = Math.min(60.0, Math.max(3.0, val));
        } else {
            const bmi = weightKg / (heightM * heightM);
            bfPercent = estimateBodyFatDeurenberg(bmi, age, sex);
            isEstimated = true;
        }
    } else {
        const bmi = weightKg / (heightM * heightM);
        bfPercent = estimateBodyFatDeurenberg(bmi, age, sex);
        isEstimated = true;
    }

    const cuts = sex === "L" ? [13, 17, 24, 30, 39] : [20, 24, 31, 39, 44];
    const bfLevel = 1 + cuts.filter((c) => bfPercent > c).length;

    const fatMassKg = weightKg * (bfPercent / 100);
    const leanMassKg = Math.max(0, weightKg - fatMassKg);
    const ffmi = leanMassKg / (heightM * heightM);

    athleticMetricsBox.hidden = false;
    ffmiValue.textContent = ffmi.toFixed(1);
    leanMassText.textContent = `Massa Bebas Lemak: ${leanMassKg.toFixed(1)} kg`;
    fatMassText.textContent = `Massa Lemak: ${fatMassKg.toFixed(1)} kg (${bfPercent.toFixed(1)}%${isEstimated ? " ~ estimasi" : ""})`;

    let wthr = 0;
    if (waistCm > 0 && heightCm > 0) {
        wthr = waistCm / heightCm;
        if (wthrChip && wthrValue) {
            wthrChip.hidden = false;
            wthrValue.textContent = wthr.toFixed(2);
        }
    } else if (wthrChip) {
        wthrChip.hidden = true;
    }

    const ffmiStatus = classifyFfmi(ffmi, sex);
    let statusText = `Klasifikasi FFMI: ${ffmiStatus}`;
    if (wthr > 0) {
        statusText += ` • WtHR: ${classifyWthr(wthr)}`;
    }

    let recoveryBonus = 0;
    if (wthr >= 0.55 || bfLevel >= 4) recoveryBonus += 15;
    if (cardioLevel === 1) recoveryBonus += 15;
    recoveryBonus = Math.min(30, recoveryBonus);

    if (recoveryBonus > 0) {
        statusText += ` • Penyesuaian jeda istirahat: +${recoveryBonus} detik/set`;
    }
    athleticStatusText.textContent = statusText;
}

updateAthleticMetrics();

/* ---------------------------------------------------------------
   Validasi visual
---------------------------------------------------------------- */
let validationHasRun = false;

function setInvalidState(control, isInvalid) {
    if (!control) return;

    control.classList.toggle("invalid", isInvalid);

    const item = control.closest(".choice-item");
    if (item) {
        item.classList.toggle("invalid", isInvalid);
    }

    const fieldWrap = control.closest(".field");
    if (fieldWrap) {
        fieldWrap.classList.toggle("invalid", isInvalid);
    }
}

function updateUnfilledState() {
    [
        document.getElementById("memberName"),
        document.getElementById("age"),
        document.getElementById("height"),
        document.getElementById("weight")
    ].forEach((input) => {
        if (!input) return;
        setInvalidState(input, !input.value.trim());
    });

    setInvalidState(daysInput, !readDays());
    setInvalidState(minutesInput, !readMinutes());

    const genderEl = document.getElementById("gender");
    if (genderEl) setInvalidState(genderEl, genderEl.value === "");

    const useBodyFatVal = document.querySelector('input[name="bodyFatToggle"]:checked')?.value === "1";
    if (bodyFatInput) {
        setInvalidState(bodyFatInput, useBodyFatVal && !bodyFatInput.value.trim());
    }

    ["experience", "physicalCondition"].forEach((name) => {
        const radios = document.querySelectorAll(`input[name="${name}"]`);
        const hasValue = [...radios].some((radio) => radio.checked);
        radios.forEach((radio) => setInvalidState(radio, !hasValue));
    });

    const specificGoalInputs = document.querySelectorAll('input[name="advancedTarget"]');
    const hasSpecificGoal = [...specificGoalInputs].some((input) => input.checked);
    specificGoalInputs.forEach((input) => setInvalidState(input, !hasSpecificGoal));

    const complexityField = document.getElementById("exerciseComplexity");
    if (complexityField) {
        setInvalidState(complexityField, !complexityField.value);
    }

    const physVal = document.querySelector('input[name="physicalCondition"]:checked')?.value;
    if (limitationStoryInput) {
        setInvalidState(limitationStoryInput, physVal === "1" && !limitationStoryInput.value.trim());
    }
}

document.querySelectorAll('input[name="physicalCondition"]').forEach((input) => {
    input.addEventListener("change", () => {
        physicalDetails.classList.toggle("visible", input.value === "1");
        if (input.value === "1" && limitationStoryInput?.value.trim()) {
            scheduleLimitationPreview();
        }
        if (validationHasRun) updateUnfilledState();
    });
});

document.querySelectorAll('input[name="advancedTarget"]').forEach((input) => {
    input.addEventListener("change", () => {
        updateDerivedPrimaryTarget();
        if (validationHasRun) updateUnfilledState();
    });
});

const bodyFatToggleInputs = document.querySelectorAll('input[name="bodyFatToggle"]');
const bodyFatFields = document.getElementById("bodyFatFields");

function toggleBodyFatFields() {
    const selected = document.querySelector('input[name="bodyFatToggle"]:checked')?.value || "0";
    if (!bodyFatFields) return;
    bodyFatFields.hidden = selected !== "1";
    bodyFatFields.classList.toggle("visible", selected === "1");
    updateAthleticMetrics();
}

bodyFatToggleInputs.forEach((input) => {
    input.addEventListener("change", () => {
        toggleBodyFatFields();
        if (validationHasRun) updateUnfilledState();
    });
});

if (bodyFatFields) {
    toggleBodyFatFields();
}

const anthropometryToggleInputs = document.querySelectorAll('input[name="anthropometryToggle"]');
const anthropometryFields = document.getElementById("anthropometryFields");

function toggleAnthropometryFields() {
    const selected = document.querySelector('input[name="anthropometryToggle"]:checked')?.value || "0";
    if (!anthropometryFields) return;
    anthropometryFields.hidden = selected !== "1";
    anthropometryFields.classList.toggle("visible", selected === "1");
}

anthropometryToggleInputs.forEach((input) => {
    input.addEventListener("change", () => {
        toggleAnthropometryFields();
        if (validationHasRun) updateUnfilledState();
    });
});

if (anthropometryFields) {
    toggleAnthropometryFields();
}

["memberName", "age", "height", "weight", "gender", "bodyFat", "cardioEndurance"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", () => { if (validationHasRun) updateUnfilledState(); });
    el.addEventListener("change", () => { if (validationHasRun) updateUnfilledState(); });
});

["experience", "physicalCondition", "bodyFatToggle", "anthropometryToggle"].forEach((name) => {
    document.querySelectorAll(`input[name="${name}"]`).forEach((radio) => {
        radio.addEventListener("change", () => { if (validationHasRun) updateUnfilledState(); });
    });
});

/* ---------------------------------------------------------------
   Pratinjau Deteksi Keluhan Fisik per Kalimat
---------------------------------------------------------------- */
let previewTimer = null;

function renderLimitationPreview(parsed) {
    if (!limitationPreview || !limitationPreviewBody) return;
    if (!parsed || (!parsed.labels?.length && !parsed.unrecognized?.length && !parsed.negated?.length)) {
        limitationPreview.hidden = true;
        limitationPreviewBody.innerHTML = "";
        return;
    }
    limitationPreview.hidden = false;
    const parts = [];
    if (parsed.labels?.length) {
        parts.push(`<p><strong>Terdeteksi:</strong> ${parsed.labels.map((l) => escapeHtml(l)).join(" • ")}</p>`);
    }
    if (parsed.unrecognized?.length) {
        const msgs = parsed.unrecognized.map((u) => `"${escapeHtml(u.sentence)}" (${escapeHtml(u.reason)})`).join("; ");
        parts.push(`<p class="small-note"><strong>Perlu diperjelas:</strong> ${msgs}</p>`);
    }
    if (parsed.referral?.required) {
        const reasons = (parsed.referral.reasons || []).map((r) => escapeHtml(r)).join(" ");
        parts.push(`<p class="small-note"><strong>Rujukan Keselamatan:</strong> ${reasons} Sistem akan menyarankan konsultasi langsung dengan Personal Trainer atau tenaga medis.</p>`);
    }
    limitationPreviewBody.innerHTML = parts.join("");
}

function scheduleLimitationPreview() {
    if (!limitationStoryInput) return;
    clearTimeout(previewTimer);
    const text = limitationStoryInput.value.trim();
    if (!text) {
        renderLimitationPreview(null);
        return;
    }
    previewTimer = setTimeout(async () => {
        try {
            const parsed = await apiRequest("/api/recommendations/limitations/parse", {
                method: "POST",
                body: JSON.stringify({ text })
            });
            renderLimitationPreview(parsed);
        } catch (err) {
            console.warn("Gagal memuat pratinjau keluhan:", err.message);
        }
    }, 250);
}

if (limitationStoryInput) {
    limitationStoryInput.addEventListener("input", () => {
        scheduleLimitationPreview();
        if (validationHasRun) updateUnfilledState();
    });
}

/* ---------------------------------------------------------------
   API
---------------------------------------------------------------- */
async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        },
        ...options
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
        const message = typeof payload === "object" && payload ? (payload.error || payload.message) : String(payload || "Request gagal.");
        const error = new Error(message || "Request gagal.");
        error.status = response.status;
        throw error;
    }

    return payload;
}

async function initializeAssessment() {
    try {
        const sessionResponse = await apiRequest("/api/auth/session");
        storedSession = sessionResponse.user;
        storedProfile = await apiRequest(`/api/profile/${encodeURIComponent(storedSession.username)}`);
        applyProfileDefaults();
    } catch (error) {
        if (error.status === 401) {
            window.location.href = "/auth/login";
            return;
        }
        console.error("Gagal memuat data asesmen dari database:", error);
        result.innerHTML = `<p class="empty">Data asesmen gagal dimuat: ${escapeHtml(error.message)}</p>`;
    }
}

initializeAssessment();

document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.addEventListener("click", async () => {
        button.disabled = true;
        try {
            await apiRequest("/api/auth/logout", { method: "POST" });
        } catch (error) {
            alert(`Logout gagal: ${error.message}`);
            button.disabled = false;
            return;
        }
        window.location.replace("/auth/login");
    });
});

window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
});

/* ---------------------------------------------------------------
   Tampilan program (format: Frekuensi, Durasi, Split, Fokus, sesi,
   serta blok tambahan Cardio dan Mobility di luar durasi sesi)
---------------------------------------------------------------- */
function formatRest(sec) {
    if (!sec) return "";
    return sec % 60 === 0 ? `${sec / 60} menit` : `${sec} detik`;
}

function formatMinutes(value) {
    const minutes = Math.round(Number(value) || 0);
    if (minutes < 60) return `${minutes} menit`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return remainingMinutes ? `${hours} jam ${remainingMinutes} menit` : `${hours} jam`;
}

function formatHoursMinutes(totalMinutes) {
    const mins = Math.round(Number(totalMinutes) || 0);
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatWorkoutDuration(avgSessionMinutes, weeklyMinutes, addonWeeklyMinutes) {
    const sessionMins = Math.round(Number(avgSessionMinutes) || 0);
    const weeklyStr = formatHoursMinutes(weeklyMinutes);
    let str = `${sessionMins} min / sesi • ${weeklyStr} total`;
    if (addonWeeklyMinutes) {
        str += ` (+${formatHoursMinutes(addonWeeklyMinutes)} addon)`;
    }
    return str;
}

function renderExerciseLine(e) {
    const side = e.unilateral ? " per sisi" : "";
    const volume = e.reps
        ? `${e.sets} Set • ${e.reps} Reps${side}`
        : `${e.sets} Set • ${e.seconds_per_set} dtk${side}`;
    return `
        <div class="exercise-card">
            <div class="exercise-card-header">
                <div class="exercise-name-group">
                    <strong class="exercise-card-name">${escapeHtml(e.name)}</strong>
                    <span class="muscle-tag">${escapeHtml(e.muscle)}</span>
                </div>
                <span class="exercise-duration-tag">⏱ ~${escapeHtml(e.est_text)}</span>
            </div>
            <div class="exercise-card-specs">
                <div class="spec-line">
                    <span class="spec-line-label">Volume:</span>
                    <span class="spec-line-value">${volume}</span>
                </div>
                <div class="spec-line">
                    <span class="spec-line-label">Jeda:</span>
                    <span class="spec-line-value">${formatRest(e.rest_sec)}</span>
                </div>
                <div class="spec-line full-width">
                    <span class="spec-line-label">Beban:</span>
                    <span class="spec-line-value load-highlight">${escapeHtml(e.load_text)}</span>
                </div>
            </div>
        </div>`;
}

function renderMobilityBlock(mob) {
    if (!mob || !Array.isArray(mob.exercises) || !mob.exercises.length) return "";
    const items = mob.exercises.map((m) => {
        const side = m.unilateral ? " per sisi" : "";
        return `<li><strong>${escapeHtml(m.name)}</strong> (${escapeHtml(m.muscle)}) — ${m.sets}x ${m.seconds_per_set} detik${side}</li>`;
    }).join("");
    return `
        <div class="addon-block">
            <p class="small-note"><strong>+ Blok Tambahan Mobility &amp; Flexibility (di luar durasi sesi inti: ~${escapeHtml(mob.est_text)})</strong></p>
            <ul>${items}</ul>
        </div>`;
}

function renderCardioBlock(cardio) {
    if (!cardio) return "";
    return `
        <div class="addon-block">
            <p class="small-note"><strong>+ Blok Tambahan Cardio &amp; Conditioning (di luar durasi sesi inti: ${formatMinutes(cardio.minutes)})</strong></p>
            <ul>
                <li><strong>${escapeHtml(cardio.name)}</strong> | ${formatMinutes(cardio.minutes)} | ${escapeHtml(cardio.intensity || "Zona 2")}</li>
            </ul>
        </div>`;
}

function renderProgramHtml(program, metaProfile) {
    const anthroNotes = (metaProfile?.anthropometry?.applied || [])
        .map((note) => `<p>• <em>Penyesuaian Antropometri:</em> ${escapeHtml(note)}</p>`)
        .join("");

    const sessions = program.sessions.map((s, idx) => {
        const exerciseCards = s.exercises.map(renderExerciseLine).join("");
        const addonNote = s.addon_seconds
            ? ` + ~${formatMinutes(Math.round(s.addon_seconds / 60))} di luar sesi`
            : "";
        return `
            <details class="daily-workout-card card p-6" ${idx === 0 ? "open" : ""}>
                <summary class="daily-card-summary">
                    <div class="daily-summary-left flex items-center space-x-4">
                        <span class="day-badge">Hari ${idx + 1}${s.day_name ? ` (${escapeHtml(s.day_name)})` : ""}</span>
                        <strong class="session-title">${escapeHtml(s.label)}</strong>
                    </div>
                    <div class="daily-summary-right flex items-center space-x-3">
                        <span class="duration-pill">${s.exercises.length} latihan • ~${formatMinutes(s.total_minutes)}${addonNote}</span>
                        <span class="chevron-icon" aria-hidden="true">▾</span>
                    </div>
                </summary>
                <div class="daily-card-body">
                    <div class="session-phase warmup">
                        <span class="phase-pill warmup">Pemanasan</span>
                        <span class="phase-name"><strong>${escapeHtml(s.warmup.name)}</strong> • Estimasi ${escapeHtml(s.warmup.est_text)}</span>
                    </div>
                    <hr class="section-divider">
                    <div class="exercise-grid grid-cols-2 gap-y-3 gap-x-4">
                        ${exerciseCards}
                    </div>
                    <hr class="section-divider">
                    <div class="session-phase cooldown">
                        <span class="phase-pill cooldown">Pendinginan</span>
                        <span class="phase-name"><strong>${escapeHtml(s.cooldown.name)}</strong> • Estimasi ${escapeHtml(s.cooldown.est_text)}</span>
                    </div>
                    ${renderCardioBlock(s.cardio_block)}
                    ${renderMobilityBlock(s.mobility_block)}
                </div>
            </details>`;
    }).join("");

    return `
        <div class="plan space-y-4">
            <div class="meta-specs-grid">
                <div class="spec-pill">
                    <span class="spec-label">Target Utama</span>
                    <span class="spec-val">${escapeHtml(program.primary_target_label || metaProfile?.primary_target_label || "-")}</span>
                </div>
                <div class="spec-pill">
                    <span class="spec-label">Frekuensi</span>
                    <span class="spec-val">${program.frequency_days}x / minggu</span>
                </div>
                <div class="spec-pill">
                    <span class="spec-label">Durasi Latihan</span>
                    <span class="spec-val">${formatWorkoutDuration(program.avg_session_minutes, program.weekly_minutes, program.weekly_addon_minutes)}</span>
                </div>
                <div class="spec-pill">
                    <span class="spec-label">Fokus Otot</span>
                    <span class="spec-val">${escapeHtml((program.focus || []).join(", "))}</span>
                </div>
            </div>
            ${anthroNotes ? `<div class="anthro-notes">${anthroNotes}</div>` : ""}
            <div class="daily-workouts-section space-y-4">
                ${sessions}
            </div>
            <p class="initial-load-note">Beban adalah estimasi awal berdasarkan pengalaman dan berat badan acuan. Anda dapat mengkustomisasi hari latihan, menukar latihan, atau menyesuaikan beban bersama Personal Trainer di halaman Beranda.</p>
        </div>`;
}

function buildDescription(program) {
    const s = program.scores;
    let text = `[${program.primary_target_label || "Program Terpersonalisasi"}] Split ${program.split}, ${program.frequency_days} hari per minggu. `
        + `Rata-rata kemiripan latihan dengan profil Anda ${s.exercise_cosine_mean}; `
        + `kecocokan target otot dengan split ${s.split_cosine}; `
        + `keseimbangan pola gerak ${s.movement_balance ?? "belum tersedia"}.`;
    if (program.uncovered_targets && program.uncovered_targets.length) {
        text += ` Belum tercakup: ${program.uncovered_targets.join(", ")}.`;
    }
    return text;
}

/* ---------------------------------------------------------------
   Submit
---------------------------------------------------------------- */
form.addEventListener("submit", async function (event) {
    event.preventDefault();

    if (!storedSession?.username) {
        result.innerHTML = '<p class="empty">Sesi pengguna tidak tersedia. Silakan masuk kembali.</p>';
        window.location.href = "/auth/login";
        return;
    }

    validationHasRun = true;
    updateUnfilledState();

    const checkedValue = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;

    const experience = checkedValue("experience") || "";
    const days = readDays();
    const sessionMinutes = readMinutes();
    const specificGoals = getSelectedSpecificGoals();
    const derivedPrimaryTarget = computeDerivedPrimaryTarget(specificGoals);
    const physicalValue = checkedValue("physicalCondition");
    const focusAreas = [...document.querySelectorAll('input[name="focusArea"]:checked')].map((input) => input.value);
    const modalities = [...document.querySelectorAll('input[name="modality"]:checked')].map((input) => input.value);
    const limitationStory = limitationStoryInput?.value?.trim() || "";
    const cardioEnduranceVal = Number(cardioSelect?.value || 2);

    const useBodyFat = checkedValue("bodyFatToggle") === "1";
    let bodyFatVal = null;
    if (useBodyFat) {
        const rawBf = bodyFatInput?.value?.trim() || "";
        const parsedBf = Number(rawBf);
        if (!rawBf || Number.isNaN(parsedBf) || parsedBf < 3 || parsedBf > 60) {
            result.innerHTML = '<p class="empty">Masukkan angka persentase lemak tubuh Anda (3–60%), atau pilih "Lewat dulu" untuk estimasi otomatis.</p>';
            return;
        }
        bodyFatVal = parsedBf;
    }

    if (!days || !sessionMinutes) {
        result.innerHTML = `<p class="empty">Jumlah hari latihan harus ${MIN_DAYS}–${MAX_DAYS} dan durasi sesi ${MIN_MINUTES}–${MAX_MINUTES} menit (Zając et al., 2015).</p>`;
        return;
    }
    if (
        !experience ||
        !specificGoals.length ||
        physicalValue === undefined ||
        (physicalValue === "1" && !limitationStory)
    ) {
        result.innerHTML = '<p class="empty">Harap lengkapi semua pertanyaan wajib (termasuk tingkat pengalaman, tujuan spesifik, dan cerita keluhan bila ada keterbatasan fisik).</p>';
        return;
    }

    const useAnthropometry = checkedValue("anthropometryToggle") === "1";
    const anthropometryPayload = {
        waist_cm: useAnthropometry ? (document.getElementById("waist")?.value || "") : "",
        hip_cm: useAnthropometry ? (document.getElementById("hip")?.value || "") : "",
        shoulder_width_cm: useAnthropometry ? (document.getElementById("shoulder")?.value || "") : "",
        arm_length_cm: useAnthropometry ? (document.getElementById("armLength")?.value || "") : "",
        leg_length_cm: useAnthropometry ? (document.getElementById("legLength")?.value || "") : "",
        inside_foot_length_cm: useAnthropometry ? (document.getElementById("insideFootLength")?.value || "") : "",
        torso_length_cm: useAnthropometry ? (document.getElementById("torsoLength")?.value || "") : ""
    };

    result.innerHTML = '<p class="empty">Menyusun program latihan Anda...</p>';

    const profilePayload = {
        name: document.getElementById("memberName")?.value?.trim() || storedSession.name || "",
        username: storedSession.username,
        age: document.getElementById("age")?.value || "",
        gender: document.getElementById("gender")?.value || "",
        height_cm: document.getElementById("height")?.value || "",
        weight_kg: document.getElementById("weight")?.value || "",
        body_fat_percent: bodyFatVal !== null ? String(bodyFatVal) : "",
        cardio_endurance: String(cardioEnduranceVal),
        ...anthropometryPayload,
        training_age_tier: String(experience),
        experience_level: String(experience),
        weekly_frequency: String(days),
        session_duration: String(sessionMinutes),
        target_primary: String(derivedPrimaryTarget),
        target_advanced: JSON.stringify(specificGoals),
        focus_areas: JSON.stringify(focusAreas),
        target_body_parts: JSON.stringify(focusAreas.length ? focusAreas : ["full_body"]),
        modalities: JSON.stringify(modalities),
        physical_condition: String(physicalValue),
        limitation_story: limitationStory,
        body_part: "",
        limitation: limitationStory,
        other_note: "",
        exercise_complexity: getExerciseComplexityLabel(),
        facilities: JSON.stringify(["1", "2", "3", "4", "5", "6", "7"])
    };

    let generated;
    try {
        generated = await apiRequest("/api/recommendations/generate", {
            method: "POST",
            body: JSON.stringify({
                training_age_tier: experience,
                experience,
                days,
                session_minutes: sessionMinutes,
                advanced_targets: specificGoals,
                focus_areas: focusAreas,
                modalities,
                physical_condition: physicalValue,
                limitation_story: limitationStory,
                exercise_complexity: getExerciseComplexityValue(),
                cardio_endurance: cardioEnduranceVal,
                body_fat: bodyFatVal !== null ? Number(bodyFatVal) : null,
                body_fat_percent: bodyFatVal !== null ? Number(bodyFatVal) : null,
                weight: Number(weightInput?.value || 0),
                height: Number(heightInput?.value || 0),
                gender: document.getElementById("gender")?.value || "",
                age: Number(ageInput?.value || 0),
                ...anthropometryPayload
            })
        });
    } catch (error) {
        console.error("Gagal menyusun rekomendasi:", error);
        result.innerHTML = `<p class="empty">Rekomendasi gagal disusun: ${escapeHtml(error.message)}</p>`;
        return;
    }

    const warnings = generated.warnings || [];
    const programs = generated.programs || [];
    const referral = generated.referral || null;
    const metaProfile = generated.meta?.profile || null;

    if (metaProfile) {
        profilePayload.ffmi = metaProfile.ffmi ?? null;
        profilePayload.wthr = metaProfile.wthr ?? null;
        if (metaProfile.training_age_tier) {
            profilePayload.training_age_tier = metaProfile.training_age_tier;
        }
        if (metaProfile.experience_level) {
            profilePayload.experience_level = metaProfile.experience_level;
        }
    }

    // Bila sistem memutuskan perlu rujukan Personal Trainer / tenaga medis:
    if (referral && referral.required) {
        try {
            await apiRequest(`/api/profile/${encodeURIComponent(storedSession.username)}`, {
                method: "PUT",
                body: JSON.stringify(profilePayload)
            });
            await apiRequest("/api/recommendations/current", {
                method: "PUT",
                body: JSON.stringify({ recommendations: [] })
            });
        } catch (err) {
            console.warn("Gagal menyimpan profil saat rujukan:", err.message);
        }
        const reasonsList = (referral.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
        const complaintsList = (referral.complaints || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("");
        result.innerHTML = `
            <div class="recommendation">
                <h3>Rujukan Konsultasi Personal Trainer / Tenaga Medis</h3>
                <p>${escapeHtml(referral.message)}</p>
                ${complaintsList ? `<p class="small-note"><strong>Keluhan yang terdeteksi:</strong></p><ul>${complaintsList}</ul>` : ""}
                ${reasonsList ? `<p class="small-note"><strong>Alasan keselamatan:</strong></p><ul>${reasonsList}</ul>` : ""}
            </div>`;
        result.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
    }

    if (!programs.length) {
        const why = warnings.map((w) => `<p class="small-note">${escapeHtml(w)}</p>`).join("");
        result.innerHTML = `<p class="empty">Belum ada program yang cocok dengan kombinasi pilihan Anda.</p>${why}`;
        return;
    }

    programs.sort((a, b) => (b.scores?.final ?? 0) - (a.scores?.final ?? 0));

    const topThree = programs.map((program, index) => {
        const progName = `Program ${String.fromCharCode(65 + index)}`;
        return {
            id: index + 1,
            name: progName,
            default_name: progName,
            custom_name: null,
            internalName: program.split,
            split: `${program.split} • ${program.frequency_days}x/minggu • ~${Math.round(program.avg_session_minutes)} min/sesi`,
            description: buildDescription(program),
            similarity: program.scores.final,
            percent: Math.round(program.scores.final * 1000) / 10,
            scores: program.scores,
            plan: renderProgramHtml(program, metaProfile),
            program,
            metaProfile,
            warnings,
            estimatedMinutes: Math.round(program.avg_session_minutes)
        };
    });

    try {
        await apiRequest(`/api/profile/${encodeURIComponent(storedSession.username)}`, {
            method: "PUT",
            body: JSON.stringify(profilePayload)
        });
        await apiRequest("/api/recommendations/current", {
            method: "PUT",
            body: JSON.stringify({ recommendations: topThree })
        });
    } catch (error) {
        console.error("Gagal menyimpan asesmen dan rekomendasi:", error);
        result.innerHTML = `<p class="empty">Data gagal disimpan ke database: ${escapeHtml(error.message)}</p>`;
        return;
    }

    result.innerHTML = warnings.length
        ? `<p class="empty">${warnings.map((warning) => escapeHtml(warning)).join(" ")}</p>`
        : '<p class="empty">Asesmen tersimpan. Memuat pilihan program di Profil & Akun...</p>';
    window.location.href = "/profile#recommendations";
});