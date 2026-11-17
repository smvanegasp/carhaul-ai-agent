import { useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  AudioLines,
  ChartNoAxesCombined,
  CircleHelp,
  History,
  PanelLeftClose,
  PanelLeftOpen,
  Phone,
} from "lucide-react";

import { CallPage, MAX_CALL_SECONDS } from "./call/CallPage";
import { ThemeToggle } from "./call/ThemeToggle";
import { BELINDA, CARHAULER, Ext, REPO, SERGIO } from "./credits";
import { PastCalls } from "./history/PastCalls";
import { IntroDialog, useIntro } from "./IntroDialog";
import type { Route } from "./lib/route";
import { useNavigationTour } from "./NavigationTour";
import { StatsPage } from "./stats/StatsPage";
import { Button } from "./ui/button";

// Storage keys keep the agent's old name ("mia.*") so saved preferences still apply.
const COLLAPSED_KEY = "mia.sidebar.collapsed";

function rememberedCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

type AppView = Exclude<Route["view"], "home">;

const VIEWS: { route: Route & { view: AppView }; label: string; tab: string; icon: ReactNode }[] = [
  { route: { view: "call" }, label: "Call Mia", tab: "Call", icon: <Phone className="size-4 shrink-0" /> },
  {
    route: { view: "calls", room: null },
    label: "Past calls",
    tab: "Past calls",
    icon: <History className="size-4 shrink-0" />,
  },
  {
    route: { view: "stats" },
    label: "Stats",
    tab: "Stats",
    icon: <ChartNoAxesCombined className="size-4 shrink-0" />,
  },
];

const HEADINGS: Record<AppView, { eyebrow: string; title: string; note: string }> = {
  call: {
    eyebrow: "Your shipping companion",
    title: "Call Mia",
    note: `Open transport · Up to ${MAX_CALL_SECONDS / 60} minutes per call`,
  },
  calls: { eyebrow: "Call activity", title: "Past calls", note: "Every call, with its transcript" },
  stats: { eyebrow: "Workspace insights", title: "Stats", note: "All calls since Mia went live" },
};

/**
 * The app: a sidebar to switch views (collapsible on desktop, tabs on a phone), the header,
 * and the view. The call view stays mounted while another view is shown, so looking at past
 * calls never drops a call in progress. The desktop content area scrolls on its own, so call
 * controls stay reachable in shorter windows.
 */
