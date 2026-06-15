// ===========================================================================
// Memoria — Frontend Application
// ===========================================================================

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    accessToken: localStorage.getItem("access_token"),
    refreshToken: localStorage.getItem("refresh_token"),
    username: localStorage.getItem("username"),
    memoriesCursor: null,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function $(id) {
    return document.getElementById(id);
}

function show(el) {
    el.classList.remove("hidden");
}

function hide(el) {
    el.classList.add("hidden");
}

let toastTimer = null;

function toast(message, type = "success") {
    const el = $("toast");
    el.textContent = message;
    el.className = "toast " + type;
    show(el);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => hide(el), 4000);
}

function setTokens(access, refresh) {
    state.accessToken = access;
    state.refreshToken = refresh;
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
}

function setUsername(username) {
    state.username = username;
    localStorage.setItem("username", username);
}

function clearAuth() {
    state.accessToken = null;
    state.refreshToken = null;
    state.username = null;
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("username");
}

function setLoading(btnId, loading) {
    const btn = $(btnId);
    if (!btn) return;
    btn.disabled = loading;
    if (loading) {
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Working...";
    } else {
        btn.textContent = btn.dataset.originalText || btn.textContent;
    }
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

async function api(method, path, body = null) {
    const headers = {};

    if (body !== null) {
        headers["Content-Type"] = "application/json";
    }
    if (state.accessToken) {
        headers["Authorization"] = "Bearer " + state.accessToken;
    }

    const opts = { method, headers };
    if (body !== null) {
        opts.body = JSON.stringify(body);
    }

    let res = await fetch(path, opts);

    // If 401 and we have a refresh token, try refreshing once
    if (res.status === 401 && state.refreshToken) {
        const refreshed = await tryRefresh();
        if (refreshed) {
            headers["Authorization"] = "Bearer " + state.accessToken;
            res = await fetch(path, { method, headers, body: opts.body });
        }
    }

    return res;
}

async function tryRefresh() {
    try {
        const res = await fetch("/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: state.refreshToken }),
        });
        if (res.ok) {
            const data = await res.json();
            setTokens(data.access_token, data.refresh_token);
            return true;
        }
    } catch (e) {
        // Refresh failed
    }
    clearAuth();
    showAuthView();
    toast("Session expired. Please login again.", "error");
    return false;
}

async function apiJSON(method, path, body = null) {
    const res = await api(method, path, body);
    if (!res.ok) {
        let detail = "Request failed";
        try {
            const err = await res.json();
            detail = err.detail || JSON.stringify(err);
        } catch (e) {}
        throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
}

// ---------------------------------------------------------------------------
// View management
// ---------------------------------------------------------------------------

function showAuthView() {
    show($("auth-view"));
    hide($("dashboard-view"));
}

function showDashboard() {
    hide($("auth-view"));
    show($("dashboard-view"));
    $("nav-user").textContent = state.username || "";
    loadMemories(true);
}

function showLoginForm() {
    $("tab-login").classList.add("active");
    $("tab-register").classList.remove("active");
    show($("login-form"));
    hide($("register-form"));
}

function showRegisterForm() {
    $("tab-register").classList.add("active");
    $("tab-login").classList.remove("active");
    hide($("login-form"));
    show($("register-form"));
}

// ---------------------------------------------------------------------------
// Auth handlers
// ---------------------------------------------------------------------------

async function handleRegister(e) {
    e.preventDefault();
    setLoading("register-btn", true);

    try {
        const body = {
            username: $("reg-username").value.trim(),
            email: $("reg-email").value.trim(),
            password: $("reg-password").value,
        };

        await apiJSON("POST", "/register", body);
        toast("Account created. You can now login.");
        $("register-form").reset();
        showLoginForm();
    } catch (err) {
        toast(err.message, "error");
    } finally {
        setLoading("register-btn", false);
    }
}

async function handleLogin(e) {
    e.preventDefault();
    setLoading("login-btn", true);

    try {
        const body = {
            username: $("login-username").value.trim(),
            password: $("login-password").value,
        };

        const data = await apiJSON("POST", "/login", body);
        setTokens(data.access_token, data.refresh_token);
        setUsername(body.username);
        $("login-form").reset();
        showDashboard();
        toast("Logged in");
    } catch (err) {
        toast(err.message, "error");
    } finally {
        setLoading("login-btn", false);
    }
}

async function handleLogout() {
    try {
        if (state.refreshToken) {
            await api("POST", "/logout", { refresh_token: state.refreshToken });
        }
    } catch (e) {
        // Best-effort logout
    }
    clearAuth();
    showAuthView();
    toast("Logged out");
}

// ---------------------------------------------------------------------------
// Memory handlers
// ---------------------------------------------------------------------------

async function handleAddMemory(e) {
    e.preventDefault();
    setLoading("add-mem-btn", true);

    try {
        const tagsRaw = $("mem-tags").value.trim();
        const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];

        const body = {
            text: $("mem-text").value,
            source: $("mem-source").value.trim() || "manual",
            category: $("mem-category").value.trim() || "general",
            tags,
        };

        await apiJSON("POST", "/memory", body);
        toast("Memory saved");
        $("memory-form").reset();
        $("mem-source").value = "manual";
        $("mem-category").value = "general";
        loadMemories(true);
    } catch (err) {
        toast(err.message, "error");
    } finally {
        setLoading("add-mem-btn", false);
    }
}

