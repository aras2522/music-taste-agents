import { useMemo, useState } from "react";
import { recommendMusic } from "./api";
import ArtistsField from "./components/ArtistsField";
import Details from "./components/Details";
import Field from "./components/Field";
import Results from "./components/Results";
import TasteField from "./components/TasteField";

const LIMIT_ERROR = "Not a valid number between 1 and 9";

function parseArtists(raw) {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function parseLimit(raw) {
  const value = String(raw ?? "").trim();
  if (!/^[1-9]$/.test(value)) return null;
  return Number(value);
}

function shortfallMessage(found, requested) {
  if (found === 0) return "Sorry, I couldn't find any albums for this search.";
  if (found < requested) return `Sorry, I can only show ${found}.`;
  return "";
}

export default function App() {
  const [taste, setTaste] = useState("");
  const [artists, setArtists] = useState("");
  const [limitRaw, setLimitRaw] = useState("5");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);

  const statusIsError = useMemo(
    () => status === LIMIT_ERROR || status.startsWith("Sorry, I can only show"),
    [status]
  );

  async function onSubmit(event) {
    event.preventDefault();
    setData(null);

    const limit = parseLimit(limitRaw);
    if (limit === null) {
      setStatus(LIMIT_ERROR);
      return;
    }

    setBusy(true);
    setStatus("Agents are checking Pitchfork and Rate Your Music…");

    try {
      const result = await recommendMusic({
        taste: taste.trim(),
        artists: parseArtists(artists),
        limit,
      });
      const n = result.recommendations?.length ?? 0;
      const note =
        shortfallMessage(n, limit) ||
        result.message ||
        (n ? `Found ${n} album${n === 1 ? "" : "s"}.` : "No recommendations returned.");
      setData(result);
      setStatus(note);
    } catch (err) {
      setStatus(err.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const found = data?.recommendations?.length ?? 0;
  const requested = parseLimit(limitRaw) ?? 5;
  const shortfall = shortfallMessage(found, requested) || data?.message || "";

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <header className="mb-8">
        <p className="font-display text-4xl font-bold tracking-tight text-ink md:text-5xl">
          Music Taste Agents
        </p>
        <p className="mt-3 max-w-2xl text-muted">
         Put your genres and artist and find similar artists from Pitchfork and Rate Your Music for <em>similar artists</em> and their albums.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-4">
        <TasteField value={taste} onChange={(e) => setTaste(e.target.value)} />
        <ArtistsField value={artists} onChange={(e) => setArtists(e.target.value)} />

        <div className="flex flex-wrap items-end gap-3">
          <Field
            label="How many"
            type="number"
            min={1}
            max={9}
            step={1}
            inputMode="numeric"
            className="w-20"
            value={limitRaw}
            onChange={(e) => {
              const digits = String(e.target.value).replace(/\D/g, "").slice(0, 1);
              setLimitRaw(digits);
            }}
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-accent px-5 py-3 font-semibold text-[#fffaf6] disabled:opacity-60"
          >
            {busy ? "Listening…" : "Find albums"}
          </button>
        </div>
      </form>

      <p className={`mt-4 ${statusIsError ? "text-accent" : "text-muted"}`} role="status">
        {status}
      </p>

      {data && (
        <>
          <Results
            recommendations={data.recommendations || []}
            shortfall={shortfall}
            found={found}
            requested={requested}
          />
          <Details agents={data.agents || []} />
        </>
      )}
    </div>
  );
}
