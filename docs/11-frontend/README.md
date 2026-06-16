# Frontend

Documentation for the React + Vite + shadcn/ui frontend — component architecture, pages, custom hooks, the API client, TypeScript types, and the real-time WebSocket integration.

## Section Contents

| Page | Description |
|------|-------------|
| [Project Structure](project-structure.md) | Directory layout, module organization, and build configuration |
| [Pages](pages.md) | Route-level page components (Home, Optimize, History, Run Detail) |
| [Components](components.md) | Reusable UI components (OptimizeForm, ComparisonDashboard, AgentProgressPanel) |
| [Hooks](hooks.md) | Custom React hooks (useOptimize, useRunHistory, useWebSocket) |
| [API Client](api-client.md) | Axios-based REST client and WebSocket manager |
| [State Management](state-management.md) | Zustand stores and React Query integration |
| [Type Definitions](type-definitions.md) | TypeScript interfaces, enums, and type guards |

## Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 18 | UI framework |
| Vite | 5 | Build tool and dev server |
| TypeScript | 5 | Type safety |
| shadcn/ui | latest | Component library |
| Tailwind CSS | 3 | Utility-first styling |
| Zustand | 4 | Client state management |
| React Query (TanStack) | 5 | Server state and caching |
| Axios | 1 | HTTP client |
| Recharts | 2 | Data visualization (efficient frontier) |

## Application Structure

```mermaid
graph TD
    subgraph "Pages"
        P1["/ (Home)"]
        P2["/optimize (OptimizePage)"]
        P3["/history (HistoryPage)"]
        P4["/runs/:id (RunDetailPage)"]
    end
    subgraph "Key Components"
        C1["OptimizeForm"]
        C2["AgentProgressPanel"]
        C3["ComparisonDashboard"]
        C4["EfficientFrontierChart"]
        C5["RunHistoryTable"]
    end
    subgraph "Data Layer"
        H1["useOptimize hook"]
        H2["useWebSocket hook"]
        H3["useRunHistory hook"]
        S1["Zustand store"]
        Q1["React Query cache"]
    end
    P2 --> C1
    P2 --> C2
    P2 --> C3
    P3 --> C5
    P4 --> C3
    C1 --> H1
    C2 --> H2
    H1 --> S1
    H3 --> Q1
```

## Cross-References

- **API endpoints consumed** → [API Reference](../04-api-reference/optimize-endpoint.md)
- **WebSocket protocol** → [WebSocket Endpoint](../04-api-reference/websocket-endpoint.md)
- **TypeScript types mirror Pydantic schemas** → [Response Schemas](../12-schemas/response-schemas.md)
- **Frontend tests** → [Frontend Tests](../13-testing/frontend-tests.md)
