import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { CallError } from "../lib/api";
import {
  bucketSize,
  buckets,
  formatSpan,
  funnel,
  inRange,
  kpis,
  MILESTONES,
  pct,
  RANGES,
  story,
  type Bucket,
  type CallFacts,
  type FunnelStep,
  type Range,
} from "../lib/stats";

/** Funnel order -> the ordinal ramp (index.css), the last step (transfers) most prominent. */
const STEP_COLOR = [
  "var(--viz-1)",
  "var(--viz-2)",
  "var(--viz-3)",
  "var(--viz-4)",
  "var(--viz-5)",
];

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; rows: CallFacts[] };

async function fetchStats(includeTests: boolean): Promise<CallFacts[]> {
  let res: Response;
  try {
    res = await fetch(`/api/stats${includeTests ? "?include_tests=true" : ""}`);
  } catch {
    throw new CallError(
      "Can't reach the server. Check your connection and try again.",
    );
  }
  if (!res.ok)
    throw new CallError(`Couldn't load the stats (error ${res.status}).`);
  return (await res.json()) as CallFacts[];
}

/**
 * Stats: what Mia's calls add up to. It leads with the KPI that matters (transfers: qualified
 * leads), then the time Mia handled, the funnel from call to transfer, and how each step
 * moves over time. One filter row scopes everything below it.
 */