async function loadMemories(reset) {
    const list = $("memories-list");

    if (reset) {
        state.memoriesCursor = null;
        list.innerHTML = '<p class="loading">Loading...</p>';
    }

    try {
        let url = "/memories?limit=20";
        if (state.memoriesCursor) {
            url += "&cursor=" + encodeURIComponent(state.memoriesCursor);
        }

        const data = await apiJSON("GET", url);

        if (reset) list.innerHTML = "";

        if (data.memories.length === 0 && reset) {
            list.innerHTML = '<p class="empty-state">No memories yet. Add one above.</p>';
        }

        data.memories.forEach(mem => {
            list.appendChild(renderMemoryItem(mem));
        });

        state.memoriesCursor = data.next_cursor;
        const loadMoreBtn = $("load-more-btn");
        if (data.next_cursor) {
            show(loadMoreBtn);
        } else {
            hide(loadMoreBtn);
        }
    } catch (err) {
        if (reset) list.innerHTML = "";
        toast(err.message, "error");
    }
}

function renderMemoryItem(mem) {
    const div = document.createElement("div");
    div.className = "memory-item";
    div.id = "mem-" + mem.id;

    let tagsHTML = "";
    if (mem.tags && mem.tags.length > 0) {
        tagsHTML = '<div class="memory-tags">' +
            mem.tags.map(t => '<span class="tag">' + escapeHTML(t) + "</span>").join("") +
            "</div>";
    }

    div.innerHTML =
        '<div class="memory-text">' + escapeHTML(mem.text) + "</div>" +
        '<div class="memory-meta">' +
            "<span>Source: " + escapeHTML(mem.source || "—") + "</span>" +
            "<span>Category: " + escapeHTML(mem.category || "—") + "</span>" +
            "<span>" + escapeHTML(mem.timestamp || "") + "</span>" +
        "</div>" +
        tagsHTML +
        '<div class="memory-actions">' +
            '<button class="btn-danger" onclick="handleDelete(\'' + mem.id + '\')">Delete</button>' +
        "</div>";

    return div;
}

async function handleDelete(id) {
    if (!confirm("Delete this memory?")) return;

    try {
        await apiJSON("DELETE", "/memory/" + id);
        const el = $("mem-" + id);
        if (el) el.remove();
        toast("Memory deleted");
    } catch (err) {
        toast(err.message, "error");
    }
}

// ---------------------------------------------------------------------------
// Search handler
// ---------------------------------------------------------------------------

