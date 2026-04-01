import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { Cpu, HardDrive, Users, Anchor, RefreshCw } from 'lucide-react';

function Meter({ value, color, label }: { value: number; color: string; label: string }) {
  return (
    <div className="space-y-1" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="flex justify-between text-[10px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium text-foreground">{value.toFixed(1)}%</span>
      </div>
      <div className="meter-track">
        <motion.div
          className="meter-fill"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(value, 100)}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

export function SystemStatus() {
  const systemStatus = useAppStore(s => s.systemStatus);
  const { refetch, isFetching } = useSystemStatus();

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="glass-card p-5 space-y-4"
      aria-label="System Status"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">System Status</h2>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-1.5 rounded-md hover:bg-foreground/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Refresh status"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-muted-foreground ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {!systemStatus ? (
        <p className="text-xs text-muted-foreground">Connecting to backend…</p>
      ) : (
        <>
          <Meter value={systemStatus.cpu_percent} color="hsl(183 75% 30%)" label="CPU" />
          <Meter value={systemStatus.mem_percent} color="hsl(212 41% 14%)" label="Memory" />

          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-center gap-2">
              <Users className="w-3.5 h-3.5 text-muted-foreground" />
              <div>
                <div className="text-[10px] text-muted-foreground">Agents</div>
                <div className="text-sm font-semibold text-foreground">{systemStatus.agents_loaded}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Anchor className="w-3.5 h-3.5 text-muted-foreground" />
              <div>
                <div className="text-[10px] text-muted-foreground">Anchor</div>
                <span className={systemStatus.contract_anchor_enabled ? 'pill-success text-[10px]' : 'pill-error text-[10px]'}>
                  {systemStatus.contract_anchor_enabled ? 'Ready' : 'Degraded'}
                </span>
              </div>
            </div>
          </div>

          <div className="text-[10px] text-muted-foreground font-mono leading-relaxed">
            {systemStatus.contract_anchor_init_error ? (
              <span className="text-error">{systemStatus.contract_anchor_init_error}</span>
            ) : (
              <>
                <div>Config: {systemStatus.agents_config_path}</div>
                <div>Memory: {(systemStatus.mem_used / (1024 * 1024)).toFixed(0)} MiB / {(systemStatus.mem_total / (1024 * 1024)).toFixed(0)} MiB</div>
              </>
            )}
          </div>
        </>
      )}
    </motion.section>
  );
}
