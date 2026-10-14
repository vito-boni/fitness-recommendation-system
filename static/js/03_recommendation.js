        const API_BASE = "";
        const resultList = document.getElementById('recommendationResultList');
        let recommendations = [];

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

        function renderRecommendations() {
            if (!recommendations.length) {
                resultList.innerHTML = '<p class="empty">Belum ada hasil rekomendasi. Silakan isi asesmen terlebih dahulu.</p>';
                return;
            }
            resultList.innerHTML = recommendations.map((program, index) => `
                <div class="recommendation">
                    <h3>${program.name}</h3>
                    <p><strong>${program.split}</strong></p>
                    <p>${program.description}</p>
                    <p class="score">Nilai Kesesuaian: ${program.similarity} (${program.percent}%)</p>
                    ${program.plan || ''}
                    <button type="button" class="choose-plan" data-plan-index="${index}">
                        Pilih ${program.name}
                    </button>
                </div>
            `).join('');
        }

        document.addEventListener('click', async function (event) {
            const trigger = event.target.closest('.choose-plan');
            if (!trigger) return;
            const selected = recommendations[Number(trigger.dataset.planIndex)];
            if (!selected) return;

            trigger.disabled = true;
            try {
                await apiRequest('/api/recommendations/selected', {
                    method: 'PUT',
                    body: JSON.stringify({
                        selected_plan: { ...selected, chosenAt: new Date().toISOString() }
                    })
                });
                window.location.href = '/dashboard';
            } catch (error) {
                trigger.disabled = false;
                resultList.insertAdjacentHTML('afterbegin', `<p class="empty">Program gagal disimpan: ${error.message}</p>`);
            }
        });

        (async function loadRecommendations() {
            try {
                await apiRequest('/api/auth/session');
                const data = await apiRequest('/api/recommendations/current');
                recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
                renderRecommendations();
            } catch (error) {
                if (error.status === 401) {
                    window.location.href = '/auth/login';
                    return;
                }
                resultList.innerHTML = `<p class="empty">Hasil rekomendasi gagal dimuat: ${error.message}</p>`;
            }
        })();
    </script>
