import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "@/store/appStore";
import { api } from "@/lib/api";
import { StreamEventSchema } from "@/lib/schemas";

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
          // continue polling
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

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
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
          addEvents([data]);
        }
      } catch (err) {
        console.warn("[Q-CONSENSUS] SSE parse error:", err);
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
