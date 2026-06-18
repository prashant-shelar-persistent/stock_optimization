/**
 * Vitest global test setup.
 *
 * Imported by vite.config.ts → test.setupFiles.
 * Extends Vitest's expect with jest-dom matchers.
 */

import "@testing-library/jest-dom";

// ── Polyfills for jsdom ────────────────────────────────────────────────────

// Radix UI Slider (and other components) use ResizeObserver internally.
// jsdom doesn't implement it, so we provide a no-op stub.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Radix UI Scroll Area uses IntersectionObserver.
if (typeof globalThis.IntersectionObserver === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).IntersectionObserver = class IntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// jsdom does not implement Element.scrollIntoView.
// ChatAssistant uses scrollEndRef.current?.scrollIntoView({ behavior: "smooth" })
// to auto-scroll the message thread. We provide a no-op stub so tests don't throw.
if (typeof Element.prototype.scrollIntoView === "undefined") {
  Element.prototype.scrollIntoView = function () {};
}

// Suppress noisy console.error from React about act() warnings in tests.
// NOTE (React 19): `act()` now lives in the `react` package itself
// (`import { act } from "react"`) rather than `react-dom/test-utils`.
// The warning filter below still applies — React 19 emits the same
// "not wrapped in act(...)" messages when state updates happen outside
// of an act() boundary during tests.
const originalError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  const msg = typeof args[0] === "string" ? args[0] : "";
  if (
    msg.includes("Warning: An update to") ||
    msg.includes("Warning: ReactDOM.render") ||
    msg.includes("act(")
  ) {
    return;
  }
  originalError(...args);
};
