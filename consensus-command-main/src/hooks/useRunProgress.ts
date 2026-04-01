import { useCallback, useEffect, useRef } from "react";
import { useAppStore } from "@/store/appStore";
import { api } from "@/lib/api";
import { ProgressSchema } from "@/lib/schemas";

/**
 * Unified progress polling hook.
 * Polls /api/run/{run_id}/progress at regular intervals and updates appStore.
 * Includes rate limiting to prevent excessive requests.
 */
export function useRunProgress(runId: string | null) {
  const { setProgress } = useAppStore();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastPollTimeRef = useRef<number>(0);
  const MIN_POLL_INTERVAL_MS = 300; // Rate limit: don't poll more than every 300ms

  const pollProgress = useCallback(async () => {
    if (!runId) return;

    // Rate limiting: skip if we polled too recently
    const now = Date.now();
    if (now - lastPollTimeRef.current < MIN_POLL_INTERVAL_MS) {
      return;
    }
    lastPollTimeRef.current = now;

    try {
      const response = await fetch(`/api/run/${runId}/progress`);
      if (response.ok) {
        const data = await response.json();
        const parsed = ProgressSchema.safeParse({
          current_stage: data.current_stage,
          agents_completed: data.agents_completed,
          total_agents: data.total_agents,
          time_elapsed_ms: data.time_elapsed_ms,
          estimated_total_ms: data.estimated_total_ms,
        });
        if (parsed.success) {
          setProgress(parsed.data);
        }
      }
    } catch {
      // Continue polling on error
    }
  }, [runId, setProgress]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      pollProgress();
    }, 500); // Poll every 500ms (same cadence as before)
  }, [pollProgress]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setProgress(null);
  }, [setProgress]);

  useEffect(() => {
    if (!runId) {
      stopPolling();
      return;
    }

    // Start polling when runId changes
    startPolling();

    return () => {
      stopPolling();
    };
  }, [runId, startPolling, stopPolling]);
}
