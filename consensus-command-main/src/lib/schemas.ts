import { z } from "zod";

// --- Endpoint Schemas ---

export const StatusSchema = z.object({
  cpu_percent: z.number(),
  mem_total: z.number(),
  mem_used: z.number(),
  mem_percent: z.number(),
  agents_loaded: z.number(),
  agents_config_path: z.string(),
  contract_anchor_enabled: z.boolean(),
  contract_anchor_init_error: z.string().nullable(),
});
export type Status = z.infer<typeof StatusSchema>;

export const RunResponseSchema = z.object({
  run_id: z.string(),
  final_answer: z.string(),
  commitment: z.string(),
  anchor_tx_hash: z.string().nullable(),
});
export type RunResponse = z.infer<typeof RunResponseSchema>;

export const RunAsyncResponseSchema = z.object({
  run_id: z.string(),
  status: z.literal("running"),
});
export type RunAsyncResponse = z.infer<typeof RunAsyncResponseSchema>;

export const RunRequestSchema = z.object({
  query: z.string().min(1).max(4000),
  max_rounds: z.number().int().min(1).max(3),
  agent_count: z.number().int().min(2).max(10),
  enable_web_context: z.boolean().optional(),
  web_context_query: z.string().min(1).max(4000).optional(),
  web_context_max_items: z.number().int().min(1).max(8).optional(),
  use_quantum_randomness: z.boolean(),
  use_quantum_weights: z.boolean(),
  use_quantum_scheduling: z.boolean(),
});
export type RunRequest = z.infer<typeof RunRequestSchema>;

export const ResultSchema = z.object({
  run_id: z.string(),
  status: z.enum(["running", "completed", "failed", "not_found"]),
  final_answer: z.string().optional(),
  commitment: z.string().optional(),
  anchor_tx_hash: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type Result = z.infer<typeof ResultSchema>;

export const ProgressSchema = z.object({
  current_stage: z.string(),
  agents_completed: z.number().int(),
  total_agents: z.number().int(),
  time_elapsed_ms: z.number(),
  estimated_total_ms: z.number(),
});
export type Progress = z.infer<typeof ProgressSchema>;

export const EventPayloadSchema = z.record(z.string(), z.unknown());

export const StreamEventSchema = z.object({
  event_id: z.string(),
  run_id: z.string(),
  ts: z.union([z.number(), z.string()]).optional(),
  ts_unix_ms: z.number().optional(),
  event_type: z.string(),
  payload: EventPayloadSchema,
  prev_event_hash: z.string().nullable().optional(),
  event_hash: z.string().optional(),
});
export type StreamEvent = z.infer<typeof StreamEventSchema>;

export const VerifyResponseSchema = z
  .object({
    verified: z.boolean().optional(),
    reason: z.string().optional(),
    details: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();
export type VerifyResponse = z.infer<typeof VerifyResponseSchema>;

export const MetricsSchema = z.record(z.string(), z.unknown());
export type Metrics = z.infer<typeof MetricsSchema>;

export const QuantumVsClassicalSchema = z.record(z.string(), z.unknown());
export type QuantumVsClassical = z.infer<typeof QuantumVsClassicalSchema>;
