import { Download, FileText } from "lucide-react";
import { useState } from "react";

import type { TranscriptLine } from "../lib/transcript";
import { transcriptFileName, transcriptText } from "../lib/transcriptDelivery";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../ui/dialog";

/**
 * After each call: offer the caller a copy of the conversation (the Lovable redesign). It
 * asked to email it, but there's no email sender, so it offers what works: a download made in
 * the browser. Nothing is sent or saved.
 */
export function TranscriptPrompt({ room, lines }: { room: string; lines: TranscriptLine[] }) {
  const [open, setOpen] = useState(lines.length > 0);

  const download = () => {
    const url = URL.createObjectURL(
      new Blob([transcriptText(lines)], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = transcriptFileName(room);
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setOpen(false);
  };

  if (lines.length === 0) return null;
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} className="self-start">
        <FileText className="size-4" /> Call transcript
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(440px,calc(100%-2rem))] rounded-lg border-line bg-surface text-ink">
          <FileText className="size-6 text-brand" />
          <DialogTitle className="pr-6 tracking-normal">Your call with Mia has ended</DialogTitle>
          <DialogDescription className="text-muted">
            Would you like a copy of the conversation? It downloads as a text file; nothing is
            sent anywhere.
          </DialogDescription>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>
              No, thanks
            </Button>
            <Button onClick={download} className="bg-brand text-brand-ink hover:bg-brand-hover">
              <Download className="size-4" /> Download transcript
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
