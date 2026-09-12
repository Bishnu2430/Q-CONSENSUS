import type { StreamEvent } from "@/lib/schemas";

export type GraphStage = "round0" | "pre_critique" | "consensus";

export interface GraphSnapshot {
  stage: GraphStage;
  label: string;
  agentIds: string[];
  similarity: number[][];
  partition: number[];
  selectedPolicy: "quantum" | "classical" | string;
}

const STAGE_BY_EVENT: Record<string, { stage: GraphStage; label: string }> = {
  quantum_randomness: { stage: "round0", label: "Round 0 · role diversity" },
  quantum_scheduling: {
    stage: "pre_critique",
    label: "Pre-critique · answer diversity",
  },
  consensus_weights: { stage: "consensus", label: "Consensus · final agreement" },
};

function isNumberMatrix(value: unknown): value is number[][] {
  return (
    Array.isArray(value) &&
    value.every((row) => Array.isArray(row) && row.every((v) => typeof v === "number"))
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((v) => typeof v === "number");
}

/** Build the (up to three) graph snapshots -- one per stage of the run --
 * from the raw event log. Pure function: same events always produce the
 * same snapshots, so this is easy to unit test and safe to call from a
 * useMemo on every render without extra state in the store. */
export function deriveGraphSnapshots(events: StreamEvent[]): GraphSnapshot[] {
  const snapshots: GraphSnapshot[] = [];

  for (const event of events) {
    const meta = STAGE_BY_EVENT[event.event_type];
    if (!meta) continue;

    const payload = event.payload as Record<string, unknown>;
    const agentIds = payload.agent_ids;
    const selectedPolicy = payload.selected_policy;
    if (!isStringArray(agentIds) || typeof selectedPolicy !== "string") continue;

    const similarityKey =
      selectedPolicy === "quantum" ? "quantum_similarity" : "classical_similarity";
    const partitionKey =
      selectedPolicy === "quantum" ? "quantum_partition" : "classical_partition";

    const similarity = payload[similarityKey];
    const partition = payload[partitionKey];

    if (!isNumberMatrix(similarity) || similarity.length !== agentIds.length) continue;

    snapshots.push({
      stage: meta.stage,
      label: meta.label,
      agentIds,
      similarity,
      partition: isNumberArray(partition) ? partition : agentIds.map(() => 0),
      selectedPolicy,
    });
  }

  return snapshots;
}

/** Map agent_id -> display_name by scanning agent_prompted/agent_responded
 * events. Falls back to the agent_id itself if no display name was seen. */
export function deriveAgentDisplayNames(events: StreamEvent[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const event of events) {
    if (event.event_type !== "agent_prompted" && event.event_type !== "agent_responded") {
      continue;
    }
    const payload = event.payload as Record<string, unknown>;
    const agentId = payload.agent_id;
    const displayName = payload.display_name;
    if (typeof agentId === "string" && typeof displayName === "string" && !names[agentId]) {
      names[agentId] = displayName;
    }
  }
  return names;
}
