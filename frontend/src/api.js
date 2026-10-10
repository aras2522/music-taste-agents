const API_BASE = import.meta.env.VITE_API_BASE || "";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  return res.json();
}

export async function recommendMusic({ taste, artists, limit }) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/recommend?_=${Date.now()}`, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(90000),
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
      },
      body: JSON.stringify({ taste, artists, limit }),
    });
  } catch (err) {
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      throw new Error("The search took too long. Try again.");
    }
    throw err;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const detailText = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
      : detail;
    throw new Error(detailText || `Request failed (${res.status})`);
  }
  return data;
}