export function App({ route, go }: { route: Route; go: (r: Route) => void }) {
  const [collapsed, setCollapsed] = useState(rememberedCollapsed);
  const intro = useIntro();
  const startTour = useNavigationTour(go, intro.open);
  const view: AppView = route.view === "home" ? "call" : route.view;
  const heading = HEADINGS[view];

  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // not remembered; fine
    }
  };

  return (
    <div className="mia-shell flex min-h-dvh flex-col lg:h-dvh lg:flex-row lg:overflow-hidden">
      <nav
        aria-label="Views"
        className={`hidden shrink-0 flex-col border-r border-line bg-surface p-4 transition-[width] lg:flex ${
          collapsed ? "w-20" : "w-60"
        }`}
      >
        <a href="#/" aria-label="F&F Car Shipping home" className="mb-10 flex h-12 items-center gap-3 px-2">
          <AudioLines className="size-7 shrink-0 text-brand" />
          {!collapsed && (
            <span className="text-3xl font-extrabold">
              Mia<span className="text-brand">.</span>
            </span>
          )}
        </a>
        {!collapsed && <p className="eyebrow mb-3 px-3">Workspace</p>}
        <div className="flex flex-col gap-2">
          {VIEWS.map((v) => (
            <NavItem
              key={v.label}
              item={v}
              active={view === v.route.view}
              collapsed={collapsed}
              onGo={() => go(v.route)}
            />
          ))}
        </div>
        <div className="mt-auto flex flex-col gap-4">
          {!collapsed && (
            <div className="border-t border-line px-2 pt-5">
              <p className="mb-2 text-xs font-semibold">F&amp;F car shipping</p>
              <p className="text-[11px] leading-relaxed text-muted">
                An academic project by <Ext href={SERGIO}>Sergio Vanegas</Ext> and{" "}
                <Ext href={BELINDA}>Belinda Hu</Ext>.
              </p>
              <p className="mt-2 text-[11px] text-muted">
                <Ext href={CARHAULER}>CarHauler247 prices</Ext> ·{" "}
                <Ext href={REPO}>
                  GitHub <ArrowUpRight className="inline size-3" />
                </Ext>
              </p>
            </div>
          )}
          <Button
            variant="ghost"
            onClick={toggle}
            aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
            aria-expanded={!collapsed}
            className="justify-start text-muted"
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            {!collapsed && <span>Collapse menu</span>}
          </Button>
        </div>
      </nav>
      <main className="flex w-full min-w-0 flex-1 flex-col lg:min-h-0">
        <header className="flex min-h-20 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface px-5 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <AudioLines className="size-6 text-brand lg:hidden" />
            <a href="#/" className="hover:opacity-80">
              <p className="text-sm font-semibold">F&amp;F car shipping</p>
              <p className="mt-1 text-[11px] text-muted">← Back to home</p>
            </a>
          </div>
          <div className="flex items-center gap-2">
            <Button
              data-tour="help"
              variant="ghost"
              size="icon"
              title="Replay navigation tour"
              aria-label="Replay navigation tour"
              onClick={() => startTour()}
            >
              <CircleHelp />
            </Button>
            <Button variant="ghost" size="sm" onClick={intro.show} className="hidden text-muted sm:inline-flex">
              About &amp; disclosure
            </Button>
            <ThemeToggle />
          </div>
        </header>
        <div role="tablist" aria-label="Views" className="flex shrink-0 gap-1 border-b border-line bg-surface px-4 lg:hidden">
          {VIEWS.map((v) => (
            <Button
              key={v.label}
              data-tour={`nav-${v.route.view}`}
              variant="ghost"
              role="tab"
              aria-selected={view === v.route.view}
              onClick={() => go(v.route)}
              className={`h-12 flex-1 rounded-none border-b-2 text-xs ${
                view === v.route.view ? "border-brand text-brand" : "border-transparent text-muted"
              }`}
            >
              {v.icon}
              {v.tab}
            </Button>
          ))}
        </div>
        {/* The scrolling area spans the full width, so its scrollbar sits at the window's
            right edge; the content inside is centered. */}
        <div className="flex flex-1 flex-col lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain">
          <div className="mia-workspace mx-auto flex w-full max-w-[1600px] flex-1 flex-col gap-4 px-5 py-4 lg:min-h-0 lg:px-8">
            {/* One line (Belinda, 2026-11-17): every pixel of height goes to the panels. */}
            <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <div className="flex items-baseline gap-3">
                <h1 className="font-display text-2xl font-semibold">{heading.title}</h1>
                <p className="eyebrow hidden sm:block">{heading.eyebrow}</p>
              </div>
              <p className="eyebrow hidden md:block">{heading.note}</p>
            </div>
            <div className={view === "call" ? "contents" : "hidden"}>
              <CallPage />
            </div>
            <div className={view === "calls" ? "contents" : "hidden"}>
              <PastCalls
                active={view === "calls"}
                room={route.view === "calls" ? route.room : null}
                onOpen={(room) => go({ view: "calls", room })}
              />
            </div>
            <div className={view === "stats" ? "contents" : "hidden"}>
              <StatsPage active={view === "stats"} />
            </div>
          </div>
        </div>
      </main>
      <IntroDialog open={intro.open} auto={intro.auto} onClose={intro.close} />
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
    <Button
      variant="ghost"
      data-tour={`nav-${item.route.view}`}
      onClick={onGo}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={`flex h-11 items-center justify-start gap-3 rounded-lg px-2.5 text-sm font-medium transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
        active ? "bg-ok-soft text-brand hover:bg-ok-soft hover:text-brand" : "text-muted hover:bg-raised/60 hover:text-ink"
      }`}
    >
      <span className={active ? "text-brand" : ""}>{item.icon}</span>
      {!collapsed && <span>{item.label}</span>}
    </Button>
  );
}
