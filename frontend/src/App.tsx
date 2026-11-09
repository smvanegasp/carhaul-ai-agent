import { formatUsd } from "./lib/format";

// Placeholder until stage 3 adds the call page (LiveKit) and stage 6 the dashboard.
export function App() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-4 px-4">
      <h1 className="text-3xl font-semibold">Call Mia</h1>
      <p className="text-stone-600">
        Mia is F&amp;F's voice assistant for car-shipping quotes. Soon you'll be able to call her
        from this page and watch the call (transcript, tool calls and latency) live. Example
        quote: {formatUsd(1291)}.
      </p>
    </main>
  );
}
