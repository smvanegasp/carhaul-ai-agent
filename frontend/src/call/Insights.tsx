import {
  formatMs,
  LATENCY_PARTS,
  toPanel,
  type MiaEvent,
  type Panel,
} from "../lib/events";

const STAGE_LABEL: Record<string, string> = {
  greeting: "Greeting",
  route: "Route",
  vehicles: "Vehicles",
  confirm: "Confirming",
  quoted: "Quoted",
  transfer: "Transfer to a representative",
};

/**
 * The call at a glance: pipeline, stage, tool calls, latency and what's on file. On desktop the
 * card fills its column and only its contents scroll, so a few extra pixels never leave a
 * scrollbar over empty space (Sergio, 2026-11-09: the panel scrolled into nothing after a call).
 */
export function Insights({ events }: { events: MiaEvent[] }) {
  const panel = toPanel(events);
  return (
    <section
      aria-label="Under the hood"
      className="flex flex-col overflow-hidden rounded-2xl border border-line bg-surface lg:min-h-0 lg:flex-1"
    >
      <div className="flex flex-col gap-3 p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
        <header className="flex flex-col gap-2">
          <h2 className="font-semibold">Under the hood</h2>
          {panel.config ? (
            <ul className="flex flex-wrap gap-1.5 text-xs text-muted">
              {[
                panel.config.stt,
                panel.config.llm,
                panel.config.tts,
                panel.config.turn_detector,
              ]
                .filter(Boolean)
                .map((part) => (
                  <li key={part} className="rounded-full bg-raised px-2 py-0.5">
                    {part}
                  </li>
                ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">
              Stats appear here once the call starts.
            </p>
          )}
        </header>
        <Stats panel={panel} />
        <Latency panel={panel} />
        <OnFile panel={panel} />
      </div>
    </section>
  );
}

function Stats({ panel }: { panel: Panel }) {
  const items = [
    { label: "Stage", value: STAGE_LABEL[panel.stage] ?? panel.stage },
    {
      label: "Quote",
      value:
        panel.quoteTotal != null
          ? `$${panel.quoteTotal.toLocaleString()}`
          : "–",
    },
    {
      label: "Tool calls",
      value: panel.toolErrors
        ? `${panel.toolCalls} (${panel.toolErrors} failed)`
        : String(panel.toolCalls),
    },
    { label: "Guardrail drops", value: String(panel.dropped) },
  ];
  return (
    <dl className="grid grid-cols-2 gap-2">
      {items.map((i) => (
        <div key={i.label} className="rounded-xl bg-raised px-3 py-2">
          <dt className="text-xs text-muted">{i.label}</dt>
          <dd className="font-medium tabular-nums">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Latency({ panel }: { panel: Panel }) {
  const max = Math.max(
    1000,
    ...LATENCY_PARTS.map((p) => panel.latency[p.key].median ?? 0),
    ...LATENCY_PARTS.map((p) => panel.latency[p.key].last ?? 0),
  );
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Latency per turn</h3>
        <span className="text-xs text-muted">median · last</span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {LATENCY_PARTS.map((p) => {
          const { median, last } = panel.latency[p.key];
          const total = p.key === "e2e";
          return (
            <li
              key={p.key}
              className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-2 text-xs"
            >
              <span className={total ? "font-semibold" : "text-muted"}>
                {p.label}
              </span>
              <span className="h-1.5 overflow-hidden rounded-full bg-raised">
                <span
                  className={`block h-full rounded-full ${total ? "bg-brand" : "bg-accent"}`}
                  style={{ width: `${((median ?? 0) / max) * 100}%` }}
                />
              </span>
              <span className="text-right font-mono tabular-nums">
                {formatMs(median)} · {formatMs(last)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function OnFile({ panel }: { panel: Panel }) {
  const f = panel.onFile;
  return (
    <div className="text-sm">
      <h3 className="mb-1 font-semibold">On file</h3>
      {!f ? (
        <p className="text-muted">Nothing saved yet.</p>
      ) : (
        <dl className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-0.5">
          <dt className="text-muted">From</dt>
          <dd>{f.origin ?? "–"}</dd>
          <dt className="text-muted">To</dt>
          <dd>{f.destination ?? "–"}</dd>
          <dt className="text-muted">Vehicles</dt>
          <dd>
            {f.vehicles.length === 0
              ? "–"
              : f.vehicles.map((v) => (
                  <span key={v.quote_id} className="block">
                    {v.vehicle}
                    {v.estimate_by_type && " (estimate by type)"}
                    {v.drivable === false && " (doesn't run)"}
                  </span>
                ))}
          </dd>
          {f.missing.length > 0 && (
            <>
              <dt className="text-muted">Missing</dt>
              <dd className="text-warn">{f.missing.join(", ")}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}
