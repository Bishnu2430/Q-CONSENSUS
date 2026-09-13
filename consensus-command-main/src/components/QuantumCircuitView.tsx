import { useMemo } from "react";
import { motion } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useAppStore } from "@/store/appStore";
import { Atom } from "lucide-react";

interface QaoaCircuitInfo {
  num_qubits: number;
  qaoa_layers: number;
  optimized_params: number[];
  measurement_counts: Record<string, number>;
  qubo_cost: number;
}

function isQaoaCircuitInfo(value: unknown): value is QaoaCircuitInfo {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.num_qubits === "number" &&
    typeof v.qaoa_layers === "number" &&
    Array.isArray(v.optimized_params) &&
    v.measurement_counts !== null &&
    typeof v.measurement_counts === "object"
  );
}

/** Static schematic of the fixed QAOA circuit shape used by the backend
 * (quantum_qaoa.py): Hadamard on every qubit, a cost-unitary layer, a
 * mixer layer, then measurement. This is real -- the gate sequence is
 * exactly what's applied -- but it's a schematic of the *structure*, not a
 * literal per-run gate trace (the backend doesn't emit one). Paired below
 * with the real per-run measurement histogram and parameters. */
function CircuitSchematic({ numQubits, layers }: { numQubits: number; layers: number }) {
  const wireGap = 34;
  const height = wireGap * numQubits + 20;
  const width = 360;
  const stageX = [60, 150, 240, 320];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto max-h-48">
      {Array.from({ length: numQubits }).map((_, q) => {
        const y = 20 + q * wireGap;
        return (
          <g key={q}>
            <line x1={20} y1={y} x2={width - 10} y2={y} stroke="currentColor" className="text-foreground/20" />
            <text x={4} y={y + 4} fontSize={9} className="fill-current text-muted-foreground" fontFamily="IBM Plex Mono, monospace">
              q{q}
            </text>
            <rect x={stageX[0] - 12} y={y - 12} width={24} height={24} rx={4} className="fill-agent-2" opacity={0.85} />
            <text x={stageX[0]} y={y + 4} textAnchor="middle" fontSize={10} className="fill-white" fontFamily="IBM Plex Mono, monospace">H</text>
          </g>
        );
      })}

      <rect x={stageX[1] - 30} y={10} width={60} height={height - 20} rx={8} className="fill-agent-4" opacity={0.18} stroke="currentColor" strokeDasharray="3 3" />
      <text x={stageX[1]} y={height - 4} textAnchor="middle" fontSize={9} className="fill-current text-muted-foreground">Cost ×{layers}</text>

      <rect x={stageX[2] - 30} y={10} width={60} height={height - 20} rx={8} className="fill-agent-3" opacity={0.18} stroke="currentColor" strokeDasharray="3 3" />
      <text x={stageX[2]} y={height - 4} textAnchor="middle" fontSize={9} className="fill-current text-muted-foreground">Mixer ×{layers}</text>

      {Array.from({ length: numQubits }).map((_, q) => {
        const y = 20 + q * wireGap;
        return (
          <g key={`m-${q}`}>
            <rect x={stageX[3] - 12} y={y - 12} width={24} height={24} rx={4} className="fill-foreground/10" stroke="currentColor" />
            <text x={stageX[3]} y={y + 4} textAnchor="middle" fontSize={9} className="fill-current text-foreground">M</text>
          </g>
        );
      })}
    </svg>
  );
}

export function QuantumCircuitView() {
  const events = useAppStore((s) => s.events);

  const circuit = useMemo(() => {
    const event = [...events].reverse().find((e) => e.event_type === "consensus_weights");
    const raw = (event?.payload as Record<string, unknown> | undefined)?.qaoa_circuit;
    return isQaoaCircuitInfo(raw) ? raw : null;
  }, [events]);

  const histogramData = useMemo(() => {
    if (!circuit) return [];
    return Object.entries(circuit.measurement_counts)
      .map(([bitstring, count]) => ({ bitstring, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12);
  }, [circuit]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
      <h3 className="text-xs font-semibold text-foreground flex items-center gap-2">
        <Atom className="w-3.5 h-3.5 text-accent-cool" /> Quantum Circuit (QAOA)
      </h3>

      {!circuit ? (
        <p className="text-xs text-muted-foreground">
          No quantum consensus computation yet — this fills in once a run reaches the
          consensus-weighting step.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-foreground/[0.02] rounded-lg p-3 border border-foreground/5">
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-2">
              Circuit structure ({circuit.num_qubits} qubits)
            </div>
            <CircuitSchematic numQubits={Math.min(circuit.num_qubits, 6)} layers={circuit.qaoa_layers} />
          </div>

          <div className="bg-foreground/[0.02] rounded-lg p-3 border border-foreground/5">
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-2">
              Measured outcomes (this run)
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={histogramData}>
                <XAxis
                  dataKey="bitstring"
                  fontSize={9}
                  fontFamily="IBM Plex Mono, monospace"
                  tick={{ fill: "hsl(var(--muted-foreground))" }}
                />
                <YAxis fontSize={9} tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                />
                <Bar dataKey="count" fill="hsl(var(--accent-cool))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="md:col-span-2 grid grid-cols-3 gap-2 text-[10px]">
            <div className="bg-foreground/[0.03] rounded-lg p-2">
              <div className="text-muted-foreground">QAOA layers</div>
              <div className="font-mono font-semibold text-foreground">{circuit.qaoa_layers}</div>
            </div>
            <div className="bg-foreground/[0.03] rounded-lg p-2">
              <div className="text-muted-foreground">QUBO cost</div>
              <div className="font-mono font-semibold text-foreground">{circuit.qubo_cost.toFixed(3)}</div>
            </div>
            <div className="bg-foreground/[0.03] rounded-lg p-2">
              <div className="text-muted-foreground">Optimized params</div>
              <div className="font-mono font-semibold text-foreground truncate">
                [{circuit.optimized_params.map((v) => v.toFixed(2)).join(", ")}]
              </div>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}
