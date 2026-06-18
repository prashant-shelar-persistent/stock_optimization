/**
 * App.tsx — Root application component.
 *
 * Defines top-level routes:
 *   /              → DashboardPage  (constraint form + real-time results)
 *   /history       → HistoryPage    (past optimization runs)
 *   /run/:runId    → RunDetailPage  (full detail for a single run)
 *   *              → NotFoundPage
 *
 * React 19.2 notes
 * ────────────────
 * • Uses the automatic JSX transform — no `import React` needed.
 *
 * • `lazy()` + `Suspense` is the idiomatic React 19 code-splitting pattern.
 *   Each page is split into its own JS chunk; React 19's concurrent scheduler
 *   streams page content while the chunk loads instead of blocking the tree.
 *
 * • Per-route `<Suspense>` boundaries (one per `<Route>`) give React 19's
 *   scheduler the finest possible granularity: only the route that is
 *   loading shows a fallback; all other mounted routes stay interactive.
 *
 * • `startTransition` in React 19.2 now accepts **async functions**, enabling
 *   data-fetching transitions that keep the UI responsive while awaiting
 *   server responses.  React Router v6 already wraps every navigation in
 *   `startTransition` automatically, so route changes are non-blocking by
 *   default.  Page components can call `startTransition(async () => { … })`
 *   directly for their own async state updates.
 *
 * • The `<Toaster />` is rendered outside every `<Suspense>` boundary so
 *   toast notifications remain visible even while a page chunk is loading.
 *
 * • React 19.2 improved Suspense: the fallback is shown only on the initial
 *   load of each chunk — subsequent navigations to already-loaded pages are
 *   instant because the chunk is cached by the module system.
 *
 * • React 19.2 `use()` API: page components can call `use(promise)` or
 *   `use(context)` at the top level to read async resources; Suspense
 *   boundaries in this file catch the resulting suspension automatically.
 */

import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";

// ── Lazy-loaded page components ────────────────────────────────────────────────
//
// Each page is split into its own chunk. React 19's improved Suspense
// integration means the fallback is shown only for the subtree that is
// waiting — the rest of the UI (Toaster) stays interactive.

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const HistoryPage = lazy(() => import("@/pages/HistoryPage"));
const RunDetailPage = lazy(() => import("@/pages/RunDetailPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

// ── Page loading fallback ──────────────────────────────────────────────────────
//
// A minimal, layout-stable skeleton shown while a page chunk is fetching.
// • `min-h-screen` on the outer div reserves the full viewport height so the
//   page does not jump when the real content arrives (prevents CLS).
// • `role="status"` + `aria-label` announce the loading state to screen
//   readers without requiring a live region update (React 19 a11y pattern).
// • `aria-hidden="true"` on the SVG prevents the spinner from being read
//   aloud — the outer label already conveys the message.

function PageFallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-label="Loading page…"
    >
      <div className="flex flex-col items-center gap-3">
        {/* Animated spinner — decorative, hidden from assistive technology */}
        <svg
          className="h-8 w-8 animate-spin text-primary/60"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
          focusable="false"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    </div>
  );
}

// ── Root component ─────────────────────────────────────────────────────────────
//
// Each `<Route>` is wrapped in its own `<Suspense>` boundary so that React 19
// can suspend only the route that is loading, leaving all other UI interactive.
// This is the recommended React 19.2 pattern for per-route code-splitting.
//
// `<Toaster />` sits outside every `<Suspense>` boundary so that toast
// notifications (e.g. "Optimization started") remain visible while any page
// chunk is loading in the background.

export default function App() {
  return (
    <>
      <Routes>
        {/*
         * Each route gets its own Suspense boundary (React 19.2 best practice).
         * This gives the concurrent scheduler maximum granularity: only the
         * route currently loading shows a fallback; already-mounted routes are
         * unaffected.  React Router v6 wraps navigations in `startTransition`
         * automatically, so the current page stays interactive while the next
         * page's chunk is fetched.
         */}
        <Route
          path="/"
          element={
            <Suspense fallback={<PageFallback />}>
              <DashboardPage />
            </Suspense>
          }
        />
        <Route
          path="/history"
          element={
            <Suspense fallback={<PageFallback />}>
              <HistoryPage />
            </Suspense>
          }
        />
        <Route
          path="/run/:runId"
          element={
            <Suspense fallback={<PageFallback />}>
              <RunDetailPage />
            </Suspense>
          }
        />
        <Route
          path="*"
          element={
            <Suspense fallback={<PageFallback />}>
              <NotFoundPage />
            </Suspense>
          }
        />
      </Routes>

      {/*
       * Toaster is intentionally outside all Suspense boundaries so that
       * toast notifications (e.g. "Optimization started") remain visible
       * while any page chunk is loading in the background.
       */}
      <Toaster />
    </>
  );
}
