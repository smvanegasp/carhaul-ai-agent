import { useEffect, useState } from "react";

import { copyText } from "../lib/copy";

/**
 * The call's ID with a one-click copy. Testers paste it in the evaluation workbook
 * (docs/evaluation/Mia_evaluation.xlsx): with it the full record can always be read, even when
 * a long JSON doesn't fit in a spreadsheet cell. Before this it was only in the page address.
 */
export function CallId({ room }: { room: string }) {
  const [copied, setCopied] = useState<boolean | null>(null);
  useEffect(() => {
    if (copied === null) return;
    const timer = setTimeout(() => setCopied(null), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <span className="inline-flex items-center gap-1.5 text-muted">
      Call ID
      <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-ink">{room}</code>
      <button
        type="button"
        onClick={async () => setCopied(await copyText(room))}
        aria-label={`Copy call ID ${room}`}
        className="rounded-full border border-line px-2 py-0.5 text-xs transition hover:bg-raised focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
      >
        <span aria-live="polite">
          {copied === null ? "Copy" : copied ? "Copied" : "Couldn't copy"}
        </span>
      </button>
    </span>
  );
}
