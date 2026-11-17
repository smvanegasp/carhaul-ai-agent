import { useEffect, useState } from "react";
import { Button } from "../ui/button";

import { voiceAvatar } from "./voiceAvatars";
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
  const description = options.find((o) => o.key === selected)?.description;
  return (
    <div className="flex w-full flex-col items-center gap-2 text-center">
      <span className="eyebrow mia-voice-muted">Choose a voice</span>
      <div role="group" aria-label="Mia's voice" className="flex w-full flex-wrap justify-center gap-1.5">
        {options.map((o) => (
          <Button variant="ghost" key={o.key} type="button" aria-pressed={o.key === selected} disabled={disabled}
            onClick={() => onChoose(o.key)}
            className="mia-voice-chip flex h-auto items-center gap-1.5 rounded-full py-1 pr-3 pl-1 font-mono text-[11px] uppercase tracking-wider transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none">
            <img src={voiceAvatar(o.label)} alt="" width={20} height={20} loading="lazy" className="size-5 rounded-full object-cover" />
            {o.label}
          </Button>
        ))}
      </div>
      {description && <span className="text-xs leading-snug mia-voice-muted">{description}</span>}
    </div>
  );
}
