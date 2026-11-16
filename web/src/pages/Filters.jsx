import { useEffect, useState } from "react";
import { useScout } from "../App.jsx";
import { api } from "../api.js";
import { nice, useAsync } from "../lib.js";
import { Async, ErrorBanner, PageHead } from "../components/ui.jsx";

const lines = (text) => text.split("\n").map((w) => w.trim()).filter(Boolean);

function ChipSet({ options, value, onChange, format = nice }) {
  const toggle = (o) => onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o]);
  return (
    <div className="chips">
      {options.map((o) => (
        <button type="button" key={o} className={`chip ${value.includes(o) ? "on" : ""}`} aria-pressed={value.includes(o)}
                onClick={() => toggle(o)}>{format(o)}</button>
      ))}
    </div>
  );
}

export default function Filters() {
  const state = useAsync(() => api.settings(), []);
  return (
    <>
      <PageHead kicker="Settings" title="What we look for">
        Change the filters and press Done. They are saved and a new run starts by itself; the results update when it finishes.
      </PageHead>
      <Async state={state} loading="Loading the saved filters...">
        {(data) => <Form data={data} onSaved={state.reload} />}
      </Async>
    </>
  );
}

function Form({ data, onSaved }) {
  const { pollRerun, rerun } = useScout();
  const { settings, options } = data;
  const [f, setF] = useState(null);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    setF({
      regions: settings.regions, recent_months: settings.recent_months,
      technologies: settings.technologies.filter((t) => options.technologies.includes(t)),
      event_types: settings.event_types,
      include: settings.extra_compressor_keywords.join("\n"), exclude: settings.excluded_keywords.join("\n"),
    });
  }, [settings, options]);
  if (!f) return null;
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setStatus({ saving: true });
    try {
      const r = await api.saveSettings({
        regions: f.regions, recent_months: Number(f.recent_months), technologies: f.technologies,
        event_types: f.event_types, extra_compressor_keywords: lines(f.include), excluded_keywords: lines(f.exclude),
      });
      setStatus({ ok: r.queued ? "Saved. A run is already going; a new one starts right after it." : "Saved. A new run is starting." });
      onSaved();
      pollRerun();
    } catch (error) { setStatus({ error }); }
  };

  return (
    <form className="card" onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div className="form-grid">
        <div className="field">
          <span>Regions</span>
          <ChipSet options={options.regions} value={f.regions} onChange={set("regions")} format={(r) => r} />
          <small>Only items about these regions are kept.</small>
        </div>
        <div className="field">
          <span>How recent: {f.recent_months} month{Number(f.recent_months) === 1 ? "" : "s"}</span>
          <input type="range" min="1" max="60" value={f.recent_months} onChange={(e) => set("recent_months")(e.target.value)}
                 aria-label="How recent, in months" />
          <small>Older items are dropped.</small>
        </div>
      </div>
      <div className="field">
        <span>Technologies</span>
        <ChipSet options={options.technologies} value={f.technologies} onChange={set("technologies")} />
        <small>None selected means all technologies.</small>
      </div>
      <div className="field">
        <span>Types of news</span>
        <ChipSet options={options.event_types} value={f.event_types} onChange={set("event_types")} />
        <small>None selected means all types of news.</small>
      </div>
      <div className="form-grid">
        <label className="field">
          <span>Also count these words as compressor-related</span>
          <textarea className="input" rows="4" value={f.include} onChange={(e) => set("include")(e.target.value)} />
          <small>One per line.</small>
        </label>
        <label className="field">
          <span>Leave out anything containing these words</span>
          <textarea className="input" rows="4" value={f.exclude} onChange={(e) => set("exclude")(e.target.value)} />
          <small>One per line.</small>
        </label>
      </div>
      {status?.error && <ErrorBanner error={status.error} />}
      {status?.ok && <div className="banner ok">{status.ok}</div>}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn btn-primary" type="submit" disabled={status?.saving}>{status?.saving ? "Saving..." : "Done"}</button>
        {rerun.state === "running" && <span className="muted" style={{ fontSize: 13 }}>A run is in progress (see the menu).</span>}
      </div>
    </form>
  );
}
