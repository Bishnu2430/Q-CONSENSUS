export interface SpanningTreeEdge {
  from: string;
  to: string;
  weight: number;
  step: number;
}

export interface SpanningTreeResult {
  /** Agent ids in the order they joined the tree; order[0] === startId. */
  order: string[];
  /** Tree edges in discovery order (n-1 edges for n reachable agents). */
  edges: SpanningTreeEdge[];
}

/** Prim's algorithm using similarity as edge weight: greedily grows a
 * maximum-weight spanning tree outward from `startId`, at each step adding
 * whichever available connection from the current tree to an agent not yet
 * in it is strongest. Used to drive the "reveal from this agent" click
 * interaction (only tree edges stay visible, discovered in this order) and
 * the default entrance animation (nodes/edges appear in the order a
 * spanning tree from the first agent would reach them, so the graph reads
 * as growing outward rather than popping in all at once).
 */
export function computeGreedySpanningTree(
  agentIds: string[],
  similarity: number[][],
  startId: string,
): SpanningTreeResult {
  const n = agentIds.length;
  const startIdx = agentIds.indexOf(startId);
  if (n === 0 || startIdx === -1) return { order: [], edges: [] };

  const visited = new Set<number>([startIdx]);
  const order = [startId];
  const edges: SpanningTreeEdge[] = [];

  while (visited.size < n) {
    let best: { from: number; to: number; weight: number } | null = null;
    for (const v of visited) {
      for (let u = 0; u < n; u += 1) {
        if (visited.has(u)) continue;
        const w = similarity[v]?.[u] ?? 0;
        if (!best || w > best.weight) best = { from: v, to: u, weight: w };
      }
    }
    if (!best) break; // remaining agents unreachable (shouldn't happen with a full matrix)

    visited.add(best.to);
    order.push(agentIds[best.to]);
    edges.push({
      from: agentIds[best.from],
      to: agentIds[best.to],
      weight: best.weight,
      step: edges.length,
    });
  }

  return { order, edges };
}
