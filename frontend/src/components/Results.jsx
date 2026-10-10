import { sourceName } from "./sourceLabels";

export default function Results({ recommendations, shortfall, found, requested }) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-bold">Recommendations</h2>
      {shortfall && found < requested && (
        <p className="mt-3 border-l-4 border-accent bg-[#8a4b2d]/10 px-4 py-3 font-medium">
          {shortfall}
        </p>
      )}

      <ol className="mt-6 space-y-6">
        {recommendations.map((rec, i) => (
          <li key={`${rec.artist}-${rec.album}-${i}`} className="border-t border-[#d9cfc4] pt-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">
              0{i + 1}
            </div>
            <h3 className="font-display text-xl font-bold">
              {rec.artist} — {rec.album}
              {rec.year ? ` (${rec.year})` : ""}
            </h3>
            <p className="mt-1 text-muted">{rec.why}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(rec.urls || {}).map(([src, url]) => (
                <a
                  key={src}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold uppercase text-accent underline"
                >
                  {sourceName(src)}
                </a>
              ))}
              {(rec.sources || [])
                .filter((src) => !(rec.urls && rec.urls[src]))
                .map((src) => (
                  <span
                    key={src}
                    className="rounded bg-white/70 px-2 py-0.5 text-xs font-semibold uppercase text-muted"
                  >
                    {sourceName(src)}
                  </span>
                ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
