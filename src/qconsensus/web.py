from __future__ import annotations

import os
from typing import List

import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .debate import DebateOrchestrator
from .eth_anchor import EthRunAnchoringClient
from .events import JsonlEventStore
from .llm_client import LlamaCppClient
from .quantum_executor import QuantumExecutor
from .types import AgentSpec, DebateConfig


class RunRequest(BaseModel):
    query: str


class RunResponse(BaseModel):
    run_id: str
    final_answer: str
    commitment: str
    anchor_tx_hash: str | None


def _default_agents() -> List[AgentSpec]:
    return [
        AgentSpec(
            agent_id="proposer",
            display_name="Proposer",
            system_prompt=(
                "You are the Proposer. Be direct and solution-oriented. "
                "Offer a clear answer quickly, then list assumptions."
            ),
        ),
        AgentSpec(
            agent_id="skeptic",
            display_name="Skeptic",
            system_prompt=(
                "You are the Skeptic. Look for flaws, missing edge cases, and overconfidence. "
                "Challenge claims and ask for evidence."
            ),
        ),
        AgentSpec(
            agent_id="verifier",
            display_name="Verifier",
            system_prompt=(
                "You are the Verifier. Focus on correctness and validation. "
                "Propose checks/tests and reconcile disagreements."
            ),
        ),
    ]


def create_app() -> FastAPI:
    app = FastAPI(title="Q-CONSENSUS")

    event_dir = os.getenv("EVENT_STORE_DIR") or os.path.join("data", "events")
    store = JsonlEventStore(event_dir)

    llm = LlamaCppClient()

    qexec = QuantumExecutor({"base_seed": int(os.getenv("QC_BASE_SEED", "42"))})

    eth = EthRunAnchoringClient.from_env()

    orch = DebateOrchestrator(event_store=store, llm=llm, quantum_executor=qexec, eth_anchorer=eth)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Q-CONSENSUS</title>
  <style>
    html, body { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 220px 1fr; gap: 12px; padding: 12px; height: calc(100% - 24px); box-sizing: border-box; }
    .pane { border: 1px solid #ddd; border-radius: 10px; padding: 10px; overflow: auto; }
    .row { display: flex; gap: 8px; }
    textarea { width: 100%; height: 120px; }
    button { padding: 8px 12px; }
    .chat { display: flex; flex-direction: column; gap: 10px; }
    .msg { border-radius: 10px; padding: 8px 10px; border: 1px solid #eee; }
    .meta { font-size: 12px; opacity: 0.7; margin-bottom: 4px; }
    pre { white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <div class='grid'>
    <div class='pane' id='inputPane'>
      <div><strong>Input</strong></div>
      <textarea id='query' placeholder='Enter your query...'></textarea>
      <div class='row'>
        <button onclick='runDebate()'>Run debate</button>
        <span id='runInfo'></span>
      </div>
    </div>
    <div class='pane' id='statusPane'>
      <div><strong>System status</strong></div>
      <pre id='status'></pre>
    </div>
    <div class='pane' id='debatePane'>
      <div><strong>Debate</strong></div>
      <div class='chat' id='chat'></div>
    </div>
    <div class='pane' id='reasonPane'>
      <div><strong>Reasoning / Validation</strong></div>
      <pre id='final'></pre>
    </div>
  </div>

<script>
async function refreshStatus() {
  const r = await fetch('/api/status');
  const j = await r.json();
  document.getElementById('status').textContent = JSON.stringify(j, null, 2);
}
setInterval(refreshStatus, 1500);
refreshStatus();

function appendMsg(agent, content) {
  const el = document.createElement('div');
  el.className = 'msg';
  el.innerHTML = `<div class='meta'>${agent}</div><pre>${escapeHtml(content)}</pre>`;
  document.getElementById('chat').appendChild(el);
}

function escapeHtml(s) {
  return s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
}

async function runDebate() {
  document.getElementById('chat').innerHTML = '';
  document.getElementById('final').textContent = '';

  const query = document.getElementById('query').value;
  const r = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  const j = await r.json();
  document.getElementById('runInfo').textContent = `run_id=${j.run_id}`;

  const ev = await fetch(`/api/events/${j.run_id}`);
  const events = await ev.json();
  for (const e of events) {
    if (e.event_type === 'agent_responded') {
      appendMsg(e.payload.display_name, e.payload.content);
    }
  }
  document.getElementById('final').textContent = `Final answer:\n\n${j.final_answer}\n\nCommitment: ${j.commitment}\nAnchor tx: ${j.anchor_tx_hash || 'n/a'}`;
}
</script>
</body>
</html>"""

    @app.get("/api/status")
    def status() -> dict:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.0),
            "mem_total": vm.total,
            "mem_used": vm.used,
            "mem_percent": vm.percent,
        }

    @app.post("/api/run", response_model=RunResponse)
    def run(req: RunRequest) -> RunResponse:
        cfg = DebateConfig(agents=_default_agents(), max_rounds=2)
        result = orch.run(user_query=req.query, config=cfg)
        return RunResponse(
            run_id=result.run_id,
            final_answer=result.final_answer,
            commitment=result.commitment,
            anchor_tx_hash=result.anchor_tx_hash,
        )

    @app.get("/api/events/{run_id}")
    def events(run_id: str) -> list[dict]:
        return [e.to_dict() for e in store.iter_events(run_id)]

    return app


app = create_app()
