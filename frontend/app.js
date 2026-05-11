/* ── Configuration ──────────────────────────────────────────────────
 * The frontend auto-detects the API base URL:
 *   - If the page is served by the Flask backend (same origin), use "".
 *   - Override by setting window.API_BASE before this script runs,
 *     e.g.  <script>window.API_BASE = "http://localhost:8080";</script>
 * ─────────────────────────────────────────────────────────────────── */
const API_BASE = window.API_BASE || "";

let currentPath = "";          // current browsing path within the KV mount
let currentSecretPath = null;  // full path of the currently displayed secret

// ── Utility ─────────────────────────────────────────────────────────

async function apiFetch(url, options = {}) {
  const resp = await fetch(API_BASE + url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await resp.json();
  return body;
}

function showToast(message, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast toast-${type}`;
  el.style.display = "block";
  clearTimeout(el._timeout);
  el._timeout = setTimeout(() => { el.style.display = "none"; }, 3500);
}

function setBadge(id, ok, trueLabel = "Yes", falseLabel = "No", nullLabel = "–") {
  const el = document.getElementById(id);
  if (ok === null || ok === undefined) {
    el.className = "badge badge-unknown";
    el.textContent = nullLabel;
  } else if (ok) {
    el.className = "badge badge-ok";
    el.textContent = trueLabel;
  } else {
    el.className = "badge badge-error";
    el.textContent = falseLabel;
  }
}

// ── Health ───────────────────────────────────────────────────────────

async function loadHealth() {
  try {
    const res = await apiFetch("/api/health");
    if (!res.ok) throw new Error(res.error);

    const { vault, authenticated } = res.data;

    document.getElementById("app-status").className = "badge badge-ok";
    document.getElementById("app-status").textContent = "OK";

    setBadge("vault-reachable", vault.reachable, "Yes", "No");
    setBadge("vault-sealed", vault.sealed === false ? true : false, "No", "Yes", "Unknown");
    if (vault.sealed !== undefined) {
      // invert: sealed=false means "not sealed" = good
      const el = document.getElementById("vault-sealed");
      if (vault.sealed === false) {
        el.className = "badge badge-ok";
        el.textContent = "No";
      } else if (vault.sealed === true) {
        el.className = "badge badge-error";
        el.textContent = "Yes";
      }
    }
    setBadge("vault-auth", authenticated, "Yes", "No");
    document.getElementById("vault-version").textContent = vault.version || "–";
  } catch (err) {
    document.getElementById("app-status").className = "badge badge-error";
    document.getElementById("app-status").textContent = "Error";
    ["vault-reachable", "vault-sealed", "vault-auth"].forEach(id => {
      const el = document.getElementById(id);
      el.className = "badge badge-error";
      el.textContent = "–";
    });
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
      ["vault.addr",      cfg.vault.addr],
      ["vault.token",     cfg.vault.token],
      ["vault.namespace", cfg.vault.namespace],
      ["vault.mount",     cfg.vault.mount],
      ["server.host",     cfg.server.host],
      ["server.port",     cfg.server.port],
      ["server.debug",    String(cfg.server.debug)],
    ];

    for (const [k, v] of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><code>${k}</code></td><td>${v}</td>`;
      tbody.appendChild(tr);
    }
  } catch (err) {
    document.getElementById("config-source").textContent = "error";
    console.error("Config fetch failed:", err);
  }
}

// ── Secrets browser ──────────────────────────────────────────────────

async function navigate(path) {
  currentPath = path.replace(/\/+$/, "");  // normalise: strip trailing slash
  showSecretDetail(false);

  const url = path === "" ? "/api/secrets" : `/api/secrets/${path}/`;
  const list = document.getElementById("key-list");
  const empty = document.getElementById("key-list-empty");
  list.innerHTML = "";
  empty.style.display = "none";

  try {
    const res = await apiFetch(url);
    if (!res.ok) {
      if (res.error && res.error.includes("not found")) {
        empty.style.display = "block";
        return;
      }
      throw new Error(res.error);
    }

    const keys = res.data.keys || [];
    if (keys.length === 0) {
      empty.style.display = "block";
      return;
    }

    for (const key of keys) {
      const isDir = key.endsWith("/");
      const li = document.createElement("li");
      li.className = isDir ? "is-dir" : "is-secret";
      const btn = document.createElement("button");
      btn.textContent = key;
      btn.title = key;
      if (isDir) {
        const childPath = currentPath ? `${currentPath}/${key.replace(/\/$/, "")}` : key.replace(/\/$/, "");
        btn.addEventListener("click", () => navigate(childPath));
      } else {
        const secretPath = currentPath ? `${currentPath}/${key}` : key;
        btn.addEventListener("click", () => readSecret(secretPath));
      }
      li.appendChild(btn);
      list.appendChild(li);
    }
  } catch (err) {
    showToast("Failed to list secrets: " + err.message, "error");
    console.error(err);
  }

  renderBreadcrumb();
}

