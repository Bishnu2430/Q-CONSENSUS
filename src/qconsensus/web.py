from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import psutil
import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .contract_anchor import ContractAnchoringClient
from .debate import DebateOrchestrator
from .events import JsonlEventStore
from .llm_client import LlamaCppClient
from .metrics import ChainVerifier, MetricsCollector
from .quantum_executor import QuantumExecutor
from .replay import DebateReplayer
from .types import AgentSpec, DebateConfig, QuantumPolicyConfig


class RunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    max_rounds: int = Field(default=3, ge=1, le=3)
    use_quantum_randomness: bool = True
    use_quantum_weights: bool = True
    use_quantum_scheduling: bool = True


class RunResponse(BaseModel):
    run_id: str
    final_answer: str
    commitment: str
    anchor_tx_hash: str | None


class AsyncRunResponse(BaseModel):
    run_id: str
    status: str


class RunResultResponse(BaseModel):
    run_id: str
    status: str
    final_answer: str | None = None
    commitment: str | None = None
    anchor_tx_hash: str | None = None
    error: str | None = None


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
        AgentSpec(
            agent_id="optimizer",
            display_name="Optimizer",
            system_prompt=(
                "You are the Optimizer. Minimize complexity, latency, and operational risk "
                "while preserving answer quality and practical deployability."
            ),
        ),
        AgentSpec(
            agent_id="quantum_strategist",
            display_name="Quantum Strategist",
            system_prompt=(
                "You are the Quantum Strategist. Identify where quantum primitives should and should not be used, "
                "always with a classical baseline recommendation."
            ),
        ),
    ]


def _load_agents_from_yaml(path: str) -> List[AgentSpec]:
    if not os.path.exists(path):
        return _default_agents()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(raw_agents, list) or not raw_agents:
        return _default_agents()

    parsed: List[AgentSpec] = []
    for item in raw_agents:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agent_id", "")).strip()
        display_name = str(item.get("display_name", "")).strip()
        system_prompt = str(item.get("system_prompt", "")).strip()
        if not agent_id or not display_name or not system_prompt:
            continue
        parsed.append(AgentSpec(agent_id=agent_id, display_name=display_name, system_prompt=system_prompt))

    return parsed or _default_agents()


