import { useEffect, useMemo, useState, type ReactNode } from "react";

import { CallError } from "../lib/api";
import {
  dispositions,
  formatSpan,
  funnel,
  kpis,
  pct,
  story,
  type CallFacts,
  type DispositionCount,
  type FunnelStep,
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
 * Stats: what Mia's calls add up to, all time (calls come in bursts, so date ranges and trends
 * would mostly be empty). It leads with the KPI that matters (transfers: qualified leads),
 * then the time Mia handled, how calls ended (the dispositions) and the funnel from call to
 * transfer.
 */
export function StatsPage({ active }: { active: boolean }) {
  const [includeTests, setIncludeTests] = useState(false);
  const [load, setLoad] = useState<Load>({ kind: "loading" });

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
    const k = kpis(load.rows);
    const steps = funnel(load.rows);
    return {
      k,
      steps,
      outcomes: dispositions(load.rows),
      text: story(k, steps),
    };
  }, [load]);

  return (
    <div className="flex flex-col gap-4 pb-2 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">All calls since Mia went live.</p>
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
        <div className="flex flex-col gap-4">
          <p className="max-w-4xl text-base leading-relaxed text-ink">
            {view.text}
          </p>
          <KpiRow k={view.k} />
          <div className="grid gap-4 xl:grid-cols-2">
            <Section
              title="How calls ended"
              note="Voice dispositions. Transfers are qualified leads."
            >
              <Dispositions outcomes={view.outcomes} />
            </Section>
            <Section
              title="Funnel"
              note="Each step's share of calls, and conversion from the step before."
            >
              <Funnel steps={view.steps} />
            </Section>
          </div>
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

// --- dispositions -------------------------------------------------------------------------

/**
 * Ranked bars, one per disposition, in two groups. Emphasis rather than six colors: the
 * qualified leads (transfers) in the accent blue, the rest in a neutral gray.
 */
function Dispositions({ outcomes }: { outcomes: DispositionCount[] }) {
  const groups = [
    { title: "Qualified leads", rows: outcomes.filter((o) => o.lead) },
    { title: "Not qualified", rows: outcomes.filter((o) => !o.lead) },
  ];
  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <div key={g.title} className="flex flex-col gap-2">
          <h3 className="text-xs font-medium tracking-wide text-muted uppercase">
            {g.title} ·{" "}
            <span className="text-ink">
              {g.rows.reduce((n, r) => n + r.count, 0)}
            </span>
          </h3>
          <ul className="flex flex-col gap-2">
            {g.rows.map((o) => (
              <li
                key={o.key}
                title={o.help}
                className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,11rem)_1fr_6rem]"
              >
                <span className="flex flex-col">
                  <span className="text-sm text-ink">{o.label}</span>
                  <span className="text-xs text-muted">{o.help}</span>
                </span>
                <span className="order-last col-span-2 h-3 sm:order-none sm:col-span-1">
                  <span
                    className="block h-3 rounded-r-[4px] transition-[width] duration-500"
                    style={{
                      width: `${Math.max((o.share ?? 0) * 100, o.count ? 1.5 : 0)}%`,
                      background: o.lead ? "var(--viz-4)" : "var(--muted)",
                      opacity: o.lead ? 1 : 0.55,
                    }}
                  />
                </span>
                <span className="text-right text-sm whitespace-nowrap text-ink">
                  <span className="font-semibold">{o.count}</span>{" "}
                  <span className="text-muted">· {pct(o.share)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
