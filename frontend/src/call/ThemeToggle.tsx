import { Button } from "../ui/button";
import { Sun, Moon } from "lucide-react";
import { useState } from "react";

const STORAGE_KEY = "mia.theme";

function isDark(): boolean {
  return document.documentElement.dataset.theme === "dark";
}

/** Light by default; dark mode on request, remembered in this browser (see index.html). */
export function ThemeToggle() {
  const [dark, setDark] = useState(isDark);

  const toggle = () => {
    const next = !dark;
    if (next) document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    setDark(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      // not remembered; it still applies to this visit
    }
  };

  return (
    <Button variant="ghost" size="icon"
      type="button"
      onClick={toggle}
      aria-pressed={dark}
      aria-label={dark ? "Light mode" : "Dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className="shrink-0 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted transition hover:text-ink focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
}
