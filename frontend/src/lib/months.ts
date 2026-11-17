/** Calls grouped by the month they started in, in the viewer's time zone, newest first. */
export interface MonthGroup<T> {
  /** "2026-11": stable, for open/closed state. */
  key: string;
  /** "November 2026". */
  label: string;
  calls: T[];
}

export function monthKey(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "unknown";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(key: string, iso: string): string {
  if (key === "unknown") return "Unknown date";
  return new Date(iso).toLocaleString("en-US", {
    month: "long",
    year: "numeric",
  });
}

/** Keeps the calls' order (the API sends them newest first), so the months come newest first too. */
export function groupByMonth<T extends { started_at: string }>(
  calls: T[],
): MonthGroup<T>[] {
  const groups = new Map<string, MonthGroup<T>>();
  for (const call of calls) {
    const key = monthKey(call.started_at);
    let group = groups.get(key);
    if (!group) {
      group = { key, label: monthLabel(key, call.started_at), calls: [] };
      groups.set(key, group);
    }
    group.calls.push(call);
  }
  return [...groups.values()];
}
