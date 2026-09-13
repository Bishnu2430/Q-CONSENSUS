import { useEffect, useMemo, useRef, useState } from "react";
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from "d3-force";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { deriveGraphSnapshots, deriveAgentDisplayNames } from "@/lib/graphSnapshots";
import { computeGreedySpanningTree } from "@/lib/greedySpanningTree";
import { agentColorVar } from "@/lib/agentColors";
import { Network, Radar } from "lucide-react";

interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface LayoutEdge {
  source: string;
  target: string;
  weight: number;
}

const WIDTH = 560;
const HEIGHT = 460;
const SIMILARITY_EDGE_THRESHOLD = 0.15;
const GROWTH_STAGGER_S = 0.12;
const REVEAL_STAGGER_S = 0.28;

/** Runs the (synchronous, deterministic) force simulation and returns final
 * node positions. This is a plain computation, not a side effect -- calling
 * it from useMemo avoids the whole class of effect-depends-on-derived-data
 * bugs a useEffect+useState pairing invites here. */
function computeForceLayout(
  agentIds: string[],
  edges: LayoutEdge[],
): Record<string, { x: number; y: number }> {
  if (agentIds.length === 0) return {};

  const nodes: SimNode[] = agentIds.map((id, i) => ({
    id,
    x: WIDTH / 2 + Math.cos((i / agentIds.length) * Math.PI * 2) * 150,
    y: HEIGHT / 2 + Math.sin((i / agentIds.length) * Math.PI * 2) * 150,
    vx: 0,
    vy: 0,
  }));

  // d3-force's forceLink mutates its link objects in place (resolving
  // .source/.target from id strings to node references). Clone so it never
  // touches the caller's edge objects.
  const simEdges = edges.map((e) => ({ ...e }));

  const sim = forceSimulation(nodes)
    .force(
      "link",
      forceLink<SimNode, LayoutEdge & { source: string | SimNode; target: string | SimNode }>(simEdges)
        .id((d) => d.id)
        .distance((d) => 270 - (d as unknown as LayoutEdge).weight * 130)
        .strength((d) => (d as unknown as LayoutEdge).weight * 0.5),
    )
    .force("charge", forceManyBody().strength(-620))
    .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
    .force("collide", forceCollide(72))
    .stop();

  for (let i = 0; i < 260; i += 1) sim.tick();

  const next: Record<string, { x: number; y: number }> = {};
  for (const node of nodes) {
    next[node.id] = {
      x: Math.max(56, Math.min(WIDTH - 56, node.x)),
      y: Math.max(56, Math.min(HEIGHT - 56, node.y)),
    };
  }
  return next;
}

function useForceLayout(agentIds: string[], edges: LayoutEdge[]) {
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally
  // keyed on content (not reference) so identical snapshots don't re-run
  // the simulation just because upstream objects were recreated.
  return useMemo(() => computeForceLayout(agentIds, edges), [agentIds.join(","), JSON.stringify(edges)]);
}

/** A gentle arc instead of a straight line -- reads as a "connection" rather
 * than a technical diagram line, and keeps overlapping edges visually
 * distinguishable when several agents cluster tightly together. */
function edgeControlPoint(from: { x: number; y: number }, to: { x: number; y: number }) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const curve = 0.12;
  return { x: mx - dy * curve, y: my + dx * curve };
}

function edgePath(from: { x: number; y: number }, to: { x: number; y: number }): string {
  const c = edgeControlPoint(from, to);
  return `M ${from.x} ${from.y} Q ${c.x} ${c.y} ${to.x} ${to.y}`;
}

/** Midpoint of the same quadratic curve edgePath draws, for label placement. */
function edgeMidpoint(from: { x: number; y: number }, to: { x: number; y: number }) {
  const c = edgeControlPoint(from, to);
  return {
    x: 0.25 * from.x + 0.5 * c.x + 0.25 * to.x,
    y: 0.25 * from.y + 0.5 * c.y + 0.25 * to.y,
  };
}

/** Labels a spanning-tree edge from the same similarity score already
 * driving its thickness/opacity -- this is a bucketed read of that number,
 * not stance or sentiment analysis (which would need real NLP work this
 * project doesn't do). "Diverges" means low measured similarity, not that
 * one agent was detected disagreeing with a specific claim. */
function relationLabel(weight: number): string {
  if (weight >= 0.6) return "Strongly agrees";
  if (weight >= 0.35) return "Partially agrees";
  if (weight >= 0.15) return "Slightly aligned";
  return "Diverges";
}

