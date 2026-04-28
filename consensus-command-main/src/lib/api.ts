import {
  StatusSchema, RunResponseSchema, RunAsyncResponseSchema,
  ResultSchema, StreamEventSchema, VerifyResponseSchema,
  ProgressSchema,
  MetricsSchema, QuantumVsClassicalSchema,
  type RunRequest, type Status, type RunResponse, type RunAsyncResponse,
  type Result, type StreamEvent, type VerifyResponse, type Progress, type Metrics, type QuantumVsClassical,
} from './schemas';
import type { z } from 'zod';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function sanitizeControlChars(raw: string): string {
  return raw.replace(/[\u0000-\u001F]/g, '');
}

function parseJsonWithFallback(raw: string, url: string): unknown {
  try {
    return JSON.parse(raw);
  } catch (err) {
    const sanitized = sanitizeControlChars(raw);
    try {
      return JSON.parse(sanitized);
    } catch {
      console.warn(`[Q-CONSENSUS] JSON parse failed for ${url}:`, err);
      throw new ApiError(500, `Invalid JSON payload for ${url}`);
    }
  }
}

function normalizeEvent(raw: unknown, idx: number): StreamEvent | null {
  if (!raw || typeof raw !== 'object') return null;
  const src = raw as Record<string, unknown>;
  const runId = typeof src.run_id === 'string' ? src.run_id : '';
  const eventType = typeof src.event_type === 'string' ? src.event_type : '';
  if (!runId || !eventType) return null;

  const ts =
    typeof src.ts_unix_ms === 'number'
      ? src.ts_unix_ms
      : typeof src.ts === 'number'
        ? src.ts
        : Date.now();

  const payload =
    src.payload && typeof src.payload === 'object'
      ? (src.payload as Record<string, unknown>)
      : { value: src.payload ?? null };

  const candidate: StreamEvent = {
    event_id:
      typeof src.event_id === 'string' && src.event_id.length > 0
        ? src.event_id
        : `${runId}-${eventType}-${ts}-${idx}`,
    run_id: runId,
    event_type: eventType,
    payload,
    ts_unix_ms: typeof src.ts_unix_ms === 'number' ? src.ts_unix_ms : ts,
    ts: typeof src.ts === 'string' || typeof src.ts === 'number' ? src.ts : ts,
    prev_event_hash:
      typeof src.prev_event_hash === 'string' || src.prev_event_hash === null
        ? src.prev_event_hash
        : null,
    event_hash: typeof src.event_hash === 'string' ? src.event_hash : undefined,
  };

  const parsed = StreamEventSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

async function safeFetch<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new ApiError(res.status, `${res.status}: ${text}`);
  }
  const text = await res.text();
  const json = parseJsonWithFallback(text, url);
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    console.warn(`[Q-CONSENSUS] Schema mismatch for ${url}:`, parsed.error.issues);
    // Return raw json to degrade gracefully
    return json as T;
  }
  return parsed.data;
}

export const api = {
  getStatus: () => safeFetch<Status>('/api/status', StatusSchema),

  run: (body: RunRequest) => safeFetch<RunResponse>('/api/run', RunResponseSchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),

  runAsync: (body: RunRequest) => safeFetch<RunAsyncResponse>('/api/run_async', RunAsyncResponseSchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),

  getResult: (runId: string) => safeFetch<Result>(`/api/result/${runId}`, ResultSchema),

  getProgress: (runId: string) => safeFetch<Progress>(`/api/run/${runId}/progress`, ProgressSchema),

  getEvents: async (runId: string) => {
    const res = await fetch(`${BASE}/api/events/${runId}`);
    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error');
      throw new ApiError(res.status, `${res.status}: ${text}`);
    }
    const text = await res.text();
    const json = parseJsonWithFallback(text, `/api/events/${runId}`);
    if (!Array.isArray(json)) return [];
    return json
      .map((ev, idx) => normalizeEvent(ev, idx))
      .filter((ev): ev is StreamEvent => ev !== null);
  },

  verify: (runId: string) => safeFetch<VerifyResponse>(`/api/verify/${runId}`, VerifyResponseSchema),

  replay: (runId: string) => fetch(`${BASE}/api/replay/${runId}`, { method: 'POST' }),

  getMetrics: () => safeFetch<Metrics>('/api/metrics', MetricsSchema),

  getQuantumVsClassical: () => safeFetch<QuantumVsClassical>('/api/metrics/quantum-vs-classical', QuantumVsClassicalSchema),

  getBlockchainHistory: (limit = 500) =>
    fetch(`${BASE}/api/blockchain/history?limit=${limit}`).then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => 'Unknown error');
        throw new ApiError(res.status, `${res.status}: ${text}`);
      }
      return res.json() as Promise<Record<string, unknown>>;
    }),

  streamUrl: (runId: string) => `${BASE}/api/stream/${runId}`,
};

export { ApiError };
