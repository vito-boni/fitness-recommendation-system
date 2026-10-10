/* ===============================================================
   Bije's Gym - Asesmen & Rekomendasi Program Latihan
   Rekomendasi disusun oleh backend (POST /api/recommendations/generate):
   filter aturan + Content-Based Filtering (Cosine Similarity).
   File ini hanya mengurus form, validasi, pemanggilan API, dan tampilan.
================================================================ */
const form = document.getElementById("recommendationForm");
const result = document.getElementById("recommendationList");
const physicalDetails = document.getElementById("physicalDetails");
const targetBodyPartsContainer = document.getElementById("targetBodyParts");
const bmiBox = document.getElementById("bmiBox");
const bmiValue = document.getElementById("bmiValue");
const bmiStatus = document.getElementById("bmiStatus");

const API_BASE = `http://${window.location.hostname || "localhost"}:5001`;

const MIN_DAYS = 1, MAX_DAYS = 6;
const MIN_MINUTES = 30, MAX_MINUTES = 180;

let storedSession = null;
let storedProfile = {};
let currentRecommendations = [];

const MUSCLE_GROUP_LABELS = {
    chest: "Dada",
    back: "Punggung",
    shoulders: "Bahu",
    legs: "Kaki",
    arms: "Lengan",
    core: "Core",
    cardio: "Kardio"
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

function applyProfileDefaults() {
    const profileFields = {
        memberName: storedProfile.name || storedSession?.name || "",
        age: storedProfile.age ?? "",
        gender: storedProfile.gender ?? "",
        height: storedProfile.height_cm ?? "",
        weight: storedProfile.weight_kg ?? "",
        bodyFat: storedProfile.body_fat_percent ?? "",
        waist: storedProfile.waist_cm ?? "",
        hip: storedProfile.hip_cm ?? "",
        shoulder: storedProfile.shoulder_width_cm ?? "",
        armLength: storedProfile.arm_length_cm ?? "",
        legLength: storedProfile.leg_length_cm ?? "",
        insideFootLength: storedProfile.inside_foot_length_cm ?? "",
        torsoLength: storedProfile.torso_length_cm ?? "",
        bodyPart: storedProfile.body_part || "",
        limitation: storedProfile.limitation || "",
        otherNote: storedProfile.other_note || ""
    };

    Object.entries(profileFields).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value !== "") {
            el.value = value;
        }
    });

    [
        ["experience_level", "experience"],
        ["target_primary", "primaryTarget"],
        ["physical_condition", "physicalCondition"]
    ].forEach(([field, name]) => {
        document.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
            input.checked = String(input.value) === String(storedProfile[field] ?? "");
        });
    });

    // Hari/minggu dan durasi sekarang berupa angka bebas (1-6 hari, 30-180 menit)
    const savedDays = Number(storedProfile.weekly_frequency);
    if (daysInput && Number.isInteger(savedDays) && savedDays >= MIN_DAYS && savedDays <= MAX_DAYS) {
        daysInput.value = savedDays;
    }
    const savedMinutes = Number(storedProfile.session_duration);
    if (minutesInput && Number.isFinite(savedMinutes) && savedMinutes >= MIN_MINUTES && savedMinutes <= MAX_MINUTES) {
        minutesInput.value = savedMinutes;
    }

    document.querySelectorAll('input[name="advancedTarget"]').forEach((input) => {
        input.checked = parseStoredArray(storedProfile.target_advanced).includes(input.value);
    });
    document.querySelectorAll('input[name="facility"]').forEach((input) => {
        input.checked = parseStoredArray(storedProfile.facilities).includes(input.value);
    });
    const facilityBoxes = [...document.querySelectorAll('input[name="facility"]')];
    const allFacilitiesInput = facilityBoxes.find((input) => input.value === "8");
    if (allFacilitiesInput) {
        allFacilitiesInput.checked = facilityBoxes
            .filter((input) => input !== allFacilitiesInput)
            .every((input) => input.checked);
    }
    const complexityValues = {
        "Sederhana & aman": "simple",
        Campuran: "balanced",
        "Teknis tinggi / kompleks": "technical"
    };
    document.getElementById("exerciseComplexity").value =
        complexityValues[storedProfile.exercise_complexity] || storedProfile.exercise_complexity || "balanced";
    physicalDetails.classList.toggle("visible", String(storedProfile.physical_condition) === "1");

    const hasAnthropometry = [
        storedProfile.waist_cm, storedProfile.hip_cm, storedProfile.shoulder_width_cm,
        storedProfile.arm_length_cm, storedProfile.leg_length_cm,
        storedProfile.inside_foot_length_cm, storedProfile.torso_length_cm
    ].some((value) => value !== undefined && value !== "" && value !== null);

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
        balanced: "Campuran",
        technical: "Teknis tinggi / kompleks"
    };
    const value = getExerciseComplexityValue();
    return labelMap[value] || value;
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

