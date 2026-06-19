/**
 * main.tsx — Application entry point.
 *
 * React 19.2 notes
 * ────────────────
 * • Uses the automatic JSX transform (`react-jsx`) — no `import React` needed.
 * • `createRoot` in React 19 accepts `onCaughtError`, `onUncaughtError`, and
 *   `onRecoverableError` callbacks for fine-grained error reporting without a
 *   class-based ErrorBoundary at the root.
 * • React 19's improved concurrent scheduler is activated automatically by
 *   `createRoot`; no extra configuration is required.
 * • `StrictMode` in React 19 additionally checks for deprecated string refs
 *   and warns about missing `key` props in fragments — all existing code
 *   already complies.
 * • TanStack Query v5 is fully compatible with React 19's concurrent rendering
 *   and the improved batching that ships with React 19.
 * • `prefetchDNS` and `preconnect` (from `react-dom`) are called at module
 *   level to warm up the connection to the backend API before the first render,
 *   leveraging React 19.2's built-in resource preloading APIs.
 *   They are called defensively (typeof check) so a stale Vite dep-cache that
 *   pre-bundled react-dom before the React 19 upgrade does not crash the app.
 */

import { StrictMode } from "react";
import { createRoot, type RootOptions } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// ── React 19.2 Resource Preloading ─────────────────────────────────────────
//
// `prefetchDNS` and `preconnect` are React 19-only APIs. We import the whole
// react-dom namespace and call them defensively so a stale Vite pre-bundle
// cache (which may have been built against React 18) does not throw a
// TypeError and leave the page blank.

import("react-dom").then((ReactDOM) => {
  if (typeof (ReactDOM as Record<string, unknown>).prefetchDNS === "function") {
    (ReactDOM as { prefetchDNS: (href: string) => void }).prefetchDNS(
      "http://localhost:8000",
    );
  }
  if (typeof (ReactDOM as Record<string, unknown>).preconnect === "function") {
    (ReactDOM as { preconnect: (href: string) => void }).preconnect(
      "http://localhost:8000",
    );
  }
});

// ── TanStack Query client ───────────────────────────────────────────────────
//
// React 19's improved batching means that multiple query invalidations that
// previously triggered separate re-renders are now coalesced into one — the
// `staleTime` and `retry` settings below remain the right defaults regardless.

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Keep data fresh for 30 s before marking it stale.
      staleTime: 30_000,
      // Retry failed requests twice before surfacing an error.
      retry: 2,
      // Don't refetch when the user switches back to the tab — the WebSocket
      // keeps real-time data current for the active run.
      refetchOnWindowFocus: false,
    },
  },
});

// ── Root element guard ──────────────────────────────────────────────────────

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error(
    "[main] Root element #root not found in document. " +
      'Ensure index.html contains <div id="root"></div>.',
  );
}

// ── Root options ────────────────────────────────────────────────────────────
//
// React 19 `createRoot` options:
//   • `onUncaughtError`    — fires for errors NOT caught by any ErrorBoundary.
//   • `onCaughtError`      — fires for errors caught by an ErrorBoundary.
//   • `onRecoverableError` — fires when React recovers from a hydration or
//     rendering error by falling back to client rendering.

const rootOptions: RootOptions = {
  onUncaughtError(error: unknown, errorInfo: { componentStack?: string }) {
    if (import.meta.env.DEV) {
      console.error("[React] Uncaught error:", error, errorInfo.componentStack);
    }
  },

  onCaughtError(
    error: unknown,
    errorInfo: { componentStack?: string; errorBoundary?: unknown },
  ) {
    if (import.meta.env.DEV) {
      console.warn(
        "[React] Error caught by boundary:",
        error,
        errorInfo.componentStack,
      );
    }
  },

  onRecoverableError(error: unknown, errorInfo: { componentStack?: string }) {
    if (import.meta.env.DEV) {
      console.warn(
        "[React] Recoverable error:",
        error,
        errorInfo.componentStack,
      );
    }
  },
};

// ── Mount ───────────────────────────────────────────────────────────────────

createRoot(rootElement, rootOptions).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
