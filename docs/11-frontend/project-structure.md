# Frontend Project Structure

The Portfolio Optimizer frontend is a React 18 single-page application built with Vite, TypeScript, Tailwind CSS, and shadcn/ui. This page covers the toolchain configuration: Vite's dev-server proxy, TypeScript strict mode, Tailwind's design-token system, the shadcn/ui component library, and the ESLint + Prettier code-quality setup.

## Directory Layout

```
frontend/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── ui/              # shadcn/ui primitives (Button, Card, Badge, …)
│   │   ├── charts/          # Recharts wrappers (AllocationPieChart, MetricsCard, …)
│   │   └── dashboard/       # Composite dashboard components
│   ├── hooks/               # Custom React hooks
│   ├── lib/                 # Utilities (api.ts, utils.ts)
│   ├── pages/               # Route-level page components
│   ├── store/               # Zustand global state
│   ├── types/               # TypeScript interfaces (api.ts)
│   ├── test/                # Vitest unit tests
│   ├── App.tsx              # Root router
│   ├── main.tsx             # Entry point (QueryClient + BrowserRouter)
│   └── index.css            # Tailwind base + CSS variables
├── vite.config.ts           # Vite + Vitest configuration
├── tsconfig.app.json        # TypeScript compiler options
├── tailwind.config.ts       # Tailwind theme extension
├── eslint.config.js         # ESLint flat config
└── package.json             # Dependencies and scripts
```

## Vite Configuration

