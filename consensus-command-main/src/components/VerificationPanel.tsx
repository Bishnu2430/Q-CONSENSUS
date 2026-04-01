import { useState } from 'react';
import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { api } from '@/lib/api';
import { Shield, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

export function VerificationPanel() {
  const { currentRunId, verificationHistory, addVerification } = useAppStore();
  const [runIdInput, setRunIdInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);

  const handleVerify = async () => {
    const rid = runIdInput.trim() || currentRunId;
    if (!rid) {
      toast.error('Enter a run ID or start a debate first.');
      return;
    }
    setLoading(true);
    try {
      const res = await api.verify(rid);
      const result = res as Record<string, unknown>;
      setLastResult(result);
      addVerification(rid, result);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25 }}
      className="glass-card p-5 space-y-4"
      aria-label="Verification"
    >
      <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <Shield className="w-4 h-4 text-accent-cool" /> Verification
      </h2>

      <div className="flex gap-2">
        <input
          type="text"
          value={runIdInput}
          onChange={e => setRunIdInput(e.target.value)}
          placeholder={currentRunId ? `Current: ${currentRunId.slice(0, 12)}…` : 'Enter run_id'}
          className="flex-1 px-3 py-2 text-xs font-mono bg-foreground/[0.03] border border-foreground/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground/50"
        />
        <button
          onClick={handleVerify}
          disabled={loading}
          className="px-4 py-2 text-xs font-semibold bg-foreground text-primary-foreground rounded-lg hover:bg-foreground/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Verify'}
        </button>
      </div>

      {lastResult && (
        <div className="p-3 bg-foreground/[0.02] rounded-lg space-y-2">
          <div className="flex items-center gap-2">
            {lastResult.verified ? (
              <><CheckCircle className="w-4 h-4 text-success" /> <span className="text-sm font-semibold text-success">Verified</span></>
            ) : (
              <><XCircle className="w-4 h-4 text-error" /> <span className="text-sm font-semibold text-error">Not Verified</span></>
            )}
          </div>
          {lastResult.reason && <div className="text-xs text-muted-foreground">{String(lastResult.reason)}</div>}
          {lastResult.details && (
            <pre className="text-[10px] font-mono text-foreground/60 overflow-auto max-h-32">
              {JSON.stringify(lastResult.details, null, 2)}
            </pre>
          )}
        </div>
      )}

      {verificationHistory.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">History</div>
          {verificationHistory.map((v, i) => (
            <div key={i} className="flex items-center justify-between text-[10px] py-1 border-b border-foreground/5 last:border-0">
              <span className="font-mono text-foreground/70 truncate max-w-[140px]">{v.runId}</span>
              <span className={v.result.verified ? 'text-success' : 'text-error'}>
                {v.result.verified ? '✓' : '✗'}
              </span>
              <span className="text-muted-foreground">{new Date(v.ts).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      )}
    </motion.section>
  );
}
