import { sourceName } from "./sourceLabels";

export default function Details({ agents }) {
  if (!agents?.length) return null;

  return (
    <details className="mt-10">
      <summary className="cursor-pointer font-medium">Agent notes</summary>
      <div className="mt-4 space-y-4">
        {agents.map((agent) => (
          <div key={agent.source} className="rounded-md bg-white/50 p-4">
            <h3 className="font-semibold capitalize">{sourceName(agent.source)}</h3>
            {agent.error && <p className="text-accent">{agent.error}</p>}
            {agent.notes && <p className="text-muted italic">{agent.notes}</p>}
            {(agent.picks || []).length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm text-muted">
                {agent.picks.map((p) => (
                  <li key={`${p.artist}-${p.album}`}>
                    {p.artist} — {p.album}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
