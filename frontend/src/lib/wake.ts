/**
 * How far along Mia's wake-up looks, for the call page's progress bar.
 *
 * A cold start takes about a minute on AWS (64 s measured in stage 4): roughly half getting a
 * Fargate machine and pulling the image (`server`), half loading the models and registering
 * with LiveKit (`loading`). The bar moves with time but respects the step the API reports, and
 * never reaches 100% until Mia is actually ready.
 */
export type WakeStep = "server" | "loading" | null;

export const EXPECTED_WAKE_MS = 65_000;

export function wakeProgress(
  elapsedMs: number,
  step: WakeStep,
): { percent: number; label: string } {
  let percent = Math.min(95, (Math.max(0, elapsedMs) / EXPECTED_WAKE_MS) * 95);
  if (step === "server") percent = Math.min(percent, 50);
  if (step === "loading") percent = Math.max(percent, 55);
  const loading = step === "loading" || (step === null && percent >= 50);
  return {
    percent: Math.round(percent),
    label: loading
      ? "Loading Mia's voice and models"
      : "Getting a server ready",
  };
}
