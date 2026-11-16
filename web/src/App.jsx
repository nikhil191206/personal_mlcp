import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api.js";
import { runLabel, useAsync } from "./lib.js";
import { IconFacts, IconFilters, IconMoon, IconOverview, IconReport, IconSearch, IconSources, IconSun } from "./components/icons.jsx";
import Overview from "./pages/Overview.jsx";
import Search from "./pages/Search.jsx";
import Facts from "./pages/Facts.jsx";
import Sources from "./pages/Sources.jsx";
import Filters from "./pages/Filters.jsx";
import Report from "./pages/Report.jsx";

const ScoutContext = createContext(null);
export const useScout = () => useContext(ScoutContext);

const PAGES = [
  { path: "/", label: "Overview", icon: IconOverview, element: <Overview /> },
  { path: "/search", label: "Search", icon: IconSearch, element: <Search /> },
  { path: "/facts", label: "Facts", icon: IconFacts, element: <Facts /> },
  { path: "/sources", label: "Sources", icon: IconSources, element: <Sources /> },
  { path: "/filters", label: "Filters", icon: IconFilters, element: <Filters /> },
  { path: "/report", label: "Report", icon: IconReport, element: <Report /> },
];

function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("scoutTheme", theme); } catch { /* private mode: the toggle still works */ }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

/** Polls the rerun status every 3 s; when a run finishes, refreshes the run list and selects the new run. */
function useRerun(onDone) {
  const [status, setStatus] = useState({ state: "idle" });
  const last = useRef("idle");
  const poll = useCallback(async () => {
    try {
      const s = await api.rerun();
      if (last.current === "running" && s.state !== "running") onDone(s);
      last.current = s.state;
      setStatus(s);
    } catch { /* the API being down is shown elsewhere */ }
  }, [onDone]);
  useEffect(() => {
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, [poll]);
  return [status, poll];
}

function ClientLogo() {
  const [src, setSrc] = useState("/atlas_copco_logo.svg");
  if (!src) return <span>Prepared for Atlas Copco</span>;
  return <img src={src} alt="Atlas Copco" onError={() => setSrc(src.endsWith(".svg") ? "/atlas_copco_logo.png" : null)} />;
}

function Sidebar({ theme, toggleTheme, health, rerun }) {
  const pct = rerun.total ? Math.round((rerun.n / rerun.total) * 100) : 0;
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="name">Market Scout</div>
        <div className="tag">Compressor market intelligence</div>
        <div className="client"><ClientLogo /></div>
      </div>
      <nav className="nav" aria-label="Main">
        <div className="nav-label">Menu</div>
        {PAGES.map(({ path, label, icon: Icon }) => (
          <NavLink key={path} to={path} end={path === "/"}><Icon />{label}</NavLink>
        ))}
      </nav>
      <div className="spacer" />
      {rerun.state === "running" && (
        <div className="side-card" role="status">
          <div className="row"><span className="k">Run in progress</span><span className="v">{pct}%</span></div>
          <div className="bar"><div style={{ width: `${pct}%` }} /></div>
          <div className="line">Source {rerun.n} of {rerun.total || "?"} · {rerun.reason}</div>
        </div>
      )}
      {rerun.state === "failed" && (
        <div className="side-card" role="alert"><span className="k" style={{ color: "#f87171" }}>Last run failed (exit {rerun.exit_code})</span></div>
      )}
      <div className="side-card optional">
        <div className="row">
          <span className="k">Data folder</span>
          {health?.demo_folders ? <span className="v warn">Live demo</span> : <span className="v">{health?.prefix || "..."}</span>}
        </div>
      </div>
      <button className="theme-toggle" onClick={toggleTheme} aria-label="Switch colour theme">
        {theme === "dark" ? "Switch to light" : "Switch to dark"}
        <span className="glyph" aria-hidden>{theme === "dark" ? <IconSun /> : <IconMoon />}</span>
      </button>
    </aside>
  );
}

function RunPicker() {
  const { runs, runId, setRunId } = useScout();
  if (!runs.length) return null;
  return (
    <label className="crumb" style={{ display: "flex", alignItems: "center", gap: 10 }}>
      Run
      <select className="input" style={{ width: "auto", padding: "6px 10px" }} value={runId || ""}
              onChange={(e) => setRunId(e.target.value)} aria-label="Choose a run">
        {runs.map((r, i) => <option key={r} value={r}>{runLabel(r)}{i === 0 ? " (latest)" : ""}</option>)}
      </select>
    </label>
  );
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [runId, setRunId] = useState(null);
  const health = useAsync(() => api.health(), []);
  const runsState = useAsync(() => api.runs(), []);
  const runs = runsState.data?.runs || [];

  useEffect(() => {
    if (runsState.data && (!runId || !runs.includes(runId))) setRunId(runsState.data.latest);
  }, [runsState.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const envelope = useAsync(() => (runId ? api.run(runId) : Promise.resolve(null)), [runId]);
  const reloadRuns = runsState.reload;
  const onRunDone = useCallback((s) => { if (s.state === "done") { setRunId(null); reloadRuns(); } }, [reloadRuns]);
  const [rerun, pollRerun] = useRerun(onRunDone);
  const location = useLocation();
  const page = PAGES.find((p) => (p.path === "/" ? location.pathname === "/" : location.pathname.startsWith(p.path)));

  const value = { runs, runId, setRunId, envelope, runsState, rerun, pollRerun, theme };
  return (
    <ScoutContext.Provider value={value}>
      <Sidebar theme={theme} toggleTheme={toggleTheme} health={health.data} rerun={rerun} />
      <main className="main">
        <header className="topbar">
          <div className="crumb">Market Scout / <strong>{page?.label || "Page"}</strong></div>
          <RunPicker />
        </header>
        <div className="content">
          {runsState.error && <div className="banner error" role="alert">{runsState.error.message}
            {runsState.error.detail && <div className="detail">{runsState.error.detail}</div>}</div>}
          <Routes>
            {PAGES.map(({ path, element }) => <Route key={path} path={path} element={element} />)}
            <Route path="*" element={<Overview />} />
          </Routes>
        </div>
      </main>
    </ScoutContext.Provider>
  );
}
