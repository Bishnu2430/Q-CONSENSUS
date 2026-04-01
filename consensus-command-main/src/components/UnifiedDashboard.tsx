import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { api } from "@/lib/api";
import { RunRequestSchema } from "@/lib/schemas";
import {
  Play,
  Zap,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { toast } from "sonner";
import { StreamPanel } from "./StreamPanel";
import { FinalReasoning } from "./FinalReasoning";
import { VerificationPanel } from "./VerificationPanel";
import { MetricsPanel } from "./MetricsPanel";
import { SystemStatus } from "./SystemStatus";

interface PanelState {
  stream: boolean;
  reasoning: boolean;
  verify: boolean;
  metrics: boolean;
  status: boolean;
}

export function UnifiedDashboard() {
  const {
    runStatus,
    setRun,
    setRunStatus,
    systemStatus,
    events,
    runMeta,
    activeTab,
  } = useAppStore();
  const maxAgents = Math.min(10, systemStatus?.agents_loaded ?? 10);

  const [query, setQuery] = useState("");
  const [maxRounds, setMaxRounds] = useState(2);
  const [agentCount, setAgentCount] = useState(Math.min(4, maxAgents));
  const [useWebContext, setUseWebContext] = useState(false);
  const [webContextItems, setWebContextItems] = useState(3);
  const [quantumRandomness, setQuantumRandomness] = useState(true);
  const [quantumWeights, setQuantumWeights] = useState(true);
  const [quantumScheduling, setQuantumScheduling] = useState(true);
  const [loading, setLoading] = useState(false);

  // Panel expansion state
  const [expandedPanels, setExpandedPanels] = useState<PanelState>({
    stream: activeTab === "stream",
    reasoning: activeTab === "reasoning",
    verify: activeTab === "verify",
    metrics: activeTab === "metrics",
    status: activeTab === "status",
  });

  // Sync activeTab to expanded panels
  useEffect(() => {
    setExpandedPanels((prev) => ({
      stream: activeTab === "stream",
      reasoning: activeTab === "reasoning",
      verify: activeTab === "verify",
      metrics: activeTab === "metrics",
      status: activeTab === "status",
    }));
  }, [activeTab]);

  const isRunning = runStatus === "running";

  useEffect(() => {
    setAgentCount((prev) => Math.max(2, Math.min(maxAgents, prev)));
  }, [maxAgents]);

  const buildRequest = useCallback(() => {
    return RunRequestSchema.safeParse({
      query: query.trim(),
      max_rounds: maxRounds,
      agent_count: Math.min(agentCount, maxAgents),
      enable_web_context: useWebContext,
      web_context_max_items: webContextItems,
      use_quantum_randomness: quantumRandomness,
      use_quantum_weights: quantumWeights,
      use_quantum_scheduling: quantumScheduling,
    });
  }, [
    query,
    maxRounds,
    agentCount,
    maxAgents,
    useWebContext,
    webContextItems,
    quantumRandomness,
    quantumWeights,
    quantumScheduling,
  ]);

  const computeProgress = useCallback(() => {
    if (runStatus !== "running")
      return {
        percent: runStatus === "completed" ? 100 : 0,
        label: runStatus === "completed" ? "Completed" : "Idle",
      };
    const eventTypes = new Set(events.map((e) => e.event_type));
    const responded = events.filter(
      (e) => e.event_type === "agent_responded",
    ).length;
    const meta = runMeta ?? {
      maxRounds: 2,
      agentCount: 3,
      mode: "async" as const,
    };
    const expectedResponses = Math.max(1, meta.maxRounds * meta.agentCount);
    const responsePct = Math.min(1, responded / expectedResponses);

    let base = 8;
    let label = "Initializing run";
    if (eventTypes.has("input_received")) {
      base = 14;
      label = "Preparing debate";
    }
    if (eventTypes.has("web_context_enriched")) {
      base = 24;
      label = "Fetching web context";
    }
    if (eventTypes.has("quantum_randomness")) {
      base = 34;
      label = "Sampling randomness";
    }
    if (eventTypes.has("quantum_scheduling")) {
      base = 44;
      label = "Scheduling agents";
    }
    if (responded > 0) {
      base = 44 + Math.round(responsePct * 38);
      label = `Collecting responses (${responded}/${expectedResponses})`;
    }
    if (eventTypes.has("consensus_weights")) {
      base = 88;
      label = "Computing consensus";
    }
    if (eventTypes.has("final_answer")) {
      base = 95;
      label = "Finalizing answer";
    }
    if (eventTypes.has("run_committed")) {
      base = 100;
      label = "Committed on chain";
    }

    return { percent: Math.max(5, Math.min(100, base)), label };
  }, [events, runMeta, runStatus]);

  const waitForResult = useCallback(
    async (runId: string) => {
      const deadline = Date.now() + 8 * 60 * 1000;
      while (Date.now() < deadline) {
        const result = await api.getResult(runId);
        if (result.status === "completed" || result.status === "failed") {
          useAppStore.getState().setResult(result);
          setRunStatus(result.status);
          return result;
        }
        await api
          .getEvents(runId)
          .then(useAppStore.getState().addEvents)
          .catch(() => {});
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Timed out waiting for run completion");
    },
    [setRunStatus],
  );

  const handleRun = async (async: boolean) => {
    const parsed = buildRequest();
    if (!parsed.success) {
      const msg = parsed.error.issues
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ");
      toast.error(`Validation: ${msg}`);
      return;
    }
    setLoading(true);
    try {
      const res = await api.runAsync(parsed.data);
      setRun(res.run_id, "running", {
        mode: async ? "async" : "sync",
        agentCount: parsed.data.agent_count,
        maxRounds: parsed.data.max_rounds,
      });

      if (async) {
        toast.success(`Async run started: ${res.run_id.slice(0, 8)}…`);
      } else {
        const result = await waitForResult(res.run_id);
        if (result.status === "completed") {
          toast.success("Synchronous run completed");
        } else {
          toast.error(result.error || "Synchronous run failed");
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Run failed";
      setRunStatus("failed");
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const progress = computeProgress();

  const Toggle = ({
    value,
    onChange,
    label,
  }: {
    value: boolean;
    onChange: (v: boolean) => void;
    label: string;
  }) => (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      aria-label={label}
      onClick={() => onChange(!value)}
      className="flex items-center gap-2 text-xs font-medium text-foreground/80 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md px-1"
    >
      {value ? (
        <ToggleRight className="w-5 h-5 text-accent-cool" />
      ) : (
        <ToggleLeft className="w-5 h-5 text-muted-foreground" />
      )}
      {label}
    </button>
  );

  interface PanelConfig {
    key: keyof PanelState;
    label: string;
    component: React.ReactNode;
  }

  const panels: PanelConfig[] = [
    { key: "stream", label: "Live Stream", component: <StreamPanel /> },
    { key: "status", label: "System Status", component: <SystemStatus /> },
    {
      key: "reasoning",
      label: "Final Reasoning",
      component: <FinalReasoning />,
    },
    { key: "verify", label: "Verification", component: <VerificationPanel /> },
    { key: "metrics", label: "Metrics", component: <MetricsPanel /> },
  ];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="w-full space-y-3"
    >
      {/* Control Panel */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass-card p-5 space-y-4"
        aria-label="Debate Control Panel"
      >
        <h2 className="text-sm font-semibold text-foreground">New Debate</h2>

        <div className="space-y-1">
          <label
            htmlFor="query"
            className="text-xs font-medium text-muted-foreground"
          >
            Query
          </label>
          <textarea
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={4000}
            rows={3}
            placeholder="Enter your debate query…"
            className="w-full px-3 py-2 text-sm font-mono bg-foreground/[0.03] border border-foreground/10 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground/50"
          />
          <div className="text-right text-[10px] text-muted-foreground">
            {query.length}/4000
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label
              htmlFor="rounds"
              className="text-xs font-medium text-muted-foreground"
            >
              Max Rounds
            </label>
            <select
              id="rounds"
              value={maxRounds}
              onChange={(e) => setMaxRounds(Number(e.target.value))}
              className="w-full px-3 py-2 text-sm bg-foreground/[0.03] border border-foreground/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {[1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label
              htmlFor="agents"
              className="text-xs font-medium text-muted-foreground"
            >
              Agents ({maxAgents} avail.)
            </label>
            <input
              id="agents"
              type="number"
              min={2}
              max={maxAgents}
              value={agentCount}
              onChange={(e) =>
                setAgentCount(
                  Math.max(2, Math.min(maxAgents, Number(e.target.value))),
                )
              }
              className="w-full px-3 py-2 text-sm bg-foreground/[0.03] border border-foreground/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Toggle
            value={useWebContext}
            onChange={setUseWebContext}
            label="Web context"
          />
          <Toggle
            value={quantumRandomness}
            onChange={setQuantumRandomness}
            label="Q-Randomness"
          />
          <Toggle
            value={quantumWeights}
            onChange={setQuantumWeights}
            label="Q-Weights"
          />
          <Toggle
            value={quantumScheduling}
            onChange={setQuantumScheduling}
            label="Q-Scheduling"
          />
        </div>

        {useWebContext && (
          <div className="space-y-1">
            <label
              htmlFor="webctx"
              className="text-xs font-medium text-muted-foreground"
            >
              Web context items
            </label>
            <input
              id="webctx"
              type="range"
              min={1}
              max={6}
              value={webContextItems}
              onChange={(e) => setWebContextItems(Number(e.target.value))}
              className="w-full"
            />
            <div className="text-[10px] text-muted-foreground">
              Using top {webContextItems} web snippets for prompt grounding
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => handleRun(false)}
            disabled={isRunning || loading || !query.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold bg-foreground text-primary-foreground rounded-lg hover:bg-foreground/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Play className="w-3.5 h-3.5" /> Run Sync
          </button>
          <button
            onClick={() => handleRun(true)}
            disabled={isRunning || loading || !query.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold bg-accent-cool text-accent-foreground rounded-lg hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Zap className="w-3.5 h-3.5" /> Async + Stream
          </button>
        </div>

        {runStatus === "running" && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
              <span className="font-medium">{progress.label}</span>
              <span className="tabular-nums">{progress.percent}%</span>
            </div>
            <div className="h-2.5 rounded-full bg-foreground/10 overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-accent-cool to-accent-cool/60"
                initial={{ width: 0 }}
                animate={{ width: `${progress.percent}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
              />
            </div>
          </div>
        )}
      </motion.section>

      {/* Dynamic Panels Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AnimatePresence mode="popLayout">
          {panels.map((panel) => (
            <motion.div
              key={panel.key}
              layout
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className={expandedPanels[panel.key] ? "lg:col-span-2" : ""}
            >
              <motion.section
                className="glass-card overflow-hidden flex flex-col h-full"
                animate={{
                  height: expandedPanels[panel.key] ? "auto" : "300px",
                }}
                transition={{ duration: 0.3, ease: "easeInOut" }}
              >
                <button
                  onClick={() =>
                    setExpandedPanels((prev) => ({
                      ...prev,
                      [panel.key]: !prev[panel.key],
                    }))
                  }
                  className="flex items-center justify-between w-full p-4 bg-foreground/5 hover:bg-foreground/10 transition-colors border-b border-foreground/10"
                >
                  <h3 className="text-sm font-semibold text-foreground">
                    {panel.label}
                  </h3>
                  <motion.div
                    animate={{
                      rotate: expandedPanels[panel.key] ? 180 : 0,
                    }}
                    transition={{ duration: 0.2 }}
                  >
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  </motion.div>
                </button>

                <motion.div
                  className="flex-1 overflow-y-auto p-4"
                  animate={{
                    opacity: expandedPanels[panel.key] ? 1 : 0.6,
                  }}
                >
                  {panel.component}
                </motion.div>
              </motion.section>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
