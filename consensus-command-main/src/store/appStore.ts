import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { StreamEvent, Status, Result, Progress } from "@/lib/schemas";

interface RunCache {
  events: StreamEvent[];
  result?: Result;
  verification?: Record<string, unknown>;
}

interface RunMeta {
  mode: "sync" | "async";
  agentCount: number;
  maxRounds: number;
}

type RunStatus = "idle" | "running" | "completed" | "failed";
type ConnectionState = "connected" | "degraded" | "disconnected";
type StreamState = "idle" | "connected" | "reconnecting" | "closed";

interface AppState {
  // Run state
  currentRunId: string | null;
  runStatus: RunStatus;
  runMeta: RunMeta | null;
  setRun: (runId: string, status: RunStatus, meta?: RunMeta) => void;
  setRunStatus: (status: RunStatus) => void;
  clearRun: () => void;

  // Connection
  apiConnection: ConnectionState;
  setApiConnection: (s: ConnectionState) => void;

  // Stream
  streamState: StreamState;
  setStreamState: (s: StreamState) => void;

  // Events
  events: StreamEvent[];
  addEvents: (evts: StreamEvent[]) => void;
  clearEvents: () => void;

  // Result cache
  result: Result | null;
  setResult: (r: Result | null) => void;

  // Progress tracking
  progress: Progress | null;
  setProgress: (p: Progress | null) => void;

  // System status
  systemStatus: Status | null;
  setSystemStatus: (s: Status) => void;

  // Per-run cache
  runCaches: Record<string, RunCache>;
  cacheEvents: (runId: string, evts: StreamEvent[]) => void;
  cacheResult: (runId: string, r: Result) => void;

  // Verification history
  verificationHistory: {
    runId: string;
    result: Record<string, unknown>;
    ts: number;
  }[];
  addVerification: (runId: string, result: Record<string, unknown>) => void;

  // UI prefs (persisted)
  autoScroll: boolean;
  toggleAutoScroll: () => void;
  compactMode: boolean;
  toggleCompactMode: () => void;

  // Filters
  eventTypeFilter: string[];
  setEventTypeFilter: (f: string[]) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;

  // Active tab
  activeTab: string;
  setActiveTab: (t: string) => void;
}

const MAX_EVENTS_PER_RUN = 5000;
const MAX_VERIFICATION_HISTORY = 10;

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      currentRunId: null,
      runStatus: "idle",
      runMeta: null,
      setRun: (runId, status, meta) =>
        set({
          currentRunId: runId,
          runStatus: status,
          runMeta: meta ?? null,
          events: [],
          result: null,
        }),
      setRunStatus: (status) => set({ runStatus: status }),
      clearRun: () =>
        set({
          currentRunId: null,
          runStatus: "idle",
          runMeta: null,
          events: [],
          result: null,
          streamState: "idle",
        }),

      apiConnection: "disconnected",
      setApiConnection: (s) => set({ apiConnection: s }),

      streamState: "idle",
      setStreamState: (s) => set({ streamState: s }),

      events: [],
      addEvents: (evts) => {
        const current = get().events;
        const existingIds = new Set(current.map((e) => e.event_id));
        const newEvts = evts.filter((e) => !existingIds.has(e.event_id));
        if (newEvts.length === 0) return;
        const merged = [...current, ...newEvts].slice(-MAX_EVENTS_PER_RUN);
        set({ events: merged });
      },
      clearEvents: () => set({ events: [] }),

      result: null,
      setResult: (r) => set({ result: r }),

      progress: null,
      setProgress: (p) => set({ progress: p }),

      systemStatus: null,
      setSystemStatus: (s) => set({ systemStatus: s }),

      runCaches: {},
      cacheEvents: (runId, evts) =>
        set((state) => ({
          runCaches: {
            ...state.runCaches,
            [runId]: {
              ...state.runCaches[runId],
              events: evts.slice(-MAX_EVENTS_PER_RUN),
            },
          },
        })),
      cacheResult: (runId, r) =>
        set((state) => ({
          runCaches: {
            ...state.runCaches,
            [runId]: {
              ...state.runCaches[runId],
              events: state.runCaches[runId]?.events ?? [],
              result: r,
            },
          },
        })),

      verificationHistory: [],
      addVerification: (runId, result) =>
        set((state) => ({
          verificationHistory: [
            { runId, result, ts: Date.now() },
            ...state.verificationHistory,
          ].slice(0, MAX_VERIFICATION_HISTORY),
        })),

      autoScroll: true,
      toggleAutoScroll: () => set((s) => ({ autoScroll: !s.autoScroll })),
      compactMode: false,
      toggleCompactMode: () => set((s) => ({ compactMode: !s.compactMode })),

      eventTypeFilter: [],
      setEventTypeFilter: (f) => set({ eventTypeFilter: f }),
      searchQuery: "",
      setSearchQuery: (q) => set({ searchQuery: q }),

      activeTab: "control",
      setActiveTab: (t) => set({ activeTab: t }),
    }),
    {
      name: "q-consensus-prefs",
      partialize: (state) => ({
        autoScroll: state.autoScroll,
        compactMode: state.compactMode,
      }),
    },
  ),
);
