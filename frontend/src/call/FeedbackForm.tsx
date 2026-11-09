import { useState, type FormEvent } from "react";

import { CallError, sendFeedback } from "../lib/api";

const RATINGS = [
  { value: 1, label: "Bad" },
  { value: 2, label: "Poor" },
  { value: 3, label: "Okay" },
  { value: 4, label: "Good" },
  { value: 5, label: "Great" },
];

/** Feedback on the call that just ended (saved with the call record). */
export function FeedbackForm({ room }: { room: string }) {
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [persona, setPersona] = useState("");
  const [status, setStatus] = useState<
    | { kind: "editing" }
    | { kind: "sending" }
    | { kind: "sent" }
    | { kind: "error"; message: string }
  >({ kind: "editing" });

  if (status.kind === "sent") {
    return <p className="rounded-2xl bg-ok-soft p-4 text-ok">Thanks for the feedback!</p>;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (rating == null) return;
    setStatus({ kind: "sending" });
    try {
      await sendFeedback(room, { rating, comment, persona });
      setStatus({ kind: "sent" });
    } catch (err) {
      const message = err instanceof CallError ? err.message : "Couldn't send your feedback.";
      setStatus({ kind: "error", message });
    }
  };

  return (
    <form
      onSubmit={submit}
      className="mt-2 flex w-full flex-col gap-3 rounded-2xl border border-line bg-raised p-4"
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-medium">How did the call go?</legend>
        <div className="flex flex-wrap gap-2">
          {RATINGS.map((r) => (
            <label
              key={r.value}
              className={`cursor-pointer rounded-full border px-4 py-1.5 text-sm has-focus-visible:ring-2 has-focus-visible:ring-accent ${
                rating === r.value
                  ? "border-brand bg-brand text-brand-ink"
                  : "border-line bg-surface hover:bg-raised"
              }`}
            >
              <input
                type="radio"
                name="rating"
                value={r.value}
                checked={rating === r.value}
                onChange={() => setRating(r.value)}
                className="sr-only"
              />
              {r.label}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex flex-col gap-1 text-sm">
        <span>
          What worked, what didn't? <span className="text-muted">(optional)</span>
        </span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={2000}
          rows={3}
          className="rounded-lg border border-line bg-surface p-2 text-ink placeholder:text-muted"
          placeholder="e.g. she talked over me when I paused, or got my car wrong"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span>
          Persona card <span className="text-muted">(testers only, optional)</span>
        </span>
        <input
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          maxLength={100}
          className="rounded-lg border border-line bg-surface p-2 text-ink placeholder:text-muted"
        />
      </label>
      {status.kind === "error" && (
        <p role="alert" className="text-sm text-danger">
          {status.message}
        </p>
      )}
      <button
        type="submit"
        disabled={rating == null || status.kind === "sending"}
        className="self-start rounded-full bg-brand px-5 py-2 font-medium text-brand-ink hover:bg-brand-hover disabled:opacity-50"
      >
        {status.kind === "sending" ? "Sending…" : "Send feedback"}
      </button>
    </form>
  );
}
