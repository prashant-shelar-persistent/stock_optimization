# Frontend Tests

The frontend test suite uses **Vitest** with **@testing-library/react** to test React
components, custom hooks, the API client, and the Zustand store. All test files live under
`frontend/src/test/`.

## Vitest Configuration

Test configuration is embedded in `frontend/vite.config.ts` under the `test` key:

```typescript
// frontend/vite.config.ts
test: {
  globals: true,
  environment: "jsdom",
  setupFiles: ["./src/test/setup.ts"],
  coverage: {
    provider: "v8",
    reporter: ["text", "lcov"],
    exclude: [
      "node_modules/",
      "src/test/",
      "**/*.d.ts",
      "**/*.config.*",
      "src/main.tsx",
    ],
  },
},
```

| Option | Value | Purpose |
|--------|-------|---------|
| `globals` | `true` | `describe`, `it`, `expect`, `vi` are available globally without imports |
| `environment` | `"jsdom"` | Simulates a browser DOM environment for React component rendering |
| `setupFiles` | `["./src/test/setup.ts"]` | Runs global setup before each test file |
| `coverage.provider` | `"v8"` | Uses Node.js V8 coverage engine |
| `coverage.reporter` | `["text", "lcov"]` | Terminal output + LCOV file for CI coverage gates |

### Running the Suite

```bash
# From the frontend/ directory
cd frontend

# Run all tests
npm test

# Run in watch mode
npm run test:watch

# Run with coverage
npm run test:coverage

# Run a specific test file
npx vitest run src/test/api.test.ts

# Run tests matching a pattern
npx vitest run --reporter=verbose src/test/AgentProgressPanel
```

---

## `setup.ts` — Global Test Setup

`frontend/src/test/setup.ts` is loaded before every test file via `setupFiles`.

```typescript
import "@testing-library/jest-dom";

// Polyfill ResizeObserver (used by Radix UI Slider)
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill IntersectionObserver (used by Radix UI Scroll Area)
if (typeof globalThis.IntersectionObserver === "undefined") {
  (globalThis as any).IntersectionObserver = class IntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Suppress React act() warnings in test output
const originalError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  const msg = typeof args[0] === "string" ? args[0] : "";
  if (msg.includes("Warning: An update to") || msg.includes("act(")) return;
  originalError(...args);
};
```

**What it does:**

1. **`@testing-library/jest-dom`** — Extends Vitest's `expect` with DOM matchers like
   `toBeInTheDocument()`, `toHaveValue()`, `toBeDisabled()`, etc.
2. **`ResizeObserver` polyfill** — Radix UI Slider uses `ResizeObserver` internally; jsdom
   doesn't implement it, so a no-op stub is provided.
3. **`IntersectionObserver` polyfill** — Radix UI Scroll Area requires this API.
4. **Console suppression** — React 18 strict mode double-invokes effects and emits `act()`
   warnings; these are suppressed to keep test output clean.

---

## `fixtures.ts` — Shared Test Data

`frontend/src/test/fixtures.ts` provides factory functions and pre-built objects reused
across multiple test files.

### Agent Progress Messages

```typescript
export function makeProgressMessage(
  node: AgentNodeName,
  status: AgentProgressMessage["status"],
  overrides: Partial<AgentProgressMessage> = {},
): AgentProgressMessage

export const FULL_PIPELINE_PROGRESS: AgentProgressMessage[]  // All 6 nodes, started + completed
export const PARTIAL_PIPELINE_PROGRESS: AgentProgressMessage[] // First 2 nodes only
```

### Portfolio Data

```typescript
export const CLASSICAL_METRICS: PortfolioMetrics   // { expected_return: 0.142, sharpe_ratio: 1.45, ... }
export const QAOA_METRICS: PortfolioMetrics         // { sharpe_ratio: 1.62, ... }
export const VQE_METRICS: PortfolioMetrics          // { sharpe_ratio: 1.55, ... }

export const CLASSICAL_WEIGHTS: AssetWeight[]       // AAPL 45%, MSFT 35%, GOOGL 20%
export const CLASSICAL_RESULT: ClassicalResult
export const QUANTUM_RESULT: QuantumResult          // Both QAOA and VQE results
export const COMPARISON_SUMMARY: ComparisonSummary
```

