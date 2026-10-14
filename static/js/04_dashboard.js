        const API_BASE = "";
        const container = document.getElementById('selectedPlan');
        const DAYS_OF_WEEK = ['', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];
        const DEFAULT_DAY_MAP = {
            1: ['Rabu'],
            2: ['Selasa', 'Jumat'],
            3: ['Senin', 'Rabu', 'Jumat'],
            4: ['Senin', 'Selasa', 'Kamis', 'Jumat'],
            5: ['Senin', 'Selasa', 'Rabu', 'Jumat', 'Sabtu'],
            6: ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu']
        };

        let currentSaved = null;
        let safeAlternatives = {};
        let isEditMode = false;

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
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

        function fmtMmSs(sec) {
            sec = Math.round(sec);
            const m = Math.floor(sec / 60);
            const s = sec % 60;
            if (m && s) return `${m} menit ${s} detik`;
            if (m) return `${m} menit`;
            return `${s} detik`;
        }

        function recalcExerciseSeconds(e) {
            const sets = Math.max(1, Number(e.sets || 3));
            const reps = e.seconds_per_set ? null : Math.max(1, Number(e.reps || 10));
            const secondsPerSet = e.seconds_per_set ? Math.max(5, Number(e.seconds_per_set)) : null;
            const rest = Math.max(15, Number(e.rest_sec || 60));
            const secPerRep = Number(e.sec_per_rep || 3);
            let work = sets * (secondsPerSet ? secondsPerSet : reps * secPerRep);
            if (e.unilateral) work *= 2;
            const workWithFatigue = work * 1.15;
            const restTime = Math.max(0, sets - 1) * rest;
            const setupTime = Number(e.setup_seconds || 30);
            const total = Math.round(workWithFatigue + restTime + setupTime + 45);
            e.sets = sets;
            if (secondsPerSet) {
                e.seconds_per_set = secondsPerSet;
            } else {
                e.reps = reps;
            }
            e.rest_sec = rest;
            e.est_seconds = total;
            e.est_text = fmtMmSs(total);
        }

        function recalcProgramTotals(program) {
            if (!program || !Array.isArray(program.sessions)) return;
            let weeklySec = 0;
            let weeklyAddonSec = 0;
            program.sessions.forEach((s) => {
                let exsSec = 0;
                (s.exercises || []).forEach((e) => {
                    recalcExerciseSeconds(e);
                    exsSec += e.est_seconds;
                });
                const warmSec = Number(s.warmup?.est_seconds || 300);
                const coolSec = Number(s.cooldown?.est_seconds || 300);
                s.total_seconds = warmSec + exsSec + coolSec;
                s.total_minutes = Math.round((s.total_seconds / 60) * 10) / 10;
                const addonSec = Number(s.cardio_block?.est_seconds || 0) + Number(s.mobility_block?.est_seconds || 0);
                s.addon_seconds = addonSec;
                weeklySec += s.total_seconds;
                weeklyAddonSec += addonSec;
            });
            program.avg_session_minutes = Math.round(
                (program.sessions.reduce((sum, s) => sum + s.total_minutes, 0) / program.sessions.length) * 10
            ) / 10;
            program.weekly_minutes = Math.round(weeklySec / 60);
            program.weekly_addon_minutes = Math.round(weeklyAddonSec / 60);
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

        function renderDailySessionsHtml(program) {
            return program.sessions.map((s, idx) => {
                const exerciseCards = s.exercises.map(renderExerciseLine).join('');
                const dayBadge = s.day_name ? ` (${escapeHtml(s.day_name)})` : '';
                const addonNote = s.addon_seconds
                    ? ` + ~${formatMinutes(Math.round(s.addon_seconds / 60))} di luar sesi`
                    : '';
                return `
                    <details class="daily-workout-card card p-6" ${idx === 0 ? 'open' : ''}>
                        <summary class="daily-card-summary">
                            <div class="daily-summary-left flex items-center space-x-4">
                                <span class="day-badge">Hari ${idx + 1}${dayBadge}</span>
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
                                <span class="phase-name"><strong>${escapeHtml(s.warmup?.name || 'Pemanasan Dinamis')}</strong> • Estimasi ${escapeHtml(s.warmup?.est_text || '5 menit')}</span>
                            </div>
                            <hr class="section-divider">
                            <div class="exercise-grid grid-cols-2 gap-y-3 gap-x-4">
                                ${exerciseCards}
                            </div>
                            <hr class="section-divider">
                            <div class="session-phase cooldown">
                                <span class="phase-pill cooldown">Pendinginan</span>
                                <span class="phase-name"><strong>${escapeHtml(s.cooldown?.name || 'Pendinginan & Peregangan')}</strong> • Estimasi ${escapeHtml(s.cooldown?.est_text || '5 menit')}</span>
                            </div>
                            ${renderCardioBlock(s.cardio_block)}
                            ${renderMobilityBlock(s.mobility_block)}
                        </div>
                    </details>`;
            }).join('');
        }

        function renderProgramHtmlFromObject(program, metaProfile) {
            const dailyCards = renderDailySessionsHtml(program);
            return `
                <div class="daily-workouts-section space-y-4">
                    <div class="daily-section-header">
                        <h3>Jadwal &amp; Rincian Sesi Latihan</h3>
                        <span class="daily-section-count">${program.sessions.length} Hari Sesi</span>
                    </div>
                    ${dailyCards}
                    <p class="initial-load-note">Beban adalah estimasi awal. Mulailah dari beban yang terasa ringan dan naikkan bertahap bersama Personal Trainer.</p>
                </div>`;
        }

        function renderCustomizeEditor(program) {
            const defaultDays = DEFAULT_DAY_MAP[program.sessions.length] || [];
            const sessionBlocks = program.sessions.map((s, sIdx) => {
                const chosenDay = s.day_name ?? (defaultDays[sIdx] || '');
                const dayOptions = DAYS_OF_WEEK.map((d) =>
                    `<option value="${escapeHtml(d)}" ${d === chosenDay ? 'selected' : ''}>${d || '-- Pilih Hari --'}</option>`
                ).join('');

                const exRows = s.exercises.map((e, eIdx) => {
                    const alts = safeAlternatives[e.muscle_key] || [];
                    const hasCurrent = alts.some((a) => a.id === e.id);
                    const list = hasCurrent ? alts : [{ id: e.id, name: e.name, muscle: e.muscle }, ...alts];
                    const exOptions = list.map((a) =>
                        `<option value="${escapeHtml(a.id)}" ${a.id === e.id ? 'selected' : ''}>${escapeHtml(a.name)} (${escapeHtml(a.muscle)})</option>`
                    ).join('');
                    const repOrSecField = e.seconds_per_set
                        ? `<div class="field"><label>Detik / Set</label><input type="number" min="10" max="180" step="5" data-edit="seconds" data-s="${sIdx}" data-e="${eIdx}" value="${e.seconds_per_set}"></div>`
                        : `<div class="field"><label>Repetisi (Reps)</label><input type="number" min="1" max="30" step="1" data-edit="reps" data-s="${sIdx}" data-e="${eIdx}" value="${e.reps || 10}"></div>`;

                    return `
                        <div class="section-block compact-block">
                            <div class="grid two-col">
                                <div class="field">
                                    <label>Variasi Latihan (${escapeHtml(e.muscle)})</label>
                                    <select data-edit="swap" data-s="${sIdx}" data-e="${eIdx}">${exOptions}</select>
                                </div>
                                <div class="field">
                                    <label>Beban Kerja</label>
                                    <input type="text" data-edit="load" data-s="${sIdx}" data-e="${eIdx}" value="${escapeHtml(e.load_text || '')}">
                                </div>
                            </div>
                            <div class="grid three-col">
                                <div class="field">
                                    <label>Jumlah Set</label>
                                    <input type="number" min="1" max="6" step="1" data-edit="sets" data-s="${sIdx}" data-e="${eIdx}" value="${e.sets}">
                                </div>
                                ${repOrSecField}
                                <div class="field">
                                    <label>Jeda Antar Set (detik)</label>
                                    <input type="number" min="15" max="300" step="5" data-edit="rest" data-s="${sIdx}" data-e="${eIdx}" value="${e.rest_sec || 60}">
                                </div>
                            </div>
                        </div>`;
                }).join('');

                return `
                    <div class="section-block">
                        <div class="grid two-col">
                            <div class="field">
                                <h4>Hari ${sIdx + 1}: ${escapeHtml(s.label)}</h4>
                                <p class="small-note">Estimasi sesi: ~${formatMinutes(s.total_minutes)}</p>
                            </div>
                            <div class="field">
                                <label>Jadwal Hari</label>
                                <select data-edit="day" data-s="${sIdx}">${dayOptions}</select>
                            </div>
                        </div>
                        ${exRows}
                    </div>`;
            }).join('');

            return `
                <div class="section-block" style="margin-top: var(--space-4, 16px);">
                    <h3>Kustomisasi Jadwal Hari &amp; Latihan (Bersama Personal Trainer)</h3>
                    <p class="small-note">Pilih hari latihan untuk setiap sesi, tukar variasi gerakan dari daftar yang telah lolos filter keamanan profil Anda, atau sesuaikan set, repetisi, beban, dan waktu istirahat.</p>
                    ${sessionBlocks}
                    <p id="customizeMsg" class="form-message" role="status"></p>
                    <div class="button-row">
                        <button type="button" id="saveCustomizeBtn">Simpan Penyesuaian Program</button>
                        <button type="button" class="secondary" id="cancelCustomizeBtn">Tutup Kustomisasi</button>
                    </div>
                </div>`;
        }

        async function apiRequest(path, options = {}) {
            const response = await fetch(`${API_BASE}${path}`, {
                credentials: 'include',
                headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
                ...options
            });
            const contentType = response.headers.get('content-type') || '';
            const payload = contentType.includes('application/json') ? await response.json() : await response.text();
            if (!response.ok) {
                const message = typeof payload === 'object' && payload
                    ? (payload.error || payload.message)
                    : String(payload || 'Request gagal.');
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

        let memberLabel = 'Halo, member';

        function renderDashboardView() {
            if (!currentSaved) {
                container.innerHTML = `
                    <div class="card">
                        <p class="welcome-text">${escapeHtml(memberLabel)}</p>
                        <p class="empty">Belum ada program yang dipilih. Silakan ambil asesmen atau pilih rekomendasi yang paling sesuai.</p>
                        <div class="button-row">
                            <a href="/asesmen" class="inline-link">Mulai Asesmen</a>
                            <button type="button" class="secondary" onclick="window.location.href='/profile'">Profil &amp; Akun</button>
                        </div>
                    </div>
                `;
                return;
            }

            const programObj = currentSaved.program;
            const metaProfile = currentSaved.metaProfile;
            const similarity = escapeHtml(currentSaved.similarity ?? '-');
            const percentVal = currentSaved.percent ?? (currentSaved.similarity ? Math.round(Number(currentSaved.similarity) * 1000) / 10 : 0);
            const percent = escapeHtml(percentVal);

            const defaultName = currentSaved.default_name || programObj?.name || currentSaved.name || 'Program Latihan';
            if (!currentSaved.default_name) currentSaved.default_name = defaultName;
            const currentName = currentSaved.custom_name || currentSaved.name || defaultName;
            const isCustomized = Boolean(currentSaved.custom_name && currentSaved.custom_name !== defaultName);

            const anthroNotes = (metaProfile?.anthropometry?.applied || [])
                .map((note) => `<p>• <em>Penyesuaian Antropometri:</em> ${escapeHtml(note)}</p>`)
                .join('');

            const dailySectionHtml = programObj
                ? renderProgramHtmlFromObject(programObj, metaProfile)
                : `<div class="daily-workouts-section space-y-4">${currentSaved.plan || '<p>Detail program belum tersedia.</p>'}</div>`;

            container.innerHTML = `
                <div>
                    <p class="welcome-text">${escapeHtml(memberLabel)}</p>
                </div>

                <!-- Program Meta-Data Card -->
                <article class="program-meta-card card">
                    <div class="meta-card-header flex items-center justify-between">
                        <div class="meta-card-title-group">
                            <div class="program-title-wrapper">
                                <div id="programTitleDisplay" class="program-title-display">
                                    <h3 id="programTitleHeading" class="program-title-heading" title="Klik untuk mengubah nama program">
                                        ${escapeHtml(currentName)}
                                    </h3>
                                    <button type="button" id="editTitleBtn" class="title-action-btn edit" title="Ubah nama program" aria-label="Ubah nama program">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                        </svg>
                                    </button>
                                    ${isCustomized ? `
                                        <button type="button" id="resetTitleBtn" class="title-action-btn reset" title="Reset ke nama awal (${escapeHtml(defaultName)})" aria-label="Reset ke nama awal">
                                            Reset
                                        </button>
                                    ` : ''}
                                </div>
                                <form id="programTitleForm" class="program-title-form" style="display: none;">
                                    <input type="text" id="programTitleInput" class="program-title-input" value="${escapeHtml(currentName)}" maxlength="60" placeholder="Nama program latihan..." required autocomplete="off" />
                                    <button type="submit" class="title-form-btn save" title="Simpan">Simpan</button>
                                    <button type="button" id="cancelTitleBtn" class="title-form-btn cancel" title="Batal">Batal</button>
                                </form>
                            </div>
                            <p class="meta-card-subtitle">${escapeHtml(currentSaved.split)}</p>
                        </div>
                        <div class="score-highlight">
                            <span class="score-label">Skor Kesesuaian</span>
                            <div class="score-value-row">
                                <span class="score-percent">${percent}%</span>
                                <span class="score-raw">(${similarity})</span>
                            </div>
                        </div>
                    </div>

                    <hr class="section-divider">

                    <p class="meta-card-desc">${escapeHtml(currentSaved.description)}</p>

                    <div class="meta-specs-grid">
                        <div class="spec-pill">
                            <span class="spec-label">Target Utama</span>
                            <span class="spec-val">${escapeHtml(programObj?.primary_target_label || metaProfile?.primary_target_label || '-')}</span>
                        </div>
                        <div class="spec-pill">
                            <span class="spec-label">Frekuensi</span>
                            <span class="spec-val">${programObj ? programObj.frequency_days + 'x / minggu' : '-'}</span>
                        </div>
                        <div class="spec-pill">
                            <span class="spec-label">Durasi Latihan</span>
                            <span class="spec-val">${programObj ? formatWorkoutDuration(programObj.avg_session_minutes, programObj.weekly_minutes, programObj.weekly_addon_minutes) : '-'}</span>
                        </div>
                        <div class="spec-pill">
                            <span class="spec-label">Fokus Otot</span>
                            <span class="spec-val">${escapeHtml((programObj?.focus || []).join(', ') || '-')}</span>
                        </div>
                    </div>

                    ${anthroNotes ? `<div class="anthro-notes">${anthroNotes}</div>` : ''}

                    <hr class="section-divider">

                    <!-- Footer Actions placed directly at bottom of Meta-Data Card -->
                    <div class="meta-card-actions button-row">
                        ${programObj ? `<button type="button" id="toggleCustomizeBtn">${isEditMode ? 'Tutup Kustomisasi' : 'Kustomisasi Latihan'}</button>` : ''}
                        <button type="button" class="secondary" onclick="window.location.href='/asesmen'">Ambil Asesmen Ulang</button>
                        <button type="button" class="secondary" onclick="window.location.href='/profile'">Profil &amp; Akun</button>
                    </div>

                    ${isEditMode && programObj ? renderCustomizeEditor(programObj) : ''}
                </article>

                <!-- Daily Cards Container -->
                ${dailySectionHtml}
            `;

            // Inline Title Edit Handlers
            const titleDisplay = document.getElementById('programTitleDisplay');
            const titleForm = document.getElementById('programTitleForm');
            const titleInput = document.getElementById('programTitleInput');
            const editBtn = document.getElementById('editTitleBtn');
            const cancelBtn = document.getElementById('cancelTitleBtn');
            const resetBtn = document.getElementById('resetTitleBtn');
            const titleHeading = document.getElementById('programTitleHeading');

            function openTitleEdit() {
                if (!titleDisplay || !titleForm) return;
                titleDisplay.style.display = 'none';
                titleForm.style.display = 'flex';
                titleInput?.focus();
                titleInput?.select();
            }

            function closeTitleEdit() {
                if (!titleDisplay || !titleForm) return;
                titleForm.style.display = 'none';
                titleDisplay.style.display = 'flex';
                if (titleInput) titleInput.value = currentSaved.custom_name || currentSaved.name || defaultName;
            }

            editBtn?.addEventListener('click', openTitleEdit);
            titleHeading?.addEventListener('click', openTitleEdit);
            cancelBtn?.addEventListener('click', closeTitleEdit);

            titleForm?.addEventListener('submit', async (e) => {
                e.preventDefault();
                const newTitle = titleInput?.value?.trim();
                if (!newTitle) return;

                if (!currentSaved.default_name) {
                    currentSaved.default_name = defaultName;
                }

                if (newTitle === currentSaved.default_name) {
                    currentSaved.custom_name = null;
                    currentSaved.name = currentSaved.default_name;
                } else {
                    currentSaved.custom_name = newTitle;
                    currentSaved.name = newTitle;
                }

                try {
                    await apiRequest('/api/recommendations/selected', {
                        method: 'PUT',
                        body: JSON.stringify({
                            selected_plan: { ...currentSaved, updatedAt: new Date().toISOString() }
                        })
                    });
                    renderDashboardView();
                } catch (err) {
                    alert(`Gagal menyimpan nama program: ${err.message}`);
                }
            });

            resetBtn?.addEventListener('click', async () => {
                currentSaved.name = defaultName;
                currentSaved.custom_name = null;
                currentSaved.default_name = defaultName;

                try {
                    await apiRequest('/api/recommendations/selected', {
                        method: 'PUT',
                        body: JSON.stringify({
                            selected_plan: { ...currentSaved, updatedAt: new Date().toISOString() }
                        })
                    });
                    renderDashboardView();
                } catch (err) {
                    alert(`Gagal mereset nama program: ${err.message}`);
                }
            });

            document.getElementById('toggleCustomizeBtn')?.addEventListener('click', async () => {
                if (!isEditMode && !Object.keys(safeAlternatives).length) {
                    try {
                        const res = await apiRequest('/api/recommendations/alternatives');
                        safeAlternatives = res.alternatives || {};
                    } catch (err) {
                        console.warn('Gagal memuat alternatif latihan:', err.message);
                    }
                }
                isEditMode = !isEditMode;
                renderDashboardView();
            });

            document.getElementById('cancelCustomizeBtn')?.addEventListener('click', () => {
                isEditMode = false;
                renderDashboardView();
            });

            container.querySelectorAll('select[data-edit="swap"]').forEach((select) => {
                select.addEventListener('change', () => {
                    const sIdx = Number(select.dataset.s);
                    const eIdx = Number(select.dataset.e);
                    const curEx = currentSaved.program.sessions[sIdx].exercises[eIdx];
                    const alts = safeAlternatives[curEx.muscle_key] || [];
                    const replacement = alts.find((a) => a.id === select.value);
                    if (replacement) {
                        currentSaved.program.sessions[sIdx].exercises[eIdx] = { ...replacement };
                        recalcProgramTotals(currentSaved.program);
                        renderDashboardView();
                    }
                });
            });

            document.getElementById('saveCustomizeBtn')?.addEventListener('click', async () => {
                const program = currentSaved.program;
                const defaultDays = DEFAULT_DAY_MAP[program.sessions.length] || [];
                container.querySelectorAll('select[data-edit="day"]').forEach((sel) => {
                    const sIdx = Number(sel.dataset.s);
                    program.sessions[sIdx].day_name = sel.value || defaultDays[sIdx] || '';
                });
                container.querySelectorAll('input[data-edit="load"]').forEach((inp) => {
                    const sIdx = Number(inp.dataset.s);
                    const eIdx = Number(inp.dataset.e);
                    program.sessions[sIdx].exercises[eIdx].load_text = inp.value.trim() || 'Sesuaikan kemampuan';
                });
                container.querySelectorAll('input[data-edit="sets"]').forEach((inp) => {
                    const sIdx = Number(inp.dataset.s);
                    const eIdx = Number(inp.dataset.e);
                    program.sessions[sIdx].exercises[eIdx].sets = Math.min(6, Math.max(1, Number(inp.value || 3)));
                });
                container.querySelectorAll('input[data-edit="reps"]').forEach((inp) => {
                    const sIdx = Number(inp.dataset.s);
                    const eIdx = Number(inp.dataset.e);
                    program.sessions[sIdx].exercises[eIdx].reps = Math.min(30, Math.max(1, Number(inp.value || 10)));
                });
                container.querySelectorAll('input[data-edit="seconds"]').forEach((inp) => {
                    const sIdx = Number(inp.dataset.s);
                    const eIdx = Number(inp.dataset.e);
                    program.sessions[sIdx].exercises[eIdx].seconds_per_set = Math.min(180, Math.max(10, Number(inp.value || 30)));
                });
                container.querySelectorAll('input[data-edit="rest"]').forEach((inp) => {
                    const sIdx = Number(inp.dataset.s);
                    const eIdx = Number(inp.dataset.e);
                    program.sessions[sIdx].exercises[eIdx].rest_sec = Math.min(300, Math.max(15, Number(inp.value || 60)));
                });

                recalcProgramTotals(program);
                currentSaved.plan = renderProgramHtmlFromObject(program, currentSaved.metaProfile);
                currentSaved.split = `${program.split} • ${program.frequency_days}x/minggu • ~${Math.round(program.avg_session_minutes)} min/sesi`;
                currentSaved.estimatedMinutes = Math.round(program.avg_session_minutes);

                const msgEl = document.getElementById('customizeMsg');
                if (msgEl) msgEl.textContent = 'Menyimpan penyesuaian...';
                try {
                    await apiRequest('/api/recommendations/selected', {
                        method: 'PUT',
                        body: JSON.stringify({
                            selected_plan: { ...currentSaved, updatedAt: new Date().toISOString() }
                        })
                    });
                    isEditMode = false;
                    renderDashboardView();
                } catch (err) {
                    if (msgEl) {
                        msgEl.textContent = `Gagal menyimpan penyesuaian: ${err.message}`;
                        msgEl.classList.add('error-message');
                    }
                }
            });
        }

        (async function loadDashboard() {
            try {
                const session = (await apiRequest('/api/auth/session')).user;
                const data = await apiRequest('/api/recommendations/current');
                currentSaved = data.selected_plan;
                if (currentSaved?.program) {
                    const defaultDays = DEFAULT_DAY_MAP[currentSaved.program.sessions.length] || [];
                    currentSaved.program.sessions.forEach((s, idx) => {
                        if (!s.day_name && defaultDays[idx]) {
                            s.day_name = defaultDays[idx];
                        }
                    });
                }
                memberLabel = `Halo, ${session.name || 'member'}`;
                renderDashboardView();
            } catch (error) {
                if (error.status === 401) {
                    window.location.href = '/auth/login';
                    return;
                }
                container.innerHTML = `<p class="empty">Data beranda gagal dimuat: ${escapeHtml(error.message)}</p>`;
            }
        })();