[
    { input: ageInput, min: 1, max: 99, step: 1 },
    { input: heightInput, min: 1, max: 250, step: 1 },
    { input: weightInput, min: 1, max: 220, step: 0.1 }
].forEach(({ input, min, max, step }) => {
    if (!input) return;

    clampNumericInput(input, min, max, step);

    input.addEventListener("input", () => {
        clampNumericInput(input, min, max, step);
        updateBmi();
    });

    input.addEventListener("change", () => {
        clampNumericInput(input, min, max, step);
        updateBmi();
    });
});

// Hari dan menit hanya dirapikan saat selesai mengetik (agar mengetik "90" tidak terpotong jadi "30")
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
   BMI
---------------------------------------------------------------- */
function getBmiClassification(bmi) {
    if (bmi < 16) return "Kekurangan Berat Badan Berat";
    if (bmi < 17) return "Kekurangan Berat Badan Sedang";
    if (bmi < 18.5) return "Kekurangan Berat Badan Ringan";
    if (bmi < 25) return "Normal";
    if (bmi < 30) return "Kelebihan Berat Badan";
    if (bmi < 35) return "Obesitas Kelas I";
    if (bmi < 40) return "Obesitas Kelas II";
    return "Obesitas Kelas III";
}

function updateBmi() {
    const heightCm = Number(heightInput?.value || 0);
    const weightKg = Number(weightInput?.value || 0);

    if (!heightCm || !weightKg || heightCm <= 0 || weightKg <= 0) {
        bmiBox.hidden = true;
        bmiValue.textContent = "0.00";
        bmiStatus.textContent = "Menunggu data dasar lengkap";
        return;
    }

    const heightM = heightCm / 100;
    const bmi = weightKg / (heightM * heightM);

    bmiBox.hidden = false;
    bmiValue.textContent = bmi.toFixed(2);
    bmiStatus.textContent = `Klasifikasi: ${getBmiClassification(bmi)}`;
}

updateBmi();

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

function getTargetBodyPartInputs() {
    return [...document.querySelectorAll('input[name="targetBodyPart"]')];
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

    [
        document.getElementById("gender"),
        document.getElementById("bodyFat")
    ].forEach((select) => {
        if (!select) return;
        setInvalidState(select, !select.value);
    });

    ["experience", "primaryTarget", "physicalCondition"].forEach((name) => {
        const radios = document.querySelectorAll(`input[name="${name}"]`);
        const hasValue = [...radios].some((radio) => radio.checked);
        radios.forEach((radio) => setInvalidState(radio, !hasValue));
    });

    const complexityField = document.getElementById("exerciseComplexity");
    if (complexityField) {
        setInvalidState(complexityField, !complexityField.value);
    }

    const facilityBoxes = document.querySelectorAll('input[name="facility"]');
    const hasFacility = [...facilityBoxes].some((input) => input.checked);
    facilityBoxes.forEach((input) => setInvalidState(input, !hasFacility));

    const targetBodyPartInputs = getTargetBodyPartInputs();
    const hasTargetBodyPart = targetBodyPartInputs.some((input) => input.checked && input.value !== "full_body");
    targetBodyPartInputs.forEach((input) => setInvalidState(input, !hasTargetBodyPart));
    targetBodyPartsContainer?.classList.toggle("invalid", !hasTargetBodyPart);
}

document.querySelectorAll('input[name="physicalCondition"]').forEach((input) => {
    input.addEventListener("change", () => {
        physicalDetails.classList.toggle("visible", input.value === "1");
        if (validationHasRun) updateUnfilledState();
    });
});

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

const facilityInputs = document.querySelectorAll('input[name="facility"]');
const allFacilitiesCheckbox = [...facilityInputs].find((input) => input.value === "8");