### Run Detail Fixtures

```typescript
export const COMPLETED_RUN_DETAIL: OptimizationRunDetail  // Full classical + quantum results
export const CLASSICAL_ONLY_RUN_DETAIL: OptimizationRunDetail  // No quantum
export const RUNNING_RUN_DETAIL: OptimizationRunDetail    // In-progress run
export const FAILED_RUN_DETAIL: OptimizationRunDetail     // Failed with error_message

export function makeRunSummary(overrides?: Partial<OptimizationRunSummary>): OptimizationRunSummary
export const RUN_SUMMARY_LIST: OptimizationRunSummary[]   // 3 runs: completed, running, failed
```

### Request Fixture

```typescript
export const SAMPLE_OPTIMIZATION_REQUEST: OptimizationRequest = {
  tickers: ["AAPL", "MSFT", "GOOGL"],
  budget: 10000,
  min_return: 0.08,
  max_volatility: 0.25,
  max_weight_per_asset: 0.5,
  sector_constraints: [{ sector: "Technology", max_weight: 0.6 }],
  run_quantum: true,
};
```

---

## `@testing-library/react` Patterns

The test suite uses three main patterns from `@testing-library/react`:

### 1. Component Rendering

```typescript
import { render, screen } from "@testing-library/react";

render(<AgentProgressPanel progress={[]} isRunning={false} />);
expect(screen.getByText("Data Fetch")).toBeInTheDocument();
```

### 2. Hook Testing with `renderHook`

```typescript
import { renderHook, act, waitFor } from "@testing-library/react";

const { result } = renderHook(() => useOptimize());
expect(result.current.isSubmitting).toBe(false);

await act(async () => {
  await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
});
```

### 3. React Query Wrapper

Hooks that use `@tanstack/react-query` need a `QueryClientProvider` wrapper:

```typescript
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const { result } = renderHook(() => useAssetSearch("AAPL"), {
  wrapper: createWrapper(),
});
```

### 4. Router Wrapper

Components that use `react-router-dom` hooks need a `MemoryRouter`:

```typescript
import { MemoryRouter } from "react-router-dom";

render(
  <MemoryRouter>
    <RunHistory />
  </MemoryRouter>
);
```

---

## Test File Inventory

### Component Tests

#### `AgentProgressPanel.test.tsx`
Tests for `@/components/dashboard/AgentProgressPanel`.

```typescript
function makeMsg(node, status, message?): AgentProgressMessage
```

| Test | Scenario |
|------|----------|
| `renders all 6 pipeline steps in idle state` | All node labels visible |
| `shows 0% progress when no events received` | Progress bar at 0% |
| `shows descriptions for pending nodes` | "Fetching live market data via yfinance" visible |
| `shows the message from a started event` | Latest message displayed |
| `shows the message from a completed event` | Completed message replaces started |
| `shows the message from a failed event` | Error message displayed |
| `progress bar increases as nodes complete` | Percentage increases with each completed node |
| `completed state shows 100%` | All nodes completed → 100% |

#### `RunHistory.test.tsx`
Tests for `@/components/RunHistory`. Mocks `useRunHistory` hook.

```typescript
vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => mockUseRunHistory(),
}));
```

| Test | Scenario |
|------|----------|
| `renders skeleton rows while loading` | Loading state shows skeleton UI |
| `renders empty state message` | No runs → empty state message |
| `renders error state` | Error → error message displayed |
| `renders run rows with correct data` | Tickers, status, Sharpe ratio visible |
| `renders pagination controls` | Next/prev buttons when multiple pages |
| `clicking next page calls setPage` | Pagination callback invoked |
| `status badge has correct color for completed` | Green badge for completed |
| `status badge has correct color for failed` | Red badge for failed |

#### `SectorConstraintRow.test.tsx`
Tests for `@/components/SectorConstraintRow`.

| Test | Scenario |
|------|----------|
| `renders the sector name` | Sector label visible |
| `renders numeric input with correct initial value` | `maxWeight=0.3` → input shows `30` |
| `renders remove button with accessible label` | `aria-label="Remove Energy constraint"` |
| `renders the % suffix` | Percentage sign visible |
| `calls onChange when input changes` | `onChange` called with new decimal value |
| `calls onRemove when remove button clicked` | `onRemove` called once |
| `does not call onChange for invalid input` | Non-numeric input → no callback |
| `is disabled when disabled prop is true` | Input and button disabled |

