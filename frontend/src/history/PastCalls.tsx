import { Button } from "../ui/button";
import { ChevronRight, MessageSquare } from "lucide-react";
import { useEffect, useState } from "react";

import { CallId } from "../call/CallId";
import { Conversation } from "../call/Conversation";
import { ErrorBoundary } from "../call/ErrorBoundary";
import { Insights } from "../call/Insights";
import {
  CallError,
  fetchCall,
  fetchCalls,
  type CallRecord,
  type CallSummary,
} from "../lib/api";
import { buildConversation } from "../lib/conversation";
import { groupByMonth, monthKey } from "../lib/months";
import type { MiaEvent, TurnEvent } from "../lib/events";
import {
  formatDuration,
  formatUsd,
  formatWhen,
  outcomeLabel,
} from "../lib/format";

type Load<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; data: T };

function message(err: unknown): string {
  return err instanceof CallError
    ? err.message
    : "Something went wrong loading calls.";
}

/**
 * Past calls: the latest calls (GET /api/calls) and, for the one picked, the same conversation
 * view and stats as a live call, rebuilt from the record the worker saved. On desktop the list
 * and the call sit side by side and each scrolls on its own; on a phone it's the list, then
 * the call with a way back.
 */
export function PastCalls({
  room,
  onOpen,
  active,
}: {
  room: string | null;
  onOpen: (room: string | null) => void;
  /** Reload the list whenever the view is shown (a call may have just ended). */
  active: boolean;
}) {
  const [list, setList] = useState<Load<CallSummary[]>>({ kind: "loading" });
  // Scripted test calls (smoke-*) are never shown, like in the stats.
  const shown: Load<CallSummary[]> =
    list.kind === "ok"
      ? {
          kind: "ok",
          data: list.data.filter((c) => !c.room.startsWith("smoke-")),
        }
      : list;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    fetchCalls()
      .then((data) => !cancelled && setList({ kind: "ok", data }))
      .catch(
        (err) =>
          !cancelled && setList({ kind: "error", message: message(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [active]);

  return (
    <div className="flex flex-col gap-4 lg:grid lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
      <section
        aria-label="Past calls"
        className={`flex flex-col rounded-2xl border border-line bg-surface lg:min-h-0 ${room ? "hidden lg:flex" : ""}`}
      >
        <header className="border-b border-line px-4 py-3">
          <h2 className="font-semibold">Past calls</h2>
          <p className="text-xs text-muted">
            The latest 100 by month, newest first.
          </p>
        </header>
        <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
          <CallList list={shown} selected={room} onOpen={onOpen} />
        </div>
      </section>

      <div
        className={`flex flex-col lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain ${room ? "" : "hidden lg:flex"}`}
      >
        {room ? (
          <ErrorBoundary
            key={room}
            fallback={<Note>This call hit a display error.</Note>}
          >
            <CallDetail room={room} onBack={() => onOpen(null)} />
          </ErrorBoundary>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 py-20">
            <MessageSquare className="size-8 text-muted" />
            <h2 className="text-lg font-semibold">Your call archive</h2>
            <p className="text-sm text-muted">No call selected.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function CallList({
  list,
  selected,
  onOpen,
}: {
  list: Load<CallSummary[]>;
  selected: string | null;
  onOpen: (room: string) => void;
}) {
  if (list.kind === "loading")
    return <p className="p-4 text-sm text-muted">Loading calls…</p>;
  if (list.kind === "error") {
    return (
      <p role="alert" className="p-4 text-sm text-danger">
        {list.message}
      </p>
    );
  }
  if (list.data.length === 0) {
    return (
      <p className="p-4 text-sm text-muted">
        No calls yet. Call Mia and it shows up here.
      </p>
    );
  }
  return <MonthList calls={list.data} selected={selected} onOpen={onOpen} />;
}

/**
 * The calls under one toggle per month. The newest month starts open, and so does the month
 * of the call being shown; the others start closed.
 */
function MonthList({
  calls,
  selected,
  onOpen,
}: {
  calls: CallSummary[];
  selected: string | null;
  onOpen: (room: string) => void;
}) {
  const groups = groupByMonth(calls);
  const picked = calls.find((c) => c.room === selected);
  const [open, setOpen] = useState<Set<string>>(
    () =>
      new Set(
        [groups[0]?.key, picked && monthKey(picked.started_at)].filter(
          (k): k is string => !!k,
        ),
      ),
  );
  const toggle = (key: string) =>
    setOpen((was) => {
      const next = new Set(was);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="flex flex-col p-2">
      {groups.map((g) => {
        const isOpen = open.has(g.key);
        return (
          <div key={g.key} className="flex flex-col">
            <button
              type="button"
              onClick={() => toggle(g.key)}
              aria-expanded={isOpen}
              aria-controls={`month-${g.key}`}
              className="flex items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-semibold text-ink transition hover:bg-raised/60 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            >
              <ChevronRight
                className={`size-4 text-muted transition-transform ${isOpen ? "rotate-90" : ""}`}
              />
              <span>{g.label}</span>
              <span className="ml-auto font-mono text-xs font-normal text-muted tabular-nums">
                {g.calls.length} {g.calls.length === 1 ? "call" : "calls"}
              </span>
            </button>
            {isOpen && (
              <CallRows
                id={`month-${g.key}`}
                calls={g.calls}
                selected={selected}
                onOpen={onOpen}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function CallRows({
  id,
  calls,
  selected,
  onOpen,
}: {
  id: string;
  calls: CallSummary[];
  selected: string | null;
  onOpen: (room: string) => void;
}) {
  return (
    <ul id={id} className="flex flex-col pb-2">
      {calls.map((c) => {
        const on = c.room === selected;
        return (
          <li key={c.room}>
            <Button
              variant="ghost"
              type="button"
              onClick={() => onOpen(c.room)}
              aria-current={on ? "true" : undefined}
              className={`h-auto items-stretch whitespace-normal flex w-full flex-col gap-2 rounded-xl px-3 py-4 text-left transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
                on ? "bg-ok-soft hover:bg-ok-soft" : "hover:bg-raised/60"
              }`}
            >
              <span className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-medium text-ink">
                  {formatWhen(c.started_at)}
                </span>
                <span className="font-mono text-xs text-muted tabular-nums">
                  {formatDuration(c.duration_s)}
                </span>
              </span>
              <span className="flex items-baseline justify-between gap-2 text-xs text-muted">
                <span>{outcomeLabel(c)}</span>
                {c.quote_total != null && (
                  <span className="font-medium text-ink">
                    {formatUsd(c.quote_total)}
                  </span>
                )}
              </span>
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

/** Older records may have no events (too big to keep); rebuild the turns from the transcript. */
function eventsOf(record: CallRecord): MiaEvent[] {
  if (record.events?.length) return record.events;
  const start = Date.parse(record.started_at);
  return (record.transcript ?? []).map((line, i): TurnEvent => ({
    type: "turn",
    seq: i,
    t: line.t,
    at: start + line.t * 1000,
    role: line.role,
    kind: line.kind as TurnEvent["kind"],
    text: line.text,
    metrics: {},
    speaking_s: null,
    interrupted: false,
  }));
}

function CallDetail({ room, onBack }: { room: string; onBack: () => void }) {
  const [record, setRecord] = useState<Load<CallRecord>>({ kind: "loading" });
  const [details, setDetails] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    // Right after a call the worker may still be saving it ("See this call" links here):
    // try a few more times before saying it isn't saved.
    const attempt = (left: number) =>
      fetchCall(room)
        .then((data) => !cancelled && setRecord({ kind: "ok", data }))
        .catch((err) => {
          if (cancelled) return;
          if (left > 0) timer = setTimeout(() => attempt(left - 1), 2500);
          else setRecord({ kind: "error", message: message(err) });
        });
    void attempt(4);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [room]);

  const back = (
    <Button
      variant="ghost"
      type="button"
      onClick={onBack}
      className="self-start text-sm text-brand underline-offset-2 hover:underline lg:hidden"
    >
      ← All calls
    </Button>
  );
  if (record.kind !== "ok") {
    return (
      <div className="flex flex-col gap-3">
        {back}
        {record.kind === "loading" ? (
          <Note>Loading the call…</Note>
        ) : (
          <Note>
            <span role="alert" className="text-danger">
              {record.message}
            </span>
          </Note>
        )}
      </div>
    );
  }

  const call = record.data;
  const events = eventsOf(call);
  const rating = call.feedback?.[0];
  return (
    <div className="flex flex-col gap-4 lg:min-h-0 lg:flex-1">
      {back}
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">
        <span className="font-semibold text-ink">
          {formatWhen(call.started_at)}
        </span>
        <span className="text-muted">
          {formatDuration(call.duration_s)} long
        </span>
        <span className="text-muted">{outcomeLabel(call)}</span>
        <CallId room={call.room} />
        {rating && (
          <span className="text-muted">
            Caller rated it{" "}
            <span className="font-medium text-ink">{rating.rating}/5</span>
            {rating.comment ? `: “${rating.comment}”` : ""}
          </span>
        )}
      </header>
      {/* The conversation has a set height (the rest of the screen on wide screens) and
          scrolls inside, so "Show details" never makes the panel grow. */}
      <div className="flex flex-col gap-4 xl:grid xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_320px] xl:grid-rows-[minmax(0,1fr)]">
        <div className="flex h-[70dvh] min-h-[420px] flex-col xl:h-auto xl:min-h-0">
          <Conversation
            items={buildConversation([], events)}
            live={false}
            details={details}
            onDetails={setDetails}
            onCopy={() => Promise.resolve(call)}
          />
        </div>
        <div className="xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain">
          <Insights events={events} />
        </div>
      </div>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl border border-line bg-surface p-4 text-sm text-muted">
      {children}
    </p>
  );
}
