import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useScout } from "../App.jsx";
import { countBy, isClientItem, nice, runLabel, searchItems, shortDate } from "../lib.js";
import { Async, Badge, Empty, PageHead, SourceLink } from "../components/ui.jsx";
import { IconSearch } from "../components/icons.jsx";

const LIMIT = 50;
const SUGGESTIONS = ["compressor", "vacuum", "blower", "acquisition", "hydrogen", "dryer"];

function Result({ item }) {
  const meta = [shortDate(item.published_at) || "date not stated", item.source_name, item.company, item.product].filter(Boolean);
  return (
    <article className="card hover result">
      <div className="badges">
        {item.label === "fact" ? <Badge tone="success">FACT</Badge> : <Badge>claim</Badge>}
        {item.event_type && <Badge tone="primary">{nice(item.event_type)}</Badge>}
        {item.technology && <Badge tone="primary">{nice(item.technology)}</Badge>}
        {item.region && <Badge>{item.region}</Badge>}
        {item.via_fallback && <Badge tone="warning">via fallback for {item.fallback_for}</Badge>}
      </div>
      <div className="title">{item.title || "(no title)"}</div>
      <div className="meta">{meta.join(" · ")}</div>
      {item.key_facts?.length > 0 && <ul>{item.key_facts.slice(0, 2).map((f, n) => <li key={n}>{f}</li>)}</ul>}
      <SourceLink url={item.source_url} />
    </article>
  );
}

export default function Search() {
  const { envelope } = useScout();
  const [params, setParams] = useSearchParams();
  const event = params.get("event") || "";
  const label = params.get("label") || "";
  // The box keeps its own text, so typing never waits on the page address; the address follows after a short pause.
  const [q, setQ] = useState(params.get("q") || "");
  const paramsRef = useRef(params);
  paramsRef.current = params;
  useEffect(() => {
    const t = setTimeout(() => {
      const next = new URLSearchParams(paramsRef.current);
      q ? next.set("q", q) : next.delete("q");
      if (next.toString() !== paramsRef.current.toString()) setParams(next, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (key, value) => {
    if (key === "q") { setQ(value); return; }
    const next = new URLSearchParams(paramsRef.current);
    value ? next.set(key, value) : next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHead kicker="Search" title="Find anything in the results">
        Every word must match somewhere: title, company, product, technology, type of news, source or key facts.
      </PageHead>
      <div className="search-box">
        <IconSearch />
        <input className="input" type="search" autoFocus placeholder="Search, for example: rotary screw compressor"
               value={q} onChange={(e) => set("q", e.target.value)} aria-label="Search" />
      </div>
      <Async state={envelope} loading="Loading facts...">
        {(env) => <Results env={env} q={q} event={event} label={label} set={set} />}
      </Async>
    </>
  );
}

function Results({ env, q, event, label, set }) {
  const items = useMemo(() => (env ? env.items.filter((i) => !isClientItem(i)) : []), [env]);
  const events = useMemo(() => countBy(items, "event_type", 12).filter((e) => e.name !== "not stated"), [items]);
  const results = useMemo(() => searchItems(items, q, { event: event || null, label: label || null }), [items, q, event, label]);
  if (!env) return <Empty>No results yet.</Empty>;
  return (
    <>
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Type of news">
          <button className={`chip ${!event ? "on" : ""}`} onClick={() => set("event", "")}>All news</button>
          {events.map((e) => {
            const raw = e.name.replaceAll(" ", "_");
            return (
              <button key={raw} className={`chip ${event === raw ? "on" : ""}`} onClick={() => set("event", event === raw ? "" : raw)}>
                {e.name} <span className="muted">{e.value}</span>
              </button>
            );
          })}
        </div>
        <select className="input" value={label} onChange={(e) => set("label", e.target.value)} aria-label="Facts or claims">
          <option value="">Facts and claims</option><option value="fact">Facts only</option><option value="claim">Claims only</option>
        </select>
      </div>
      <p style={{ fontSize: 13 }}>
        {results.length} result{results.length === 1 ? "" : "s"}{results.length > LIMIT ? `, showing the newest ${LIMIT}` : ""}
        {" "}· searching {items.length} facts from the run of {runLabel(env.run_id)}
        {items.length < 20 && <strong style={{ color: "var(--color-warning)" }}> (a small run: choose another in the top bar)</strong>}
      </p>
      {results.length ? (
        <div className="list">{results.slice(0, LIMIT).map((i) => <Result key={i.id} item={i} />)}</div>
      ) : (
        <Empty>
          Nothing matches. Try one broader word:{" "}
          <span className="chips" style={{ display: "inline-flex", marginTop: 10 }}>
            {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => set("q", s)}>{s}</button>)}
          </span>
        </Empty>
      )}
    </>
  );
}