function renderBreadcrumb() {
  const bc = document.getElementById("breadcrumb");
  bc.innerHTML = "";

  const rootLink = document.createElement("a");
  rootLink.href = "#";
  rootLink.textContent = "root";
  rootLink.addEventListener("click", (e) => { e.preventDefault(); navigate(""); });
  bc.appendChild(rootLink);

  if (!currentPath) return;

  const parts = currentPath.split("/");
  parts.forEach((part, idx) => {
    const sep = document.createElement("span");
    sep.className = "sep";
    sep.textContent = " / ";
    bc.appendChild(sep);

    const link = document.createElement("a");
    link.href = "#";
    link.textContent = part;
    const pathUpTo = parts.slice(0, idx + 1).join("/");
    link.addEventListener("click", (e) => { e.preventDefault(); navigate(pathUpTo); });
    bc.appendChild(link);
  });
}

async function readSecret(path) {
  try {
    const res = await apiFetch(`/api/secrets/${path}`);
    if (!res.ok) throw new Error(res.error);

    currentSecretPath = path;
    document.getElementById("secret-path-label").textContent = path;

    const tbody = document.getElementById("secret-data-body");
    tbody.innerHTML = "";

    const data = res.data.data || {};
    const entries = Object.entries(data);
    if (entries.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="2" style="color:var(--muted)">No data fields.</td>`;
      tbody.appendChild(tr);
    } else {
      for (const [k, v] of entries) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><code>${escapeHtml(k)}</code></td><td><code>${escapeHtml(String(v))}</code></td>`;
        tbody.appendChild(tr);
      }
    }
    showSecretDetail(true);
  } catch (err) {
    showToast("Failed to read secret: " + err.message, "error");
  }
}

function showSecretDetail(show) {
  document.getElementById("secret-detail").style.display = show ? "block" : "none";
  if (!show) currentSecretPath = null;
}

async function deleteCurrentSecret() {
  if (!currentSecretPath) return;
  if (!confirm(`Delete secret at path "${currentSecretPath}"?`)) return;
  try {
    const res = await apiFetch(`/api/secrets/${currentSecretPath}`, { method: "DELETE" });
    if (!res.ok) throw new Error(res.error);
    showToast("Secret deleted.", "ok");
    showSecretDetail(false);
    navigate(currentPath);
  } catch (err) {
    showToast("Delete failed: " + err.message, "error");
  }
}

// ── Write modal ──────────────────────────────────────────────────────

function openWriteModal() {
  const pathInput = document.getElementById("write-path").value.trim();
  if (!pathInput) {
    showToast("Please enter a secret path.", "error");
    return;
  }
  document.getElementById("modal-path-label").textContent = pathInput;
  document.getElementById("kv-pairs").innerHTML = `
    <div class="kv-row">
      <input type="text" placeholder="key" class="kv-key" />
      <input type="text" placeholder="value" class="kv-val" />
      <button class="btn btn-small btn-danger" onclick="removeKvRow(this)">–</button>
    </div>`;
  document.getElementById("write-modal").style.display = "flex";
}

function closeWriteModal() {
  document.getElementById("write-modal").style.display = "none";
}

function addKvRow() {
  const container = document.getElementById("kv-pairs");
  const row = document.createElement("div");
  row.className = "kv-row";
  row.innerHTML = `
    <input type="text" placeholder="key" class="kv-key" />
    <input type="text" placeholder="value" class="kv-val" />
    <button class="btn btn-small btn-danger" onclick="removeKvRow(this)">–</button>`;
  container.appendChild(row);
}

function removeKvRow(btn) {
  const rows = document.querySelectorAll("#kv-pairs .kv-row");
  if (rows.length > 1) btn.closest(".kv-row").remove();
}

async function submitWrite() {
  const path = document.getElementById("modal-path-label").textContent.trim();
  const pairs = document.querySelectorAll("#kv-pairs .kv-row");
  const data = {};
  for (const row of pairs) {
    const k = row.querySelector(".kv-key").value.trim();
    const v = row.querySelector(".kv-val").value;
    if (k) data[k] = v;
  }
  if (Object.keys(data).length === 0) {
    showToast("Add at least one key-value pair.", "error");
    return;
  }
  try {
    const res = await apiFetch(`/api/secrets/${path}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.error);
    showToast("Secret saved successfully.", "ok");
    closeWriteModal();
    // Refresh list if the new path is under the current browsing path
    navigate(currentPath);
  } catch (err) {
    showToast("Write failed: " + err.message, "error");
  }
}

// ── Helpers ──────────────────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
}

// ── Init ─────────────────────────────────────────────────────────────

(async function init() {
  await Promise.all([loadHealth(), loadConfig()]);
  await navigate("");
})();
