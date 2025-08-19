import { Component, type ReactNode } from "react";

export class WorkbenchBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="empty" role="alert">
        <h1>The workbench could not open.</h1>
        <p>
          A browser update or interrupted connection may have left an
          unavailable interface module. Reload to request the current workbench.
        </p>
        <button
          onClick={() => {
            const url = new URL(window.location.href);
            url.searchParams.set("_workbench_reload", Date.now().toString(36));
            window.location.replace(url.href);
          }}
        >
          Reload workbench
        </button>
      </main>
    );
  }
}