export function AgentRelationshipGraph() {
  const events = useAppStore((s) => s.events);
  const [snapshotIdx, setSnapshotIdx] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [manualPositions, setManualPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const draggedRef = useRef(false);

  const snapshots = useMemo(() => deriveGraphSnapshots(events), [events]);
  const displayNames = useMemo(() => deriveAgentDisplayNames(events), [events]);

  useEffect(() => {
    // Auto-advance to the latest available stage as the run progresses.
    setSnapshotIdx(snapshots.length > 0 ? snapshots.length - 1 : 0);
  }, [snapshots.length]);

  // A newly-selected agent might not exist in a later snapshot (different
  // agent roster) -- drop the selection rather than pointing at nothing.
  // Manually-dragged positions are stage-specific too, so clear those as well.
  useEffect(() => {
    setSelectedAgent(null);
    setManualPositions({});
  }, [snapshotIdx]);

  const snapshot = snapshots[snapshotIdx];

  const edges = useMemo<LayoutEdge[]>(() => {
    if (!snapshot) return [];
    const result: LayoutEdge[] = [];
    for (let i = 0; i < snapshot.agentIds.length; i += 1) {
      for (let j = i + 1; j < snapshot.agentIds.length; j += 1) {
        const weight = snapshot.similarity[i]?.[j] ?? 0;
        if (weight >= SIMILARITY_EDGE_THRESHOLD) {
          result.push({ source: snapshot.agentIds[i], target: snapshot.agentIds[j], weight });
        }
      }
    }
    return result;
  }, [snapshot]);

  const simPositions = useForceLayout(snapshot?.agentIds ?? [], edges);
  // Manual drags win over the simulation's placement -- lets you pull nodes
  // apart yourself when the auto-layout leaves too little room between them.
  const positions = useMemo(
    () => ({ ...simPositions, ...manualPositions }),
    [simPositions, manualPositions],
  );

  function toSvgPoint(clientX: number, clientY: number): { x: number; y: number } | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const transformed = pt.matrixTransform(ctm.inverse());
    return { x: transformed.x, y: transformed.y };
  }

  function handleNodePointerDown(agentId: string, e: React.PointerEvent) {
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    draggedRef.current = false;
    setDraggingId(agentId);
  }

  function handleSvgPointerMove(e: React.PointerEvent) {
    if (!draggingId) return;
    const p = toSvgPoint(e.clientX, e.clientY);
    if (!p) return;
    draggedRef.current = true;
    setManualPositions((prev) => ({
      ...prev,
      [draggingId]: {
        x: Math.max(36, Math.min(WIDTH - 36, p.x)),
        y: Math.max(36, Math.min(HEIGHT - 36, p.y)),
      },
    }));
  }

  function handleSvgPointerUp() {
    setDraggingId(null);
  }

  function handleNodeClick(agentId: string) {
    if (draggedRef.current) {
      // This click was the tail end of a drag, not an intentional select.
      draggedRef.current = false;
      return;
    }
    setSelectedAgent(selectedAgent === agentId ? null : agentId);
  }

  // Greedy (Prim's) max-weight spanning tree from the first agent, purely
  // to order the default entrance animation -- the graph reveals itself as
  // if growing outward from one agent instead of popping in all at once.
  const growthTree = useMemo(() => {
    if (!snapshot || snapshot.agentIds.length === 0) return null;
    return computeGreedySpanningTree(snapshot.agentIds, snapshot.similarity, snapshot.agentIds[0]);
  }, [snapshot]);

  // Same algorithm, but rooted at whichever agent was clicked -- this is
  // the one actually shown to the user: only these tree edges stay at full
  // opacity, revealed step by step, while everything else fades out.
  const revealTree = useMemo(() => {
    if (!snapshot || !selectedAgent) return null;
    return computeGreedySpanningTree(snapshot.agentIds, snapshot.similarity, selectedAgent);
  }, [snapshot, selectedAgent]);

  const growthStep = useMemo(() => {
    const map = new Map<string, number>();
    growthTree?.order.forEach((id, i) => map.set(id, i));
    return map;
  }, [growthTree]);

  const revealStep = useMemo(() => {
    const map = new Map<string, number>();
    revealTree?.order.forEach((id, i) => map.set(id, i));
    return map;
  }, [revealTree]);

  const revealEdgeKeys = useMemo(() => {
    const set = new Set<string>();
    revealTree?.edges.forEach((e) => set.add([e.from, e.to].sort().join("::")));
    return set;
  }, [revealTree]);

  const majorityLabel = useMemo(() => {
    if (!snapshot) return null;
    const counts = new Map<number, number>();
    for (const label of snapshot.partition) counts.set(label, (counts.get(label) ?? 0) + 1);
    let majority = 0;
    let max = -1;
    for (const [label, count] of counts) {
      if (count > max) {
        max = count;
        majority = label;
      }
    }
    return majority;
  }, [snapshot]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card flex flex-col overflow-hidden h-full"
      aria-label="Agent relationship graph"
    >
      <div className="px-4 pt-3 pb-2 border-b border-foreground/5 flex items-center justify-between shrink-0">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Network className="w-4 h-4 text-accent-cool" /> Agent Relationships
        </h2>
        <div className="flex items-center gap-2">
          {selectedAgent && (
            <button
              onClick={() => setSelectedAgent(null)}
              className="text-[10px] px-2.5 py-1 rounded-full border border-accent-cool/40 text-accent-cool font-medium hover:bg-accent-cool/10 transition-colors"
            >
              Show all
            </button>
          )}
          {snapshots.length > 0 && (
            <div className="flex items-center gap-1">
              {snapshots.map((s, i) => (
                <button
                  key={s.stage}
                  onClick={() => setSnapshotIdx(i)}
                  className={`text-[10px] px-2.5 py-1 rounded-full border font-medium transition-colors ${
                    i === snapshotIdx
                      ? "bg-foreground text-primary-foreground border-foreground"
                      : "border-foreground/10 text-muted-foreground hover:border-foreground/30"
                  }`}
                  title={s.label}
                >
                  {s.stage === "round0" ? "R0" : s.stage === "pre_critique" ? "Pre" : "Final"}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex items-center justify-center relative p-1">
        {!snapshot ? (
          <div className="flex flex-col items-center gap-3 text-center px-4">
            <div className="w-14 h-14 rounded-full bg-accent-cool/10 flex items-center justify-center">
              <Radar className="w-6 h-6 text-accent-cool/60" />
            </div>
            <p className="text-xs text-muted-foreground max-w-[220px]">
              No relationship data yet. Start a debate — the graph fills in after round 0.
            </p>
          </div>
        ) : (
          <svg
            ref={svgRef}
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="w-full h-full"
            preserveAspectRatio="xMidYMid meet"
            onPointerMove={handleSvgPointerMove}
            onPointerUp={handleSvgPointerUp}
            onPointerLeave={handleSvgPointerUp}
          >
            <defs>
              <pattern id="graph-dots" width="24" height="24" patternUnits="userSpaceOnUse">
                <circle cx="1.5" cy="1.5" r="1.5" className="fill-foreground/[0.06]" />
              </pattern>
              <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopOpacity="0.55" />
                <stop offset="100%" stopOpacity="0" />
              </radialGradient>
            </defs>

            <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="url(#graph-dots)" />

            {/* Context edges: everything below the similarity threshold cutoff.
                Full opacity/staggered growth when nothing is selected; faded
                far into the background once a reveal is active so the
                spanning tree drawn on top of them reads clearly. */}
            <g>
              {edges.map((edge, i) => {
                const from = positions[edge.source as string];
                const to = positions[edge.target as string];
                if (!from || !to) return null;
                const key = [edge.source, edge.target].sort().join("::");
                const isTreeEdge = revealEdgeKeys.has(key);
                if (selectedAgent && isTreeEdge) return null; // drawn by the tree layer below
                const delay = selectedAgent
                  ? 0
                  : Math.max(
                      growthStep.get(edge.source as string) ?? 0,
                      growthStep.get(edge.target as string) ?? 0,
                    ) * GROWTH_STAGGER_S;
                return (
                  <motion.path
                    key={i}
                    d={edgePath(from, to)}
                    fill="none"
                    stroke="currentColor"
                    className="text-foreground"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{
                      pathLength: 1,
                      opacity: selectedAgent ? 0.03 : 0.14 + edge.weight * 0.45,
                    }}
                    transition={{ duration: 0.5, ease: "easeOut", delay }}
                    strokeWidth={1.5 + edge.weight * 3.5}
                    strokeLinecap="round"
                  />
                );
              })}
            </g>

            {/* Spanning-tree reveal: only rendered while an agent is
                selected. Edges light up in discovery order (Prim's
                algorithm, greedily following the strongest available
                connection outward), so clicking an agent visibly "grows"
                a tree from it instead of just toggling a filter. */}
            {selectedAgent && revealTree && (
              <g>
                {revealTree.edges.map((edge) => {
                  const from = positions[edge.from];
                  const to = positions[edge.to];
                  if (!from || !to) return null;
                  const mid = edgeMidpoint(from, to);
                  const label = relationLabel(edge.weight);
                  const labelDelay = edge.step * REVEAL_STAGGER_S + 0.25;
                  return (
                    <motion.g key={`${edge.from}-${edge.to}`}>
                      <motion.path
                        d={edgePath(from, to)}
                        fill="none"
                        stroke="hsl(var(--accent-cool))"
                        initial={{ pathLength: 0, opacity: 0 }}
                        animate={{ pathLength: 1, opacity: 0.35 + edge.weight * 0.5 }}
                        transition={{ duration: 0.45, ease: "easeOut", delay: edge.step * REVEAL_STAGGER_S }}
                        strokeWidth={2 + edge.weight * 4}
                        strokeLinecap="round"
                      />
                      <motion.g
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.3, delay: labelDelay }}
                        transform={`translate(${mid.x}, ${mid.y})`}
                      >
                        <rect
                          x={-(label.length * 3 + 6)}
                          y={-9}
                          width={label.length * 6 + 12}
                          height={18}
                          rx={9}
                          className="fill-background/90"
                          stroke="hsl(var(--accent-cool))"
                          strokeWidth={1}
                          strokeOpacity={0.4}
                        />
                        <text
                          textAnchor="middle"
                          y={4}
                          fontSize={10}
                          fontFamily="IBM Plex Mono, monospace"
                          className="fill-current text-accent-cool font-medium"
                        >
                          {label}
                        </text>
                      </motion.g>
                    </motion.g>
                  );
                })}
              </g>
            )}

            <g>
              {snapshot.agentIds.map((agentId, i) => {
                const pos = positions[agentId];
                if (!pos) return null;
                const isMinority = snapshot.partition[i] !== majorityLabel;
                const isSelected = selectedAgent === agentId;
                const inTree = !selectedAgent || revealStep.has(agentId);
                const dimmed = selectedAgent && !inTree;
                const radius = isMinority ? 24 : 30;
                const color = agentColorVar(agentId);
                const label = displayNames[agentId] ?? agentId;
                const delay = selectedAgent
                  ? (revealStep.get(agentId) ?? 0) * REVEAL_STAGGER_S
                  : (growthStep.get(agentId) ?? 0) * GROWTH_STAGGER_S;
                const isDragging = draggingId === agentId;
                return (
                  <motion.g
                    key={agentId}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{
                      opacity: dimmed ? 0.25 : 1,
                      scale: isSelected || isDragging ? 1.15 : 1,
                      x: pos.x,
                      y: pos.y,
                    }}
                    transition={
                      isDragging
                        ? { type: "tween", duration: 0 }
                        : { type: "spring", stiffness: 220, damping: 20, delay }
                    }
                    onPointerDown={(e) => handleNodePointerDown(agentId, e)}
                    onClick={() => handleNodeClick(agentId)}
                    className={isDragging ? "cursor-grabbing" : "cursor-grab"}
                  >
                    <circle r={radius * 2.1} fill={color} style={{ color }} />
                    <circle r={radius * 2.1} fill="url(#node-glow)" style={{ color }} />
                    <circle
                      r={radius}
                      fill={color}
                      stroke={isSelected ? "white" : "rgba(255,255,255,0.35)"}
                      strokeWidth={isSelected ? 3.5 : 2}
                    />
                    <rect
                      x={-(label.length * 3.4 + 9)}
                      y={radius + 9}
                      width={label.length * 6.8 + 18}
                      height={18}
                      rx={9}
                      className="fill-background/85"
                    />
                    <text
                      textAnchor="middle"
                      y={radius + 22}
                      className="fill-current text-foreground font-semibold"
                      fontSize={12}
                      fontFamily="Space Grotesk, sans-serif"
                    >
                      {label}
                    </text>
                  </motion.g>
                );
              })}
            </g>
          </svg>
        )}
      </div>

      <AnimatePresence>
        {snapshot && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="px-4 py-2.5 border-t border-foreground/5 shrink-0 flex items-center justify-between gap-3"
          >
            {selectedAgent ? (
              <div className="flex items-center gap-1.5 text-[10px] text-accent-cool">
                <span className="w-2.5 h-2.5 rounded-full bg-accent-cool inline-block" />
                spanning tree from {displayNames[selectedAgent] ?? selectedAgent}
              </div>
            ) : (
              <div className="flex items-center gap-3 text-[10px]">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <span className="w-2.5 h-2.5 rounded-full bg-foreground/70 inline-block" /> consensus cluster
                </span>
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <span className="w-2 h-2 rounded-full bg-foreground/30 inline-block" /> dissenting
                </span>
              </div>
            )}
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span>{snapshot.label}</span>
              <span className="font-mono text-foreground/70">{snapshot.selectedPolicy}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
