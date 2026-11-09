import { useEffect, useRef } from "react";

import {
  formatMs,
  LATENCY_PARTS,
  toPanel,
  type DroppedEvent,
  type EndEvent,
  type MiaEvent,
  type Panel,
  type ToolEvent,
  type TurnEvent,
} from "../lib/events";

const STAGE_LABEL: Record<string, string> = {
  greeting: "Greeting",
  route: "Route",
  vehicles: "Vehicles",
  confirm: "Confirming",
  quoted: "Quoted",
  transfer: "Transfer to Sergio",
};

const END_LABEL: Record<string, string> = {
  mia: "Mia ended the call",
  caller: "Caller hung up",
  time_limit: "Time limit reached",
};

/** What Mia is doing under the hood: pipeline, latency, what's on file, every tool call. */
export function LivePanel({ events, live }: { events: MiaEvent[]; live: boolean }) {
  const panel = toPanel(events);
  return (
    <section
      aria-label="Live panel"
      className="flex min-w-0 flex-col gap-4 rounded-2xl border border-stone-200 bg-stone-50 p-4 shadow-sm"
    >
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">Under the hood</h2>
        {live && !panel.ended && (
          <span className="flex items-center gap-1 text-xs text-emerald-700">
            <span className="size-2 animate-pulse rounded-full bg-emerald-500" /> live
          </span>
        )}
        {panel.config && (
          <ul className="flex w-full flex-wrap gap-1.5 text-xs text-stone-600">
            {[panel.config.stt, panel.config.llm, panel.config.tts, panel.config.turn_detector]
              .filter(Boolean)
              .map((part) => (
                <li key={part} className="rounded-full bg-white px-2 py-0.5 ring-1 ring-stone-200">
                  {part}
                </li>
              ))}
          </ul>
        )}
      </header>

      {events.length === 0 ? (
        <p className="text-sm text-stone-500">
          {live ? "Waiting for Mia…" : "Call Mia to see her pipeline work in real time."}
        </p>
      ) : (
        <>
          <Stats panel={panel} />
          <Latency panel={panel} />
          <OnFileCard panel={panel} />
          <Timeline panel={panel} />
        </>
      )}
    </section>
  );
}