#### `TickerBadge.test.tsx`
Tests for `@/components/TickerBadge`.

| Test | Scenario |
|------|----------|
| `renders the ticker symbol` | "AAPL" visible |
| `renders the sector when provided` | "Technology" visible |
| `does not render sector when not provided` | No sector text |
| `renders remove button with accessible label` | `aria-label="Remove TSLA"` |
| `calls onRemove when remove button clicked` | `onRemove` called once |
| `hides remove button when disabled` | No button when `disabled=true` |

### Hook Tests

#### `useAssetSearch.test.tsx`
Tests for `@/hooks/useAssetSearch`. Mocks `@/lib/api`.

```typescript
const mockSearchAssets = vi.fn();
vi.mock("@/lib/api", () => ({
  searchAssets: (...args: unknown[]) => mockSearchAssets(...args),
}));
```

| Test | Scenario |
|------|----------|
| `returns empty results for empty query` | `""` → `results=[]`, no API call |
| `calls searchAssets after debounce period` | After 300ms → API called with query |
| `does not call API before debounce period` | Before 300ms → no API call |
| `returns results from API` | API response → `results` populated |
| `sets isLoading=true while fetching` | Loading state during fetch |
| `returns empty results on API error` | Error → `results=[]`, `isLoading=false` |

#### `useOptimize.test.tsx`
Tests for `@/hooks/useOptimize`. Mocks `@/lib/api` and `@/hooks/use-toast`.

```typescript
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, submitOptimization: (...args) => mockSubmitOptimization(...args) };
});
```

| Test | Scenario |
|------|----------|
| `starts with isSubmitting=false and error=null` | Initial state |
| `returns the run_id on successful submission` | Returns `run_id` from API |
| `sets isSubmitting=true during submission` | Loading state during fetch |
| `calls startNewRun on the store with run_id` | Zustand store updated |
| `shows a success toast on successful submission` | Toast with "Optimization started" |
| `sets error on ApiError` | `error` state set with error message |
| `shows error toast on ApiError` | Toast with error title |
| `clears error on successful submission after error` | Previous error cleared |

#### `useWebSocket.test.tsx`
Tests for `@/hooks/useWebSocket`. Uses a `MockWebSocket` class.

```typescript
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  simulateMessage(data: unknown) { ... }
  simulateOpen() { ... }
  simulateError() { ... }
  simulateClose(code = 1006) { ... }
}

vi.mock("@/lib/api", () => ({
  openProgressSocket: (runId: string) => new MockWebSocket(`ws://test/${runId}`),
}));
```

| Test | Scenario |
|------|----------|
| `creates WebSocket connection when runId provided` | Socket created with correct URL |
| `does not create WebSocket when runId is null` | No socket for null runId |
| `dispatches progress messages to store` | `addAgentProgress` called |
| `handles result message and sets result` | `setOptimizationResult` called |
| `closes WebSocket on unmount` | `close()` called on cleanup |
| `reconnects on abnormal close` | Reconnect after code 1006 |
| `does not reconnect on normal close` | No reconnect after code 1000 |

### Store Tests

#### `uiStore.test.ts`
Tests for `@/store/uiStore` (Zustand). Accesses store state directly without React hooks.

```typescript
function getStore() {
  return useUIStore.getState();
}

