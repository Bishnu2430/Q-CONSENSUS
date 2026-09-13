/** Deterministic agent_id -> color assignment, consistent across the
 * relationship graph and chat feed, and across light/dark mode (each
 * --agent-N token has both a light and dark value in index.css). */

const AGENT_COLOR_COUNT = 10;

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 31 + input.charCodeAt(i)) >>> 0;
  }
  return hash;
}

/** Returns 1-10, matching the --agent-N CSS variables / agent-N Tailwind color. */
export function agentColorIndex(agentId: string): number {
  return (hashString(agentId) % AGENT_COLOR_COUNT) + 1;
}

export function agentColorVar(agentId: string): string {
  return `hsl(var(--agent-${agentColorIndex(agentId)}))`;
}

export function agentColorClass(agentId: string, prefix: "text" | "bg" | "border" = "text"): string {
  return `${prefix}-agent-${agentColorIndex(agentId)}`;
}
