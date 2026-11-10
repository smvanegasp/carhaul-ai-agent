import { useEffect, useState } from "react";

/**
 * The page's views, in the URL hash so a past call can be linked to:
 * `#/` the call, `#/calls` the past calls, `#/calls/<room>` one of them, `#/stats` the stats.
 */
export type Route =
  { view: "call" } | { view: "calls"; room: string | null } | { view: "stats" };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "calls") return { view: "calls", room: parts[1] ?? null };
  if (parts[0] === "stats") return { view: "stats" };
  return { view: "call" };
}

export function routeHash(route: Route): string {
  if (route.view === "call") return "#/";
  if (route.view === "stats") return "#/stats";
  return route.room ? `#/calls/${route.room}` : "#/calls";
}

export function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [route, (r) => (window.location.hash = routeHash(r))];
}