export function StatsPage({ active }: { active: boolean }) {
  const [range, setRange] = useState<Range>("30d");
  const [includeTests, setIncludeTests] = useState(false);
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [table, setTable] = useState(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    fetchStats(includeTests)
      .then((rows) => !cancelled && setLoad({ kind: "ok", rows }))
      .catch(
        (err) =>
          !cancelled &&
          setLoad({
            kind: "error",
            message:
              err instanceof CallError
                ? err.message
                : "Couldn't load the stats.",
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [active, includeTests]);

  const view = useMemo(() => {
    if (load.kind !== "ok") return null;
    const rows = inRange(load.rows, range);
    const k = kpis(rows);
    const steps = funnel(rows);
    const days = buckets(rows, range);
    return { rows, k, steps, days, text: story(k, steps) };
  }, [load, range]);

  return (
    <div className="flex flex-col gap-4 pb-2 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
      <div className="flex flex-wrap items-center gap-3">
        <div
          role="radiogroup"
          aria-label="Date range"
          className="flex gap-1 rounded-full bg-raised p-1"
        >
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              role="radio"
              aria-checked={range === r.key}
              onClick={() => setRange(r.key)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
                range === r.key
                  ? "bg-surface text-ink shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={includeTests}
            onChange={(e) => setIncludeTests(e.target.checked)}
            className="size-4 accent-[var(--brand)]"
          />
          Include scripted test calls
        </label>
      </div>

      {load.kind === "loading" && <Card>Loading the stats…</Card>}
      {load.kind === "error" && (
        <Card>
          <span role="alert" className="text-danger">
            {load.message}
          </span>
        </Card>
      )}
      {view && (
        <div
          className={`flex flex-col gap-4 transition-opacity ${load.kind === "ok" ? "" : "opacity-60"}`}
        >
          <p className="max-w-4xl text-base leading-relaxed text-ink">
            {view.text}
          </p>
          <KpiRow k={view.k} />
          <Section
            title="Funnel"
            note="Each step's share of calls, and conversion from the step before."
          >
            <Funnel steps={view.steps} />
          </Section>
          <Section
            title="Over time"
            note={`Per ${bucketSize(view.days)}, in your time zone.`}
            action={
              <button
                type="button"
                onClick={() => setTable(!table)}
                className="text-sm text-brand underline-offset-2 hover:underline"
              >
                {table ? "Show charts" : "Show as table"}
              </button>
            }
          >
            {view.days.length === 0 ? (
              <p className="text-sm text-muted">No calls in this period yet.</p>
            ) : table ? (
              <TrendTable days={view.days} unit={bucketSize(view.days)} />
            ) : (
              <Trends days={view.days} unit={bucketSize(view.days)} />
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4 text-sm text-muted">
      {children}
    </div>
  );
}

function Section({
  title,
  note,
  action,
  children,
}: {
  title: string;
  note: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="text-xs text-muted">{note}</p>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

// --- KPIs ---------------------------------------------------------------------------------

function KpiRow({ k }: { k: ReturnType<typeof kpis> }) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
      <div className="col-span-2 flex flex-col justify-between gap-1 rounded-2xl border border-line bg-surface p-4 xl:col-span-1">
        <span className="text-sm text-muted">
          Transfers to a representative
        </span>
        <span className="text-5xl font-semibold tracking-tight text-ink">
          {k.transfers}
        </span>
        <span className="text-sm text-muted">
          Qualified leads ·{" "}
          <span className="font-medium text-ink">{pct(k.transferRate)}</span> of
          calls
        </span>
      </div>
      <Tile label="Calls" value={String(k.calls)} sub="Answered by Mia" />
      <Tile
        label="Time handled by Mia"
        value={formatSpan(k.miaSeconds)}
        sub={
          k.avgMiaSeconds != null
            ? `${formatSpan(k.avgMiaSeconds)} a call on average`
            : "–"
        }
      />
      <Tile
        label="Quotes given"
        value={String(k.quotes)}
        sub={`${pct(k.quoteRate)} of calls`}
      />
      <Tile
        label="Response time"
        value={
          k.medianLatencyMs != null
            ? `${(k.medianLatencyMs / 1000).toFixed(1)} s`
            : "–"
        }
        sub="Median, caller stops to Mia speaks"
      />
    </div>
  );
}

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-4">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-2xl font-semibold tracking-tight text-ink">
        {value}
      </span>
      <span className="text-xs text-muted">{sub}</span>
    </div>
  );
}

// --- funnel -------------------------------------------------------------------------------

function Funnel({ steps }: { steps: FunnelStep[] }) {
  const [hover, setHover] = useState<number | null>(null);
  return (
    <ol
      className="flex flex-col gap-2.5"
      aria-label="Funnel from call to transfer"
    >
      {steps.map((s, i) => (
        <li
          key={s.key}
          tabIndex={0}
          onPointerEnter={() => setHover(i)}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(i)}
          onBlur={() => setHover(null)}
          aria-label={`${s.label}: ${s.count} calls, ${pct(s.ofCalls)} of calls${
            s.ofPrev != null ? `, ${pct(s.ofPrev)} of the step before` : ""
          }`}
          className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 rounded-lg py-1 outline-none focus-visible:ring-2 focus-visible:ring-accent sm:grid-cols-[minmax(7rem,13rem)_1fr_6rem_5rem]"
        >
          <span className="text-sm text-ink">{s.label}</span>
          {/* On a phone the bar gets its own full-width row, under the label and numbers. */}
          <span className="relative order-last col-span-2 h-4 sm:order-none sm:col-span-1">
            <span
              className="block h-4 rounded-r-[4px] transition-[width,filter] duration-500"
              style={{
                width: `${Math.max((s.ofCalls ?? 0) * 100, s.count ? 1.5 : 0)}%`,
                background: STEP_COLOR[i],
                filter: hover === i ? "brightness(1.12)" : undefined,
              }}
            />
            {hover === i && (
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-0 z-10 mb-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs whitespace-nowrap text-muted shadow-md"
              >
                <span className="font-semibold text-ink">{s.count}</span>{" "}
                {s.label.toLowerCase()} · {pct(s.ofCalls)} of calls
                {s.ofPrev != null && <> · {pct(s.ofPrev)} of the step before</>}
              </span>
            )}
          </span>
          <span className="text-right text-sm whitespace-nowrap text-ink sm:text-left">
            <span className="font-semibold">{s.count}</span>{" "}
            <span className="text-muted">· {pct(s.ofCalls)}</span>
            {s.ofPrev != null && (
              <span className="text-xs text-muted sm:hidden">
                {" "}
                · {pct(s.ofPrev)} of prev.
              </span>
            )}
          </span>
          <span className="hidden text-right text-xs text-muted sm:block">
            {s.ofPrev != null ? (
              <>
                <span className="font-medium text-ink">{pct(s.ofPrev)}</span> of
                prev.
              </>
            ) : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

// --- trends -------------------------------------------------------------------------------

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function dayLabel(ms: number, unit: "day" | "week"): string {
  const d = new Date(ms).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  return unit === "week" ? `Week of ${d}` : d;
}

const PAD = { left: 34, right: 8, top: 8, bottom: 22 };

function Trends({ days, unit }: { days: Bucket[]; unit: "day" | "week" }) {
  return (
    <div className="flex flex-col gap-5">
      <CallsChart days={days} unit={unit} />
      <div>
        <h3 className="text-sm font-medium text-ink">
          Share of calls reaching each step
        </h3>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          {MILESTONES.slice(1).map((m, i) => (
            <RateChart
              key={m.key}
              days={days}
              unit={unit}
              step={m.key as Exclude<typeof m.key, "calls">}
              label={m.label}
              color={STEP_COLOR[i + 1]}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Shared x layout: one slot per bucket. */
function xs(n: number, width: number) {
  const inner = Math.max(0, width - PAD.left - PAD.right);
  const slot = n ? inner / n : 0;
  return { slot, center: (i: number) => PAD.left + slot * i + slot / 2 };
}

function XAxis({
  days,
  unit,
  width,
  height,
}: {
  days: Bucket[];
  unit: "day" | "week";
  width: number;
  height: number;
}) {
  const { center } = xs(days.length, width);
  const ticks =
    days.length <= 3
      ? days.map((_, i) => i)
      : [0, Math.floor((days.length - 1) / 2), days.length - 1];
  return (
    <g className="fill-[var(--muted)] text-[11px]">
      {ticks.map((i) => (
        <text
          key={i}
          x={
            i === 0 && ticks.length > 1
              ? PAD.left
              : i === days.length - 1 && i > 0
                ? width - PAD.right
                : center(i)
          }
          y={height - 6}
          textAnchor={
            i === 0 && ticks.length > 1
              ? "start"
              : i === days.length - 1 && i > 0
                ? "end"
                : "middle"
          }
        >
          {dayLabel(days[i].start, unit).replace("Week of ", "")}
        </text>
      ))}
    </g>
  );
}

function Hover({
  days,
  width,
  height,
  index,
  onIndex,
}: {
  days: Bucket[];
  width: number;
  height: number;
  index: number | null;
  onIndex: (i: number | null) => void;
}) {
  const { slot, center } = xs(days.length, width);
  return (
    <>
      {index != null && (
        <line
          x1={center(index)}
          x2={center(index)}
          y1={PAD.top}
          y2={height - PAD.bottom}
          className="stroke-[var(--muted)]"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      )}
      <rect
        x={PAD.left}
        y={0}
        width={Math.max(0, width - PAD.left - PAD.right)}
        height={height}
        fill="transparent"
        onPointerMove={(e) => {
          const box = (
            e.currentTarget.ownerSVGElement as SVGSVGElement
          ).getBoundingClientRect();
          const i = Math.floor((e.clientX - box.left - PAD.left) / (slot || 1));
          onIndex(Math.max(0, Math.min(days.length - 1, i)));
        }}
        onPointerLeave={() => onIndex(null)}
      />
    </>
  );
}

function Tip({
  x,
  width,
  children,
}: {
  x: number;
  width: number;
  children: ReactNode;
}) {
  const left = Math.min(Math.max(x - 80, 0), Math.max(0, width - 170));
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute top-0 z-10 w-[170px] rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted shadow-md"
      style={{ left }}
    >
      {children}
    </div>
  );
}

function CallsChart({ days, unit }: { days: Bucket[]; unit: "day" | "week" }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [index, setIndex] = useState<number | null>(null);
  const height = 170;
  const max = Math.max(1, ...days.map((d) => d.calls));
  const top = Math.max(2, Math.ceil(max / 2) * 2);
  const y = (v: number) =>
    PAD.top + (1 - v / top) * (height - PAD.top - PAD.bottom);
  const { slot, center } = xs(days.length, width);
  const barW = Math.max(2, Math.min(28, slot - 2));
  const d = index != null ? days[index] : null;
  return (
    <div>
      <h3 className="text-sm font-medium text-ink">
        Calls and transfers per {unit}
      </h3>
      <div ref={ref} className="relative mt-2">
        {width > 0 && (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`Calls per ${unit}`}
          >
            {[0, top / 2, top].map((v) => (
              <g key={v}>
                <line
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(v)}
                  y2={y(v)}
                  className="stroke-[var(--viz-grid)]"
                />
                <text
                  x={PAD.left - 6}
                  y={y(v) + 4}
                  textAnchor="end"
                  className="fill-[var(--muted)] text-[11px]"
                >
                  {v}
                </text>
              </g>
            ))}
            {days.map((b, i) => (
              <g
                key={b.start}
                opacity={index == null || index === i ? 1 : 0.55}
              >
                {b.calls > 0 && (
                  <path
                    d={roundedTop(
                      center(i) - barW / 2,
                      y(b.calls),
                      barW,
                      y(0) - y(b.calls),
                    )}
                    fill="var(--viz-2)"
                  />
                )}
                {b.transfer > 0 && (
                  <path
                    d={roundedTop(
                      center(i) - barW / 2,
                      y(b.transfer),
                      barW,
                      y(0) - y(b.transfer),
                    )}
                    fill="var(--viz-5)"
                    stroke="var(--surface)"
                    strokeWidth={2}
                    paintOrder="stroke"
                  />
                )}
              </g>
            ))}
            <XAxis days={days} unit={unit} width={width} height={height} />
            <Hover
              days={days}
              width={width}
              height={height}
              index={index}
              onIndex={setIndex}
            />
          </svg>
        )}
        {d && index != null && (
          <Tip x={center(index)} width={width}>
            <div className="mb-1 text-ink">{dayLabel(d.start, unit)}</div>
            <Row color="var(--viz-2)" value={d.calls} label="calls" />
            <Row color="var(--viz-5)" value={d.transfer} label="transfers" />
            <div className="mt-1">Mia: {formatSpan(d.miaSeconds)}</div>
          </Tip>
        )}
      </div>
      <div className="mt-1 flex gap-4 text-xs text-muted">
        <Legend color="var(--viz-2)" label="Calls" />
        <Legend color="var(--viz-5)" label="Transfers" />
      </div>
    </div>
  );
}

function roundedTop(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

function Row({
  color,
  value,
  label,
}: {
  color: string;
  value: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-0.5 w-3 rounded" style={{ background: color }} />
      <span className="font-semibold text-ink">{value}</span> {label}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="size-2.5 rounded-[2px]" style={{ background: color }} />
      {label}
    </span>
  );
}

function RateChart({
  days,
  unit,
  step,
  label,
  color,
}: {
  days: Bucket[];
  unit: "day" | "week";
  step: "route" | "vehicles" | "quoted" | "transfer";
  label: string;
  color: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [index, setIndex] = useState<number | null>(null);
  const height = 130;
  const y = (v: number) => PAD.top + (1 - v) * (height - PAD.top - PAD.bottom);
  const { center } = xs(days.length, width);
  const points = days.map((b, i) =>
    b.calls ? { x: center(i), y: y(b[step] / b.calls), i } : null,
  );
  // Days without calls break the line (no rate to draw), they don't drop it to zero.
  const segments: { x: number; y: number; i: number }[][] = [];
  for (const p of points) {
    if (!p) segments.push([]);
    else (segments.at(-1) ?? segments[segments.push([]) - 1]).push(p);
  }
  const d = index != null ? days[index] : null;
  const total = days.reduce((s, b) => s + b.calls, 0);
  const hits = days.reduce((s, b) => s + b[step], 0);
  return (
    <div ref={ref} className="relative">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink">{label}</span>
        <span className="text-muted">
          <span className="font-semibold text-ink">
            {pct(total ? hits / total : null)}
          </span>{" "}
          overall
        </span>
      </div>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`${label}, share of calls per ${unit}`}
        >
          {[0, 0.5, 1].map((v) => (
            <g key={v}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(v)}
                y2={y(v)}
                className="stroke-[var(--viz-grid)]"
              />
              <text
                x={PAD.left - 6}
                y={y(v) + 4}
                textAnchor="end"
                className="fill-[var(--muted)] text-[11px]"
              >
                {v * 100}%
              </text>
            </g>
          ))}
          {segments.map((seg, k) =>
            seg.length > 1 ? (
              <polyline
                key={k}
                points={seg.map((p) => `${p.x},${p.y}`).join(" ")}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ) : null,
          )}
          {points.map((p) =>
            p ? (
              <circle
                key={p.i}
                cx={p.x}
                cy={p.y}
                r={index === p.i ? 5 : 3.5}
                fill={color}
                stroke="var(--surface)"
                strokeWidth={2}
              />
            ) : null,
          )}
          <XAxis days={days} unit={unit} width={width} height={height} />
          <Hover
            days={days}
            width={width}
            height={height}
            index={index}
            onIndex={setIndex}
          />
        </svg>
      )}
      {d && index != null && (
        <Tip x={center(index)} width={width}>
          <div className="mb-1 text-ink">{dayLabel(d.start, unit)}</div>
          {d.calls ? (
            <div>
              <span className="font-semibold text-ink">
                {pct(d[step] / d.calls)}
              </span>{" "}
              ({d[step]} of {d.calls} calls)
            </div>
          ) : (
            <div>No calls</div>
          )}
        </Tip>
      )}
    </div>
  );
}

function TrendTable({ days, unit }: { days: Bucket[]; unit: "day" | "week" }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-1.5 pr-4 font-medium">
              {unit === "week" ? "Week of" : "Day"}
            </th>
            {MILESTONES.map((m) => (
              <th key={m.key} className="py-1.5 pr-4 text-right font-medium">
                {m.short}
              </th>
            ))}
            <th className="py-1.5 text-right font-medium">Mia's time</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {[...days].reverse().map((b) => (
            <tr key={b.start} className="border-t border-line">
              <td className="py-1.5 pr-4 text-ink">
                {dayLabel(b.start, "day")}
              </td>
              {MILESTONES.map((m) => (
                <td key={m.key} className="py-1.5 pr-4 text-right text-ink">
                  {m.key === "calls" ? b.calls : b[m.key]}
                </td>
              ))}
              <td className="py-1.5 text-right text-ink">
                {b.miaSeconds ? formatSpan(b.miaSeconds) : "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
