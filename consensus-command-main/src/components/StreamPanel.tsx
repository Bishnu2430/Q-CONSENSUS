import { useRef, useEffect, useMemo, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { Search, ArrowDown, ArrowUp, X } from "lucide-react";
import type { StreamEvent } from "@/lib/schemas";

const EVENT_TYPES = [
  "agent_prompted",
  "agent_responded",
  "quantum_randomness",
  "quantum_scheduling",
  "consensus_weights",
  "web_context_enriched",
  "final_answer",
  "run_committed",
];

function EventRow({
  event,
  compact,
}: {
  event: StreamEvent;
  compact: boolean;
}) {
  const p = event.payload as Record<string, unknown>;
  const type = event.event_type;
  const ts = event.ts_unix_ms ?? event.ts;

  const renderContent = () => {
    switch (type) {
      case "agent_prompted":
        return (
          <div className="text-xs text-muted-foreground">
            <span className="pill-neutral text-[10px]">system</span>{" "}
            <span className="font-medium text-foreground">
              {String(p.display_name ?? p.agent_id)}
            </span>{" "}
            started round {String(p.round_idx)}
          </div>
        );
      case "agent_responded":
        return (
          <div className="space-y-1">
            <div className="text-xs font-medium text-foreground">
              {String(p.display_name ?? p.agent_id)} — R{String(p.round_idx)}
            </div>
            {!compact && (
              <div className="text-xs font-mono leading-relaxed text-foreground/80 whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                {String(p.content ?? "")}
              </div>
            )}
          </div>
        );
      case "quantum_randomness":
        return (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="pill-cool text-[10px]">Q-Random</span>
            <span className="text-xs text-foreground">
              policy: {String(p.selected_policy ?? "—")}
            </span>
            {Array.isArray(p.selected_order) && (
              <span className="text-[10px] text-muted-foreground font-mono">
                order: [{(p.selected_order as string[]).join(", ")}]
              </span>
            )}
          </div>
        );
      case "quantum_scheduling":
        return (
          <div className="flex items-center gap-1.5">
            <span className="pill-cool text-[10px]">Q-Sched</span>
            <span className="text-xs">{String(p.selected_policy ?? "—")}</span>
          </div>
        );
      case "consensus_weights":
        return (
          <div className="flex items-center gap-1.5">
            <span className="pill-warm text-[10px]">Weights</span>
            <span className="text-xs">{String(p.selected_policy ?? "—")}</span>
          </div>
        );
      case "web_context_enriched":
        return (
          <div className="flex items-center gap-1.5">
            <span className="pill-cool text-[10px]">Web Context</span>
            <span className="text-xs text-foreground">
              {Number(p.items_count ?? 0)} snippets
            </span>
          </div>
        );
      case "final_answer":
        return (
          <div className="space-y-1">
            <span className="pill-success text-[10px]">Final Answer</span>
            {!compact && (
              <div className="text-xs font-mono text-foreground/80">
                {String(p.final_answer ?? "")}
              </div>
            )}
          </div>
        );
      case "run_committed":
        return (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="pill-success text-[10px]">Committed</span>
            {p.anchor_tx_hash && (
              <span className="text-[10px] font-mono text-muted-foreground truncate max-w-[200px]">
                tx: {String(p.anchor_tx_hash)}
              </span>
            )}
          </div>
        );
      default:
        return (
          <div className="text-xs text-muted-foreground font-mono">
            {type}: {JSON.stringify(p).slice(0, 120)}
          </div>
        );
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="px-3 py-2 border-b border-foreground/5 last:border-0"
    >
      <div className="flex items-start gap-2">
        <span className="text-[10px] font-mono text-muted-foreground/60 pt-0.5 shrink-0">
          {typeof ts === "number"
            ? new Date(ts).toLocaleTimeString()
            : String(ts ?? "").slice(11, 19)}
        </span>
        <div className="flex-1 min-w-0">{renderContent()}</div>
      </div>
    </motion.div>
  );
}

export function StreamPanel() {
  const {
    events,
    eventTypeFilter,
    setEventTypeFilter,
    searchQuery,
    setSearchQuery,
    autoScroll,
    toggleAutoScroll,
    compactMode,
    clearEvents,
    streamState,
  } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearch = useCallback(
    (val: string) => {
      setSearchInput(val);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => setSearchQuery(val), 300);
    },
    [setSearchQuery],
  );

  const filtered = useMemo(() => {
    let result = events;
    if (eventTypeFilter.length > 0) {
      result = result.filter((e) => eventTypeFilter.includes(e.event_type));
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (e) =>
          e.event_type === "agent_responded" &&
          String((e.payload as Record<string, unknown>).content ?? "")
            .toLowerCase()
            .includes(q),
      );
    }
    return result;
  }, [events, eventTypeFilter, searchQuery]);

  useEffect(() => {
    if (autoScroll && !userScrolled && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filtered, autoScroll, userScrolled]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setUserScrolled(scrollHeight - scrollTop - clientHeight > 60);
  };

  const toggleFilter = (t: string) => {
    setEventTypeFilter(
      eventTypeFilter.includes(t)
        ? eventTypeFilter.filter((f) => f !== t)
        : [...eventTypeFilter, t],
    );
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="glass-card flex flex-col overflow-hidden"
      style={{ height: "min(600px, 60vh)" }}
      aria-label="Live Stream"
    >
      <div className="px-4 pt-3 pb-2 border-b border-foreground/5 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">
              Live Stream
            </h2>
            {streamState !== "idle" && (
              <span
                className={`text-[10px] font-medium ${streamState === "connected" ? "text-success" : streamState === "reconnecting" ? "text-accent-warm" : "text-muted-foreground"}`}
              >
                ● {streamState}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={toggleAutoScroll}
              className="pill-neutral text-[10px]"
              aria-label="Toggle auto-scroll"
            >
              {autoScroll ? (
                <ArrowDown className="w-3 h-3" />
              ) : (
                <ArrowUp className="w-3 h-3" />
              )}
              Auto
            </button>
            <button
              onClick={clearEvents}
              className="pill-neutral text-[10px]"
              aria-label="Clear stream"
            >
              <X className="w-3 h-3" /> Clear
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-1">
          {EVENT_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => toggleFilter(t)}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                eventTypeFilter.includes(t)
                  ? "bg-foreground text-primary-foreground border-foreground"
                  : "border-foreground/10 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {t.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search responses…"
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-foreground/[0.03] border border-foreground/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground/50"
          />
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
            {events.length === 0
              ? "No events yet. Start a debate to see live updates."
              : "No matching events."}
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {filtered.map((event) => (
              <EventRow
                key={event.event_id}
                event={event}
                compact={compactMode}
              />
            ))}
          </AnimatePresence>
        )}
      </div>

      <div className="px-4 py-1.5 border-t border-foreground/5 text-[10px] text-muted-foreground">
        {filtered.length} / {events.length} events
      </div>
    </motion.section>
  );
}
