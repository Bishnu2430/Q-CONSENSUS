import { describe, it, expect } from "vitest";
import { deriveGraphSnapshots, deriveAgentDisplayNames } from "./graphSnapshots";
import type { StreamEvent } from "@/lib/schemas";

function makeEvent(eventType: string, payload: Record<string, unknown>): StreamEvent {
  return {
    event_id: `${eventType}-${Math.random()}`,
    run_id: "run-1",
    event_type: eventType,
    payload,
  };
}

describe("deriveGraphSnapshots", () => {
  it("returns no snapshots when there are no relevant events", () => {
    const events = [makeEvent("agent_prompted", { agent_id: "a" })];
    expect(deriveGraphSnapshots(events)).toEqual([]);
  });

  it("builds a snapshot from a quantum_randomness event using the selected policy", () => {
    const events = [
      makeEvent("quantum_randomness", {
        agent_ids: ["a", "b"],
        selected_policy: "quantum",
        quantum_similarity: [
          [1, 0.5],
          [0.5, 1],
        ],
        classical_similarity: [
          [1, 0.2],
          [0.2, 1],
        ],
        quantum_partition: [0, 1],
        classical_partition: [0, 0],
      }),
    ];

    const snapshots = deriveGraphSnapshots(events);
    expect(snapshots).toHaveLength(1);
    expect(snapshots[0].stage).toBe("round0");
    expect(snapshots[0].agentIds).toEqual(["a", "b"]);
    expect(snapshots[0].similarity).toEqual([
      [1, 0.5],
      [0.5, 1],
    ]);
    expect(snapshots[0].partition).toEqual([0, 1]);
  });

  it("uses the classical similarity/partition when selected_policy is classical", () => {
    const events = [
      makeEvent("quantum_scheduling", {
        agent_ids: ["a", "b"],
        selected_policy: "classical",
        quantum_similarity: [
          [1, 0.9],
          [0.9, 1],
        ],
        classical_similarity: [
          [1, 0.1],
          [0.1, 1],
        ],
        quantum_partition: [0, 0],
        classical_partition: [0, 1],
      }),
    ];

    const snapshots = deriveGraphSnapshots(events);
    expect(snapshots[0].similarity).toEqual([
      [1, 0.1],
      [0.1, 1],
    ]);
    expect(snapshots[0].partition).toEqual([0, 1]);
  });

  it("skips malformed events instead of throwing", () => {
    const events = [
      makeEvent("consensus_weights", { agent_ids: ["a"], selected_policy: "quantum" }), // missing similarity
      makeEvent("consensus_weights", {
        agent_ids: ["a", "b", "c"],
        selected_policy: "quantum",
        quantum_similarity: [[1, 0.5]], // wrong size for 3 agents
      }),
    ];
    expect(deriveGraphSnapshots(events)).toEqual([]);
  });

  it("produces snapshots in event order across all three stages", () => {
    const base = {
      agent_ids: ["a", "b"],
      selected_policy: "quantum",
      quantum_similarity: [
        [1, 0.5],
        [0.5, 1],
      ],
      quantum_partition: [0, 1],
    };
    const events = [
      makeEvent("quantum_randomness", base),
      makeEvent("quantum_scheduling", base),
      makeEvent("consensus_weights", base),
    ];
    const snapshots = deriveGraphSnapshots(events);
    expect(snapshots.map((s) => s.stage)).toEqual(["round0", "pre_critique", "consensus"]);
  });
});

describe("deriveAgentDisplayNames", () => {
  it("maps agent_id to the first display_name seen", () => {
    const events = [
      makeEvent("agent_prompted", { agent_id: "proposer", display_name: "Proposer" }),
      makeEvent("agent_responded", { agent_id: "proposer", display_name: "Proposer (again)" }),
      makeEvent("agent_responded", { agent_id: "skeptic", display_name: "Skeptic" }),
    ];
    expect(deriveAgentDisplayNames(events)).toEqual({
      proposer: "Proposer",
      skeptic: "Skeptic",
    });
  });

  it("returns an empty map when there are no agent events", () => {
    expect(deriveAgentDisplayNames([])).toEqual({});
  });
});
