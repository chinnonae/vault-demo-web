/* ── Configuration ──────────────────────────────────────────────────
 * The frontend auto-detects the API base URL:
 *   - If the page is served by the Flask backend (same origin), use "".
 *   - Override by setting window.API_BASE before this script runs,
 *     e.g.  <script>window.API_BASE = "http://localhost:8080";</script>
 * ─────────────────────────────────────────────────────────────────── */
const API_BASE = window.API_BASE || "";

// ── Utility ─────────────────────────────────────────────────────────

async function apiFetch(url, options = {}) {
  const resp = await fetch(API_BASE + url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return resp.json();
}

function showToast(message, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast toast-${type}`;
  el.style.display = "block";
  clearTimeout(el._timeout);
  el._timeout = setTimeout(() => { el.style.display = "none"; }, 3500);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Health ───────────────────────────────────────────────────────────

async function loadHealth() {
  const appStatus = document.getElementById("app-status");
  try {
    const res = await apiFetch("/api/health");
    if (!res.ok) throw new Error(res.error);
    appStatus.className = "badge badge-ok";
    appStatus.textContent = "OK";
  } catch (err) {
    appStatus.className = "badge badge-error";
    appStatus.textContent = "Error";
    console.error("Health check failed:", err);
  }
}

// ── Config ───────────────────────────────────────────────────────────

async function loadConfig() {
  try {
    const res = await apiFetch("/api/config");
    if (!res.ok) throw new Error(res.error);

    const cfg = res.data;
    document.getElementById("config-source").textContent = cfg.source;

    const tbody = document.getElementById("config-body");
    tbody.innerHTML = "";

    const rows = [
      ["server.host",          cfg.server.host],
      ["server.port",          cfg.server.port],
      ["server.debug",         String(cfg.server.debug)],
      ["secrets.source",       cfg.secrets.source],
      ["secrets.path",         cfg.secrets.path],
      ["secrets.env_prefix",   cfg.secrets.env_prefix],
    ];

    for (const [k, v] of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><code>${escapeHtml(k)}</code></td><td>${escapeHtml(v)}</td>`;
      tbody.appendChild(tr);
    }

    // Update the secrets-source badge in the status bar
    const sourceEl = document.getElementById("secrets-source-badge");
    const src = cfg.secrets.source;
    sourceEl.className = `source-tag source-${src === "env" ? "env" : "file"}`;
    sourceEl.textContent = src;

    return cfg;
  } catch (err) {
    document.getElementById("config-source").textContent = "error";
    console.error("Config fetch failed:", err);
    return null;
  }
}

// ── Injected secrets ─────────────────────────────────────────────────

async function loadSecrets() {
  const listEl   = document.getElementById("secrets-list");
  const emptyEl  = document.getElementById("secrets-empty");
  const countEl  = document.getElementById("secrets-count");
  const detailEl = document.getElementById("secret-detail");

  listEl.innerHTML = "";
  emptyEl.style.display = "none";
  detailEl.style.display = "none";

  try {
    const res = await apiFetch("/api/secrets");
    if (!res.ok) throw new Error(res.error);

    const secrets = res.data;
    countEl.textContent = secrets.length;

    if (secrets.length === 0) {
      emptyEl.style.display = "block";
      return;
    }

    for (const s of secrets) {
      const card = document.createElement("div");
      card.className = "secret-card";
      card.innerHTML = `
        <div class="secret-card-name">${escapeHtml(s.name)}</div>
        <div class="secret-card-meta">
          <span class="source-tag source-${s.source}">${escapeHtml(s.source)}</span>
          &nbsp;${s.field_count} field${s.field_count !== 1 ? "s" : ""}
        </div>`;
      card.addEventListener("click", () => showSecret(s.name));
      listEl.appendChild(card);
    }
  } catch (err) {
    showToast("Failed to load secrets: " + err.message, "error");
    console.error(err);
  }
}

async function showSecret(name) {
  try {
    const res = await apiFetch(`/api/secrets/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(res.error);

    const { name: sName, source, fields } = res.data;

    document.getElementById("secret-source-icon").textContent =
      source === "env" ? "🌐" : "📄";
    document.getElementById("secret-name-label").textContent = sName;

    const tbody = document.getElementById("secret-fields-body");
    tbody.innerHTML = "";

    const entries = Object.entries(fields);
    if (entries.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="3" style="color:var(--muted)">No fields.</td>`;
      tbody.appendChild(tr);
    } else {
      for (const [k, v] of entries) {
        const valId = `val-${Math.random().toString(36).slice(2)}`;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><code>${escapeHtml(k)}</code></td>
          <td class="val-cell">
            <span id="${valId}" style="filter:blur(4px);user-select:none">${escapeHtml(String(v))}</span>
          </td>
          <td>
            <button class="reveal-btn" onclick="toggleReveal('${valId}', this)">reveal</button>
          </td>`;
        tbody.appendChild(tr);
      }
    }

    document.getElementById("secret-detail").style.display = "block";
    document.getElementById("secret-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    showToast("Failed to read secret: " + err.message, "error");
  }
}

function toggleReveal(spanId, btn) {
  const span = document.getElementById(spanId);
  const hidden = span.style.filter !== "none";
  span.style.filter = hidden ? "none" : "blur(4px)";
  span.style.userSelect = hidden ? "auto" : "none";
  btn.textContent = hidden ? "hide" : "reveal";
}

function closeDetail() {
  document.getElementById("secret-detail").style.display = "none";
}

// ── Compose ──────────────────────────────────────────────────────────

async function refresh() {
  await Promise.all([loadHealth(), loadConfig()]);
  await loadSecrets();
}

// ── Init ─────────────────────────────────────────────────────────────

(async function init() {
  await refresh();
})();
