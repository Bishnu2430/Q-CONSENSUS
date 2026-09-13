import { describe, it, expect } from "vitest";
import { computeGreedySpanningTree } from "./greedySpanningTree";

describe("computeGreedySpanningTree", () => {
  it("returns an empty result for an unknown or missing start id", () => {
    expect(computeGreedySpanningTree([], [], "a")).toEqual({ order: [], edges: [] });
    expect(computeGreedySpanningTree(["a", "b"], [[1, 0.5], [0.5, 1]], "z")).toEqual({
      order: [],
      edges: [],
    });
  });

  it("a single agent has no edges but is its own order", () => {
    const result = computeGreedySpanningTree(["a"], [[1]], "a");
    expect(result.order).toEqual(["a"]);
    expect(result.edges).toEqual([]);
  });

  it("greedily picks the strongest available edge at each step", () => {
    // a-b weak, a-c strong, b-c strongest: starting from a, Prim's should
    // take a->c first (strongest edge touching the tree), then c->b
    // (stronger than a->b).
    const agentIds = ["a", "b", "c"];
    const similarity = [
      [1, 0.1, 0.9],
      [0.1, 1, 0.8],
      [0.9, 0.8, 1],
    ];
    const result = computeGreedySpanningTree(agentIds, similarity, "a");
    expect(result.order).toEqual(["a", "c", "b"]);
    expect(result.edges).toEqual([
      { from: "a", to: "c", weight: 0.9, step: 0 },
      { from: "c", to: "b", weight: 0.8, step: 1 },
    ]);
  });

  it("reaches every agent exactly once for a fully-connected matrix", () => {
    const agentIds = ["p", "q", "r", "s"];
    const similarity = [
      [1, 0.4, 0.2, 0.6],
      [0.4, 1, 0.3, 0.1],
      [0.2, 0.3, 1, 0.5],
      [0.6, 0.1, 0.5, 1],
    ];
    const result = computeGreedySpanningTree(agentIds, similarity, "q");
    expect(result.order).toHaveLength(4);
    expect(new Set(result.order)).toEqual(new Set(agentIds));
    expect(result.edges).toHaveLength(3);
    // Every edge endpoint must already be in the tree at the time it's added.
    const seen = new Set(["q"]);
    for (const edge of result.edges) {
      expect(seen.has(edge.from)).toBe(true);
      seen.add(edge.to);
    }
  });

  it("starting agent is always order[0]", () => {
    const agentIds = ["x", "y", "z"];
    const similarity = [
      [1, 0.5, 0.5],
      [0.5, 1, 0.5],
      [0.5, 0.5, 1],
    ];
    const result = computeGreedySpanningTree(agentIds, similarity, "z");
    expect(result.order[0]).toBe("z");
  });
});
