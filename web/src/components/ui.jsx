import { IconExternal } from "./icons.jsx";
import { safeUrl } from "../lib.js";

export const Badge = ({ tone = "neutral", children }) => <span className={`badge ${tone}`}>{children}</span>;

export const PageHead = ({ kicker, title, children, right }) => (
  <div className="head-row">
    <div className="page-head">
      <div className="kicker">{kicker}</div>
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </div>
    {right}
  </div>
);

export const SectionHead = ({ kicker, title, children, right }) => (
  <div className="head-row">
    <div className="section-head">
      <div className="kicker">{kicker}</div>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
    {right}
  </div>
);

export const Loading = ({ children = "Loading..." }) => (
  <div className="loading" role="status"><div className="spinner" />{children}</div>
);

export const ErrorBanner = ({ error }) => (
  <div className="banner error" role="alert">
    {error?.message || String(error)}
    {error?.detail && <div className="detail">{error.detail}</div>}
  </div>
);

export const Empty = ({ children }) => <div className="empty">{children}</div>;

export const StatTile = ({ label, value }) => (
  <div className="stat-tile"><div className="label">{label}</div><div className="value">{value}</div></div>
);

export const SourceLink = ({ url, children = "Open source" }) => {
  const href = safeUrl(url);
  return href ? <a className="link" href={href} target="_blank" rel="noopener noreferrer">{children} <IconExternal /></a> : null;
};

/** Shows loading / error / content for a useAsync result. */
export function Async({ state, children, loading }) {
  if (state.loading && !state.data) return <Loading>{loading}</Loading>;
  if (state.error) return <ErrorBanner error={state.error} />;
  return children(state.data);
}
