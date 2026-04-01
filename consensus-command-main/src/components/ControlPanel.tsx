import { useState, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { useRunProgress } from "@/hooks/useRunProgress";
import { api } from "@/lib/api";
import { RunRequestSchema } from "@/lib/schemas";
import { Play, Zap, ToggleLeft, ToggleRight, Clock } from "lucide-react";
import { toast } from "sonner";

export function ControlPanel() {
  const {
    currentRunId,
    runStatus,
    setRun,
    setRunStatus,
    systemStatus,
    events,
    runMeta,
    progress,
  } = useAppStore();

  // Initialize unified progress polling
  useRunProgress(runStatus === "running" ? currentRunId : null);

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

  const computeProgressPercent = useCallback(() => {
    if (!progress) return 0;

    const stageMap: Record<string, number> = {
      idle: 0,
      initializing: 8,
      fetching_web: 15,
      sampling: 25,
      scheduling: 35,
      thinking: 45,
      consensus: 80,
      finalizing: 95,
      completed: 100,
    };

    const basePercent = stageMap[progress.current_stage] || 0;

    // Boost by agent completion if in thinking stage
    if (progress.current_stage === "thinking" && progress.total_agents > 0) {
      const agentBoost =
        (progress.agents_completed / progress.total_agents) * 30;
      return Math.min(75, basePercent + agentBoost);
    }

    return basePercent;
  }, [progress]);

  const getProgressLabel = useCallback(() => {
    if (!progress) return "Idle";

    const labels: Record<string, string> = {
      idle: "Waiting",
      initializing: "Initializing",
      fetching_web: "Fetching web context",
      sampling: "Sampling quantum",
      scheduling: "Scheduling agents",
      thinking: `Collecting responses (${progress.agents_completed}/${progress.total_agents})`,
      consensus: "Computing consensus",
      finalizing: "Finalizing",
      completed: "Completed",
    };

    return labels[progress.current_stage] || progress.current_stage;
  }, [progress]);

  const getEtaSeconds = useCallback(() => {
    if (!progress || progress.estimated_total_ms <= 0) return 0;
    const remaining = Math.max(
      0,
      progress.estimated_total_ms - progress.time_elapsed_ms,
    );
    return Math.ceil(remaining / 1000);
  }, [progress]);

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
    setProgress(null);
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

  const progressPercent = computeProgressPercent();
  const progressLabel = getProgressLabel();
  const etaSeconds = getEtaSeconds();

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

  return (
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
          rows={4}
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

      {isRunning && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[10px] text-muted-foreground">
            <span className="font-medium">{progressLabel}</span>
            <div className="flex items-center gap-1">
              {etaSeconds > 0 && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />~{etaSeconds}s
                </span>
              )}
              <span className="font-semibold">
                {Math.round(progressPercent)}%
              </span>
            </div>
          </div>
          <div className="h-2 rounded-full bg-foreground/10 overflow-hidden">
            <motion.div
              className="h-full bg-accent-cool"
              initial={{ width: 0 }}
              animate={{ width: `${progressPercent}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          </div>
          {progress && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="bg-foreground/5 p-2 rounded-md">
                  <div className="text-muted-foreground">Stage</div>
                  <div className="font-mono font-semibold text-foreground capitalize">
                    {progress.current_stage.replace(/_/g, " ")}
                  </div>
                </div>
                <div className="bg-foreground/5 p-2 rounded-md">
                  <div className="text-muted-foreground">Agents</div>
                  <div className="font-mono font-semibold text-foreground">
                    {progress.agents_completed}/{progress.total_agents}
                  </div>
                </div>
                <div className="bg-foreground/5 p-2 rounded-md">
                  <div className="text-muted-foreground">Elapsed / Total</div>
                  <div className="font-mono font-semibold text-foreground">
                    {Math.round(progress.time_elapsed_ms / 1000)}s /{" "}
                    {Math.round(progress.estimated_total_ms / 1000)}s
                  </div>
                </div>
                <div className="bg-foreground/5 p-2 rounded-md">
                  <div className="text-muted-foreground">ETA</div>
                  <div className="font-mono font-semibold text-accent-cool">
                    ~{etaSeconds}s
                  </div>
                </div>
              </div>

              {events.length > 0 && (
                <div className="text-[9px] text-muted-foreground/60 border-t border-foreground/5 pt-1">
                  <div className="font-mono">Recent events:</div>
                  <div className="font-mono truncate">
                    {events
                      .slice(-5)
                      .map((e) => e.event_type)
                      .join(" → ")}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </motion.section>
  );
}
