/**
 * Vitest global test setup.
 *
 * Imported by vite.config.ts → test.setupFiles.
 * Extends Vitest's expect with jest-dom matchers.
 */

import "@testing-library/jest-dom";

// ── Polyfills for jsdom ────────────────────────────────────────────────────────

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

// Suppress noisy console.error from React about act() warnings in tests
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
