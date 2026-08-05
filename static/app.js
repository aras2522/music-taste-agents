const form = document.getElementById("taste-form");
const statusEl = document.getElementById("status");
const results = document.getElementById("results");
const recList = document.getElementById("rec-list");
const agentNotes = document.getElementById("agent-notes");
const submitBtn = document.getElementById("submit-btn");
const limitInput = document.getElementById("limit");
const shortfallNote = document.getElementById("shortfall-note");

const SOURCE_LABEL = {
  pitchfork: "Pitchfork",
  rym: "Rate Your Music",
};

const LIMIT_ERROR = "Not a valid number between 1 and 9";

function parseArtists(raw) {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function setBusy(busy, message = "") {
  submitBtn.disabled = busy;
  submitBtn.textContent = busy ? "Listening…" : "Find albums";
  statusEl.textContent = message;
  const isShortfall = typeof message === "string" && message.startsWith("Sorry, I can only show");
  statusEl.classList.toggle("error", !busy && (message === LIMIT_ERROR || isShortfall));
}

function parseLimit(raw) {
  const value = String(raw ?? "").trim();
  if (!/^[1-9]$/.test(value)) {
    return null;
  }
  return Number(value);
}

function shortfallMessage(found, requested) {
  const n = Number(found);
  const want = Number(requested);
  if (!Number.isFinite(n) || !Number.isFinite(want)) {
    return "";
  }
  if (n === 0) {
    return "Sorry, I couldn't find any albums for this search.";
  }
  if (n < want) {
    return `Sorry, I can only show ${n}.`;
  }
  return "";
}

limitInput.addEventListener("beforeinput", (event) => {
  if (event.inputType?.startsWith("delete") || event.inputType === "historyUndo") {
    return;
  }
  const data = event.data ?? "";
  if (data && !/^[0-9]+$/.test(data)) {
    event.preventDefault();
  }
});

limitInput.addEventListener("keydown", (event) => {
  // Block scientific notation / signs that number inputs sometimes allow
  if (["e", "E", "+", "-", ".", ","].includes(event.key)) {
    event.preventDefault();
  }
});

limitInput.addEventListener("input", () => {
  const digitsOnly = String(limitInput.value).replace(/\D/g, "").slice(0, 1);
  if (limitInput.value !== digitsOnly) {
    limitInput.value = digitsOnly;
  }
  if (statusEl.textContent === LIMIT_ERROR) {
    statusEl.textContent = "";
    statusEl.classList.remove("error");
  }
});

limitInput.addEventListener("change", () => {
  const n = Number(limitInput.value);
  if (Number.isInteger(n) && n >= 1 && n <= 9) {
    limitInput.value = String(n);
  }
});

function renderRecommendations(data, requested) {
  recList.innerHTML = "";
  data.recommendations.forEach((rec, i) => {
    const li = document.createElement("li");
    const year = rec.year ? ` (${rec.year})` : "";
    const links = Object.entries(rec.urls || {})
      .map(
        ([src, url]) =>
          `<a class="source-link ${src}" href="${url}" target="_blank" rel="noopener noreferrer">${SOURCE_LABEL[src] || src}</a>`
      )
      .join("");
    const tags = (rec.sources || [])
      .filter((src) => !(rec.urls && rec.urls[src]))
      .map((src) => `<span class="source-tag ${src}">${SOURCE_LABEL[src] || src}</span>`)
      .join("");

    li.innerHTML = `
      <div class="rec-rank">0${i + 1}</div>
      <h3 class="rec-title">${escapeHtml(rec.artist)} — ${escapeHtml(rec.album)}${escapeHtml(year)}</h3>
      <p class="rec-why">${escapeHtml(rec.why)}</p>
      <div class="sources">${links}${tags}</div>
    `;
    recList.appendChild(li);
  });

  const found = data.recommendations?.length ?? 0;
  const note = shortfallMessage(found, requested) || data.message || "";
  if (shortfallNote) {
    if (note && found < Number(requested)) {
      shortfallNote.hidden = false;
      shortfallNote.textContent = note;
    } else {
      shortfallNote.hidden = true;
      shortfallNote.textContent = "";
    }
  }

  agentNotes.innerHTML = "";
  (data.agents || []).forEach((agent) => {
    const block = document.createElement("div");
    const skipped = !agent.picks?.length && !agent.error;
    block.className = `agent-block${agent.error ? " error" : skipped ? " skipped" : ""}`;
    const picks = (agent.picks || [])
      .map((p) => `<li>${escapeHtml(p.artist)} — ${escapeHtml(p.album)}</li>`)
      .join("");
    block.innerHTML = `
      <h3>${SOURCE_LABEL[agent.source] || agent.source}</h3>
      ${agent.error ? `<p>${escapeHtml(agent.error)}</p>` : ""}
      ${agent.notes ? `<p class="agent-note">${escapeHtml(agent.notes)}</p>` : ""}
      ${picks ? `<ul>${picks}</ul>` : ""}
    `;
    agentNotes.appendChild(block);
  });

  results.hidden = false;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clearResults() {
  results.hidden = true;
  recList.innerHTML = "";
  agentNotes.innerHTML = "";
  if (shortfallNote) {
    shortfallNote.hidden = true;
    shortfallNote.textContent = "";
  }
}

["taste", "artists", "limit"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", () => {
    if (!results.hidden) {
      clearResults();
      statusEl.textContent = "";
      statusEl.classList.remove("error");
    }
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearResults();

  const limit = parseLimit(limitInput.value);
  if (limit === null) {
    setBusy(false, LIMIT_ERROR);
    limitInput.focus();
    return;
  }

  setBusy(true, "Agents are checking Pitchfork and Rate Your Music…");

  const body = {
    taste: document.getElementById("taste").value.trim(),
    artists: parseArtists(document.getElementById("artists").value),
    limit,
  };

  try {
    const res = await fetch(`/api/recommend?_=${Date.now()}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
      },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const detailText = Array.isArray(detail)
        ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
        : detail;
      throw new Error(detailText || `Request failed (${res.status})`);
    }
    const n = Array.isArray(data.recommendations) ? data.recommendations.length : 0;
    // Prefer client-side shortfall so the message always shows even if API omits it
    const note =
      shortfallMessage(n, limit) ||
      data.message ||
      (n ? `Found ${n} album${n === 1 ? "" : "s"}.` : "No recommendations returned.");
    renderRecommendations(data, limit);
    setBusy(false, note);
  } catch (err) {
    setBusy(false, err.message || "Something went wrong.");
  }
});
