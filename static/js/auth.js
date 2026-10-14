const API_BASE = "";
const ASSESSMENT_PAGE = "/asesmen";
const DASHBOARD_PAGE = "/dashboard";
const LOGIN_PAGE = "/auth/login";

const tabLogin = document.getElementById("tabLogin");
const tabRegister = document.getElementById("tabRegister");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");

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
        const message = typeof payload === "object" && payload
            ? (payload.error || payload.message)
            : String(payload || "Request gagal.");
        throw new Error(message || "Request gagal.");
    }
    return payload;
}

function showTab(name) {
    const isLogin = name === "login";
    loginForm.hidden = !isLogin;
    registerForm.hidden = isLogin;
    tabLogin.classList.toggle("active", isLogin);
    tabRegister.classList.toggle("active", !isLogin);
    tabLogin.setAttribute("aria-selected", isLogin);
    tabRegister.setAttribute("aria-selected", !isLogin);
    clearErrors(loginForm);
    clearErrors(registerForm);
}

tabLogin.addEventListener("click", () => showTab("login"));
tabRegister.addEventListener("click", () => showTab("register"));

document.querySelectorAll("[data-switch]").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.switch));
});

document.querySelectorAll(".toggle-pw").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.getElementById(button.dataset.target);
        const hidden = input.type === "password";
        input.type = hidden ? "text" : "password";
        button.textContent = hidden ? "Sembunyikan" : "Tampilkan";
    });
});

document.querySelectorAll("[data-action='logout']").forEach((button) => {
    button.addEventListener("click", async () => {
        try {
            await apiRequest("/api/auth/logout", { method: "POST" });
        } catch (error) {
            console.error("Gagal mengakhiri sesi:", error.message);
        } finally {
            window.location.href = LOGIN_PAGE;
        }
    });
});

function setError(inputId, message) {
    const input = document.getElementById(inputId);
    const error = document.getElementById(inputId + "Error");
    input.classList.toggle("invalid", Boolean(message));
    input.setAttribute("aria-invalid", Boolean(message));
    error.textContent = message || "";
}

function setMessage(form, text, success) {
    const message = form.querySelector(".form-message");
    message.textContent = text || "";
    message.classList.toggle("success", Boolean(success));
}

function clearErrors(form) {
    form.querySelectorAll("input").forEach((input) => setError(input.id, ""));
    setMessage(form, "");
}

document.querySelectorAll(".auth-form input").forEach((input) => {
    input.addEventListener("input", () => setError(input.id, ""));
});

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(loginForm);

    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    let valid = true;

    if (!username) {
        setError("loginUsername", "Username wajib diisi.");
        valid = false;
    }
    if (!password) {
        setError("loginPassword", "Kata sandi wajib diisi.");
        valid = false;
    }
    if (!valid) return;

    setMessage(loginForm, "Memeriksa akun...", true);
    try {
        await apiRequest("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ username, password })
        });
        setMessage(loginForm, "Berhasil masuk. Mengalihkan...", true);
        window.setTimeout(() => {
            window.location.href = DASHBOARD_PAGE;
        }, 600);
    } catch (error) {
        setMessage(loginForm, error.message || "Username atau kata sandi salah.");
    }
});

registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(registerForm);

    const name = document.getElementById("registerName").value.trim();
    const username = document.getElementById("registerUsername").value.trim();
    const password = document.getElementById("registerPassword").value;
    const confirm = document.getElementById("registerConfirm").value;
    let valid = true;

    if (!name) {
        setError("registerName", "Nama lengkap wajib diisi.");
        valid = false;
    }
    if (!username) {
        setError("registerUsername", "Username wajib diisi.");
        valid = false;
    }
    if (!password) {
        setError("registerPassword", "Kata sandi wajib diisi.");
        valid = false;
    } else if (password.length < 8) {
        setError("registerPassword", "Kata sandi minimal 8 karakter.");
        valid = false;
    }
    if (!confirm) {
        setError("registerConfirm", "Ketik ulang kata sandi Anda.");
        valid = false;
    } else if (password && confirm !== password) {
        setError("registerConfirm", "Kata sandi tidak sama.");
        valid = false;
    }
    if (!valid) return;

    setMessage(registerForm, "Mendaftarkan akun...", true);
    try {
        await apiRequest("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ name, username, password })
        });
        setMessage(registerForm, "Akun berhasil dibuat. Mengalihkan ke asesmen...", true);
        window.setTimeout(() => {
            window.location.href = ASSESSMENT_PAGE;
        }, 800);
    } catch (error) {
        setMessage(registerForm, error.message || "Pendaftaran gagal.");
    }
});

apiRequest("/api/auth/session")
    .then(() => {
        window.location.href = DASHBOARD_PAGE;
    })
    .catch((error) => {
        if (error.message !== "Sesi tidak valid atau sudah berakhir." && !error.message.includes("401")) {
            console.warn("Tidak dapat memeriksa sesi aktif:", error.message);
        }
    });