def _build_config(req: RunRequest, agents: List[AgentSpec]) -> DebateConfig:
    return DebateConfig(
        agents=agents,
        max_rounds=req.max_rounds,
        quantum=QuantumPolicyConfig(
            use_quantum_randomness=req.use_quantum_randomness,
            use_quantum_weights=req.use_quantum_weights,
            use_quantum_scheduling=req.use_quantum_scheduling,
        ),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Q-CONSENSUS")

    event_dir = os.getenv("EVENT_STORE_DIR") or os.path.join("data", "events")
    store = JsonlEventStore(event_dir)

    llm = LlamaCppClient()
    qexec = QuantumExecutor({"base_seed": int(os.getenv("QC_BASE_SEED", "42"))})

    contract_init_error: str | None = None
    try:
      contract_client = ContractAnchoringClient.from_env()
    except Exception as exc:  # pragma: no cover - startup resilience
      # Do not fail app startup if blockchain is temporarily unavailable.
      contract_client = None
      contract_init_error = str(exc)
    anchor_contract_address = os.getenv("ANCHOR_CONTRACT_ADDRESS")

    agents_path = os.getenv("AGENTS_CONFIG_PATH", os.path.join("config", "agents.yaml"))
    agents = _load_agents_from_yaml(agents_path)

    metrics = MetricsCollector()
    verifier = ChainVerifier(anchor_client=contract_client, event_store=store)
    replayer = DebateReplayer(event_store=store, llm=llm)
    run_registry: Dict[str, Dict[str, Any]] = {}
    run_lock = threading.Lock()

    orch = DebateOrchestrator(
        event_store=store,
        llm=llm,
        quantum_executor=qexec,
        contract_anchorer=contract_client,
        anchor_contract_address=anchor_contract_address,
    )

    def _record_metrics(run_id: str, cfg: DebateConfig, total_messages: int) -> None:
        metrics.record_run(
            run_id=run_id,
            quantum_policy={
                "use_quantum_randomness": cfg.quantum.use_quantum_randomness,
                "use_quantum_weights": cfg.quantum.use_quantum_weights,
                "use_quantum_scheduling": cfg.quantum.use_quantum_scheduling,
            },
            num_agents=len(cfg.agents),
            num_rounds=cfg.max_rounds,
            total_messages=total_messages,
        )

    def _set_run_state(run_id: str, data: Dict[str, Any]) -> None:
        with run_lock:
            run_registry[run_id] = data

    def _get_run_state(run_id: str) -> Optional[Dict[str, Any]]:
        with run_lock:
            return run_registry.get(run_id)

    def _run_async_worker(run_key: str, req: RunRequest) -> None:
        cfg = _build_config(req, agents)
        _set_run_state(run_key, {"run_id": run_key, "status": "running"})
        try:
            result = orch.run(user_query=req.query, config=cfg, run_id=run_key)
            _record_metrics(run_key, cfg, len(result.messages))
            _set_run_state(
                run_key,
                {
                    "run_id": run_key,
                    "status": "completed",
                    "final_answer": result.final_answer,
                    "commitment": result.commitment,
                    "anchor_tx_hash": result.anchor_tx_hash,
                },
            )
        except Exception as exc:  # pragma: no cover
            _set_run_state(
                run_key,
                {
                    "run_id": run_key,
                    "status": "failed",
                    "error": str(exc),
                },
            )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Q-CONSENSUS</title>
  <link rel='preconnect' href='https://fonts.googleapis.com'>
  <link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
  <link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap' rel='stylesheet'>
  <style>
    :root {
      --bg-1: #f5f1e7;
      --bg-2: #e5ecf4;
      --ink: #162030;
      --accent: #a41f2f;
      --accent-2: #0f8b8d;
      --card: rgba(255, 255, 255, 0.74);
      --border: rgba(22, 32, 48, 0.16);
      --mono: 'IBM Plex Mono', monospace;
      --sans: 'Space Grotesk', sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      font-family: var(--sans);
      color: var(--ink);
      background:
        radial-gradient(circle at 20% 10%, rgba(164,31,47,.22), transparent 45%),
        radial-gradient(circle at 80% 90%, rgba(15,139,141,.20), transparent 38%),
        linear-gradient(130deg, var(--bg-1), var(--bg-2));
      animation: breathe 14s ease-in-out infinite alternate;
    }
    @keyframes breathe { from { background-position: 0% 0%, 100% 100%, 0 0; } to { background-position: 10% 5%, 90% 95%, 0 0; } }
    .shell { max-width: 1300px; margin: 0 auto; padding: 16px; min-height: 100%; display: grid; gap: 12px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: center;
      background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 12px 14px;
      backdrop-filter: blur(6px);
    }
    .brand { font-weight: 700; letter-spacing: .03em; }
    .sub { font-family: var(--mono); font-size: 12px; opacity: .75; }
    .grid { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 12px; }
    .pane {
      background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 12px;
      backdrop-filter: blur(6px); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
      transform: translateY(10px); opacity: 0; animation: rise .35s ease forwards;
    }
    .pane:nth-child(2) { animation-delay: .08s; }
    .pane:nth-child(3) { animation-delay: .16s; }
    .pane:nth-child(4) { animation-delay: .24s; }
    @keyframes rise { to { transform: translateY(0); opacity: 1; } }
    .title { font-weight: 700; margin-bottom: 8px; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    textarea { width: 100%; min-height: 130px; border-radius: 10px; border: 1px solid var(--border); padding: 10px; font-family: var(--mono); resize: vertical; }
    .pill { border-radius: 999px; border: 1px solid var(--border); padding: 4px 10px; font-family: var(--mono); font-size: 12px; background: rgba(255,255,255,.58); }
    button { border: 0; border-radius: 10px; padding: 10px 14px; font-weight: 700; color: #fff; background: linear-gradient(115deg, var(--accent), #d35400); cursor: pointer; }
    button.secondary { background: linear-gradient(115deg, #27566b, var(--accent-2)); }
    .chat { display: flex; flex-direction: column; gap: 10px; max-height: 58vh; overflow: auto; }
    .msg { border-radius: 10px; padding: 8px 10px; border: 1px solid var(--border); background: rgba(255,255,255,.78); }
    .meta { font-size: 12px; font-family: var(--mono); opacity: 0.75; margin-bottom: 4px; }
    pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-family: var(--mono); }
    .controls { display: grid; grid-template-columns: repeat(3, minmax(130px, 1fr)); gap: 8px; margin: 10px 0; }
    .toggle { display: flex; align-items: center; gap: 6px; font-size: 13px; }
    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } .chat { max-height: 42vh; } }
  </style>
</head>
<body>
  <div class='shell'>
    <div class='topbar'>
      <div>
        <div class='brand'>Q-CONSENSUS Debate Control Room</div>
        <div class='sub'>multi-agent · quantum-policy-aware · blockchain-anchorable</div>
      </div>
      <div class='pill' id='runInfo'>idle</div>
    </div>
    <div class='grid'>
      <div class='pane' id='inputPane'>
        <div class='title'>Input</div>
        <textarea id='query' placeholder='Enter your query...'></textarea>
        <div class='controls'>
          <label class='toggle'><input id='qRand' type='checkbox' checked /> quantum randomness</label>
          <label class='toggle'><input id='qWeight' type='checkbox' checked /> quantum weights</label>
          <label class='toggle'><input id='qSched' type='checkbox' checked /> quantum scheduling</label>
        </div>
        <div class='row'>
          <button onclick='runDebate()'>Run debate</button>
          <button class='secondary' onclick='runDebateAsync()'>Run async + stream</button>
        </div>
      </div>
      <div class='pane' id='statusPane'>
        <div class='title'>System status</div>
        <pre id='status'></pre>
      </div>
      <div class='pane' id='debatePane'>
        <div class='title'>Debate stream</div>
        <div class='chat' id='chat'></div>
      </div>
      <div class='pane' id='reasonPane'>
        <div class='title'>Reasoning / Validation</div>
        <pre id='final'></pre>
      </div>
    </div>
  </div>

<script>
let currentEventSource = null;

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

function addSystemMsg(content) {
  appendMsg('system', content);
}

function escapeHtml(s) {
  return (s || '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
}

function requestBody() {
  return {
    query: document.getElementById('query').value,
    use_quantum_randomness: document.getElementById('qRand').checked,
    use_quantum_weights: document.getElementById('qWeight').checked,
    use_quantum_scheduling: document.getElementById('qSched').checked,
    max_rounds: 3,
  };
}

async function runDebate() {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  document.getElementById('chat').innerHTML = '';
  document.getElementById('final').textContent = '';

  const r = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody())
  });

  if (!r.ok) {
    addSystemMsg(`run failed: ${await r.text()}`);
    return;
  }

  const j = await r.json();
  document.getElementById('runInfo').textContent = `run_id=${j.run_id}`;

  const ev = await fetch(`/api/events/${j.run_id}`);
  const events = await ev.json();
  for (const e of events) {
    if (e.event_type === 'agent_responded') {
      appendMsg(`${e.payload.display_name} · round ${e.payload.round_idx}`, e.payload.content);
    }
  }
  document.getElementById('final').textContent = `Final answer:\n\n${j.final_answer}\n\nCommitment: ${j.commitment}\nAnchor tx: ${j.anchor_tx_hash || 'n/a'}`;
}

