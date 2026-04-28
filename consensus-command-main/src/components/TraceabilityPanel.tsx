import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { api } from "@/lib/api";
import { Link2, Copy, ShieldCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";

type VerifyResult = {
  verified?: boolean;
  reason?: string;
  details?: Record<string, unknown>;
};

function shortHash(v: string | null | undefined): string {
  if (!v) return "n/a";
  if (v.length <= 18) return v;
  return `${v.slice(0, 10)}…${v.slice(-8)}`;
}

export function TraceabilityPanel() {
  const { currentRunId, events, result } = useAppStore();
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);

  const historyQuery = useQuery({
    queryKey: ["blockchain-history"],
    queryFn: () => api.getBlockchainHistory(1200),
    refetchInterval: 15000,
    retry: 1,
  });

  const committedEvent = useMemo(
    () => [...events].reverse().find((e) => e.event_type === "run_committed"),
    [events],
  );

  const chainHealth = useMemo(() => {
    let linkChecks = 0;
    let brokenLinks = 0;

    for (let i = 1; i < events.length; i += 1) {
      const prev = events[i - 1];
      const curr = events[i];
      if (curr.prev_event_hash && prev.event_hash) {
        linkChecks += 1;
        if (curr.prev_event_hash !== prev.event_hash) {
          brokenLinks += 1;
        }
      }
    }

    return {
      linkChecks,
      brokenLinks,
      healthy: brokenLinks === 0,
    };
  }, [events]);

  const onVerify = async () => {
    if (!currentRunId) {
      toast.error("No active run. Start a debate first.");
      return;
    }
    setVerifying(true);
    try {
      const res = (await api.verify(currentRunId)) as VerifyResult;
      setVerifyResult(res);
      if (res.verified) {
        toast.success("On-chain verification passed");
      } else {
        toast.error(res.reason || "Verification failed");
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  };

  const commitment =
    result?.commitment ??
    (committedEvent?.payload as Record<string, unknown> | undefined)?.commitment;
  const anchorTx =
    result?.anchor_tx_hash ??
    (committedEvent?.payload as Record<string, unknown> | undefined)
      ?.anchor_tx_hash;

  const history = historyQuery.data as Record<string, unknown> | undefined;
  const historyTx = Number(history?.total_txs ?? 0);
  const historyBlocks = Number(history?.total_blocks ?? 0);
  const committedRuns = Array.isArray(history?.committed_runs)
    ? (history?.committed_runs as Array<Record<string, unknown>>)
    : [];

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-card p-5 space-y-4"
      aria-label="Traceability"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Link2 className="w-4 h-4 text-accent-cool" /> Blockchain Traceability
        </h2>
        <button
          onClick={onVerify}
          disabled={verifying || !currentRunId}
          className="px-3 py-1.5 text-[11px] font-semibold rounded-md bg-foreground text-primary-foreground hover:bg-foreground/90 disabled:opacity-40"
        >
          {verifying ? (
            <span className="inline-flex items-center gap-1">
              <RefreshCw className="w-3 h-3 animate-spin" /> Verifying
            </span>
          ) : (
            "Verify Chain"
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Event Links
          </div>
          <div className="text-lg font-semibold font-mono text-foreground">
            {chainHealth.linkChecks}
          </div>
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Broken Links
          </div>
          <div className="text-lg font-semibold font-mono text-foreground">
            {chainHealth.brokenLinks}
          </div>
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Integrity
          </div>
          <div
            className={`text-sm font-semibold ${chainHealth.healthy ? "text-success" : "text-error"}`}
          >
            {chainHealth.healthy ? "healthy" : "mismatch detected"}
          </div>
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Chain Blocks
          </div>
          <div className="text-lg font-semibold font-mono text-foreground">
            {historyBlocks}
          </div>
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Chain Transactions
          </div>
          <div className="text-lg font-semibold font-mono text-foreground">
            {historyTx}
          </div>
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Anchored Runs Found
          </div>
          <div className="text-lg font-semibold font-mono text-foreground">
            {committedRuns.length}
          </div>
        </div>
      </div>

      {historyQuery.isError && (
        <div className="text-xs text-error">
          Failed to fetch blockchain history from backend.
        </div>
      )}

      <div className="space-y-2">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
          Commitment
        </div>
        <div className="flex items-center gap-2 bg-foreground/[0.03] rounded-lg p-2.5">
          <code className="text-[11px] font-mono flex-1 truncate">{String(commitment ?? "n/a")}</code>
          {!!commitment && (
            <button
              onClick={() => {
                navigator.clipboard
                  .writeText(String(commitment))
                  .then(() => toast.success("Commitment copied"));
              }}
              className="p-1 rounded hover:bg-foreground/10"
              aria-label="Copy commitment"
            >
              <Copy className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
          Anchor Transaction
        </div>
        <div className="bg-foreground/[0.03] rounded-lg p-2.5 text-[11px] font-mono text-foreground/80">
          {String(anchorTx ?? "n/a")}
        </div>
      </div>

      {verifyResult && (
        <div className="rounded-lg border border-foreground/10 p-3 bg-foreground/[0.02]">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span className={verifyResult.verified ? "text-success" : "text-error"}>
              {verifyResult.verified ? "Verified" : "Not verified"}
            </span>
          </div>
          {verifyResult.reason && (
            <div className="text-xs text-muted-foreground mt-1">{verifyResult.reason}</div>
          )}
        </div>
      )}

      <div className="space-y-2">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
          Event Hash Chain
        </div>
        <div className="max-h-64 overflow-auto rounded-lg border border-foreground/10">
          {events.length === 0 ? (
            <div className="p-3 text-xs text-muted-foreground">No events yet.</div>
          ) : (
            [...events].slice(-40).map((e) => (
              <div
                key={e.event_id}
                className="grid grid-cols-[120px_1fr_1fr] gap-2 px-3 py-2 border-b border-foreground/5 last:border-0 text-[10px] font-mono"
              >
                <span className="text-foreground/80">{e.event_type}</span>
                <span className="text-muted-foreground">{shortHash(e.prev_event_hash)}</span>
                <span className="text-foreground">{shortHash(e.event_hash)}</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wide">
          Existing On-Chain Records
        </div>
        <div className="max-h-64 overflow-auto rounded-lg border border-foreground/10">
          {committedRuns.length === 0 ? (
            <div className="p-3 text-xs text-muted-foreground">
              No anchored run records returned by history endpoint.
            </div>
          ) : (
            committedRuns.slice(-80).reverse().map((r, idx) => (
              <div
                key={`${String(r.anchor_tx_hash ?? idx)}-${idx}`}
                className="grid grid-cols-[120px_1fr_1fr] gap-2 px-3 py-2 border-b border-foreground/5 last:border-0 text-[10px] font-mono"
              >
                <span className="text-foreground/80 truncate">
                  {String(r.run_id ?? "unknown")}
                </span>
                <span className="text-muted-foreground truncate">
                  {shortHash(String(r.commitment ?? "n/a"))}
                </span>
                <span className="text-foreground truncate">
                  {shortHash(String(r.anchor_tx_hash ?? "n/a"))}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </motion.section>
  );
}
