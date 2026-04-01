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
  const { runStatus, apiConnection, streamState, activeTab, setActiveTab } =
    useAppStore();

  const tabs = [
    { id: "control", label: "Control" },
    { id: "status", label: "Status" },
    { id: "stream", label: "Stream" },
    { id: "reasoning", label: "Reasoning" },
    { id: "verify", label: "Verification" },
    { id: "metrics", label: "Metrics" },
  ];

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
            Debate Control Room
          </span>
        </h1>
      </div>

      <nav className="flex items-center gap-1 overflow-x-auto" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-all whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === tab.id
                ? "bg-foreground text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-foreground/5"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="flex items-center gap-2">
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