facilityInputs.forEach((input) => {
    input.addEventListener("change", () => {
        if (input.value === "8") {
            facilityInputs.forEach((box) => {
                if (box !== input) box.checked = input.checked;
            });
        } else {
            allFacilitiesCheckbox.checked = [...facilityInputs]
                .filter((box) => box !== allFacilitiesCheckbox)
                .every((box) => box.checked);
        }
        if (validationHasRun) updateUnfilledState();
    });
});

["memberName", "age", "height", "weight", "gender", "bodyFat"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", () => { if (validationHasRun) updateUnfilledState(); });
    el.addEventListener("change", () => { if (validationHasRun) updateUnfilledState(); });
});

["experience", "primaryTarget", "physicalCondition"].forEach((name) => {
    document.querySelectorAll(`input[name="${name}"]`).forEach((radio) => {
        radio.addEventListener("change", () => { if (validationHasRun) updateUnfilledState(); });
    });
});

/* ---------------------------------------------------------------
   Pilihan "Target Bagian Tubuh" dibaca dari kolom muscle_group
   pada data/exercises.csv (gunakan exercises_v2.csv)
---------------------------------------------------------------- */
let exercisesReadyPromise = null;

function parseCsvRows(csvText) {
    const lines = csvText.split(/\r?\n/).filter((line) => line.trim().length > 0);
    if (!lines.length) return [];

    const headers = lines[0].split(",").map((header) => header.trim());
    return lines.slice(1).map((line) => {
        const values = line.split(",");
        const item = {};
        headers.forEach((header, index) => {
            item[header] = (values[index] || "").trim();
        });
        return item;
    }).filter((row) => row.name && row.name !== "");
}

function storedTargetBodyParts() {
    const stored = storedProfile.target_body_parts;
    if (Array.isArray(stored)) return stored;
    if (typeof stored !== "string" || !stored) return [];
    try {
        const parsed = JSON.parse(stored);
        return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
        console.warn("Target bagian tubuh tersimpan tidak valid:", error.message);
        return [];
    }
}

function renderTargetBodyParts(rows) {
    if (!targetBodyPartsContainer) return;

    const muscleGroups = [...new Set(rows
        .map((row) => String(row.muscle_group || "").trim().toLowerCase())
        .filter((group) => group && group !== "full_body"))];
    if (!muscleGroups.length) {
        throw new Error("CSV tidak memiliki data muscle_group untuk target bagian tubuh.");
    }

    const savedParts = storedTargetBodyParts();
    const hasSavedFullBody = savedParts.includes("full_body");
    targetBodyPartsContainer.replaceChildren();

    const fullBodyLabel = document.createElement("label");
    fullBodyLabel.className = "choice-item";
    const fullBodyInput = document.createElement("input");
    fullBodyInput.type = "checkbox";
    fullBodyInput.name = "targetBodyPart";
    fullBodyInput.value = "full_body";
    fullBodyLabel.append(fullBodyInput, document.createTextNode(" Full-body"));
    targetBodyPartsContainer.append(fullBodyLabel);

    muscleGroups.forEach((group) => {
        const label = document.createElement("label");
        label.className = "choice-item";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.name = "targetBodyPart";
        input.value = group;
        input.checked = hasSavedFullBody || savedParts.includes(group);
        label.append(input, document.createTextNode(` ${MUSCLE_GROUP_LABELS[group] || group.replace(/_/g, " ")}`));
        targetBodyPartsContainer.append(label);
    });

    fullBodyInput.checked = hasSavedFullBody || muscleGroups.every((group) => savedParts.includes(group));
    syncTargetBodyPartSelection(fullBodyInput);
}

function syncTargetBodyPartSelection(changedInput) {
    const inputs = getTargetBodyPartInputs();
    const fullBodyInput = inputs.find((input) => input.value === "full_body");
    const bodyPartInputs = inputs.filter((input) => input !== fullBodyInput);
    if (!fullBodyInput) return;

    if (changedInput === fullBodyInput) {
        bodyPartInputs.forEach((input) => { input.checked = fullBodyInput.checked; });
    } else {
        fullBodyInput.checked = bodyPartInputs.length > 0 && bodyPartInputs.every((input) => input.checked);
    }

    if (validationHasRun) updateUnfilledState();
}

targetBodyPartsContainer?.addEventListener("change", (event) => {
    if (event.target instanceof HTMLInputElement && event.target.name === "targetBodyPart") {
        syncTargetBodyPartSelection(event.target);
    }
});

