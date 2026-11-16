import { useState } from "react";
import { useScout } from "../App.jsx";
import { api } from "../api.js";
import { download, isClientItem, runLabel } from "../lib.js";
import { Async, Empty, ErrorBanner, PageHead, StatTile } from "../components/ui.jsx";
import { IconReport } from "../components/icons.jsx";

const FORMATS = [
  ["pptx", "PowerPoint", "Slides for the meeting: facts, sources and why it matters."],
  ["pdf", "PDF", "The same brief as a document to send or print."],
];

export default function Report() {
  const { envelope, runId } = useScout();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const build = async (fmt) => {
    setBusy(fmt);
    setError(null);
    try {
      download(await api.report(runId, fmt), `brief_${runId}.${fmt}`);
    } catch (e) { setError(e); }
    setBusy(null);
  };

  return (
    <>
      <PageHead kicker="The brief" title="Report">
        One document with three parts: the facts, the sources, and why it matters for Atlas Copco. Facts marked Not
        important are left out.
      </PageHead>
      <Async state={envelope} loading="Loading the run...">
        {(env) => {
          if (!env) return <Empty>No results yet.</Empty>;
          const kept = env.items.filter((i) => !isClientItem(i));
          return (
            <>
              <div className="stat-grid">
                <StatTile label="Run" value={<span style={{ fontSize: 15 }}>{runLabel(env.run_id)}</span>} />
                <StatTile label="Facts" value={kept.length} />
                <StatTile label="Sources with facts" value={new Set(kept.map((i) => i.source_id)).size} />
                <StatTile label="Stories" value={(env.stories || []).length} />
              </div>
              {error && <ErrorBanner error={error} />}
              <div className="grid-2">
                {FORMATS.map(([fmt, name, text]) => (
                  <div key={fmt} className="card hover" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center",
                                    background: "var(--color-primary-soft)", color: "var(--color-primary)" }}>
                        <div style={{ width: 22, height: 22 }}><IconReport /></div>
                      </div>
                      <div><h3>{name}</h3><p className="card-sub">{text}</p></div>
                    </div>
                    <button className="btn btn-primary" disabled={!!busy} onClick={() => build(fmt)}>
                      {busy === fmt ? <><span className="spinner" style={{ width: 14, height: 14 }} /> Building...</> : `Build and download ${name}`}
                    </button>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 13 }}>The file is built on the server, stored on Databricks, and handed to your browser. Nothing is saved on this laptop by the app.</p>
            </>
          );
        }}
      </Async>
    </>
  );
}
