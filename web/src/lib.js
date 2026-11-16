import { useCallback, useEffect, useState } from "react";

const MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");

export const nice = (v) => (v || "").replaceAll("_", " ");

export const isClientItem = (item) => (item.company || "").toLowerCase().startsWith("atlas copco");

export function runLabel(id) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(id || "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}, ${m[4]}:${m[5]} UTC` : id || "";
}

export function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "";
}

export const safeUrl = (url) => (/^https?:\/\//i.test(url || "") ? url : null);

export const byNewest = (a, b) => (b.published_at || "").localeCompare(a.published_at || "");

export function haystack(item) {
  return [item.title, item.company, item.product, item.technology, item.event_type, item.source_name, item.region,
    ...(item.key_facts || [])].filter(Boolean).join(" ").toLowerCase().replaceAll("_", " ");
}

export function searchItems(items, query, { event, label } = {}) {
  const words = (query || "").toLowerCase().split(/\s+/).filter(Boolean);
  return items
    .filter((i) => !isClientItem(i))
    .filter((i) => words.every((w) => haystack(i).includes(w)))
    .filter((i) => !event || i.event_type === event)
    .filter((i) => !label || i.label === label)
    .sort(byNewest);
}

export function countBy(items, key, limit = 8) {
  const counts = new Map();
  for (const it of items) {
    const k = nice(typeof key === "function" ? key(it) : it[key]) || "not stated";
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  return [...counts].map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value).slice(0, limit);
}

/** Load async data; `reload()` fetches again. deps work like useEffect deps. */
export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => alive && setState({ loading: false, data, error: null }))
      .catch((error) => alive && setState({ loading: false, data: null, error }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

export function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
