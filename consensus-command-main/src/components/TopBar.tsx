import { motion } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { Activity, Wifi, WifiOff, AlertTriangle } from "lucide-react";

const statusColors: Record<string, string> = {
  idle: "pill-neutral",
  running: "pill-cool",
  completed: "pill-success",
  failed: "pill-error",
};

const connectionIcons: Record<string, React.ReactNode> = {
  connected: <Wifi className="w-3 h-3" />,
  degraded: <AlertTriangle className="w-3 h-3" />,
  disconnected: <WifiOff className="w-3 h-3" />,
};

export function TopBar() {
  const { runStatus, apiConnection, streamState, currentRunId } = useAppStore();

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-center gap-3">
        <Activity className="w-5 h-5 text-accent-cool" />
        <h1 className="text-sm font-bold tracking-tight text-foreground">
          Q-CONSENSUS{" "}
          <span className="font-normal text-muted-foreground">
            Unified Ops Dashboard
          </span>
        </h1>
      </div>

      <div className="flex items-center gap-2">
        {currentRunId && (
          <span className="pill-neutral text-[10px] font-mono max-w-[220px] truncate">
            run: {currentRunId}
          </span>
        )}
        <span className={statusColors[runStatus]}>
          {runStatus === "running" && (
            <span className="w-1.5 h-1.5 rounded-full bg-current motion-safe:animate-pulse-live" />
          )}
          {runStatus}
        </span>

        <span className={`pill-neutral`}>
          {connectionIcons[apiConnection]}
          <span className="capitalize">{apiConnection}</span>
        </span>

        {streamState !== "idle" && (
          <span className="pill-neutral text-[10px]">SSE: {streamState}</span>
        )}
      </div>
    </motion.header>
  );
}
