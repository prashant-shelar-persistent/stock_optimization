/**
 * useWebSocket — custom hook managing the WebSocket lifecycle for a run.
 *
 * Responsibilities:
 *   - Opens a WebSocket via openProgressSocket(runId) when runId is non-null
 *   - Parses incoming WebSocketMessage objects (typed from @/types/api)
 *   - On "progress" messages: calls uiStore.addAgentProgress()
 *   - On "result"  messages: calls uiStore.setOptimizationResult() + setIsOptimizing(false)
 *   - On "error"   messages: shows a toast error and sets isOptimizing(false)
 *   - Handles reconnection on unexpected close (up to 3 retries with 2 s backoff)
 *   - Cleans up the WebSocket on unmount or when runId changes
 *
 * Returns: { connectionState }
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { openProgressSocket } from "@/lib/api";
import { useUIStore } from "@/store/uiStore";
import { useToast } from "@/hooks/use-toast";
import type { WebSocketMessage } from "@/types/api";

export type ConnectionState = "connecting" | "open" | "closed" | "error";

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

interface UseWebSocketReturn {
  connectionState: ConnectionState;
}

export function useWebSocket(runId: string | null): UseWebSocketReturn {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("closed");

  const socketRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Keep a stable ref to runId so the cleanup/retry logic always sees the latest value
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  const addAgentProgress = useUIStore((s) => s.addAgentProgress);
  const setOptimizationResult = useUIStore((s) => s.setOptimizationResult);
  const setIsOptimizing = useUIStore((s) => s.setIsOptimizing);
  const { toast } = useToast();

  // ── Message handler ────────────────────────────────────────────────────────

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      let msg: WebSocketMessage;
      try {
        msg = JSON.parse(event.data as string) as WebSocketMessage;
      } catch {
        console.warn("[useWebSocket] Failed to parse message:", event.data);
        return;
      }

      switch (msg.type) {
        case "progress":
          addAgentProgress(msg);
          break;

        case "result":
          setOptimizationResult(msg.result);
          setIsOptimizing(false);
          break;

        case "error":
          setIsOptimizing(false);
          toast({
            variant: "destructive",
            title: `Agent error: ${msg.error_code}`,
            description: msg.message,
          });
          break;

        default:
          console.warn("[useWebSocket] Unknown message type:", msg);
      }
    },
    [addAgentProgress, setOptimizationResult, setIsOptimizing, toast],
  );

  // ── Connection factory ─────────────────────────────────────────────────────

  const connect = useCallback(
    (id: string) => {
      // Close any existing socket before opening a new one
      if (socketRef.current) {
        socketRef.current.onclose = null; // prevent retry logic from firing
        socketRef.current.close();
        socketRef.current = null;
      }

      setConnectionState("connecting");

      const ws = openProgressSocket(id);
      socketRef.current = ws;

      ws.onopen = () => {
        retryCountRef.current = 0;
        setConnectionState("open");
      };

      ws.onmessage = handleMessage;

      ws.onerror = () => {
        setConnectionState("error");
      };

      ws.onclose = (event) => {
        // Normal closure (code 1000) or the component unmounted — do not retry
        if (event.code === 1000 || runIdRef.current !== id) {
          setConnectionState("closed");
          return;
        }

        // Unexpected closure — attempt reconnection with backoff
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current += 1;
          const delay = RETRY_DELAY_MS * retryCountRef.current;
          console.info(
            `[useWebSocket] Connection closed (code ${event.code}). ` +
              `Retrying in ${delay}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})…`,
          );
          retryTimerRef.current = setTimeout(() => {
            if (runIdRef.current === id) {
              connect(id);
            }
          }, delay);
        } else {
          console.warn(
            `[useWebSocket] Max retries (${MAX_RETRIES}) reached for run ${id}.`,
          );
          setConnectionState("error");
          setIsOptimizing(false);
          toast({
            variant: "destructive",
            title: "Connection lost",
            description:
              "Lost connection to the optimization server. Please refresh and try again.",
          });
        }
      };
    },
    [handleMessage, setIsOptimizing, toast],
  );

  // ── Effect: open/close socket when runId changes ───────────────────────────

  useEffect(() => {
    if (!runId) {
      // No active run — ensure any existing socket is closed
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
        socketRef.current = null;
      }
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      retryCountRef.current = 0;
      setConnectionState("closed");
      return;
    }

    connect(runId);

    // Cleanup: close socket and cancel any pending retry when runId changes or
    // the component unmounts
    return () => {
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.onclose = null; // prevent retry logic
        socketRef.current.close(1000, "Component unmounted");
        socketRef.current = null;
      }
      retryCountRef.current = 0;
    };
  }, [runId, connect]);

  return { connectionState };
}
