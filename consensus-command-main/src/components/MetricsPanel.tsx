import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAppStore } from "@/store/appStore";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

export function MetricsPanel() {
  const [timeWindow, setTimeWindow] = useState<"session" | "all">("all");
  const { events, result } = useAppStore();

  const metricsQuery = useQuery({
    queryKey: ["metrics"],
    queryFn: api.getMetrics,
    refetchInterval: 15000,
    retry: 1,
  });

  const qvcQuery = useQuery({
    queryKey: ["quantum-vs-classical"],
    queryFn: api.getQuantumVsClassical,
    refetchInterval: 15000,
    retry: 1,
  });

  const metrics = metricsQuery.data;
  const qvc = qvcQuery.data;

  const sessionMetrics = useMemo(() => {
    const eventCounts = events.reduce<Record<string, number>>((acc, ev) => {
      acc[ev.event_type] = (acc[ev.event_type] ?? 0) + 1;
      return acc;
    }, {});

    return {
      total_events: events.length,
      agent_responses: eventCounts.agent_responded ?? 0,
      run_completed: result?.status === "completed" ? 1 : 0,
      run_failed: result?.status === "failed" ? 1 : 0,
      run_state: result?.status ?? "running",
      commitment_emitted: eventCounts.run_committed ?? 0,
    };
  }, [events, result]);

  const sessionQvc = useMemo(() => {
    let quantumSelections = 0;
    let classicalSelections = 0;

    for (const ev of events) {
      if (
        ![
          "quantum_randomness",
          "quantum_scheduling",
          "consensus_weights",
          "final_answer",
        ].includes(ev.event_type)
      ) {
        continue;
      }

      const policy = String(
        (ev.payload as Record<string, unknown>).selected_policy ?? "",
      ).toLowerCase();
      if (!policy) {
        continue;
      }

      if (policy.includes("quantum")) {
        quantumSelections += 1;
      }
      if (policy.includes("classical")) {
        classicalSelections += 1;
      }
    }

    return {
      quantum_selections: quantumSelections,
      classical_selections: classicalSelections,
    };
  }, [events]);

  const activeMetrics =
    timeWindow === "session" ? sessionMetrics : (metrics ?? {});
  const activeQvc = timeWindow === "session" ? sessionQvc : (qvc ?? {});

  // Transform qvc data for chart
  const chartData = Object.entries(activeQvc).map(([key, value]) => ({
    name: key.replace(/_/g, " "),
    value: typeof value === "number" ? value : 0,
  }));

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="glass-card p-5 space-y-4"
      aria-label="Metrics"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Metrics</h2>
        <div className="flex items-center gap-2">
          <div className="flex rounded-full border border-foreground/10 overflow-hidden">
            {(["session", "all"] as const).map((w) => (
              <button
                key={w}
                onClick={() => setTimeWindow(w)}
                className={`px-2.5 py-1 text-[10px] font-medium transition-colors ${
                  timeWindow === w
                    ? "bg-foreground text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {w === "session" ? "Session" : "All Time"}
              </button>
            ))}
          </div>
          <button
            onClick={() => {
              metricsQuery.refetch();
              qvcQuery.refetch();
            }}
            className="p-1.5 rounded-md hover:bg-foreground/5 transition-colors"
            aria-label="Refresh metrics"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 text-muted-foreground ${metricsQuery.isFetching || qvcQuery.isFetching ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {metricsQuery.isError && qvcQuery.isError ? (
        <div className="text-xs text-muted-foreground py-8 text-center">
          Metrics unavailable.{" "}
          <button
            onClick={() => {
              metricsQuery.refetch();
              qvcQuery.refetch();
            }}
            className="text-accent-cool underline"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          {Object.keys(activeMetrics).length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {Object.entries(activeMetrics)
                .slice(0, 6)
                .map(([key, value]) => (
                  <div
                    key={key}
                    className="p-3 bg-foreground/[0.02] rounded-lg"
                  >
                    <div className="text-[10px] text-muted-foreground capitalize">
                      {key.replace(/_/g, " ")}
                    </div>
                    <div className="text-lg font-semibold font-mono text-foreground">
                      {typeof value === "number"
                        ? Number.isInteger(value)
                          ? value
                          : value.toFixed(2)
                        : String(value)}
                    </div>
                  </div>
                ))}
            </div>
          )}

          {chartData.length > 0 && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Quantum vs Classical
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(21,35,52,0.06)"
                    />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                    <Bar
                      dataKey="value"
                      fill="hsl(183 75% 30%)"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}
    </motion.section>
  );
}