async function handleSearch(e) {
    e.preventDefault();
    setLoading("search-btn", true);
    const results = $("search-results");
    results.innerHTML = '<p class="loading">Searching...</p>';

    try {
        const q = $("search-input").value.trim();
        const data = await apiJSON("GET", "/search?q=" + encodeURIComponent(q));

        results.innerHTML = "";

        if (data.results.length === 0) {
            results.innerHTML = '<p class="empty-state">No results found.</p>';
            return;
        }

        data.results.forEach(r => {
            const div = document.createElement("div");
            div.className = "result-item";
            div.innerHTML =
                '<div class="result-score">Score: ' + (r.score ? r.score.toFixed(4) : "—") + "</div>" +
                '<div class="result-text">' + escapeHTML(r.text) + "</div>";
            results.appendChild(div);
        });
    } catch (err) {
        results.innerHTML = "";
        toast(err.message, "error");
    } finally {
        setLoading("search-btn", false);
    }
}

// ---------------------------------------------------------------------------
// Ask handler
// ---------------------------------------------------------------------------

async function handleAsk(e) {
    e.preventDefault();
    setLoading("ask-btn", true);
    const results = $("ask-results");
    results.innerHTML = '<p class="loading">Thinking...</p>';

    try {
        const question = $("ask-input").value.trim();
        const data = await apiJSON("POST", "/ask", { question });

        results.innerHTML = "";

        // Show retrieved memories
        if (data.memories && data.memories.length > 0) {
            const memLabel = document.createElement("div");
            memLabel.className = "answer-label";
            memLabel.textContent = "Retrieved Memories";
            results.appendChild(memLabel);

            data.memories.forEach(m => {
                const div = document.createElement("div");
                div.className = "result-item";
                div.innerHTML = '<div class="result-text">' + escapeHTML(m.text || "") + "</div>";
                results.appendChild(div);
            });
        }

        // Show answer
        if (data.answer) {
            const box = document.createElement("div");
            box.className = "answer-box";
            box.innerHTML =
                '<div class="answer-label">Answer</div>' +
                '<div class="answer-text">' + escapeHTML(data.answer) + "</div>";
            results.appendChild(box);
        }
    } catch (err) {
        results.innerHTML = "";
        toast(err.message, "error");
    } finally {
        setLoading("ask-btn", false);
    }
}

// ---------------------------------------------------------------------------
// Export handler
// ---------------------------------------------------------------------------

async function handleExport() {
    toast("Exporting...");

    try {
        let allMemories = [];
        let cursor = null;

        // Paginate through all memories
        do {
            let url = "/export?limit=500";
            if (cursor) url += "&cursor=" + encodeURIComponent(cursor);

            const data = await apiJSON("GET", url);
            allMemories = allMemories.concat(data.memories);
            cursor = data.next_cursor;
        } while (cursor);

        // Download as JSON
        const blob = new Blob([JSON.stringify(allMemories, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "memoria-export-" + new Date().toISOString().slice(0, 10) + ".json";
        a.click();
        URL.revokeObjectURL(url);

        toast("Exported " + allMemories.length + " memories");
    } catch (err) {
        toast(err.message, "error");
    }
}

// ---------------------------------------------------------------------------
// Import handler
// ---------------------------------------------------------------------------

async function handleImport() {
    const fileInput = $("import-file");
    const file = fileInput.files[0];

    if (!file) {
        toast("Select a JSON file first", "error");
        return;
    }

    setLoading("import-btn", true);

    try {
        const text = await file.text();
        const memories = JSON.parse(text);

        if (!Array.isArray(memories)) {
            throw new Error("JSON must be an array of memories");
        }

        // Strip fields the backend doesn't accept (like id, user_id, etc.)
        const cleaned = memories.map(m => ({
            text: m.text,
            source: m.source || "import",
            category: m.category || "general",
            tags: m.tags || [],
        }));

        const data = await apiJSON("POST", "/import", cleaned);
        toast("Imported " + data.imported + " memories");
        fileInput.value = "";
        loadMemories(true);
    } catch (err) {
        toast(err.message, "error");
    } finally {
        setLoading("import-btn", false);
    }
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    if (state.accessToken) {
        showDashboard();
    } else {
        showAuthView();
    }
});
