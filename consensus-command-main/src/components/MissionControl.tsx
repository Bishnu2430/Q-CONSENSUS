import { useAppStore } from "@/store/appStore";
import { useSSEStream } from "@/hooks/useSSEStream";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { TopBar } from "@/components/TopBar";
import { ControlPanel } from "@/components/ControlPanel";
import { StreamPanel } from "@/components/StreamPanel";
import { AgentRelationshipGraph } from "@/components/AgentRelationshipGraph";
import { FinalReasoning } from "@/components/FinalReasoning";
import { SystemStatus } from "@/components/SystemStatus";
import { VerificationPanel } from "@/components/VerificationPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { TraceabilityPanel } from "@/components/TraceabilityPanel";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
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
        {/* Primary view: a fixed-height row so a growing chat feed can never
            push the rest of the page around. Left column (controls, final
            answer, blockchain) scrolls independently of the right column
            (relationship graph + chat feed). */}
        <div
          className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-3 min-h-[560px]"
          style={{ height: "78vh" }}
        >
          <div className="flex flex-col gap-3 overflow-y-auto pr-1 min-h-0">
            <SystemStatus />
            <ControlPanel />
            <FinalReasoning />
            <TraceabilityPanel />
          </div>

          <div className="flex flex-col gap-3 min-h-0">
            <div className="shrink-0 h-[46%] min-h-[320px]">
              <AgentRelationshipGraph />
            </div>
            <div className="flex-1 min-h-0">
              <StreamPanel />
            </div>
          </div>
        </div>

        {/* Secondary views: metrics and on-chain verification. Traceability
            (+ the quantum circuit view embedded in it) lives in the always-
            visible left column above instead of a tab. */}
        <Tabs defaultValue="metrics" className="w-full">
          <TabsList className="glass-card w-full grid grid-cols-2 h-auto p-1 bg-[var(--glass-bg)]">
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
            <TabsTrigger value="verification">Verification</TabsTrigger>
          </TabsList>
          <TabsContent value="metrics" className="mt-3">
            <MetricsPanel />
          </TabsContent>
          <TabsContent value="verification" className="mt-3">
            <VerificationPanel />
          </TabsContent>
        </Tabs>
      </div>

      <footer className="text-center text-[10px] text-muted-foreground py-2">
        Q-CONSENSUS Debate Orchestrator — Mission Control v2.0
      </footer>
    </div>
  );
}
