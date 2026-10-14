        const API_BASE = "";
        let sessionUser = null;
        let loadedProfile = {};
        let recommendations = [];

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function parseStoredArray(value) {
            if (Array.isArray(value)) return value.map(String);
            if (typeof value !== 'string' || !value) return [];
            try {
                const parsed = JSON.parse(value);
                return Array.isArray(parsed) ? parsed.map(String) : [];
            } catch {
                return [];
            }
        }

        function formatRest(sec) {
            if (!sec) return '';
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
            const side = e.unilateral ? ' per sisi' : '';
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
            if (!mob || !Array.isArray(mob.exercises) || !mob.exercises.length) return '';
            const items = mob.exercises.map((m) => {
                const side = m.unilateral ? ' per sisi' : '';
                return `<li><strong>${escapeHtml(m.name)}</strong> (${escapeHtml(m.muscle)}) — ${m.sets}x ${m.seconds_per_set} detik${side}</li>`;
            }).join('');
            return `
                <div class="addon-block">
                    <p class="small-note"><strong>+ Blok Tambahan Mobility &amp; Flexibility (di luar durasi sesi inti: ~${escapeHtml(mob.est_text)})</strong></p>
                    <ul>${items}</ul>
                </div>`;
        }

        function renderCardioBlock(cardio) {
            if (!cardio) return '';
            return `
                <div class="addon-block">
                    <p class="small-note"><strong>+ Blok Tambahan Cardio &amp; Conditioning (di luar durasi sesi inti: ${formatMinutes(cardio.minutes)})</strong></p>
                    <ul>
                        <li><strong>${escapeHtml(cardio.name)}</strong> | ${formatMinutes(cardio.minutes)} | ${escapeHtml(cardio.intensity || 'Zona 2')}</li>
                    </ul>
                </div>`;
        }

        function renderProgramHtml(program, metaProfile) {
            const anthroNotes = (metaProfile?.anthropometry?.applied || [])
                .map((note) => `<p>• <em>Penyesuaian Antropometri:</em> ${escapeHtml(note)}</p>`)
                .join('');

            const sessions = program.sessions.map((s, idx) => {
                const exerciseCards = s.exercises.map(renderExerciseLine).join('');
                const addonNote = s.addon_seconds
                    ? ` + ~${formatMinutes(Math.round(s.addon_seconds / 60))} di luar sesi`
                    : '';
                return `
                    <details class="daily-workout-card card p-6" ${idx === 0 ? 'open' : ''}>
                        <summary class="daily-card-summary">
                            <div class="daily-summary-left flex items-center space-x-4">
                                <span class="day-badge">Hari ${idx + 1}</span>
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
            }).join('');

            return `
                <div class="plan space-y-4">
                    <div class="meta-specs-grid">
                        <div class="spec-pill">
                            <span class="spec-label">Target Utama</span>
                            <span class="spec-val">${escapeHtml(program.primary_target_label || metaProfile?.primary_target_label || '-')}</span>
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
                            <span class="spec-val">${escapeHtml((program.focus || []).join(', '))}</span>
                        </div>
                    </div>
                    ${anthroNotes ? `<div class="anthro-notes">${anthroNotes}</div>` : ''}
                    <div class="daily-workouts-section space-y-4">
                        ${sessions}
                    </div>
                    <p class="initial-load-note">Beban adalah estimasi awal. Anda dapat mengkustomisasi jadwal hari, menukar latihan, atau menyesuaikan beban bersama Personal Trainer di Beranda.</p>
                </div>`;
        }

        function buildDescription(program) {
            const s = program.scores;
            let text = `[${program.primary_target_label || 'Program Terpersonalisasi'}] Split ${program.split}, ${program.frequency_days} hari per minggu. `
                + `Rata-rata kemiripan latihan dengan profil Anda ${s.exercise_cosine_mean}; `
                + `kecocokan target otot dengan split ${s.split_cosine}; `
                + `keseimbangan pola gerak ${s.movement_balance ?? 'belum tersedia'}.`;
            if (program.uncovered_targets && program.uncovered_targets.length) {
                text += ` Belum tercakup: ${program.uncovered_targets.join(', ')}.`;
            }
            return text;
        }

        function renderRecommendations(data) {
            recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
            // Pastikan program rekomendasi terurut tegas dari skor kecocokan tertinggi ke terendah (Top 1, Top 2, Top 3)
            recommendations.sort((a, b) => {
                const scoreA = Number(a.similarity ?? a.scores?.final ?? (a.percent ? a.percent / 100 : 0));
                const scoreB = Number(b.similarity ?? b.scores?.final ?? (b.percent ? b.percent / 100 : 0));
                return scoreB - scoreA;
            });

            const container = document.getElementById('profileRecommendations');
            if (!recommendations.length) {
                container.innerHTML = '<p class="empty">Belum ada hasil rekomendasi. Silakan ambil asesmen atau klik tombol Perbarui Rekomendasi di atas.</p>';
                return;
            }

            const savedPlanName = data.selected_plan?.name;
            container.innerHTML = recommendations.map((program, index) => `
                <article class="recommendation">
                    <label class="recommendation-choice">
                        <input type="radio" name="selectedPlan" value="${index}" ${(program.name === savedPlanName || (!savedPlanName && index === 0)) ? 'checked' : ''}>
                        <span>
                            <strong>${escapeHtml(program.name)}</strong>
                            <span class="recommendation-split">${escapeHtml(program.split || '')}</span>
                        </span>
                    </label>
                    <p>${escapeHtml(program.description || '')}</p>
                    <div class="score-highlight" style="margin-bottom: 12px;">
                        <span class="score-label">Skor Kesesuaian</span>
                        <div class="score-value-row">
                            <span class="score-percent">${escapeHtml(program.percent ?? '')}%</span>
                            <span class="score-raw">(${escapeHtml(program.similarity ?? '')})</span>
                        </div>
                    </div>
                    <details class="recommendation-details">
                        <summary>Lihat detail program</summary>
                        ${program.plan || '<p>Detail program belum tersedia.</p>'}
                    </details>
                </article>
            `).join('');
            container.addEventListener('change', () => setProfileMessage(''), { once: true });
        }

        function setProfileMessage(message, isError = false) {
            const element = document.getElementById('profileMessage');
            element.textContent = message;
            element.classList.toggle('error-message', isError);
        }

        async function apiRequest(path, options = {}) {
            const response = await fetch(`${API_BASE}${path}`, {
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    ...(options.headers || {})
                },
                ...options
            });

            const contentType = response.headers.get('content-type') || '';
            const payload = contentType.includes('application/json') ? await response.json() : await response.text();

            if (!response.ok) {
                const message = typeof payload === 'object' && payload ? (payload.error || payload.message) : String(payload || 'Request gagal.');
                const error = new Error(message || 'Request gagal.');
                error.status = response.status;
                throw error;
            }

            return payload;
        }

        document.querySelectorAll('[data-action="logout"]').forEach((button) => {
            button.addEventListener('click', async () => {
                button.disabled = true;
                try {
                    await apiRequest('/api/auth/logout', { method: 'POST' });
                } catch (error) {
                    alert(`Logout gagal: ${error.message}`);
                    button.disabled = false;
                    return;
                }
                window.location.replace('/auth/login');
            });
        });

        window.addEventListener('pageshow', (event) => {
            if (event.persisted) window.location.reload();
        });

        /* ---------------------------------------------------------------
           Engine Komposisi Tubuh Atletik Modern (FFMI & WtHR)
        ---------------------------------------------------------------- */
        function classifyFfmi(ffmi, gender) {
            if (!ffmi || ffmi <= 0) return "Belum ada data";
            const isFemale = (gender === "P");
            if (isFemale) {
                if (ffmi < 15.0) return "Di Bawah Rata-rata";
                if (ffmi < 17.0) return "Normal / Rata-rata";
                if (ffmi < 19.0) return "Atletis & Terlatih";
                if (ffmi < 22.0) return "Sangat Berotot / Hipertrofi Prima";
                return "Potensi Genetik Maksimal / Elite";
            }
            if (ffmi < 18.0) return "Di Bawah Rata-rata";
            if (ffmi < 20.0) return "Normal / Rata-rata";
            if (ffmi < 22.0) return "Atletis & Terlatih";
            if (ffmi < 25.0) return "Sangat Berotot / Hipertrofi Prima";
            return "Potensi Genetik Maksimal / Elite";
        }

        function classifyWthr(wthr) {
            if (!wthr || wthr <= 0) return "";
            if (wthr < 0.50) return "Optimal Sehat (Rasio Perut Seimbang)";
            if (wthr < 0.60) return "Perhatian Lemak Sentral (Prioritas Metabolik)";
            return "Adipositas Sentral Tinggi (Proteksi Sendi & Kardio)";
        }

        function estimateBodyFatDeurenberg(bmi, age, gender) {
            if (!bmi || bmi <= 0) return gender === "P" ? 25.0 : 18.0;
            const ageVal = age && age > 0 ? age : 25;
            const sexVal = gender === "P" ? 0 : 1;
            const est = 1.20 * bmi + 0.23 * ageVal - 10.8 * sexVal - 5.4;
            return Math.max(5.0, Math.min(55.0, Number(est.toFixed(1))));
        }

        function updateAthleticMetricsFromProfile(profile) {
            const box = document.getElementById("athleticMetricsBox");
            if (!box) return;
            const heightCm = Number(profile.height_cm || 0);
            const weightKg = Number(profile.weight_kg || 0);
            const age = Number(profile.age || 0);
            const gender = profile.gender || "L";
            const waistCm = Number(profile.waist_cm || 0);
            const cardioLevel = Number(profile.cardio_endurance || 2);

            const ffmiValue = document.getElementById("ffmiValue");
            const wthrChip = document.getElementById("wthrChip");
            const wthrValue = document.getElementById("wthrValue");
            const athleticStatusText = document.getElementById("athleticStatusText");
            const leanMassText = document.getElementById("leanMassText");
            const fatMassText = document.getElementById("fatMassText");

            if (!heightCm || !weightKg || heightCm <= 0 || weightKg <= 0) {
                box.hidden = true;
                if (ffmiValue) ffmiValue.textContent = "0.0";
                if (wthrChip) wthrChip.hidden = true;
                return;
            }

            box.hidden = false;
            const heightM = heightCm / 100;
            const bmi = weightKg / (heightM * heightM);

            let bfPct = 0;
            let isEstimated = false;
            const rawBf = profile.body_fat_percent;
            if (rawBf !== undefined && rawBf !== null && rawBf !== "" && !Number.isNaN(Number(rawBf)) && Number(rawBf) > 0) {
                bfPct = Math.max(3.0, Math.min(60.0, Number(rawBf)));
            } else {
                bfPct = estimateBodyFatDeurenberg(bmi, age, gender);
                isEstimated = true;
            }

            const fatMass = weightKg * (bfPct / 100);
            const leanMass = Math.max(0, weightKg - fatMass);
            let ffmi = 0;
            if (profile.ffmi && Number(profile.ffmi) > 0) {
                ffmi = Number(profile.ffmi);
            } else if (heightM > 0 && leanMass > 0) {
                ffmi = leanMass / (heightM * heightM);
            }

            if (ffmiValue) {
                ffmiValue.textContent = ffmi.toFixed(1) + (isEstimated ? " ~ estimasi" : "");
            }
            if (leanMassText) leanMassText.textContent = `Massa Bebas Lemak: ${leanMass.toFixed(1)} kg`;
            if (fatMassText) fatMassText.textContent = `Massa Lemak: ${fatMass.toFixed(1)} kg (${bfPct.toFixed(1)}%)`;

            let wthr = 0;
            if (profile.wthr && Number(profile.wthr) > 0) {
                wthr = Number(profile.wthr);
            } else if (waistCm > 0 && heightCm > 0) {
                wthr = waistCm / heightCm;
            }

            if (wthr > 0 && wthrChip && wthrValue) {
                wthrChip.hidden = false;
                wthrValue.textContent = wthr.toFixed(2);
            } else if (wthrChip) {
                wthrChip.hidden = true;
            }

            const ffmiStatus = classifyFfmi(ffmi, gender);
            let statusText = `Klasifikasi FFMI: ${ffmiStatus}`;
            if (wthr > 0) {
                statusText += ` • WtHR: ${classifyWthr(wthr)}`;
            }

            let recoveryBonus = 0;
            if (wthr >= 0.55 || (gender === "L" ? bfPct >= 25 : bfPct >= 32)) recoveryBonus += 15;
            if (cardioLevel === 1) recoveryBonus += 15;
            recoveryBonus = Math.min(30, recoveryBonus);

            if (recoveryBonus > 0) {
                statusText += ` • Penyesuaian jeda istirahat: +${recoveryBonus} detik/set`;
            }
            if (athleticStatusText) athleticStatusText.textContent = statusText;
        }

        function fillProfile(profile) {
            // User Data
            const viewName = document.getElementById('viewName');
            if (viewName) viewName.textContent = profile.name || '-';
            const viewUsername = document.getElementById('viewUsername');
            if (viewUsername) viewUsername.textContent = profile.username || '-';

            // Basic Data & Body Composition
            const viewAge = document.getElementById('viewAge');
            if (viewAge) viewAge.textContent = profile.age ? `${profile.age} tahun` : '-';
            const viewGender = document.getElementById('viewGender');
            if (viewGender) viewGender.textContent = profile.gender === 'L' ? 'Laki-laki' : (profile.gender === 'P' ? 'Perempuan' : '-');
            const viewHeight = document.getElementById('viewHeight');
            if (viewHeight) viewHeight.textContent = profile.height_cm ? `${profile.height_cm} cm` : '-';
            const viewWeight = document.getElementById('viewWeight');
            if (viewWeight) viewWeight.textContent = profile.weight_kg ? `${profile.weight_kg} kg` : '-';

            const cardioMap = {
                '1': 'Rendah (mudah lelah)',
                '2': 'Sedang / Normal',
                '3': 'Baik / Terlatih'
            };
            const viewCardio = document.getElementById('viewCardio');
            if (viewCardio) viewCardio.textContent = cardioMap[String(profile.cardio_endurance || '2')] || 'Sedang / Normal';

            const viewBodyFat = document.getElementById('viewBodyFat');
            if (viewBodyFat) {
                if (profile.body_fat_percent && Number(profile.body_fat_percent) > 0) {
                    viewBodyFat.textContent = `${profile.body_fat_percent}% (Data terukur)`;
                } else {
                    viewBodyFat.textContent = 'Estimasi otomatis';
                }
            }

            // Anthropometry
            const anthroMap = [
                ['viewWaist', profile.waist_cm],
                ['viewHip', profile.hip_cm],
                ['viewShoulder', profile.shoulder_width_cm],
                ['viewArmLength', profile.arm_length_cm],
                ['viewLegLength', profile.leg_length_cm],
                ['viewInsideFootLength', profile.inside_foot_length_cm],
                ['viewTorsoLength', profile.torso_length_cm]
            ];
            anthroMap.forEach(([elId, val]) => {
                const el = document.getElementById(elId);
                if (el) el.textContent = (val !== undefined && val !== null && val !== '' && Number(val) > 0) ? `${val} cm` : '-';
            });

            // Training Parameters & Preferences
            const viewWeeklyFrequency = document.getElementById('viewWeeklyFrequency');
            if (viewWeeklyFrequency) viewWeeklyFrequency.textContent = `${profile.weekly_frequency || 3} hari per minggu`;

            const viewSessionDuration = document.getElementById('viewSessionDuration');
            if (viewSessionDuration) viewSessionDuration.textContent = `${profile.session_duration || 60} menit per sesi`;

            const tierMap = {
                rookie: 'Rookie (< 6 bln)',
                novice: 'Novice (6–12 bln)',
                intermediate: 'Intermediate (1–2 thn)',
                upper_intermediate: 'Upper Intermediate (2–4 thn)',
                advanced: 'Advanced (4–7 thn)',
                veteran: 'Veteran (> 7 thn)'
            };
            const currentTier = String(profile.training_age_tier || profile.experience_level || 'novice').toLowerCase();
            const viewTrainingAgeTier = document.getElementById('viewTrainingAgeTier');
            if (viewTrainingAgeTier) viewTrainingAgeTier.textContent = tierMap[currentTier] || 'Novice (6–12 bln)';

            const complexityMap = {
                simple: 'Sederhana & praktis (dominan mesin)',
                balanced: 'Seimbang (mesin & free weight)',
                technical: 'Teknis tinggi / kompleks (free weight & barbell rack)'
            };
            const viewExerciseComplexity = document.getElementById('viewExerciseComplexity');
            if (viewExerciseComplexity) viewExerciseComplexity.textContent = complexityMap[profile.exercise_complexity || 'balanced'] || 'Campuran (mesin & free weight)';

            const targetMap = {
                '0': 'Peningkatan Kesehatan & Kualitas Hidup',
                '1': 'Fat Loss & Ketahanan',
                '2': 'Bentuk Tubuh Ideal & Hipertrofi',
                '3': 'Kekuatan & Performa Atletik'
            };
            const viewDerivedTarget = document.getElementById('viewDerivedTarget');
            if (viewDerivedTarget) viewDerivedTarget.textContent = targetMap[String(profile.target_primary || '2')] || 'Bentuk Tubuh Ideal & Hipertrofi';

            // Specific targets badges
            const advancedTargets = parseStoredArray(profile.target_advanced);
            const viewAdvancedTargets = document.getElementById('viewAdvancedTargets');
            if (viewAdvancedTargets) {
                if (advancedTargets.length) {
                    viewAdvancedTargets.innerHTML = advancedTargets.map(t => `<span class="readonly-badge neutral">${escapeHtml(t)}</span>`).join('');
                } else {
                    viewAdvancedTargets.innerHTML = `<span class="readonly-badge neutral">Bentuk Tubuh Ideal</span>`;
                }
            }

            // Focus Areas badges
            const focusMap = {
                chest: 'Dada',
                back: 'Punggung',
                shoulders: 'Bahu',
                glutes: 'Glutes',
                thighs: 'Paha',
                arms: 'Lengan',
                calves: 'Betis',
                core: 'Perut'
            };
            const focusAreas = parseStoredArray(profile.focus_areas);
            const viewFocusAreas = document.getElementById('viewFocusAreas');
            if (viewFocusAreas) {
                if (focusAreas.length) {
                    viewFocusAreas.innerHTML = focusAreas.map(f => `<span class="readonly-badge highlight">${escapeHtml(focusMap[f] || f)}</span>`).join('');
                } else {
                    viewFocusAreas.innerHTML = `<span class="readonly-badge neutral">Seluruh tubuh seimbang</span>`;
                }
            }

            // Modalities badges
            const modalities = parseStoredArray(profile.modalities);
            const viewModalities = document.getElementById('viewModalities');
            if (viewModalities) {
                const badges = ['<span class="readonly-badge neutral">Resistance Training &amp; Muscle Building (Inti)</span>'];
                if (modalities.includes('cardio')) {
                    badges.push('<span class="readonly-badge highlight">+ Cardio &amp; Conditioning</span>');
                }
                if (modalities.includes('mobility')) {
                    badges.push('<span class="readonly-badge highlight">+ Mobility &amp; Flexibility</span>');
                }
                viewModalities.innerHTML = badges.join('');
            }

            // Physical condition / Limitations
            const hasLimitation = (String(profile.physical_condition) === '1' || profile.physical_condition === 1);
            const viewLimitation = document.getElementById('viewLimitation');
            if (viewLimitation) {
                if (hasLimitation) {
                    const complaint = escapeHtml(profile.limitation_story || profile.limitation || 'Ada kondisi fisik tertentu');
                    viewLimitation.innerHTML = `<span class="readonly-badge highlight">Ada kondisi tertentu</span> <span style="margin-left: 8px;">${complaint}</span>`;
                } else {
                    viewLimitation.innerHTML = `<span class="readonly-badge neutral">Tidak ada keluhan</span>`;
                }
            }

            // Update athletic metrics box
            updateAthleticMetricsFromProfile(profile);
        }

        async function loadProfile() {
            try {
                sessionUser = (await apiRequest('/api/auth/session')).user;
                loadedProfile = await apiRequest(`/api/profile/${encodeURIComponent(sessionUser.username)}`);
                fillProfile(loadedProfile);
                const recommendationData = await apiRequest('/api/recommendations/current');
                renderRecommendations(recommendationData);
            } catch (error) {
                if (error.status === 401) {
                    window.location.href = '../login/login.html';
                    return;
                }
                alert(`Profil gagal dimuat dari database: ${error.message}`);
            }
        }

        document.getElementById('saveSelectedPlanBtn')?.addEventListener('click', async () => {
            const btn = document.getElementById('saveSelectedPlanBtn');
            const selectedInput = document.querySelector('input[name="selectedPlan"]:checked');
            if (recommendations.length && !selectedInput) {
                setProfileMessage('Pilih salah satu program rekomendasi terlebih dahulu.', true);
                document.getElementById('recommendations')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                return;
            }
            const selectedPlan = selectedInput ? recommendations[Number(selectedInput.value)] : null;
            if (selectedInput && !selectedPlan) {
                setProfileMessage('Pilihan program tidak valid. Muat ulang halaman lalu coba lagi.', true);
                return;
            }

            btn.disabled = true;
            setProfileMessage('Menyimpan program pilihan...');
            try {
                if (selectedPlan) {
                    await apiRequest('/api/recommendations/selected', {
                        method: 'PUT',
                        body: JSON.stringify({
                            selected_plan: {
                                ...selectedPlan,
                                name: selectedPlan.default_name || selectedPlan.name,
                                default_name: selectedPlan.default_name || selectedPlan.name,
                                custom_name: null,
                                chosenAt: new Date().toISOString()
                            }
                        })
                    });
                }
                setProfileMessage('Program pilihan berhasil disimpan!');
                window.location.href = '../dashboard/index.html';
            } catch (error) {
                setProfileMessage(`Gagal menyimpan program pilihan: ${error.message}`, true);
                btn.disabled = false;
            }
        });

        /* ---------------------------------------------------------------
           Alur Hapus Akun Permanen (2-Step Secure Confirmation Flow)
        ---------------------------------------------------------------- */
        const CONFIRMATION_PHRASE = 'hapus akun permanen';
        const deleteModalStep1 = document.getElementById('deleteModalStep1');
        const deleteModalStep2 = document.getElementById('deleteModalStep2');
        const deleteConfirmInput = document.getElementById('deleteConfirmInput');
        const proceedDeleteStep1Btn = document.getElementById('proceedDeleteStep1Btn');
        const cancelDeleteStep1Btn = document.getElementById('cancelDeleteStep1Btn');
        const cancelDeleteStep2Btn = document.getElementById('cancelDeleteStep2Btn');
        const confirmFinalDeleteBtn = document.getElementById('confirmFinalDeleteBtn');
        const deleteAccountBtn = document.getElementById('deleteAccountBtn');

        deleteAccountBtn?.addEventListener('click', () => {
            if (deleteConfirmInput) deleteConfirmInput.value = '';
            if (proceedDeleteStep1Btn) proceedDeleteStep1Btn.disabled = true;
            if (deleteModalStep1) deleteModalStep1.hidden = false;
            deleteConfirmInput?.focus();
        });

        deleteConfirmInput?.addEventListener('input', () => {
            const typed = (deleteConfirmInput.value || '').trim().toLowerCase();
            if (proceedDeleteStep1Btn) {
                proceedDeleteStep1Btn.disabled = (typed !== CONFIRMATION_PHRASE);
            }
        });

        cancelDeleteStep1Btn?.addEventListener('click', () => {
            if (deleteModalStep1) deleteModalStep1.hidden = true;
            if (deleteConfirmInput) deleteConfirmInput.value = '';
        });

        proceedDeleteStep1Btn?.addEventListener('click', () => {
            const typed = (deleteConfirmInput.value || '').trim().toLowerCase();
            if (typed === CONFIRMATION_PHRASE) {
                if (deleteModalStep1) deleteModalStep1.hidden = true;
                if (deleteModalStep2) deleteModalStep2.hidden = false;
            }
        });

        cancelDeleteStep2Btn?.addEventListener('click', () => {
            if (deleteModalStep2) deleteModalStep2.hidden = true;
        });

        confirmFinalDeleteBtn?.addEventListener('click', async () => {
            confirmFinalDeleteBtn.disabled = true;
            confirmFinalDeleteBtn.textContent = 'Menghapus akun...';
            try {
                await apiRequest(`/api/profile/${encodeURIComponent(sessionUser.username)}`, {
                    method: 'DELETE'
                });
                localStorage.clear();
                sessionStorage.clear();
                window.location.replace('/auth/login');
            } catch (error) {
                alert(`Penghapusan akun gagal: ${error.message}`);
                confirmFinalDeleteBtn.disabled = false;
                confirmFinalDeleteBtn.textContent = 'Ya, hapus akun secara permanen';
                if (deleteModalStep2) deleteModalStep2.hidden = true;
            }
        });

        loadProfile();
