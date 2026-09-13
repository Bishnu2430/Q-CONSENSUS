import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { TraceabilityPanel } from "@/components/TraceabilityPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { VerificationPanel } from "@/components/VerificationPanel";

/** The "Block Chain" box: traceability is the default view, with Metrics
 * and Verification folded in as tabs rather than separate boxes on the
 * page. Fills whatever height its parent gives it and scrolls internally
 * -- the left column's New Debate and Final Reasoning boxes above it are
 * naturally sized, so this is the one that absorbs any extra vertical
 * space (mirroring how the chat feed absorbs it on the right). */
export function BlockChainBox() {
  return (
    <Tabs defaultValue="traceability" className="h-full flex flex-col min-h-0">
      <TabsList className="glass-card w-full grid grid-cols-3 h-auto p-1 bg-[var(--glass-bg)] shrink-0">
        <TabsTrigger value="traceability">Block Chain</TabsTrigger>
        <TabsTrigger value="metrics">Metrics</TabsTrigger>
        <TabsTrigger value="verification">Verification</TabsTrigger>
      </TabsList>
      <div className="flex-1 min-h-0 overflow-y-auto mt-3">
        <TabsContent value="traceability" className="mt-0">
          <TraceabilityPanel />
        </TabsContent>
        <TabsContent value="metrics" className="mt-0">
          <MetricsPanel />
        </TabsContent>
        <TabsContent value="verification" className="mt-0">
          <VerificationPanel />
        </TabsContent>
      </div>
    </Tabs>
  );
}
