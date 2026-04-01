import { useAppStore } from "@/store/appStore";
import { useSSEStream } from "@/hooks/useSSEStream";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { TopBar } from "@/components/TopBar";
import { ControlPanel } from "@/components/ControlPanel";
import { StreamPanel } from "@/components/StreamPanel";
import { FinalReasoning } from "@/components/FinalReasoning";
import { SystemStatus } from "@/components/SystemStatus";
import { VerificationPanel } from "@/components/VerificationPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { motion, AnimatePresence } from "framer-motion";
import { Download, ChevronDown } from "lucide-react";
import { toast } from "sonner";

interface PanelConfig {
  id: string;
  label: string;
  component: React.ReactNode;
}

function ExportButton() {
  const events = useAppStore((s) => s.events);
  const handleExport = () => {
    if (events.length === 0) {
      toast.error("No events to export.");
      return;
    }
    const blob = new Blob([JSON.stringify(events, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `q-consensus-transcript-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button
      onClick={handleExport}
      className="pill-neutral text-[10px]"
      aria-label="Export transcript"
    >
      <Download className="w-3 h-3" /> Export
    </button>
  );
}

function PanelCard({
  panel,
  isExpanded,
  onToggle,
}: {
  panel: PanelConfig;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <motion.div
      layout
      className="glass-card overflow-hidden"
      transition={{ duration: 0.3, ease: "easeInOut" }}
    >
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-foreground/5 transition-colors"
      >
        <h2 className="text-sm font-semibold text-foreground">{panel.label}</h2>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        </motion.div>
      </button>

      <AnimatePresence>
        <motion.div
          initial={false}
          animate={{
            opacity: isExpanded ? 1 : 0,
            height: isExpanded ? "auto" : 0,
          }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
          className="border-t border-border overflow-hidden"
        >
          <div className="p-4">{panel.component}</div>
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}

export default function MissionControl() {
  const { currentRunId, runStatus, activeTab, setActiveTab } = useAppStore();

  // Start SSE stream when there's an active async run
  useSSEStream(runStatus === "running" ? currentRunId : null);

  // Poll system status
  useSystemStatus();

  const panels: PanelConfig[] = [
    { id: "control", label: "Control", component: <ControlPanel /> },
    { id: "status", label: "Status", component: <SystemStatus /> },
    { id: "stream", label: "Stream", component: <StreamPanel /> },
    { id: "reasoning", label: "Reasoning", component: <FinalReasoning /> },
    { id: "verify", label: "Verification", component: <VerificationPanel /> },
    { id: "metrics", label: "Metrics", component: <MetricsPanel /> },
  ];

  return (
    <div className="min-h-screen flex flex-col gap-3 p-3 sm:p-4 max-w-[1600px] mx-auto">
      <TopBar />

      <div className="flex items-center justify-end gap-2 px-1">
        <ExportButton />
      </div>

      <div className="flex-1 flex flex-col gap-3 min-h-0">
        <div className="flex flex-col gap-2.5 overflow-y-auto">
          {panels.map((panel) => (
            <PanelCard
              key={panel.id}
              panel={panel}
              isExpanded={activeTab === panel.id}
              onToggle={() =>
                setActiveTab(activeTab === panel.id ? "control" : panel.id)
              }
            />
          ))}
        </div>
      </div>

      <footer className="text-center text-[10px] text-muted-foreground py-2">
        Q-CONSENSUS Debate Orchestrator — Mission Control v1.0
      </footer>
    </div>
  );
}
