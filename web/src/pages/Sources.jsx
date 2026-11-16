import { useState } from "react";
import { useScout } from "../App.jsx";
import { api } from "../api.js";
import { nice, safeUrl, useAsync } from "../lib.js";
import { Async, Badge, Empty, ErrorBanner, PageHead } from "../components/ui.jsx";

const TABS = [
  ["confirmed", "Confirmed", "Undo", "pending"],
  ["to_confirm", "To confirm", "Confirm", "confirmed"],
  ["blocked", "Blocked", null, null],
];

function Score({ value }) {
  const color = value >= 70 ? "var(--color-success)" : value >= 40 ? "var(--color-warning)" : "var(--color-danger)";
  return (
    <div className="score">
      Trust score <strong style={{ color: "var(--color-text)" }}>{value}</strong>/100
      <div className="track"><div style={{ width: `${value}%`, background: color }} /></div>
    </div>
  );
}

export default function Sources() {
  const { pollRerun } = useScout();
  const state = useAsync(() => api.sources(), []);
  const [tab, setTab] = useState("to_confirm");
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);

  const act = async (row, value) => {
    setBusy(row.id);
    setMessage(null);
    try {
      await api.setSource(row.id, value);
      setMessage({ ok: `Saved: ${row.name}. A new run is starting.` });
      state.reload();
      pollRerun();
    } catch (error) { setMessage({ error }); }
    setBusy(null);
  };

  return (
    <>
      <PageHead kicker="Where facts come from" title="Sources">
        Confirm the sources you are happy with. Blocked sources are listed with the reason; we never read them.
      </PageHead>
      <div className="banner info">Confirming records the team's decision. It is not an approval by Atlas Copco.</div>
      {message?.error && <ErrorBanner error={message.error} />}
      {message?.ok && <div className="banner ok">{message.ok}</div>}
      <Async state={state} loading="Loading sources...">
        {(groups) => {
          const [, , button, value] = TABS.find(([k]) => k === tab);
          const rows = groups[tab] || [];
          return (
            <>
              <div className="tabs" role="tablist">
                {TABS.map(([key, label]) => (
                  <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
                    {label} <span className="count">{(groups[key] || []).length}</span>
                  </button>
                ))}
              </div>
              <div className="list">
                {rows.length === 0 && <Empty>Nothing here.</Empty>}
                {rows.map((row) => {
                  const url = safeUrl(row.url);
                  return (
                    <article key={row.id} className="card hover">
                      <div className="row-between">
                        <div>
                          <div className="badges">
                            <Badge>{row.kind === "discovered" ? "found by the scout" : "on our list"}</Badge>
                            <Badge tone="primary">{nice(row.type) || "unknown type"}</Badge>
                            {tab === "blocked" && <Badge tone="danger">not read</Badge>}
                            {tab === "confirmed" && <Badge tone="success">confirmed</Badge>}
                          </div>
                          <div className="result"><div className="title">{row.name}</div></div>
                          {url && <a className="link mono" href={url} target="_blank" rel="noopener noreferrer">{url}</a>}
                          {row.score != null && <Score value={row.score} />}
                          {row.detail && <div className="detail-text">{row.detail.slice(0, 280)}</div>}
                        </div>
                        {button && (
                          <button className={`btn btn-sm ${value === "confirmed" ? "btn-primary" : "btn-secondary"}`}
                                  disabled={busy === row.id} onClick={() => act(row, value)}>
                            {busy === row.id ? "Saving..." : button}
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