function resolveExerciseDataUrls() {
    const currentHref = window.location.href || "";
    const currentOrigin = window.location.origin || "http://127.0.0.1";
    const candidates = [];

    try {
        const base = new URL(currentHref);
        const originBase = `${base.origin}${base.pathname}`;
        candidates.push(new URL("../../data/exercises.csv", originBase).toString());
        candidates.push(new URL("../../../data/exercises.csv", originBase).toString());
    } catch (error) {
        // lanjut ke varian relatif
    }

    candidates.push("../../data/exercises.csv");
    candidates.push("../../../data/exercises.csv");
    candidates.push("/data/exercises.csv");
    candidates.push(`${currentOrigin}/data/exercises.csv`);

    return [...new Set(candidates.filter(Boolean))];
}

async function loadExercisesFromCsv() {
    if (exercisesReadyPromise) return exercisesReadyPromise;

    exercisesReadyPromise = (async () => {
        let lastError = null;

        for (const csvUrl of resolveExerciseDataUrls()) {
            try {
                const response = await fetch(csvUrl, { cache: "no-store" });
                if (!response.ok) {
                    throw new Error(`CSV fetch failed: ${response.status}`);
                }
                const rows = parseCsvRows(await response.text());
                if (!rows.length) {
                    throw new Error("CSV empty");
                }
                renderTargetBodyParts(rows);
                return rows;
            } catch (error) {
                lastError = error;
            }
        }

        throw lastError || new Error("Tidak dapat memuat daftar latihan dari data/exercises.csv");
    })();

    return exercisesReadyPromise;
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
        await loadExercisesFromCsv();
    } catch (error) {
        if (error.status === 401) {
            window.location.href = "../login/login.html";
            return;
        }
        console.error("Gagal memuat data asesmen dari database:", error);
        result.innerHTML = `<p class="empty">Data asesmen gagal dimuat: ${escapeHtml(error.message)}</p>`;
    }
}

initializeAssessment();

/* ---------------------------------------------------------------
   Tampilan program (format: Frekuensi, Durasi, Split, Fokus, sesi)
---------------------------------------------------------------- */
function formatRest(sec) {
    if (!sec) return "";
    return sec % 60 === 0 ? `${sec / 60} menit` : `${sec} detik`;
}

function formatMinutes(value) {
    const minutes = Math.round(value);
    if (minutes < 60) return `${minutes} menit`;

    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    const duration = remainingMinutes ? `${hours} jam ${remainingMinutes} menit` : `${hours} jam`;
    return `${duration} (${minutes} menit)`;
}

function renderExerciseLine(e) {
    const side = e.unilateral ? " per sisi" : "";
    const volume = e.reps
        ? `${e.sets} Set | ${e.reps} Reps${side} (estimasi ${e.sec_per_rep} detik/rep)`
        : `${e.sets} Set | ${e.seconds_per_set} detik${side} per set`;
    return `<li><strong>${escapeHtml(e.name)}</strong> | ${escapeHtml(e.muscle)} | ${volume}`
        + ` | Jeda antar set ${formatRest(e.rest_sec)} | Beban ${escapeHtml(e.load_text)}`
        + ` | Estimasi waktu latihan: ${escapeHtml(e.est_text)}</li>`;
}

function renderProgramHtml(program) {
    const weekly = formatMinutes(program.weekly_minutes);
    const sessions = program.sessions.map((s, idx) => {
        const lines = s.exercises.map(renderExerciseLine).join("");
        const cardio = s.cardio_finisher
            ? `<li>${escapeHtml(s.cardio_finisher.name)} | Kardio penutup | ${formatMinutes(s.cardio_finisher.minutes)}</li>`
            : "";
        return `
            <details ${idx === 0 ? "open" : ""}>
                <summary>Hari ${idx + 1}: ${escapeHtml(s.label)} (${s.exercises.length} latihan, ~${formatMinutes(s.total_minutes)})</summary>
                <ul>
                    <li>${escapeHtml(s.warmup.name)} | Pemanasan | ${escapeHtml(s.warmup.est_text)}</li>
                    ${lines}
                    ${cardio}
                    <li>${escapeHtml(s.cooldown.name)} | Pendinginan | ${escapeHtml(s.cooldown.est_text)}</li>
                </ul>
            </details>`;
    }).join("");

    return `
        <div class="plan">
            <p class="small-note"><strong>Frekuensi</strong>: ${program.frequency_days}x seminggu</p>
            <p class="small-note"><strong>Durasi</strong>: ~${formatMinutes(program.avg_session_minutes)} per sesi (${weekly} total mingguan)</p>
            <p class="small-note"><strong>Split</strong>: ${escapeHtml(program.split)}</p>
            <p class="small-note"><strong>Fokus</strong>: ${escapeHtml(program.focus.join(", "))}</p>
            ${sessions}
            <p class="small-note">Beban adalah estimasi awal. Mulailah dari beban yang terasa ringan dan naikkan bertahap. Sesuaikan dengan arahan trainer.</p>
        </div>`;
}

