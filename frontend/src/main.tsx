import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import { Landing } from "./landing/Landing";
import { useRoute } from "./lib/route";
import "./index.css";

// Loaded only when opened, so the landing page doesn't download LiveKit.
const App = lazy(() => import("./App").then((m) => ({ default: m.App })));

/** The landing page on the bare URL; the app (call, past calls, stats) on its hash routes.
 * The app mounts only when opened, so the landing page never wakes the worker. */
function Root() {
  const [route, go] = useRoute();
  if (route.view === "home") return <Landing />;
  return (
    <Suspense fallback={null}>
      <App route={route} go={go} />
    </Suspense>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
