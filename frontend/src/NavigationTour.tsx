import { driver } from "driver.js";
import "driver.js/dist/driver.css";
import { useCallback, useEffect } from "react";

import type { Route } from "./lib/route";
import { TOUR_KEY, shouldStartTour } from "./lib/tour";

/** A short first-visit tour of the app (driver.js), after the intro dialog closes; the help
 * button in the header replays it. Done or skipped is remembered in this browser only. */
export function useNavigationTour(go: (route: Route) => void, introOpen: boolean) {
  const start = useCallback(() => {
    go({ view: "call" });
    // Desktop has the sidebar, a phone the tabs: point at whichever is on screen.
    const visibleNav = (view: string) =>
      Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="nav-${view}"]`)).find(
        (el) => el.getClientRects().length > 0,
      );
    const tour = driver({
      animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      showProgress: true,
      allowClose: true,
      nextBtnText: "Next",
      prevBtnText: "Back",
      doneBtnText: "Got it",
      onDestroyed: () => {
        try {
          localStorage.setItem(TOUR_KEY, "1");
        } catch {
          // optional
        }
        go({ view: "call" });
      },
      steps: [
        {
          element: "[data-tour='call-controls']",
          popover: {
            title: "Meet your voice assistant",
            description:
              "Choose Mia’s voice and start a call here. Your browser asks for the microphone; headphones work best.",
            side: "right",
            align: "start",
          },
        },
        {
          element: "[data-tour='conversation']",
          popover: {
            title: "Follow the conversation",
            description: "Read the transcript here. Show details adds Mia’s tool calls and response times.",
            side: "left",
          },
        },
        {
          element: visibleNav("calls"),
          popover: {
            title: "Explore past calls",
            description:
              "Open Past calls, then select a call to see its conversation, shipping quote, and caller feedback.",
            side: "bottom",
          },
        },
        {
          element: visibleNav("stats"),
          popover: {
            title: "See the bigger picture",
            description: "Stats brings together call totals, quotes, and transfers to a representative.",
            side: "bottom",
          },
        },
        {
          element: "[data-tour='help']",
          popover: {
            title: "A little help, anytime",
            description: "Replay this tour here whenever you need a refresher. You’re ready to talk to Mia.",
            side: "bottom",
            align: "end",
          },
        },
      ],
    });
    window.requestAnimationFrame(() => tour.drive());
    return tour;
  }, [go]);

  useEffect(() => {
    let seen: string | null = null;
    try {
      seen = localStorage.getItem(TOUR_KEY);
    } catch {
      // optional
    }
    if (!shouldStartTour(introOpen, seen)) return;
    const timer = window.setTimeout(start, 400);
    return () => window.clearTimeout(timer);
  }, [introOpen, start]);
  return start;
}
