import { useEffect, useState } from "react";

import { fetchVoices, type VoiceOption } from "../lib/api";

const STORAGE_KEY = "mia.voice";

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // private mode or blocked storage: no memory, that's fine
  }
}

/** The caller's voice choice for Mia, remembered in this browser. */
export function useVoiceChoice() {
  const [options, setOptions] = useState<VoiceOption[]>([]);
  const [voice, setVoice] = useState<string | null>(remembered);

  useEffect(() => {
    void fetchVoices().then(setOptions);
  }, []);

  const choose = (key: string) => {
    setVoice(key);
    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch {
      // not remembered; the choice still applies to this visit
    }
  };

  const known = options.some((o) => o.key === voice);
  const selected = known ? voice : (options.find((o) => o.default)?.key ?? null);
  return { options, selected, choose };
}

export function VoicePicker({
  options,
  selected,
  onChoose,
  disabled,
}: {
  options: VoiceOption[];
  selected: string | null;
  onChoose: (key: string) => void;
  disabled?: boolean;
}) {
  if (options.length === 0) return null;
  return (
    <label className="flex w-full flex-col gap-1 text-sm">
      <span className="text-muted">Mia's voice</span>
      <select
        value={selected ?? ""}
        disabled={disabled}
        onChange={(e) => onChoose(e.target.value)}
        className="rounded-lg border border-line bg-surface px-3 py-2 text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none disabled:opacity-60"
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
