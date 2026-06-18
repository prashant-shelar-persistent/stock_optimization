/**
 * main.tsx — Application entry point.
 *
 * React 19.2 notes
 * ────────────────
 * • Uses the automatic JSX transform (`react-jsx`) — no `import React` needed.
 * • `createRoot` in React 19 accepts `onCaughtError`, `onUncaughtError`, and
 *   `onRecoverableError` callbacks for fine-grained error reporting without a
 *   class-based ErrorBoundary at the root.  The `@types/react-dom` package is
 *   augmented below to expose these React 19-only options until the DefinitelyTyped
 *   package is updated to reflect the React 19 API surface.
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
 */

import { StrictMode } from "react";
import { prefetchDNS, preconnect } from "react-dom";
import { createRoot, type RootOptions } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// ── React 19.2 Resource Preloading ─────────────────────────────────────────────
//
// `prefetchDNS` issues a DNS prefetch hint for the backend origin so the
// browser resolves the hostname before the first API request is made.
// `preconnect` goes further and warms up the full TCP (and TLS, if applicable)
// connection, eliminating connection-setup latency on the first fetch.
//
// Both calls are side-effectful and must run at module evaluation time —
// before `createRoot` — so the browser can act on the hints as early as
// possible during the initial page load.
//
// These are React 19 DOM APIs (react-dom, not react-dom/client) and are
// fully typed in @types/react-dom@^19.2.3.

prefetchDNS("http://localhost:8000");
preconnect("http://localhost:8000");

// ── React 19 RootOptions type augmentation ─────────────────────────────────────
//
// React 19 added `onUncaughtError` and `onCaughtError` to `createRoot` options.
// The installed @types/react-dom package predates React 19 and only declares
// `onRecoverableError`.  We extend the interface here so TypeScript accepts the
// full React 19 API without requiring a package update.

// NOTE: @types/react-dom@19.2.3 already includes onCaughtError, onUncaughtError,
// and onRecoverableError in RootOptions — no module augmentation needed.

// ── TanStack Query client ──────────────────────────────────────────────────────
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

// ── Root element guard ─────────────────────────────────────────────────────────

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error(
    "[main] Root element #root not found in document. " +
      'Ensure index.html contains <div id="root"></div>.',
  );
}

// ── Root options ───────────────────────────────────────────────────────────────
//
// React 19 `createRoot` options:
//   • `onUncaughtError`    — fires for errors NOT caught by any ErrorBoundary.
//     Replaces the old `window.onerror` pattern for React-rendered trees.
//   • `onCaughtError`      — fires for errors caught by an ErrorBoundary,
//     giving a central place to log them (e.g. to Sentry) without subclassing.
//   • `onRecoverableError` — fires when React recovers from a hydration or
//     rendering error by falling back to client rendering.
//
// In development (`import.meta.env.DEV`) all three are logged to the console.
// In production, replace the console calls with your error-reporting service
// (e.g. Sentry.captureException).

const rootOptions: RootOptions = {
  // Errors NOT caught by any ErrorBoundary — these are fatal from React's POV.
  onUncaughtError(error: unknown, errorInfo: { componentStack?: string }) {
    if (import.meta.env.DEV) {
      console.error("[React] Uncaught error:", error, errorInfo.componentStack);
    }
  },

  // Errors caught by an ErrorBoundary — UI recovered, but we still want to log.
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

  // Recoverable errors — React auto-fixed them (e.g. hydration mismatches).
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

// ── Mount ──────────────────────────────────────────────────────────────────────

createRoot(rootElement, rootOptions).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
