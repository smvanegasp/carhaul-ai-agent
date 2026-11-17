import { useCallback, useEffect, useState } from "react";

/**
 * The page's views, in the URL hash so a past call can be linked to: `#/` (or no hash) the
 * landing page, `#/call` the call, `#/calls` the past calls, `#/calls/<room>` one of them,
 * `#/stats` the stats. The hash, not the path, because CloudFront serves the bucket as is
 * (no fallback to index.html for other paths).
 */
export type Route =
  | { view: "home" }
  | { view: "call" }
  | { view: "calls"; room: string | null }
  | { view: "stats" };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "call") return { view: "call" };
  if (parts[0] === "calls") return { view: "calls", room: parts[1] ?? null };
  if (parts[0] === "stats") return { view: "stats" };
  return { view: "home" };
}

export function routeHash(route: Route): string {
  if (route.view === "home") return "#/";
  if (route.view === "call") return "#/call";
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
  const go = useCallback((r: Route) => {
    window.location.hash = routeHash(r);
  }, []);
  return [route, go];
}