function buildDescription(program) {
    const s = program.scores;
    let text = `Split ${program.split}, ${program.frequency_days} hari per minggu. `
        + `Rata-rata kemiripan latihan dengan profil Anda ${s.exercise_cosine_mean}; `
        + `kecocokan susunan otot ${s.split_cosine}.`;
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

    try {
        await loadExercisesFromCsv();
    } catch (error) {
        console.error("Gagal memuat pilihan target bagian tubuh:", error);
        result.innerHTML = '<p class="empty">Pilihan target bagian tubuh gagal dimuat. Silakan muat ulang halaman dan coba lagi.</p>';
        return;
    }
    if (!storedSession?.username) {
        result.innerHTML = '<p class="empty">Sesi pengguna tidak tersedia. Silakan masuk kembali.</p>';
        window.location.href = "../login/login.html";
        return;
    }

    validationHasRun = true;
    updateUnfilledState();

    const checkedValue = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;

    const experience = Number(checkedValue("experience") || 0);
    const days = readDays();
    const sessionMinutes = readMinutes();
    const primaryTarget = Number(checkedValue("primaryTarget") || 0);
    const physicalValue = checkedValue("physicalCondition");
    const selectedTargetBodyParts = getTargetBodyPartInputs()
        .filter((input) => input.checked)
        .map((input) => input.value);
    const facilityList = [...document.querySelectorAll('input[name="facility"]:checked')]
        .filter((input) => input.value !== "8")
        .map((input) => input.value);

    if (!days || !sessionMinutes) {
        result.innerHTML = `<p class="empty">Jumlah hari latihan harus ${MIN_DAYS}–${MAX_DAYS} dan durasi sesi ${MIN_MINUTES}–${MAX_MINUTES} menit.</p>`;
        return;
    }
    if (
        !experience ||
        !primaryTarget ||
        physicalValue === undefined ||
        !selectedTargetBodyParts.some((part) => part !== "full_body") ||
        !facilityList.length
    ) {
        result.innerHTML = '<p class="empty">Harap lengkapi semua pertanyaan penting sebelum melihat rekomendasi.</p>';
        return;
    }

    const advancedTargets = [...document.querySelectorAll('input[name="advancedTarget"]:checked')].map((input) => input.value);
    const limitationFields = {
        body_part: document.getElementById("bodyPart")?.value?.trim() || "",
        limitation: document.getElementById("limitation")?.value?.trim() || "",
        other_note: document.getElementById("otherNote")?.value?.trim() || ""
    };

    result.innerHTML = '<p class="empty">Menyusun program latihan Anda...</p>';

    let generated;
    try {
        generated = await apiRequest("/api/recommendations/generate", {
            method: "POST",
            body: JSON.stringify({
                experience,
                days,
                session_minutes: sessionMinutes,
                primary_target: primaryTarget,
                advanced_targets: advancedTargets,
                target_body_parts: selectedTargetBodyParts,
                facilities: facilityList,
                physical_condition: physicalValue,
                ...limitationFields,
                exercise_complexity: getExerciseComplexityValue(),
                weight: Number(weightInput?.value || 0),
                height: Number(heightInput?.value || 0),
                gender: document.getElementById("gender")?.value || "",
                age: Number(ageInput?.value || 0)
            })
        });
    } catch (error) {
        console.error("Gagal menyusun rekomendasi:", error);
        result.innerHTML = `<p class="empty">Rekomendasi gagal disusun: ${escapeHtml(error.message)}</p>`;
        return;
    }

    const warnings = generated.warnings || [];
    const programs = generated.programs || [];
    if (!programs.length) {
        const why = warnings.map((w) => `<p class="small-note">${escapeHtml(w)}</p>`).join("");
        result.innerHTML = `<p class="empty">Belum ada program yang cocok dengan kombinasi pilihan Anda.</p>${why}`;
        return;
    }

    const topThree = programs.map((program, index) => ({
        id: index + 1,
        name: program.name,
        internalName: program.split,
        split: `${program.split} • ${program.frequency_days}x/minggu • ~${formatMinutes(program.avg_session_minutes)}/sesi`,
        description: buildDescription(program),
        similarity: program.scores.final,
        percent: Math.round(program.scores.final * 1000) / 10,
        scores: program.scores,
        plan: renderProgramHtml(program),
        program,
        estimatedMinutes: Math.round(program.avg_session_minutes)
    }));

    const profilePayload = {
        name: document.getElementById("memberName")?.value?.trim() || storedSession.name || "",
        username: storedSession.username,
        age: document.getElementById("age")?.value || "",
        gender: document.getElementById("gender")?.value || "",
        height_cm: document.getElementById("height")?.value || "",
        weight_kg: document.getElementById("weight")?.value || "",
        body_fat_percent: document.getElementById("bodyFat")?.value || "",
        waist_cm: document.getElementById("waist")?.value || "",
        hip_cm: document.getElementById("hip")?.value || "",
        shoulder_width_cm: document.getElementById("shoulder")?.value || "",
        arm_length_cm: document.getElementById("armLength")?.value || "",
        leg_length_cm: document.getElementById("legLength")?.value || "",
        inside_foot_length_cm: document.getElementById("insideFootLength")?.value || "",
        torso_length_cm: document.getElementById("torsoLength")?.value || "",
        experience_level: String(experience),
        weekly_frequency: String(days),
        session_duration: String(sessionMinutes),
        target_primary: String(primaryTarget),
        target_body_parts: JSON.stringify(selectedTargetBodyParts),
        target_advanced: JSON.stringify(advancedTargets),
        physical_condition: String(physicalValue),
        ...limitationFields,
        exercise_complexity: getExerciseComplexityLabel(),
        facilities: JSON.stringify(facilityList)
    };

    try {
        await apiRequest(`/api/profile/${encodeURIComponent(storedSession.username)}`, {
            method: "PUT",
            body: JSON.stringify(profilePayload)
        });
        await apiRequest("/api/recommendations/current", {
            method: "PUT",
            body: JSON.stringify({ recommendations: topThree })
        });
        currentRecommendations = topThree;
    } catch (error) {
        console.error("Gagal menyimpan asesmen dan rekomendasi:", error);
        result.innerHTML = `<p class="empty">Data gagal disimpan ke database: ${escapeHtml(error.message)}</p>`;
        return;
    }

    const warningHtml = warnings.length
        ? `<div class="recommendation">${warnings.map((w) => `<p class="small-note">⚠ ${escapeHtml(w)}</p>`).join("")}</div>`
        : "";

    result.innerHTML = warningHtml + topThree
        .map((program) => `
            <div class="recommendation">
                <h3>${escapeHtml(program.name)}</h3>
                <p><strong>${escapeHtml(program.split)}</strong></p>
                <p>${escapeHtml(program.description)}</p>
                <p class="score">Skor kesesuaian: ${program.similarity}</p>
                ${program.plan}
                <button type="button" class="choose-plan" data-plan-name="${encodeURIComponent(program.name)}" data-plan-score="${program.similarity}">
                    Pilih ${escapeHtml(program.name)}
                </button>
            </div>
        `)
        .join("");
});

result.addEventListener("click", async function (event) {
    const trigger = event.target.closest(".choose-plan");
    if (!trigger) return;

    const selectedName = decodeURIComponent(trigger.dataset.planName);
    const selected = currentRecommendations.find((item) => item.name === selectedName);

    if (!selected) return;

    try {
        await apiRequest("/api/recommendations/selected", {
            method: "PUT",
            body: JSON.stringify({
                selected_plan: {
                    ...selected,
                    chosenAt: new Date().toISOString()
                }
            })
        });
        window.location.href = "../dashboard/index.html";
    } catch (error) {
        console.error("Gagal menyimpan program pilihan:", error);
        result.insertAdjacentHTML("afterbegin", `<p class="empty">Program pilihan gagal disimpan: ${escapeHtml(error.message)}</p>`);
    }
});