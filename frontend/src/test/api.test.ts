/**
 * Tests for @/lib/api
 *
 * Uses vi.stubGlobal to mock fetch and WebSocket.
 * Covers: submitOptimization, getOptimizationRun, listRuns,
 *         searchAssets, getHealth, openProgressSocket, ApiError.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  submitOptimization,
  getOptimizationRun,
  listRuns,
  searchAssets,
  getHealth,
  openProgressSocket,
  ApiError,
} from "@/lib/api";

// ── Fetch mock helpers ────────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200) {
  const response = {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
  return vi.fn().mockResolvedValue(response);
}

function mockFetchError(body: unknown, status: number) {
  const response = {
    ok: false,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
  return vi.fn().mockResolvedValue(response);
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({}));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── ApiError ──────────────────────────────────────────────────────────────────

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError(404, "NOT_FOUND", "Not found");
    expect(err).toBeInstanceOf(Error);
  });

  it("has the correct name", () => {
    const err = new ApiError(404, "NOT_FOUND", "Not found");
    expect(err.name).toBe("ApiError");
  });

  it("exposes status, errorCode, and message", () => {
    const err = new ApiError(422, "VALIDATION_ERROR", "Invalid input", {
      field: "tickers",
    });
    expect(err.status).toBe(422);
    expect(err.errorCode).toBe("VALIDATION_ERROR");
    expect(err.message).toBe("Invalid input");
    expect(err.details).toEqual({ field: "tickers" });
  });
});

// ── submitOptimization ────────────────────────────────────────────────────────

describe("submitOptimization", () => {
  it("POSTs to /api/v1/optimize and returns run_id", async () => {
    const fetchMock = mockFetch({ run_id: "run-abc-123" });
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitOptimization({
      tickers: ["AAPL", "MSFT"],
      budget: 10000,
    });

    expect(result.run_id).toBe("run-abc-123");
    expect(fetchMock).toHaveBeenCalledOnce();

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/optimize");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toMatchObject({
      tickers: ["AAPL", "MSFT"],
      budget: 10000,
    });
  });

  it("throws ApiError on 422 response", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "VALIDATION_ERROR", message: "Invalid tickers" },
        422,
      ),
    );

    await expect(
      submitOptimization({ tickers: [], budget: 0 }),
    ).rejects.toThrow(ApiError);
  });

  it("throws ApiError with correct status on 500", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SERVER_ERROR", message: "Internal error" }, 500),
    );

    try {
      await submitOptimization({ tickers: ["AAPL"], budget: 1000 });
      expect.fail("Should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).errorCode).toBe("SERVER_ERROR");
    }
  });

  it("uses UNKNOWN_ERROR code when error body has no error_code", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({}, 503),
    );

    try {
      await submitOptimization({ tickers: ["AAPL"], budget: 1000 });
      expect.fail("Should have thrown");
    } catch (err) {
      expect((err as ApiError).errorCode).toBe("UNKNOWN_ERROR");
    }
  });
});

// ── getOptimizationRun ────────────────────────────────────────────────────────

describe("getOptimizationRun", () => {
  it("GETs /api/v1/runs/:runId and returns run detail", async () => {
    const mockRun = {
      run_id: "run-xyz",
      status: "completed",
      tickers: ["AAPL"],
      budget: 5000,
      created_at: "2024-01-01T00:00:00Z",
    };
    const fetchMock = mockFetch(mockRun);
    vi.stubGlobal("fetch", fetchMock);

    const result = await getOptimizationRun("run-xyz");

    expect(result.run_id).toBe("run-xyz");
    expect(result.status).toBe("completed");
    expect(result.tickers).toEqual(["AAPL"]);

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/runs/run-xyz");
  });

  it("throws ApiError on 404", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "NOT_FOUND", message: "Run not found" }, 404),
    );

    await expect(getOptimizationRun("nonexistent")).rejects.toThrow(ApiError);
  });
});

// ── listRuns ──────────────────────────────────────────────────────────────────

describe("listRuns", () => {
  it("GETs /api/v1/runs and returns paginated list", async () => {
    const mockResponse = {
      items: [
        {
          run_id: "r1",
          status: "completed",
          tickers: ["AAPL"],
          budget: 1000,
          created_at: "2024-01-01T00:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };
    const fetchMock = mockFetch(mockResponse);
    vi.stubGlobal("fetch", fetchMock);

    const result = await listRuns({ page: 1, page_size: 20 });

    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
    expect(result.page).toBe(1);

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/runs");
    expect(url).toContain("page=1");
    expect(url).toContain("page_size=20");
  });

  it("calls /api/v1/runs without query params when no params provided", async () => {
    const fetchMock = mockFetch({ items: [], total: 0, page: 1, page_size: 20 });
    vi.stubGlobal("fetch", fetchMock);

    await listRuns();

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/runs");
    // No query string appended
    expect(url).not.toContain("?");
  });

  it("throws ApiError on server error", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SERVER_ERROR", message: "DB error" }, 500),
    );

    await expect(listRuns()).rejects.toThrow(ApiError);
  });
});

// ── searchAssets ──────────────────────────────────────────────────────────────

describe("searchAssets", () => {
  it("GETs /api/v1/assets/search with encoded query", async () => {
    const mockResults = [
      { ticker: "AAPL", name: "Apple Inc.", sector: "Technology" },
    ];
    const fetchMock = mockFetch(mockResults);
    vi.stubGlobal("fetch", fetchMock);

    const results = await searchAssets("AAPL");

    expect(results).toHaveLength(1);
    expect(results[0].ticker).toBe("AAPL");
    expect(results[0].name).toBe("Apple Inc.");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/assets/search");
    expect(url).toContain("q=AAPL");
  });

  it("URL-encodes special characters in query", async () => {
    const fetchMock = mockFetch([]);
    vi.stubGlobal("fetch", fetchMock);

    await searchAssets("S&P 500");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("q=S%26P%20500");
  });

  it("returns empty array on 200 with empty body", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    const results = await searchAssets("xyz");
    expect(results).toEqual([]);
  });
});

// ── getHealth ─────────────────────────────────────────────────────────────────

describe("getHealth", () => {
  it("GETs /api/v1/health and returns health status", async () => {
    const mockHealth = {
      status: "healthy",
      version: "1.0.0",
      services: { database: "up", redis: "up", celery: "up" },
    };
    const fetchMock = mockFetch(mockHealth);
    vi.stubGlobal("fetch", fetchMock);

    const health = await getHealth();

    expect(health.status).toBe("healthy");
    expect(health.version).toBe("1.0.0");
    expect(health.services.database).toBe("up");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/health");
  });

  it("throws ApiError when service is unhealthy (503)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "SERVICE_UNAVAILABLE", message: "DB down" },
        503,
      ),
    );

    await expect(getHealth()).rejects.toThrow(ApiError);
  });
});

// ── openProgressSocket ────────────────────────────────────────────────────────

describe("openProgressSocket", () => {
  it("creates a WebSocket with the correct URL", () => {
    const mockWs = { url: "" };
    const MockWebSocket = vi.fn().mockImplementation((url: string) => {
      mockWs.url = url;
      return mockWs;
    });
    vi.stubGlobal("WebSocket", MockWebSocket);

    const ws = openProgressSocket("run-test-123");

    expect(MockWebSocket).toHaveBeenCalledOnce();
    expect(ws).toBe(mockWs);
    // URL should contain the run ID and the progress path
    expect(mockWs.url).toContain("run-test-123");
    expect(mockWs.url).toContain("progress");
  });

  it("returns a WebSocket instance", () => {
    const mockWs = {};
    vi.stubGlobal("WebSocket", vi.fn().mockReturnValue(mockWs));

    const result = openProgressSocket("run-abc");
    expect(result).toBe(mockWs);
  });
});