async function runDebateAsync() {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  document.getElementById('chat').innerHTML = '';
  document.getElementById('final').textContent = '';

  const r = await fetch('/api/run_async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody())
  });

  if (!r.ok) {
    addSystemMsg(`async start failed: ${await r.text()}`);
    return;
  }

  const j = await r.json();
  document.getElementById('runInfo').textContent = `run_id=${j.run_id} · ${j.status}`;
  addSystemMsg('stream opened');

  currentEventSource = new EventSource(`/api/stream/${j.run_id}`);
  currentEventSource.onmessage = (evt) => {
    const e = JSON.parse(evt.data);
    if (e.event_type === 'agent_responded') {
      appendMsg(`${e.payload.display_name} · round ${e.payload.round_idx}`, e.payload.content);
    }
    if (e.event_type === 'run_committed') {
      document.getElementById('final').textContent = `Commitment: ${e.payload.commitment}\nAnchor tx: ${e.payload.anchor_tx_hash || 'n/a'}`;
    }
  };

  currentEventSource.onerror = () => {
    addSystemMsg('stream disconnected');
    currentEventSource.close();
    currentEventSource = null;
  };

  const poll = async () => {
    const rr = await fetch(`/api/result/${j.run_id}`);
    const rj = await rr.json();
    if (rj.status === 'completed' || rj.status === 'failed') {
      document.getElementById('runInfo').textContent = `run_id=${j.run_id} · ${rj.status}`;
      if (rj.final_answer) {
        document.getElementById('final').textContent = `Final answer:\n\n${rj.final_answer}\n\nCommitment: ${rj.commitment || 'n/a'}\nAnchor tx: ${rj.anchor_tx_hash || 'n/a'}`;
      }
      if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
      }
      return;
    }
    setTimeout(poll, 1000);
  };
  setTimeout(poll, 1000);
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
            "agents_loaded": len(agents),
            "agents_config_path": agents_path,
            "contract_anchor_enabled": bool(contract_client and anchor_contract_address),
        "contract_anchor_init_error": contract_init_error,
        }

    @app.post("/api/run", response_model=RunResponse)
    def run(req: RunRequest) -> RunResponse:
        cfg = _build_config(req, agents)
        result = orch.run(user_query=req.query, config=cfg)
        _record_metrics(result.run_id, cfg, len(result.messages))
        _set_run_state(
            result.run_id,
            {
                "run_id": result.run_id,
                "status": "completed",
                "final_answer": result.final_answer,
                "commitment": result.commitment,
                "anchor_tx_hash": result.anchor_tx_hash,
            },
        )
        return RunResponse(
            run_id=result.run_id,
            final_answer=result.final_answer,
            commitment=result.commitment,
            anchor_tx_hash=result.anchor_tx_hash,
        )

    @app.post("/api/run_async", response_model=AsyncRunResponse)
    def run_async(req: RunRequest) -> AsyncRunResponse:
        run_key = f"pending-{int(time.time() * 1000)}"
        t = threading.Thread(target=_run_async_worker, args=(run_key, req), daemon=True)
        t.start()
        return AsyncRunResponse(run_id=run_key, status="running")

    @app.get("/api/events/{run_id}")
    def events(run_id: str) -> list[dict]:
        return [e.to_dict() for e in store.iter_events(run_id)]

    @app.post("/api/replay/{run_id}")
    def replay(run_id: str) -> dict:
      return replayer.replay(run_id=run_id)

    @app.get("/api/stream/{run_id}")
    def stream(run_id: str) -> StreamingResponse:
        q = store.subscribe(run_id)

        def generate():
            try:
                for ev in store.iter_events(run_id):
                    yield f"data: {json.dumps(ev.to_dict(), ensure_ascii=False)}\\n\\n"

                while True:
                    try:
                        ev = q.get(timeout=20)
                        yield f"data: {json.dumps(ev.to_dict(), ensure_ascii=False)}\\n\\n"
                    except queue.Empty:
                        yield ": keepalive\\n\\n"
            finally:
                store.unsubscribe(run_id, q)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/result/{run_id}", response_model=RunResultResponse)
    def result(run_id: str) -> RunResultResponse:
        state = _get_run_state(run_id)
        if state:
            return RunResultResponse(**state)

        events = [e.to_dict() for e in store.iter_events(run_id)]
        if not events:
            return RunResultResponse(run_id=run_id, status="not_found")

        final_answer = None
        commitment = None
        anchor_tx_hash = None
        for e in events:
            if e.get("event_type") == "final_answer":
                final_answer = e.get("payload", {}).get("final_answer")
            if e.get("event_type") == "run_committed":
                commitment = e.get("payload", {}).get("commitment")
                anchor_tx_hash = e.get("payload", {}).get("anchor_tx_hash")

        return RunResultResponse(
            run_id=run_id,
            status="completed" if commitment else "running",
            final_answer=final_answer,
            commitment=commitment,
            anchor_tx_hash=anchor_tx_hash,
        )

    @app.get("/api/verify/{run_id}")
    def verify(run_id: str) -> dict:
      if not contract_client:
        return {
          "verified": False,
          "reason": "Contract anchor client is unavailable",
          "details": contract_init_error,
        }
        if not anchor_contract_address:
            return {"verified": False, "reason": "ANCHOR_CONTRACT_ADDRESS is not configured"}
        return verifier.verify_run(run_id=run_id, contract_address=anchor_contract_address)

    @app.get("/api/metrics")
    def metrics_summary() -> dict:
        return metrics.get_summary()

    @app.get("/api/metrics/quantum-vs-classical")
    def metrics_qvc() -> dict:
        return metrics.get_quantum_vs_classical()

    return app


app = create_app()
