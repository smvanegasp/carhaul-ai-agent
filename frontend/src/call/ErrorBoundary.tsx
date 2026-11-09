import { Component, type ReactNode } from "react";

/**
 * Keeps a display bug from taking the call down: without it React unmounts the whole page
 * (blank screen), which also disconnects the caller. Mia's audio lives outside the boundaries,
 * so the call goes on.
 */
export class ErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("display error (the call continues):", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
