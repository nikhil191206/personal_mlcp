import { useState } from "react";
import { useScout } from "../App.jsx";
import { api } from "../api.js";
import { download, nice, safeUrl, shortDate, useAsync } from "../lib.js";
import { Async, Badge, Empty, ErrorBanner, PageHead, SourceLink, StatTile } from "../components/ui.jsx";

const STATUS = { confirmed: ["success", "Confirmed"], not_confirmed: ["warning", "Not confirmed"] };

function Status({ v }) {
  if (!v) return <Badge>not checked</Badge>;
  const [tone, label] = STATUS[v.status] || ["neutral", v.status];
  return <Badge tone={tone}>{label}</Badge>;
}

function Logo({ logo, name }) {
  const [ok, setOk] = useState(true);
  const src = safeUrl(logo?.url);
  if (!src || !ok) return <div className="company-logo placeholder" aria-hidden>{name.slice(0, 1)}</div>;
  return <img className="company-logo" src={src} alt={`${name} logo`} onError={() => setOk(false)} />;
}

function CompanyCard({ profile, items, runId }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const mine = profile.item_ids.map((id) => items[id]).filter(Boolean);
  const website = safeUrl(profile.website);

  const report = async (fmt) => {
    setBusy(fmt);
    setError(null);
    try { download(await api.companyReport(runId, profile.company_id, fmt), `${profile.company_id}_${runId}.${fmt}`); }
    catch (e) { setError(e); }
    setBusy(null);
  };

  return (
    <article className="card">
      <div className="row-between">
        <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
          <Logo logo={profile.logo} name={profile.name} />
          <div>
            <div className="result"><div className="title">{profile.name}</div></div>
            {website && <a className="link mono" href={website} target="_blank" rel="noopener noreferrer">{website}</a>}
            <div className="badges" style={{ marginTop: 8 }}>
              <Badge tone="primary">{profile.item_ids.length} item{profile.item_ids.length === 1 ? "" : "s"}</Badge>
              <Badge tone={profile.confirmed_item_ids.length ? "success" : "neutral"}>{profile.confirmed_item_ids.length} confirmed</Badge>
              <Badge>{profile.source_ids.length} source{profile.source_ids.length === 1 ? "" : "s"}</Badge>
              {Object.keys(profile.event_types).slice(0, 3).map((e) => <Badge key={e}>{nice(e)}</Badge>)}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <a className="btn btn-sm btn-secondary" href={`/view/${encodeURIComponent(runId)}/${encodeURIComponent(profile.company_id)}`}
             target="_blank" rel="noopener noreferrer">View</a>
          <button className="btn btn-sm btn-secondary" disabled={!!busy} onClick={() => report("pdf")}>{busy === "pdf" ? "Building..." : "PDF"}</button>
          <button className="btn btn-sm btn-secondary" disabled={!!busy} onClick={() => report("pptx")}>{busy === "pptx" ? "Building..." : "PowerPoint"}</button>
          <button className="btn btn-sm btn-primary" onClick={() => setOpen(!open)}>{open ? "Hide" : "Details"}</button>
        </div>
      </div>
      {error && <ErrorBanner error={error} />}
      {open && (
        <div style={{ marginTop: 14 }}>
          <h3 className="sub">Contact details</h3>
          {profile.contacts.length === 0 && <div className="detail-text">No contact details yet. Company website: {profile.profile_status}.</div>}
          {profile.contacts.map((c) => (
            <div key={`${c.kind}-${c.value}`} className="detail-text">
              <Status v={c.validation} /> <strong>{c.kind}</strong> {c.value}
              {c.found_on?.[0] && <> · <SourceLink url={c.found_on[0]}>where found</SourceLink></>}
            </div>
          ))}
          <h3 className="sub">News and facts</h3>
          {mine.map((i) => (
            <div key={i.id} className="detail-text" style={{ marginBottom: 8 }}>
              <Status v={i.validation} /> {shortDate(i.published_at) || "(no date)"} · {nice(i.event_type) || "-"} · {i.title}
              {" "}<SourceLink url={i.source_url} />
              <div style={{ opacity: 0.75 }}>
                {(i.validation?.status === "confirmed" ? i.validation.criteria_met : i.validation?.reasons || []).join("; ")}
              </div>
            </div>
          ))}
          {profile.images.length > 0 && <>
            <h3 className="sub">Images (links)</h3>
            {profile.images.map((img) => <div key={img.url} className="detail-text"><SourceLink url={img.url}>{img.alt || "image"}</SourceLink></div>)}
          </>}
        </div>
      )}
    </article>
  );
}

export default function Companies() {
  const { runId } = useScout();
  const state = useAsync(() => (runId ? api.companies(runId) : Promise.resolve(null)), [runId]);
  return (
    <>
      <PageHead kicker="Company-wise" title="Companies">
        Every company found in this run, with its news, which facts are confirmed and why, its contact details and a
        one-page report per company. Contacts and logos appear after <span className="mono">python -m atlas.companies --fetch-profiles</span>.
      </PageHead>
      <Async state={state} loading="Grouping the run by company...">
        {(data) => {
          if (!data) return <Empty>No results yet.</Empty>;
          const { index, items } = data;
          const confirmed = Object.values(items).filter((i) => i.validation?.status === "confirmed").length;
          return (
            <>
              <div className="stat-grid">
                <StatTile label="Companies" value={index.companies.length} />
                <StatTile label="Items" value={Object.keys(items).length} />
                <StatTile label="Confirmed" value={confirmed} />
                <StatTile label="No company found" value={index.unattributed_item_ids.length} />
              </div>
              <div className="list">
                {index.companies.length === 0 && <Empty>No company was found in this run.</Empty>}
                {index.companies.map((p) => <CompanyCard key={p.company_id} profile={p} items={items} runId={runId} />)}
              </div>
              <details className="card" style={{ marginTop: 16 }}>
                <summary>How Confirmed and Not confirmed are decided</summary>
                <ul>{index.criteria.map((c) => <li key={c} className="detail-text">{c}</li>)}</ul>
              </details>
            </>
          );
        }}
      </Async>
    </>
  );
}
