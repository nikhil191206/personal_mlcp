import { useEffect, useMemo, useState } from "react";
import { useScout } from "../App.jsx";
import { api } from "../api.js";
import { byNewest, isClientItem, nice, shortDate, useAsync } from "../lib.js";
import { Async, Empty, ErrorBanner, PageHead, SourceLink, StatTile } from "../components/ui.jsx";

const CHOICES = [["approved", "Important"], ["denied", "Not important"], ["", "Not decided"]];
const SHOWN = 80;

export default function Facts() {
  const { envelope, pollRerun } = useScout();
  const saved = useAsync(() => api.facts(), []);
  const [changes, setChanges] = useState({});
  const [view, setView] = useState("all");
  const [status, setStatus] = useState(null);

  useEffect(() => setChanges({}), [saved.data]);

  return (
    <>
      <PageHead kicker="Review" title="Facts">
        Mark each fact Important or Not important. Not important facts are left out of the next run and of the report.
      </PageHead>
      <Async state={saved} loading="Loading your decisions...">
        {(d) => (
          <Async state={envelope} loading="Loading facts...">
            {(env) => <FactList env={env} decisions={{ ...d.decisions, ...changes }} changes={changes} setChanges={setChanges}
                                view={view} setView={setView} status={status}
                                onSave={async () => {
                                  setStatus({ saving: true });
                                  try {
                                    const r = await api.saveFacts(changes);
                                    setStatus({ ok: r.queued ? "Saved. A run is already going; a new one starts right after it." : "Saved. A new run is starting." });
                                    saved.reload();
                                    pollRerun();
                                  } catch (error) { setStatus({ error }); }
                                }} />}
          </Async>
        )}
      </Async>
    </>
  );
}

function FactList({ env, decisions, changes, setChanges, view, setView, status, onSave }) {
  const items = useMemo(() => (env ? env.items.filter((i) => !isClientItem(i) && i.key_facts?.length).sort(byNewest) : []), [env]);
  if (!env) return <Empty>No facts yet.</Empty>;
  const count = (k) => items.filter((i) => (decisions[i.id] || "") === k).length;
  const visible = items.filter((i) => view === "all" || (decisions[i.id] || "") === view).slice(0, SHOWN);
  const nChanges = Object.keys(changes).length;

  return (
    <>
      <div className="stat-grid">
        <StatTile label="Important" value={count("approved")} />
        <StatTile label="Not important" value={count("denied")} />
        <StatTile label="Not decided" value={count("")} />
      </div>
      <div className="chips" role="group" aria-label="Show">
        {[["all", "All"], ["", "Not decided"], ["approved", "Important"], ["denied", "Not important"]].map(([k, l]) => (
          <button key={k || "none"} className={`chip ${view === k ? "on" : ""}`} onClick={() => setView(k)}>{l}</button>
        ))}
      </div>
      {status?.error && <ErrorBanner error={status.error} />}
      {status?.ok && <div className="banner ok">{status.ok}</div>}
      <div className="list">
        {visible.length === 0 && <Empty>Nothing in this view.</Empty>}
        {visible.map((item) => {
          const current = decisions[item.id] || "";
          return (
            <article key={item.id} className="card">
              <div className="row-between">
                <div>
                  <div className="meta" style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                    <strong style={{ color: "var(--color-text)" }}>{item.company || "Unknown company"}</strong>
                    {" · "}{nice(item.event_type) || "other"}{" · "}{shortDate(item.published_at) || "date not stated"}
                  </div>
                  <p style={{ color: "var(--color-text)", marginTop: 8, fontSize: 14 }}>{item.key_facts[0]}</p>
                  <div style={{ marginTop: 8 }}><SourceLink url={item.source_url}>{item.source_name}</SourceLink></div>
                </div>
                <div className="seg" role="radiogroup" aria-label="Decision">
                  {CHOICES.map(([value, label]) => (
                    <button key={label} role="radio" aria-checked={current === value}
                            className={`${current === value ? "on" : ""} ${value || "none"}`}
                            onClick={() => setChanges((c) => ({ ...c, [item.id]: value }))}>{label}</button>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {items.length > SHOWN && <p style={{ fontSize: 13 }}>Showing the {SHOWN} newest facts in this view.</p>}
      <div className="savebar">
        <span style={{ fontSize: 13.5 }}>{nChanges ? `${nChanges} unsaved change${nChanges === 1 ? "" : "s"}` : "No unsaved changes"}</span>
        <button className="btn btn-primary" disabled={!nChanges || status?.saving} onClick={onSave}>
          {status?.saving ? "Saving..." : "Save and rerun"}
        </button>
      </div>
    </>
  );
}
