import {
  StatusSchema, RunResponseSchema, RunAsyncResponseSchema,
  ResultSchema, StreamEventSchema, VerifyResponseSchema,
  MetricsSchema, QuantumVsClassicalSchema,
  type RunRequest, type Status, type RunResponse, type RunAsyncResponse,
  type Result, type StreamEvent, type VerifyResponse, type Metrics, type QuantumVsClassical,
} from './schemas';
import type { z } from 'zod';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function safeFetch<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new ApiError(res.status, `${res.status}: ${text}`);
  }
  const json = await res.json();
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

  getEvents: (runId: string) => safeFetch<StreamEvent[]>(`/api/events/${runId}`, StreamEventSchema.array()),

  verify: (runId: string) => safeFetch<VerifyResponse>(`/api/verify/${runId}`, VerifyResponseSchema),

  replay: (runId: string) => fetch(`${BASE}/api/replay/${runId}`, { method: 'POST' }),

  getMetrics: () => safeFetch<Metrics>('/api/metrics', MetricsSchema),

  getQuantumVsClassical: () => safeFetch<QuantumVsClassical>('/api/metrics/quantum-vs-classical', QuantumVsClassicalSchema),

  streamUrl: (runId: string) => `${BASE}/api/stream/${runId}`,
};

export { ApiError };
