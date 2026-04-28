import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "@/store/appStore";
import { api } from "@/lib/api";
import { StreamEventSchema, type StreamEvent } from "@/lib/schemas";

function parseSSEData(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    const sanitized = raw.replace(/[\u0000-\u001F]/g, "");
    return JSON.parse(sanitized);
  }
}

function normalizeSseEvent(raw: unknown): StreamEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const src = raw as Record<string, unknown>;
  const runId = typeof src.run_id === "string" ? src.run_id : "";
  const eventType = typeof src.event_type === "string" ? src.event_type : "";
  if (!runId || !eventType) return null;

  const ts =
    typeof src.ts_unix_ms === "number"
      ? src.ts_unix_ms
      : typeof src.ts === "number"
        ? src.ts
        : Date.now();

  const payload =
    src.payload && typeof src.payload === "object"
      ? (src.payload as Record<string, unknown>)
      : { value: src.payload ?? null };

  const event: StreamEvent = {
    event_id:
      typeof src.event_id === "string" && src.event_id.length > 0
        ? src.event_id
        : `${runId}-${eventType}-${ts}`,
    run_id: runId,
    event_type: eventType,
    payload,
    ts_unix_ms: typeof src.ts_unix_ms === "number" ? src.ts_unix_ms : ts,
    ts: typeof src.ts === "string" || typeof src.ts === "number" ? src.ts : ts,
    prev_event_hash:
      typeof src.prev_event_hash === "string" || src.prev_event_hash === null
        ? src.prev_event_hash
        : null,
    event_hash: typeof src.event_hash === "string" ? src.event_hash : undefined,
  };

  const parsed = StreamEventSchema.safeParse(event);
  return parsed.success ? parsed.data : null;
}

export function useSSEStream(runId: string | null) {
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { addEvents, setStreamState, setRunStatus, setResult } = useAppStore();

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (rid: string) => {
      if (pollRef.current) return;
      pollRef.current = setInterval(async () => {
        try {
          const events = await api.getEvents(rid);
          addEvents(events);
        } catch {
          // continue polling events
        }

        try {
          const result = await api.getResult(rid);
          if (result.status === "completed" || result.status === "failed") {
            setResult(result);
            setRunStatus(result.status);
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setStreamState("closed");
          }
        } catch {
          // continue polling result
        }
      }, 1200);
    },
    [addEvents, setResult, setRunStatus, setStreamState],
  );

  useEffect(() => {
    if (!runId) return;

    closeStream();
    setStreamState("connected");

    // Hydrate any events that may have been persisted before stream subscription.
    api
      .getEvents(runId)
      .then(addEvents)
      .catch(() => {});

    const es = new EventSource(api.streamUrl(runId));
    esRef.current = es;

    // Keep polling active as a reliability fallback in case stream frames are malformed.
    startPolling(runId);

    es.onmessage = (e) => {
      try {
        const data = parseSSEData(e.data);
        const parsed = StreamEventSchema.safeParse(data);
        if (parsed.success) {
          addEvents([parsed.data]);
          if (
            parsed.data.event_type === "run_committed" ||
            parsed.data.event_type === "final_answer"
          ) {
            // Fetch final result
            api
              .getResult(runId)
              .then((r) => {
                setResult(r);
                if (r.status === "completed" || r.status === "failed") {
                  setRunStatus(r.status);
                }
              })
              .catch(() => {});
          }
        } else {
          console.warn(
            "[Q-CONSENSUS] SSE event schema mismatch:",
            parsed.error.issues,
          );
          const normalized = normalizeSseEvent(data);
          if (normalized) {
            addEvents([normalized]);
          }
        }
      } catch (err) {
        console.warn("[Q-CONSENSUS] SSE parse error:", err);
        setStreamState("reconnecting");
        startPolling(runId);
      }
    };

    es.onerror = () => {
      setStreamState("reconnecting");
      es.close();
      esRef.current = null;
      // Fallback to polling
      startPolling(runId);
    };

    return () => {
      closeStream();
      setStreamState("closed");
    };
  }, [
    runId,
    addEvents,
    setStreamState,
    setRunStatus,
    setResult,
    closeStream,
    startPolling,
  ]);

  return { closeStream };
}
