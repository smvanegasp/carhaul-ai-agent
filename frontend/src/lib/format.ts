/** Whole-dollar price as spoken in quotes, e.g. 2729 -> "$2,729". */
export function formatUsd(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(amount);
}

/** 61.5 -> "1:02". */
export function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** ISO time -> "Nov 9, 4:30 PM" in the viewer's time zone. */
export function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** How a call ended, in a few words. */
export function outcomeLabel(call: {
  stage: string;
  transfer?: string | null;
  quote_total?: number | null;
}): string {
  if (call.transfer === "connected") return "Transferred to a representative";
  if (call.transfer === "no_answer") return "Transfer not answered";
  if (call.stage === "quoted" || call.quote_total != null) return "Got a quote";
  const stages: Record<string, string> = {
    greeting: "Left at the greeting",
    route: "Left during the route",
    vehicles: "Left during the vehicles",
    confirm: "Left before the quote",
    transfer: "Asked for a representative",
  };
  return stages[call.stage] ?? call.stage;
}