**File:** `frontend/vite.config.ts`

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      // Proxy REST API calls to the FastAPI backend
      "/api": {
        target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      // Proxy WebSocket connections
      "/ws": {
        target: process.env.VITE_WS_BASE_URL ?? "ws://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          recharts: ["recharts"],
          radix: ["@radix-ui/react-dialog", /* … */],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

### Dev-Server Proxy

The Vite dev server runs on **port 5173** and proxies two path prefixes to the FastAPI backend:

| Prefix | Protocol | Default Target | Purpose |
|--------|----------|----------------|---------|
| `/api` | HTTP | `http://localhost:8000` | REST API calls |
| `/ws`  | WebSocket | `ws://localhost:8000` | Agent progress stream |

Both targets are overridable via environment variables:

- `VITE_API_BASE_URL` — full base URL for the backend (e.g. `http://api.example.com`)
- `VITE_WS_BASE_URL` — WebSocket base URL (e.g. `wss://api.example.com`)

The `changeOrigin: true` flag rewrites the `Host` header so the backend sees its own hostname. The `ws: true` flag enables WebSocket proxying for the `/ws` prefix.

### Path Alias `@/`

The `resolve.alias` entry maps `@` to `./src`, enabling clean absolute imports throughout the codebase:

```typescript
// Instead of:
import { useUIStore } from "../../../store/uiStore";

// You write:
import { useUIStore } from "@/store/uiStore";
```

### Build Chunking

The production build splits vendor code into three named chunks for optimal browser caching:

- **`react`** — React, ReactDOM, React Router
- **`recharts`** — the charting library (largest single dependency)
- **`radix`** — all Radix UI primitives used by shadcn/ui

Source maps are enabled (`sourcemap: true`) for production debugging.

## TypeScript Configuration

**File:** `frontend/tsconfig.app.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",

    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"],
  "exclude": ["src/test/**/*"]
}
```

### Strict Mode Flags

The `"strict": true` umbrella enables all TypeScript strict checks:

| Flag | Effect |
|------|--------|
| `strictNullChecks` | `null` and `undefined` are not assignable to other types |
| `strictFunctionTypes` | Stricter function parameter checking |
| `strictPropertyInitialization` | Class properties must be initialized |
| `noImplicitAny` | Variables without type annotations must be inferable |

Additional linting flags:

- **`noUnusedLocals`** — error on declared but unused local variables
- **`noUnusedParameters`** — error on unused function parameters
- **`noFallthroughCasesInSwitch`** — error on switch cases without `break`

### Path Mapping

The `paths` entry mirrors the Vite alias so TypeScript resolves `@/` imports correctly during type-checking:

```json
"baseUrl": ".",
"paths": {
  "@/*": ["./src/*"]
}
```

The project uses a **composite** `tsconfig.json` that references two sub-configs:
- `tsconfig.app.json` — application source (`src/`)
- `tsconfig.node.json` — Node.js tooling (`vite.config.ts`, etc.)

## Tailwind CSS Setup

**File:** `frontend/tailwind.config.ts`

Tailwind is configured with the `class` dark-mode strategy and a custom design-token theme that integrates with shadcn/ui's CSS variable system.

### Content Paths

```typescript
content: [
  "./index.html",
  "./src/**/*.{ts,tsx}",
],
```

### Design Tokens

All colors are defined as CSS custom properties (`hsl(var(--token))`) so they can be overridden per theme:

```typescript
colors: {
  border:      "hsl(var(--border))",
  background:  "hsl(var(--background))",
  foreground:  "hsl(var(--foreground))",
  primary:     { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
  secondary:   { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
  destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
  muted:       { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
  // Portfolio-specific semantic colors:
  quantum:     { DEFAULT: "hsl(var(--quantum))", foreground: "hsl(var(--quantum-foreground))" },
  classical:   { DEFAULT: "hsl(var(--classical))", foreground: "hsl(var(--classical-foreground))" },
}
```

The `quantum` and `classical` tokens are application-specific semantic colors used to visually distinguish quantum (violet/purple) from classical (blue) optimization results throughout the UI.

### Custom Animations

```typescript
keyframes: {
  "pulse-quantum": {
    "0%, 100%": { opacity: "1" },
    "50%":      { opacity: "0.4" },
  },
},
animation: {
  "pulse-quantum": "pulse-quantum 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
},
```

The `pulse-quantum` animation is used on quantum-related UI elements to indicate active computation.

### Plugin

`tailwindcss-animate` is included for the accordion open/close animations used by shadcn/ui's collapsible components.

## shadcn/ui Component Library

shadcn/ui provides copy-paste React components built on top of Radix UI primitives and styled with Tailwind CSS. Components live in `src/components/ui/` and are owned by the project (not a node_modules dependency).

### Installed Primitives

| Component | Radix Primitive | Usage |
|-----------|----------------|-------|
| `Button` | `@radix-ui/react-slot` | All clickable actions |
| `Badge` | — | Status indicators, ticker labels |
| `Card` | — | Content containers |
| `Dialog` | `@radix-ui/react-dialog` | Modal overlays |
| `DropdownMenu` | `@radix-ui/react-dropdown-menu` | Context menus |
| `Input` | — | Text inputs |
| `Label` | `@radix-ui/react-label` | Form labels |
| `Progress` | `@radix-ui/react-progress` | Pipeline progress bar |
| `ScrollArea` | `@radix-ui/react-scroll-area` | Scrollable containers |
| `Select` | `@radix-ui/react-select` | Dropdown selects |
| `Separator` | `@radix-ui/react-separator` | Visual dividers |
| `Skeleton` | — | Loading placeholders |
| `Slider` | `@radix-ui/react-slider` | Range inputs |
| `Switch` | `@radix-ui/react-switch` | Toggle controls |
| `Table` | — | Data tables |
| `Tabs` | `@radix-ui/react-tabs` | Tab navigation |
| `Toast` / `Toaster` | `@radix-ui/react-toast` | Notification toasts |
| `Tooltip` | `@radix-ui/react-tooltip` | Hover tooltips |

### `cn()` Utility

All components use the `cn()` helper from `src/lib/utils.ts` to merge Tailwind classes with conflict resolution:

```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

This prevents duplicate or conflicting Tailwind classes (e.g., `p-2 p-4` → `p-4`).

## ESLint Configuration

**File:** `frontend/eslint.config.js`

The project uses ESLint's new **flat config** format (ESLint 9+):

```javascript
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": ["error", {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
      }],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/consistent-type-imports": ["error", {
        prefer: "type-imports",
      }],
    },
  },
);
```

### Key Rules

| Rule | Level | Purpose |
|------|-------|---------|
| `react-hooks/rules-of-hooks` | error | Enforce hooks call order |
| `react-hooks/exhaustive-deps` | warn | Catch missing `useEffect` deps |
| `react-refresh/only-export-components` | warn | Ensure HMR works correctly |
| `@typescript-eslint/no-unused-vars` | error | Catch dead code (prefix `_` to suppress) |
| `@typescript-eslint/no-explicit-any` | warn | Discourage `any` type |
| `@typescript-eslint/consistent-type-imports` | error | Enforce `import type` for type-only imports |

## Prettier Configuration

Prettier is configured via `package.json` scripts (no separate config file). The `prettier-plugin-tailwindcss` plugin automatically sorts Tailwind class names in the canonical order:

```json
"scripts": {
  "format":       "prettier --write \"src/**/*.{ts,tsx,css}\"",
  "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\""
}
```

## NPM Scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `dev` | `vite` | Start dev server on port 5173 |
| `build` | `tsc -b && vite build` | Type-check then bundle |
| `preview` | `vite preview` | Preview production build |
| `lint` | `eslint . --max-warnings 0` | Lint with zero-warning policy |
| `lint:fix` | `eslint . --fix` | Auto-fix lint issues |
| `format` | `prettier --write …` | Format source files |
| `format:check` | `prettier --check …` | Check formatting in CI |
| `test` | `vitest run` | Run unit tests once |
| `test:watch` | `vitest` | Run tests in watch mode |
| `test:coverage` | `vitest run --coverage` | Generate coverage report |
| `type-check` | `tsc --noEmit` | Type-check without emitting |

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `react` | 18.x | UI framework |
| `react-router-dom` | 6.x | Client-side routing |
| `@tanstack/react-query` | 5.x | Server state management |
| `zustand` | 4.x | Client state management |
| `recharts` | 2.x | Charts (pie, bar) |
| `lucide-react` | 0.400+ | Icon library |
| `tailwindcss` | 3.x | Utility-first CSS |
| `class-variance-authority` | 0.7+ | Component variant system |
| `clsx` + `tailwind-merge` | — | Class name utilities |
| `vitest` | 1.x | Unit test runner |
| `@testing-library/react` | 16.x | Component testing |

> **Note:** The `vitest/config` import in `vite.config.ts` (instead of `vite`) is intentional — it extends Vite's config type with Vitest-specific options while keeping a single config file for both bundling and testing.
