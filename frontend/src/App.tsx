import { useState, type ReactNode } from "react";

import { CallPage, MAX_CALL_SECONDS } from "./call/CallPage";
import { ThemeToggle } from "./call/ThemeToggle";
import { PastCalls } from "./history/PastCalls";
import { useRoute, type Route } from "./lib/route";

const COLLAPSED_KEY = "mia.sidebar.collapsed";

function rememberedCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

const VIEWS: { route: Route; label: string; icon: ReactNode }[] = [
  { route: { view: "call" }, label: "Call Mia", icon: <PhoneIcon /> },
  {
    route: { view: "calls", room: null },
    label: "Past calls",
    icon: <ListIcon />,
  },
];

/**
 * The page: a sidebar to switch views (collapsible on desktop, tabs on a phone), the header,
 * and the view. The call view stays mounted while another view is shown, so looking at past
 * calls never drops a call in progress. On desktop the page fits the screen and only the
 * panels inside scroll.
 */
export function App() {
  const [route, go] = useRoute();
  const [collapsed, setCollapsed] = useState(rememberedCollapsed);

  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // not remembered; fine
    }
  };

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:flex-row lg:overflow-hidden">
      <nav
        aria-label="Views"
        className={`hidden shrink-0 flex-col gap-1 border-r border-line bg-surface p-3 transition-[width] lg:flex ${
          collapsed ? "w-16" : "w-56"
        }`}
      >
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          aria-expanded={!collapsed}
          className="mb-2 flex h-9 items-center gap-3 rounded-lg px-2.5 text-muted transition hover:bg-raised hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
        >
          <ChevronIcon flipped={collapsed} />
          {!collapsed && (
            <span className="text-xs font-medium tracking-wide uppercase">
              Menu
            </span>
          )}
        </button>
        {VIEWS.map((v) => (
          <NavItem
            key={v.label}
            item={v}
            active={route.view === v.route.view}
            collapsed={collapsed}
            onGo={() => go(v.route)}
          />
        ))}
      </nav>

      <main className="mx-auto flex w-full max-w-7xl min-w-0 flex-1 flex-col gap-4 px-4 py-5 lg:min-h-0 lg:py-6">
        <header className="flex flex-col gap-1">
          <div className="flex items-start justify-between gap-3">
            <h1 className="font-display text-3xl tracking-tight">
              Call Mia{" "}
              <span className="text-muted">· F&amp;F car shipping quotes</span>
            </h1>
            <ThemeToggle />
          </div>
          <p className="max-w-3xl text-sm text-muted">
            Mia is a voice assistant for open car-shipping quotes. Tell her
            where your car is going from and to, and its year, make and model.
            Calls last up to {MAX_CALL_SECONDS / 60} minutes.
          </p>
          <p className="max-w-3xl text-xs text-muted">
            <span className="font-semibold text-ink">Disclosure:</span> this is
            a demo. If you ask to speak with a licensed representative, Mia
            transfers your call to Sergio, the developer of this demo, on his
            personal phone.
          </p>
        </header>

        <div
          role="tablist"
          aria-label="Views"
          className="flex gap-1 rounded-full bg-raised p-1 lg:hidden"
        >
          {VIEWS.map((v) => {
            const active = route.view === v.route.view;
            return (
              <button
                key={v.label}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => go(v.route)}
                className={`flex flex-1 items-center justify-center gap-2 rounded-full px-3 py-2 text-sm font-medium transition ${
                  active ? "bg-surface text-ink shadow-sm" : "text-muted"
                }`}
              >
                {v.icon}
                {v.label}
              </button>
            );
          })}
        </div>

        <div className={route.view === "call" ? "contents" : "hidden"}>
          <CallPage />
        </div>
        <div className={route.view === "calls" ? "contents" : "hidden"}>
          <PastCalls
            active={route.view === "calls"}
            room={route.view === "calls" ? route.room : null}
            onOpen={(room) => go({ view: "calls", room })}
          />
        </div>
      </main>
    </div>
  );
}

function NavItem({
  item,
  active,
  collapsed,
  onGo,
}: {
  item: (typeof VIEWS)[number];
  active: boolean;
  collapsed: boolean;
  onGo: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onGo}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={`flex h-10 items-center gap-3 rounded-lg px-2.5 text-sm font-medium transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
        active
          ? "bg-raised text-ink"
          : "text-muted hover:bg-raised/60 hover:text-ink"
      }`}
    >
      <span className={active ? "text-brand" : ""}>{item.icon}</span>
      {!collapsed && <span>{item.label}</span>}
    </button>
  );
}

function PhoneIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
    >
      <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
    </svg>
  );
}

function ChevronIcon({ flipped }: { flipped: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={`size-5 shrink-0 transition ${flipped ? "rotate-180" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M15 6l-6 6 6 6" />
    </svg>
  );
}