function Stats({ panel }: { panel: Panel }) {
  const items = [
    { label: "Stage", value: STAGE_LABEL[panel.stage] ?? panel.stage },
    {
      label: "Tool calls",
      value: panel.toolErrors
        ? `${panel.toolCalls} (${panel.toolErrors} failed)`
        : String(panel.toolCalls),
    },
    { label: "Guardrail drops", value: String(panel.dropped) },
    {
      label: "Quote",
      value: panel.quoteTotal != null ? `$${panel.quoteTotal.toLocaleString()}` : "–",
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((i) => (
        <div key={i.label} className="rounded-xl bg-white p-2 ring-1 ring-stone-200">
          <dt className="text-xs text-stone-500">{i.label}</dt>
          <dd className="font-medium tabular-nums">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Latency({ panel }: { panel: Panel }) {
  // Bars share one scale so the parts compare at a glance.
  const max = Math.max(
    1000,
    ...LATENCY_PARTS.map((p) => panel.latency[p.key].median ?? 0),
    ...LATENCY_PARTS.map((p) => panel.latency[p.key].last ?? 0),
  );
  return (
    <div className="rounded-xl bg-white p-3 ring-1 ring-stone-200">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Latency per turn</h3>
        <span className="text-xs text-stone-500">median · last</span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {LATENCY_PARTS.map((p) => {
          const { median, last } = panel.latency[p.key];
          const total = p.key === "e2e";
          return (
            <li
              key={p.key}
              className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-2 text-xs sm:grid-cols-[9rem_1fr_auto]"
            >
              <span className={total ? "font-semibold" : "text-stone-600"}>{p.label}</span>
              <span className="h-2 overflow-hidden rounded-full bg-stone-100">
                <span
                  className={`block h-full rounded-full ${total ? "bg-emerald-500" : "bg-sky-400"}`}
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

function OnFileCard({ panel }: { panel: Panel }) {
  const f = panel.onFile;
  return (
    <div className="rounded-xl bg-white p-3 text-sm ring-1 ring-stone-200">
      <h3 className="mb-1 text-sm font-semibold">On file</h3>
      {!f ? (
        <p className="text-stone-500">Nothing saved yet.</p>
      ) : (
        <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-0.5">
          <dt className="text-stone-500">From</dt>
          <dd>{f.origin ?? "–"}</dd>
          <dt className="text-stone-500">To</dt>
          <dd>{f.destination ?? "–"}</dd>
          <dt className="text-stone-500">Vehicles</dt>
          <dd>
            {f.vehicles.length === 0
              ? "–"
              : f.vehicles.map((v) => (
                  <span key={v.quote_id} className="block">
                    <span className="font-mono text-xs text-stone-400">{v.quote_id}</span>{" "}
                    {v.vehicle}
                    {v.estimate_by_type && " (estimate by type)"}
                    {v.drivable === false && " (doesn't run)"}
                  </span>
                ))}
          </dd>
          {f.missing.length > 0 && (
            <>
              <dt className="text-stone-500">Missing</dt>
              <dd className="text-amber-700">{f.missing.join(", ")}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

function Timeline({ panel }: { panel: Panel }) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [panel.timeline.length]);
  return (
    <div className="rounded-xl bg-white p-3 ring-1 ring-stone-200">
      <h3 className="mb-2 text-sm font-semibold">Timeline</h3>
      <ol className="flex max-h-[50dvh] flex-col gap-2 overflow-y-auto pr-1 text-sm">
        {panel.timeline.map((e) => (
          <li key={e.seq} className="flex gap-2">
            <span className="w-10 shrink-0 pt-0.5 text-right font-mono text-xs text-stone-400 tabular-nums">
              {e.t.toFixed(1)}s
            </span>
            <div className="min-w-0 flex-1">
              {e.type === "turn" && <TurnRow e={e} />}
              {e.type === "tool" && <ToolRow e={e} />}
              {e.type === "dropped" && <DroppedRow e={e} />}
              {e.type === "end" && <EndRow e={e} />}
            </div>
          </li>
        ))}
        <li ref={end} aria-hidden />
      </ol>
    </div>
  );
}

const KIND_NOTE: Record<string, string> = {
  greeting: "greeting (from code)",
  filler: "filler line (from code)",
  time_limit: "time limit (from code)",
};

function TurnRow({ e }: { e: TurnEvent }) {
  const m = e.metrics;
  const chips =
    e.role === "caller"
      ? [
          ["end of turn", m.end_of_turn],
          ["STT", m.stt],
        ]
      : [
          ["total", m.e2e],
          ["LLM", m.llm_ttft],
          ["voice", m.tts_ttfb],
        ];
  return (
    <div>
      <p>
        <span
          className={`font-medium ${e.role === "caller" ? "text-sky-800" : "text-emerald-800"}`}
        >
          {e.role === "caller" ? "You" : "Mia"}:
        </span>{" "}
        {e.text}
      </p>
      <p className="mt-0.5 flex flex-wrap gap-1 text-xs text-stone-500">
        {KIND_NOTE[e.kind] && <span className="italic">{KIND_NOTE[e.kind]}</span>}
        {e.interrupted && <span className="text-amber-700">interrupted</span>}
        {chips
          .filter(([, v]) => typeof v === "number")
          .map(([label, v]) => (
            <span key={label as string} className="rounded bg-stone-100 px-1.5 font-mono">
              {label} {formatMs(v as number)}
            </span>
          ))}
      </p>
    </div>
  );
}

function ToolRow({ e }: { e: ToolEvent }) {
  return (
    <details className="min-w-0 rounded-lg border border-stone-200 bg-stone-50">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-2 py-1">
        <span className="font-mono text-xs font-semibold">{e.name}()</span>
        <span
          className={`rounded px-1.5 text-xs ${
            e.ok ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
          }`}
        >
          {e.ok ? "ok" : "error"}
        </span>
        <span className="font-mono text-xs text-stone-500">{formatMs(e.ms)}</span>
      </summary>
      <div className="grid min-w-0 gap-2 px-2 pb-2">
        <Json label="Arguments" value={e.args} />
        <Json label="Result (what the LLM got back)" value={e.result} />
      </div>
    </details>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="text-xs text-stone-500">{label}</p>
      <pre className="max-h-64 overflow-auto rounded bg-stone-900 p-2 text-xs whitespace-pre-wrap text-stone-100 [overflow-wrap:anywhere]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function DroppedRow({ e }: { e: DroppedEvent }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900">
      <span className="font-semibold">Guardrail dropped</span>{" "}
      <span className="font-mono">
        {e.tool}({e.args})
      </span>
      : {e.why}
    </div>
  );
}

function EndRow({ e }: { e: EndEvent }) {
  return (
    <p className="text-xs font-medium text-stone-500">
      {END_LABEL[e.end_reason ?? ""] ?? "Call ended"}
    </p>
  );
}
