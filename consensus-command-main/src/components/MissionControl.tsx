import { useAppStore } from "@/store/appStore";
import { useSSEStream } from "@/hooks/useSSEStream";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { TopBar } from "@/components/TopBar";
import { ControlPanel } from "@/components/ControlPanel";
import { StreamPanel } from "@/components/StreamPanel";
import { AgentRelationshipGraph } from "@/components/AgentRelationshipGraph";
import { FinalReasoning } from "@/components/FinalReasoning";
import { BlockChainBox } from "@/components/BlockChainBox";
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
    <div className="h-screen flex flex-col gap-3 p-3 sm:p-4 max-w-[1680px] mx-auto overflow-hidden">
      <TopBar />

      <div className="flex items-center justify-end gap-2 px-1 shrink-0">
        <ExportButton />
      </div>

      {/* Fixed 40/60 layout: left column (New Debate, Final Reasoning, Block
          Chain) and right column (Agent Relationships, Chat Feed) both fill
          the same fixed height. The page itself never scrolls. Chat Feed is
          the main scrolling surface on the right; the left column also
          scrolls internally (rather than being clipped with no way back)
          if New Debate's expanded "run in progress" state and Final
          Reasoning's content together push Block Chain out of view. */}
      <div className="flex-1 min-h-0 grid grid-cols-[2fr_3fr] gap-4">
        <div className="flex flex-col gap-3 min-h-0 overflow-y-auto pr-1">
          <div className="shrink-0">
            <ControlPanel />
          </div>
          <div className="shrink-0">
            <FinalReasoning />
          </div>
          <div className="flex-1 min-h-[340px]">
            <BlockChainBox />
          </div>
        </div>

        <div className="flex flex-col gap-3 min-h-0">
          <div className="shrink-0 h-[42%] min-h-[300px]">
            <AgentRelationshipGraph />
          </div>
          <div className="flex-1 min-h-0">
            <StreamPanel />
          </div>
        </div>
      </div>

      <footer className="text-center text-[10px] text-muted-foreground py-1 shrink-0">
        Q-CONSENSUS Debate Orchestrator — Mission Control v2.0
      </footer>
    </div>
  );
}
