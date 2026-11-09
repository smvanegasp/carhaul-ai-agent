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
    return (
      <p className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
        Thanks for the feedback!
      </p>
    );
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
      className="flex w-full flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-4 shadow-sm"
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-medium">How did the call go?</legend>
        <div className="flex flex-wrap gap-2">
          {RATINGS.map((r) => (
            <label
              key={r.value}
              className={`cursor-pointer rounded-full border px-4 py-1.5 text-sm has-focus-visible:ring-2 has-focus-visible:ring-sky-400 ${
                rating === r.value
                  ? "border-emerald-600 bg-emerald-600 text-white"
                  : "border-stone-300 hover:bg-stone-100"
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
          What worked, what didn't? <span className="text-stone-500">(optional)</span>
        </span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={2000}
          rows={3}
          className="rounded-lg border border-stone-300 p-2"
          placeholder="e.g. she talked over me when I paused, or got my car wrong"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span>
          Persona card <span className="text-stone-500">(testers only, optional)</span>
        </span>
        <input
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          maxLength={100}
          className="rounded-lg border border-stone-300 p-2"
        />
      </label>
      {status.kind === "error" && (
        <p role="alert" className="text-sm text-red-700">
          {status.message}
        </p>
      )}
      <button
        type="submit"
        disabled={rating == null || status.kind === "sending"}
        className="self-start rounded-full bg-stone-900 px-5 py-2 font-medium text-white hover:bg-stone-700 disabled:opacity-50"
      >
        {status.kind === "sending" ? "Sending…" : "Send feedback"}
      </button>
    </form>
  );
}
