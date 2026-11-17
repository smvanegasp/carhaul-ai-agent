export const TOUR_KEY = "mia.navigation-tour.seen";

export function shouldStartTour(introOpen: boolean, seen: string | null): boolean {
  return !introOpen && seen !== "1";
}