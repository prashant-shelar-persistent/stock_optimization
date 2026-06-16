/**
 * Tests for the chat-related functions in @/lib/api
 *
 * Covers:
 *   - createChatSession: POST /api/v1/chat/sessions
 *   - sendChatMessage: POST /api/v1/chat/sessions/{id}/messages
 *   - confirmChatRun: POST /api/v1/chat/sessions/{id}/confirm
 *   - getChatSession: GET /api/v1/chat/sessions/{id}
 *
 * Uses vi.stubGlobal to mock fetch. Verifies:
 *   - Correct HTTP method and URL
 *   - Correct request body serialisation
 *   - Correct response parsing
 *   - ApiError thrown on non-2xx responses with correct status/code/message
 *   - URL encoding of session IDs that contain special characters
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createChatSession,
  sendChatMessage,
  confirmChatRun,
  getChatSession,
  ApiError,
} from "@/lib/api";
import type {
  ChatSession,
  SendChatMessageResponse,
  ConfirmChatSessionResponse,
} from "@/types/api";

// ── Fetch mock helpers ─────────────────────────────────────────────────────

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

// ── Fixtures ───────────────────────────────────────────────────────────────

const MOCK_CHAT_SESSION: ChatSession = {
  session_id: "sess-abc-123",
  status: "active",
  messages: [
    {
      role: "user",
      content: "Build me a portfolio",
      timestamp: "2024-06-01T12:00:00.000Z",
    },
    {
      role: "assistant",
      content: "What tickers are you interested in?",
      timestamp: "2024-06-01T12:00:01.000Z",
    },
  ],
  extracted_slots: { tickers: ["AAPL"] },
  created_at: "2024-06-01T12:00:00.000Z",
};

const MOCK_SEND_RESPONSE: SendChatMessageResponse = {
  reply: "Great, I have AAPL and MSFT. What budget?",
  status: "active",
  extracted_slots: { tickers: ["AAPL", "MSFT"] },
  payload_preview: null,
};

const MOCK_CONFIRM_RESPONSE: ConfirmChatSessionResponse = {
  run_id: "run-xyz-789",
  session_id: "sess-abc-123",
};

// ── createChatSession ──────────────────────────────────────────────────────

describe("createChatSession", () => {
  it("POSTs to /api/v1/chat/sessions", async () => {
    const fetchMock = mockFetch(MOCK_CHAT_SESSION);
    vi.stubGlobal("fetch", fetchMock);

    await createChatSession({});

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/chat/sessions");
    expect(url).not.toContain("/messages");
  });

  it("uses POST method", async () => {
    const fetchMock = mockFetch(MOCK_CHAT_SESSION);
    vi.stubGlobal("fetch", fetchMock);

    await createChatSession({});

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.method).toBe("POST");
  });

  it("sends initial_message in the request body when provided", async () => {
    const fetchMock = mockFetch(MOCK_CHAT_SESSION);
    vi.stubGlobal("fetch", fetchMock);

    await createChatSession({ initial_message: "Build me a portfolio" });

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(options.body as string);
    expect(body.initial_message).toBe("Build me a portfolio");
  });

  it("returns the ChatSession object from the response", async () => {
    vi.stubGlobal("fetch", mockFetch(MOCK_CHAT_SESSION));

    const result = await createChatSession({});

    expect(result.session_id).toBe("sess-abc-123");
    expect(result.status).toBe("active");
    expect(result.messages).toHaveLength(2);
    expect(result.extracted_slots).toEqual({ tickers: ["AAPL"] });
  });

  it("throws ApiError on 422 response", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "VALIDATION_ERROR", message: "Invalid request" },
        422,
      ),
    );

    await expect(createChatSession({})).rejects.toThrow(ApiError);
  });

  it("throws ApiError with correct status and code on 422", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "VALIDATION_ERROR", message: "Invalid request" },
        422,
      ),
    );

    try {
      await createChatSession({});
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.errorCode).toBe("VALIDATION_ERROR");
      expect(apiErr.message).toBe("Invalid request");
    }
  });

  it("throws ApiError on 500 response", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "INTERNAL_ERROR", message: "Server error" }, 500),
    );

    await expect(createChatSession({})).rejects.toThrow(ApiError);
  });
});

// ── sendChatMessage ────────────────────────────────────────────────────────

describe("sendChatMessage", () => {
  it("POSTs to the correct session messages URL", async () => {
    const fetchMock = mockFetch(MOCK_SEND_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await sendChatMessage("sess-abc-123", "Hello");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/chat/sessions/sess-abc-123/messages");
  });

  it("uses POST method", async () => {
    const fetchMock = mockFetch(MOCK_SEND_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await sendChatMessage("sess-abc-123", "Hello");

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.method).toBe("POST");
  });

  it("sends the content in the request body", async () => {
    const fetchMock = mockFetch(MOCK_SEND_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await sendChatMessage("sess-abc-123", "I want AAPL and MSFT");

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(options.body as string);
    expect(body.content).toBe("I want AAPL and MSFT");
  });

  it("returns the SendChatMessageResponse with reply and status", async () => {
    vi.stubGlobal("fetch", mockFetch(MOCK_SEND_RESPONSE));

    const result = await sendChatMessage("sess-abc-123", "Hello");

    expect(result.reply).toBe("Great, I have AAPL and MSFT. What budget?");
    expect(result.status).toBe("active");
    expect(result.extracted_slots).toEqual({ tickers: ["AAPL", "MSFT"] });
    expect(result.payload_preview).toBeNull();
  });

  it("returns payload_preview when session is pending_confirmation", async () => {
    const responseWithPreview: SendChatMessageResponse = {
      reply: "Ready to confirm!",
      status: "pending_confirmation",
      extracted_slots: { tickers: ["AAPL"], budget: 10000 },
      payload_preview: { tickers: ["AAPL"], budget: 10000 },
    };
    vi.stubGlobal("fetch", mockFetch(responseWithPreview));

    const result = await sendChatMessage("sess-abc-123", "Budget is $10k");

    expect(result.status).toBe("pending_confirmation");
    expect(result.payload_preview).toEqual({ tickers: ["AAPL"], budget: 10000 });
  });

  it("URL-encodes the session ID", async () => {
    const fetchMock = mockFetch(MOCK_SEND_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await sendChatMessage("sess/with/slashes", "Hello");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(encodeURIComponent("sess/with/slashes"));
  });

  it("throws ApiError on 404 (session not found)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SESSION_NOT_FOUND", message: "Session not found" }, 404),
    );

    await expect(sendChatMessage("bad-id", "Hello")).rejects.toThrow(ApiError);
  });

  it("throws ApiError with SESSION_NOT_FOUND code on 404", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SESSION_NOT_FOUND", message: "Session not found" }, 404),
    );

    try {
      await sendChatMessage("bad-id", "Hello");
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.errorCode).toBe("SESSION_NOT_FOUND");
    }
  });
});

// ── confirmChatRun ─────────────────────────────────────────────────────────

describe("confirmChatRun", () => {
  it("POSTs to the correct session confirm URL", async () => {
    const fetchMock = mockFetch(MOCK_CONFIRM_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await confirmChatRun("sess-abc-123");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/chat/sessions/sess-abc-123/confirm");
  });

  it("uses POST method", async () => {
    const fetchMock = mockFetch(MOCK_CONFIRM_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await confirmChatRun("sess-abc-123");

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.method).toBe("POST");
  });

  it("sends an empty body when no overrides provided", async () => {
    const fetchMock = mockFetch(MOCK_CONFIRM_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await confirmChatRun("sess-abc-123");

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(options.body as string);
    // Default body is {} — slot_overrides is not present
    expect(body.slot_overrides).toBeUndefined();
  });

  it("sends slot_overrides in the request body when provided", async () => {
    const fetchMock = mockFetch(MOCK_CONFIRM_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await confirmChatRun("sess-abc-123", {
      slot_overrides: { budget: 20000 },
    });

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(options.body as string);
    expect(body.slot_overrides).toEqual({ budget: 20000 });
  });

  it("returns the ConfirmChatSessionResponse with run_id", async () => {
    vi.stubGlobal("fetch", mockFetch(MOCK_CONFIRM_RESPONSE));

    const result = await confirmChatRun("sess-abc-123");

    expect(result.run_id).toBe("run-xyz-789");
    expect(result.session_id).toBe("sess-abc-123");
  });

  it("throws ApiError on 409 (session not in pending_confirmation state)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "INVALID_SESSION_STATE", message: "Session is not pending confirmation" },
        409,
      ),
    );

    await expect(confirmChatRun("sess-abc-123")).rejects.toThrow(ApiError);
  });

  it("throws ApiError with correct code on 409", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError(
        { error_code: "INVALID_SESSION_STATE", message: "Session is not pending confirmation" },
        409,
      ),
    );

    try {
      await confirmChatRun("sess-abc-123");
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(409);
      expect(apiErr.errorCode).toBe("INVALID_SESSION_STATE");
    }
  });

  it("URL-encodes the session ID", async () => {
    const fetchMock = mockFetch(MOCK_CONFIRM_RESPONSE);
    vi.stubGlobal("fetch", fetchMock);

    await confirmChatRun("sess/special");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(encodeURIComponent("sess/special"));
  });
});

// ── getChatSession ─────────────────────────────────────────────────────────

describe("getChatSession", () => {
  it("GETs from the correct session URL", async () => {
    const fetchMock = mockFetch(MOCK_CHAT_SESSION);
    vi.stubGlobal("fetch", fetchMock);

    await getChatSession("sess-abc-123");

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/chat/sessions/sess-abc-123");
    expect(url).not.toContain("/messages");
    expect(url).not.toContain("/confirm");
    // GET requests have no method override (defaults to GET)
    expect(options?.method).toBeUndefined();
  });

  it("returns the full ChatSession object", async () => {
    vi.stubGlobal("fetch", mockFetch(MOCK_CHAT_SESSION));

    const result = await getChatSession("sess-abc-123");

    expect(result.session_id).toBe("sess-abc-123");
    expect(result.status).toBe("active");
    expect(result.messages).toHaveLength(2);
    expect(result.messages[0].role).toBe("user");
    expect(result.messages[1].role).toBe("assistant");
    expect(result.extracted_slots).toEqual({ tickers: ["AAPL"] });
  });

  it("throws ApiError on 404 (session not found)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SESSION_NOT_FOUND", message: "Not found" }, 404),
    );

    await expect(getChatSession("nonexistent")).rejects.toThrow(ApiError);
  });

  it("throws ApiError with correct status on 404", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchError({ error_code: "SESSION_NOT_FOUND", message: "Not found" }, 404),
    );

    try {
      await getChatSession("nonexistent");
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.errorCode).toBe("SESSION_NOT_FOUND");
      expect(apiErr.message).toBe("Not found");
    }
  });

  it("URL-encodes the session ID", async () => {
    const fetchMock = mockFetch(MOCK_CHAT_SESSION);
    vi.stubGlobal("fetch", fetchMock);

    await getChatSession("sess/with/slashes");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(encodeURIComponent("sess/with/slashes"));
  });

  it("returns a session with pending_confirmation status and extracted slots", async () => {
    const pendingSession: ChatSession = {
      ...MOCK_CHAT_SESSION,
      status: "pending_confirmation",
      extracted_slots: { tickers: ["AAPL", "MSFT"], budget: 50000 },
    };
    vi.stubGlobal("fetch", mockFetch(pendingSession));

    const result = await getChatSession("sess-abc-123");

    expect(result.status).toBe("pending_confirmation");
    expect(result.extracted_slots.tickers).toEqual(["AAPL", "MSFT"]);
    expect(result.extracted_slots.budget).toBe(50000);
  });
});
