/**
 * The Stats view's numbers, from GET /api/stats (one row of facts per call; backend/app/
 * stats.py). Everything is computed here so the date range and days follow the viewer's
 * time zone.
 *
 * The story it tells (Sergio, 2026-11-10): transfers are the KPI that matters (a licensed
 * representative picked up: a qualified lead); time handled by Mia is time the business got
 * back; the funnel shows where callers drop off on the way.
 */

export interface CallFacts {
  room: string;
  started_at: string;
  test: boolean;
  duration_s: number;
  mia_s: number;
  route: boolean;
  vehicles: boolean;
  quoted: boolean;
  transfer: boolean;
  e2e_p50_ms: number | null;
}

export type Range = "7d" | "30d" | "all";

export const RANGES: { key: Range; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "all", label: "All time" },
];

const DAY_MS = 86_400_000;

export function inRange(
  rows: CallFacts[],
  range: Range,
  now = Date.now(),
): CallFacts[] {
  if (range === "all") return rows;
  const days = range === "7d" ? 7 : 30;
  const since = startOfDay(now - (days - 1) * DAY_MS);
  return rows.filter((r) => Date.parse(r.started_at) >= since);
}

function startOfDay(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

const ratio = (n: number, d: number) => (d ? n / d : null);

export interface Kpis {
  calls: number;
  transfers: number;
  transferRate: number | null;
  quotes: number;
  quoteRate: number | null;
  miaSeconds: number;
  avgMiaSeconds: number | null;
  medianLatencyMs: number | null;
}

export function kpis(rows: CallFacts[]): Kpis {
  const transfers = rows.filter((r) => r.transfer).length;
  const quotes = rows.filter((r) => r.quoted).length;
  const miaSeconds = rows.reduce((s, r) => s + r.mia_s, 0);
  return {
    calls: rows.length,
    transfers,
    transferRate: ratio(transfers, rows.length),
    quotes,
    quoteRate: ratio(quotes, rows.length),
    miaSeconds,
    avgMiaSeconds: rows.length ? miaSeconds / rows.length : null,
    medianLatencyMs: median(
      rows.map((r) => r.e2e_p50_ms).filter((v): v is number => v != null),
    ),
  };
}

export type Milestone = "calls" | "route" | "vehicles" | "quoted" | "transfer";

export const MILESTONES: { key: Milestone; label: string; short: string }[] = [
  { key: "calls", label: "Called", short: "Calls" },
  { key: "route", label: "Gave both cities", short: "Cities" },
  { key: "vehicles", label: "Gave a vehicle", short: "Vehicles" },
  { key: "quoted", label: "Got a quote", short: "Quotes" },
  {
    key: "transfer",
    label: "Transferred to a representative",
    short: "Transfers",
  },
];

export interface FunnelStep {
  key: Milestone;
  label: string;
  count: number;
  /** Share of all calls. */
  ofCalls: number | null;
  /** Conversion from the step before (null for the first step). */
  ofPrev: number | null;
}

const reached = (r: CallFacts, m: Milestone) => (m === "calls" ? true : r[m]);

export function funnel(rows: CallFacts[]): FunnelStep[] {
  let prev: number | null = null;
  return MILESTONES.map(({ key, label }) => {
    const count = rows.filter((r) => reached(r, key)).length;
    const step: FunnelStep = {
      key,
      label,
      count,
      ofCalls: ratio(count, rows.length),
      ofPrev: prev === null ? null : ratio(count, prev),
    };
    prev = count;
    return step;
  });
}

export interface Bucket {
  /** Local start of the day (or week), epoch ms. */
  start: number;
  calls: number;
  route: number;
  vehicles: number;
  quoted: number;
  transfer: number;
  miaSeconds: number;
}

/**
 * Calls per day (per week once the range spans more than 45 days), with no gaps: days without
 * calls are zeros, so the trend's spacing is honest.
 */
export function buckets(
  rows: CallFacts[],
  range: Range,
  now = Date.now(),
): Bucket[] {
  if (rows.length === 0) return [];
  const times = rows.map((r) => Date.parse(r.started_at));
  const first =
    range === "all"
      ? startOfDay(Math.min(...times))
      : startOfDay(now - ((range === "7d" ? 7 : 30) - 1) * DAY_MS);
  const last = startOfDay(Math.max(now, ...times));
  const span = Math.round((last - first) / DAY_MS) + 1;
  const size = span > 45 ? 7 : 1;
  const out: Bucket[] = [];
  for (let d = 0; d < span; d += size) {
    const start = startOfDay(first + d * DAY_MS + DAY_MS / 2); // safe across DST changes
    out.push({
      start,
      calls: 0,
      route: 0,
      vehicles: 0,
      quoted: 0,
      transfer: 0,
      miaSeconds: 0,
    });
  }
  rows.forEach((r, i) => {
    // Whole days since the first bucket (rounded: a DST day is 23 or 25 hours long).
    const day = Math.round((startOfDay(times[i]) - first) / DAY_MS);
    const b =
      out[Math.min(out.length - 1, Math.max(0, Math.floor(day / size)))];
    b.calls += 1;
    b.miaSeconds += r.mia_s;
    for (const m of ["route", "vehicles", "quoted", "transfer"] as const)
      if (r[m]) b[m] += 1;
  });
  return out;
}

export function bucketSize(list: Bucket[]): "day" | "week" {
  return list.length > 1 && list[1].start - list[0].start > 2 * DAY_MS
    ? "week"
    : "day";
}

/** 4320 -> "1 h 12 min"; 95 -> "1 min 35 s". */
export function formatSpan(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return m ? `${h} h ${m} min` : `${h} h`;
  const rest = s % 60;
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

export function pct(value: number | null): string {
  return value == null ? "–" : `${Math.round(value * 100)}%`;
}

/** One or two sentences that say what the numbers mean. */
export function story(k: Kpis, steps: FunnelStep[]): string {
  if (k.calls === 0) return "No calls in this period yet.";
  const calls = `${k.calls} call${k.calls === 1 ? "" : "s"}`;
  const leads = `${k.transfers} qualified lead${k.transfers === 1 ? "" : "s"}`;
  let text =
    `Mia handled ${calls} (${formatSpan(k.miaSeconds)} a person didn't have to spend) and ` +
    `passed ${leads} to a licensed representative (${pct(k.transferRate)} of calls).`;
  // The biggest drop-off between two steps where the earlier one had callers.
  const drops = steps
    .slice(1)
    .map((s, i) => ({ from: steps[i], to: s }))
    .filter((d) => d.from.count > 0 && d.to.ofPrev != null && d.to.ofPrev < 1);
  if (drops.length) {
    const worst = drops.reduce((a, b) =>
      (b.to.ofPrev ?? 1) < (a.to.ofPrev ?? 1) ? b : a,
    );
    const lost = 1 - (worst.to.ofPrev ?? 0);
    text +=
      ` The biggest drop-off is from “${worst.from.label.toLowerCase()}” to ` +
      `“${worst.to.label.toLowerCase()}”: ${pct(lost)} of callers stop there.`;
  }
  return text;
}
