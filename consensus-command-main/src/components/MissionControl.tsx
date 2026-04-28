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
import { TraceabilityPanel } from "@/components/TraceabilityPanel";
import { motion } from "framer-motion";
import { Download } from "lucide-react";
import { toast } from "sonner";

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

export default function MissionControl() {
  const { currentRunId, runStatus } = useAppStore();

  // Start SSE stream when there's an active async run
  useSSEStream(runStatus === "running" ? currentRunId : null);

  // Poll system status
  useSystemStatus();

  return (
    <div className="min-h-screen flex flex-col gap-3 p-3 sm:p-4 max-w-[1680px] mx-auto">
      <TopBar />

      <div className="flex items-center justify-end gap-2 px-1">
        <ExportButton />
      </div>

      <div className="flex-1 flex flex-col gap-3 min-h-0">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 items-start">
          <div className="xl:col-span-2">
            <ControlPanel />
          </div>
          <div className="xl:col-span-1">
            <SystemStatus />
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 items-start">
          <div className="xl:col-span-2">
            <StreamPanel />
          </div>
          <div className="xl:col-span-1">
            <FinalReasoning />
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 items-start">
          <div className="xl:col-span-2">
            <TraceabilityPanel />
          </div>
          <div className="xl:col-span-1 flex flex-col gap-3">
            <VerificationPanel />
            <MetricsPanel />
          </div>
        </div>
      </div>

      <footer className="text-center text-[10px] text-muted-foreground py-2">
        Q-CONSENSUS Debate Orchestrator — Mission Control v1.0
      </footer>
    </div>
  );
}