beforeEach(() => {
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});
```

| Test Group | Coverage |
|------------|----------|
| `initial state` | All fields at default values |
| `setCurrentRunId` | Sets and clears run ID |
| `setOptimizationResult` | Sets result, clears result |
| `setIsOptimizing` | Toggles boolean flag |
| `addAgentProgress` | Appends messages, deduplicates by `(node, status)` |
| `resetProgress` | Clears `agentProgress` array |
| `setActiveTab` | Switches between `"classical"`, `"quantum"`, `"comparison"` |
| `startNewRun` | Sets `currentRunId`, `isOptimizing=true`, clears progress |
| Selectors | `selectCurrentRunId`, `selectOptimizationResult`, `selectIsOptimizing`, `selectAgentProgress`, `selectActiveTab` |

### API Client Tests

#### `api.test.ts`
Tests for `@/lib/api`. Uses `vi.stubGlobal("fetch", ...)` to mock the global fetch.

```typescript
function mockFetch(body: unknown, status = 200) {
  const response = { ok: true, status, json: vi.fn().mockResolvedValue(body) };
  return vi.fn().mockResolvedValue(response);
}
```

| Test Group | Coverage |
|------------|----------|
| `ApiError` | `instanceof Error`, correct `name`, exposes `status`, `errorCode`, `message`, `details` |
| `submitOptimization` | POSTs to `/api/v1/optimize`, returns `run_id`, throws `ApiError` on 422/500, uses `UNKNOWN_ERROR` when no `error_code` |
| `getOptimizationRun` | GETs `/api/v1/runs/:runId`, returns run detail, throws on 404 |
| `listRuns` | GETs `/api/v1/runs` with query params, returns paginated response |
| `searchAssets` | GETs `/api/v1/assets/search?q=...`, returns asset list |
| `getHealth` | GETs `/health`, returns health status |
| `openProgressSocket` | Creates `WebSocket` with correct URL |

### Utility Tests

#### `utils.test.ts`
Tests for `@/lib/utils` — formatting and class name utilities.

| Function | Tests |
|----------|-------|
| `cn` | Merges class names, ignores falsy values, resolves Tailwind conflicts (last wins), handles arrays |
| `formatPercent` | `0.1234` → `"12.34%"`, custom decimal places, negative values |
| `formatCurrency` | `10000` → `"$10,000.00"`, custom currency |
| `formatNumber` | Locale-aware number formatting |
| `truncate` | Truncates strings to max length with ellipsis |

---

## Test Directory Structure

```
frontend/src/test/
├── setup.ts                    # Global setup (jest-dom, polyfills)
├── fixtures.ts                 # Shared test data factories
├── AgentProgressPanel.test.tsx # Component: agent pipeline progress
├── RunHistory.test.tsx         # Component: run history table
├── SectorConstraintRow.test.tsx # Component: sector constraint input
├── TickerBadge.test.tsx        # Component: ticker chip with remove
├── api.test.ts                 # API client: fetch wrapper + ApiError
├── uiStore.test.ts             # Zustand store: all actions + selectors
├── useAssetSearch.test.tsx     # Hook: debounced asset search
├── useOptimize.test.tsx        # Hook: optimization submission flow
├── useWebSocket.test.tsx       # Hook: WebSocket lifecycle + messages
├── utils.test.ts               # Utilities: cn, formatPercent, etc.
├── components/                 # Additional component tests
│   ├── AgentProgressPanel.test.tsx
│   ├── AllocationChart.test.tsx
│   ├── ComparisonDashboard.test.tsx
│   ├── OptimizeForm.test.tsx
│   └── RunHistory.test.tsx
├── hooks/                      # Additional hook tests
│   ├── useRunHistory.test.ts
│   └── useWebSocket.test.ts
└── store/
    └── uiStore.test.ts
```

---

## Mocking Patterns

### Mocking API Modules

```typescript
// Mock the entire module
vi.mock("@/lib/api", () => ({
  searchAssets: (...args: unknown[]) => mockSearchAssets(...args),
}));

// Partial mock (preserve real implementations)
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, submitOptimization: mockSubmitOptimization };
});
```

### Mocking Global APIs

```typescript
// Mock fetch globally
vi.stubGlobal("fetch", mockFetch({ run_id: "run-123" }));

// Mock WebSocket globally
vi.stubGlobal("WebSocket", MockWebSocket);

// Restore after test
afterEach(() => vi.unstubAllGlobals());
```

### Mocking React Hooks

```typescript
const mockUseRunHistory = vi.fn();
vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => mockUseRunHistory(),
}));

// Configure return value per test
mockUseRunHistory.mockReturnValue({
  runs: [makeRun()],
  isLoading: false,
  error: null,
  page: 1,
  setPage: vi.fn(),
  totalPages: 1,
});
```

### Zustand Store Reset

```typescript
beforeEach(() => {
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});
```

> **Note:** Zustand stores persist state between tests unless explicitly reset. Always call
> `useUIStore.setState(initialState)` in `beforeEach` for tests that depend on store state.
