import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { Copy, ExternalLink, ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import { useState } from 'react';

function copyText(text: string) {
  navigator.clipboard.writeText(text).then(() => toast.success('Copied'));
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-foreground/5 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-foreground hover:bg-foreground/[0.02] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {title}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-3 pb-3 text-xs font-mono text-foreground/70 whitespace-pre-wrap">{children}</div>}
    </div>
  );
}

export function FinalReasoning() {
  const { result, events } = useAppStore();

  // Also look for final_answer event for baseline data
  const finalEvent = events.find(e => e.event_type === 'final_answer');
  const fp = finalEvent?.payload as Record<string, unknown> | undefined;
  const commitEvent = events.find(e => e.event_type === 'run_committed');
  const cp = commitEvent?.payload as Record<string, unknown> | undefined;

  const finalAnswer = result?.final_answer ?? (fp?.final_answer as string) ?? null;
  const commitment = result?.commitment ?? (cp?.commitment as string) ?? null;
  const txHash = result?.anchor_tx_hash ?? (cp?.anchor_tx_hash as string) ?? null;

  if (!finalAnswer && !commitment) {
    return (
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card p-5"
        aria-label="Final Reasoning"
      >
        <h2 className="text-sm font-semibold text-foreground mb-3">Final Reasoning</h2>
        <p className="text-xs text-muted-foreground">No result yet. Run a debate to see the final reasoning here.</p>
      </motion.section>
    );
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-card p-5 space-y-4"
      aria-label="Final Reasoning"
    >
      <h2 className="text-sm font-semibold text-foreground">Final Reasoning</h2>

      {finalAnswer && (
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Final Answer</div>
          <div className="text-sm font-mono text-foreground leading-relaxed whitespace-pre-wrap bg-foreground/[0.02] rounded-lg p-3">
            {finalAnswer}
          </div>
        </div>
      )}

      {fp?.selected_policy && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground">Policy:</span>
          <span className="pill-cool text-[10px]">{String(fp.selected_policy)}</span>
        </div>
      )}

      {fp?.quantum_baseline_answer && (
        <Collapsible title="Quantum Baseline Answer">
          {String(fp.quantum_baseline_answer)}
        </Collapsible>
      )}

      {fp?.classical_baseline_answer && (
        <Collapsible title="Classical Baseline Answer">
          {String(fp.classical_baseline_answer)}
        </Collapsible>
      )}

      {commitment && (
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Commitment</div>
          <div className="flex items-center gap-2">
            <code className="text-[11px] font-mono text-foreground/70 truncate flex-1">{commitment}</code>
            <button onClick={() => copyText(commitment)} className="shrink-0 p-1 rounded hover:bg-foreground/5" aria-label="Copy commitment">
              <Copy className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          </div>
        </div>
      )}

      {txHash && (
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Anchor TX</div>
          <div className="flex items-center gap-2">
            <code className="text-[11px] font-mono text-foreground/70 truncate flex-1">{txHash}</code>
            <button onClick={() => copyText(txHash)} className="shrink-0 p-1 rounded hover:bg-foreground/5" aria-label="Copy tx hash">
              <Copy className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
            <a
              href={`#explorer/${txHash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 p-1 rounded hover:bg-foreground/5"
              aria-label="View on explorer"
            >
              <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
            </a>
          </div>
        </div>
      )}
    </motion.section>
  );
}
