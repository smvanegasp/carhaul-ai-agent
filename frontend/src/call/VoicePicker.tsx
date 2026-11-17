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
  // Two columns (Belinda, 2026-11-17): each chip has the voice's picture, its name and its
  // provider underneath, so six voices fit in three short rows.
  return (
    <div className="flex w-full flex-col items-center gap-2 text-center">
      <span className="eyebrow mia-voice-muted">Choose a voice</span>
      <div role="group" aria-label="Mia's voice" className="grid w-full grid-cols-2 gap-1.5">
        {options.map((o) => {
          const [provider, name] = o.label.split("·").map((part) => part.trim());
          return (
            <Button
              variant="ghost"
              key={o.key}
              type="button"
              aria-pressed={o.key === selected}
              aria-label={o.label}
              disabled={disabled}
              onClick={() => onChoose(o.key)}
              className="mia-voice-chip flex h-auto min-w-0 items-center justify-start gap-2 rounded-lg py-1 pr-2 pl-1 text-left transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            >
              <img
                src={voiceAvatar(o.label)}
                alt=""
                width={24}
                height={24}
                loading="lazy"
                className="size-6 shrink-0 rounded-full object-cover"
              />
              <span className="flex min-w-0 flex-col leading-tight">
                <span className="truncate text-xs font-semibold">{name ?? o.label}</span>
                {name && (
                  <span className="truncate font-mono text-[9px] tracking-wider uppercase opacity-70">
                    {provider}
                  </span>
                )}
              </span>
            </Button>
          );
        })}
      </div>
      {description && <span className="text-xs leading-snug mia-voice-muted">{description}</span>}
    </div>
  );
}
