import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useScout } from "../App.jsx";
import { byNewest, countBy, isClientItem, nice, shortDate } from "../lib.js";
import { Async, Badge, Empty, SectionHead, SourceLink } from "../components/ui.jsx";
import { IconArrow } from "../components/icons.jsx";

function useChartColors(theme) {
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement);
    const v = (n) => css.getPropertyValue(n).trim();
    return { bar: v("--chart-1"), grid: v("--chart-grid"), text: v("--color-text-muted") };
  }, [theme]); // eslint-disable-line react-hooks/exhaustive-deps
}

const Tip = ({ active, payload }) =>
  active && payload?.length ? (
    <div className="chart-tip"><strong>{payload[0].payload.name}</strong>: {payload[0].value} fact(s)</div>
  ) : null;

function HBar({ data, colors }) {
  const height = Math.max(160, data.length * 34 + 30);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid horizontal={false} stroke={colors.grid} />
        <XAxis type="number" allowDecimals={false} tick={{ fill: colors.text, fontSize: 12 }} axisLine={{ stroke: colors.grid }} tickLine={false} />
        <YAxis type="category" dataKey="name" width={150} tick={{ fill: colors.text, fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip content={<Tip />} cursor={{ fill: "rgba(90,169,230,0.08)" }} />
        <Bar dataKey="value" fill={colors.bar} radius={[0, 4, 4, 0]} maxBarSize={20} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Overview() {
  const { envelope, theme } = useScout();
  const colors = useChartColors(theme);
  return (
    <>
      <section className="hero">
        <div className="kicker">Compressor market scout</div>
        <h1>Know the market <span className="gradient-text">before</span> it moves.</h1>
        <p className="lede">
          Public news on compressors, blowers, vacuum and gas compression in North America. Read politely, checked by
          rules, and every fact keeps its source link.
        </p>
        <div className="hero-actions">
          <Link to="/search" className="btn btn-primary">Search the findings <IconArrow /></Link>
          <Link to="/report" className="btn btn-secondary">Get the brief</Link>
        </div>
      </section>

      <Async state={envelope} loading="Loading the latest run...">
        {(env) => {
          if (!env) return <Empty>No results yet. Open <Link to="/filters">Filters</Link> and press Done to run.</Empty>;
          const items = env.items.filter((i) => !isClientItem(i));
          const read = env.sources.filter((s) => s.kind !== "fallback" && s.items_collected > 0).length;
          const refused = env.sources.filter((s) => s.status !== "working").length;
          const latest = [...items].sort(byNewest).slice(0, 10);
          return (
            <>
              <div className="stats">
                <div className="stat"><div className="v">{items.length}</div><div className="c">Facts kept</div></div>
                <div className="stat"><div className="v">{read}</div><div className="c">Sources read</div></div>
                <div className="stat"><div className="v">{refused}</div><div className="c">Sources refused</div></div>
                <div className="stat"><div className="v">{(env.stories || []).length}</div><div className="c">Stories</div></div>
              </div>

              <div className="grid-2">
                <div className="card">
                  <h3>Facts per source</h3>
                  <p className="card-sub">Where this run's facts came from.</p>
                  <div style={{ marginTop: 12 }}>{items.length ? <HBar data={countBy(items, "source_name")} colors={colors} /> : <Empty>No facts.</Empty>}</div>
                </div>
                <div className="card">
                  <h3>Types of news</h3>
                  <p className="card-sub">What kind of event each fact is about.</p>
                  <div style={{ marginTop: 12 }}>{items.length ? <HBar data={countBy(items, "event_type")} colors={colors} /> : <Empty>No facts.</Empty>}</div>
                </div>
              </div>

              <SectionHead kicker="The findings" title="Latest facts"
                           right={<Link to="/search" className="btn btn-secondary btn-sm">See all {items.length} <IconArrow /></Link>}>
                Newest first. Every row links to the original article.
              </SectionHead>
              {latest.length ? (
                <div className="table-wrap">
                  <table className="data">
                    <thead><tr><th>Date</th><th>Company</th><th>News</th><th>Fact</th><th>Label</th><th>Source</th></tr></thead>
                    <tbody>
                      {latest.map((i) => (
                        <tr key={i.id}>
                          <td style={{ whiteSpace: "nowrap" }}>{shortDate(i.published_at) || "not stated"}</td>
                          <td>{i.company || <span className="muted">unknown</span>}</td>
                          <td>{nice(i.event_type) || "other"}</td>
                          <td className="fact">{i.key_facts?.[0] || i.title}</td>
                          <td>{i.label === "fact" ? <Badge tone="success">FACT</Badge> : <Badge>claim</Badge>}</td>
                          <td><SourceLink url={i.source_url}>open</SourceLink></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <Empty>This run kept no facts. Try widening the filters.</Empty>}
            </>
          );
        }}
      </Async>
    </>
  );
}
