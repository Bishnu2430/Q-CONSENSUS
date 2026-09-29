#!/usr/bin/env bash
# Q-CONSENSUS launcher: checks every dependency, then starts the project.
#
# Usage: scripts/start.sh [command] [options]
#
# Commands:
#   up        (default) build and start the full Docker stack at http://localhost:8000
#   dev       llama + blockchain in Docker; API and frontend run locally with hot reload
#   check     run the dependency checks only (for "up"; add --dev for dev mode)
#   status    show container state and endpoint health
#   logs      follow container logs (optionally: logs <service>)
#   stop      stop the Docker stack (chain data volume is kept)
#
# Options:
#   --smoke      after startup, run a short real debate and verify it produced an answer
#   --no-build   start with the existing orchestrator image (skip docker compose build)
#   --no-open    don't open the browser
#   --dev        with "check": check dev-mode dependencies instead of Docker-mode ones
#   -h, --help   show this help
#
# Runs on Linux and on Windows in Git Bash (with Docker Desktop);
# scripts\start.cmd is the same launcher for PowerShell/cmd.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 VENV_PY_REL=".venv/Scripts/python.exe" ;;
  *) IS_WINDOWS=0 VENV_PY_REL=".venv/bin/python" ;;
esac

FRONTEND_DIR="consensus-command-main"
API_PORT=8000
LLM_PORT=8080
RPC_PORT=8545
VITE_PORT=5173
MIN_RAM_GB=6
MIN_DISK_GB=5
MODELS_VOLUME="qconsensus_models"
# Well-known account of the local geth dev chain (see blockchain/init-geth.sh).
# It only ever holds test ether on this private chain.
DEV_CHAIN_ADDRESS="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
DEV_CHAIN_PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


# ---------------------------------------------------------------- output ---

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RED=$'\033[31m' C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' C_BLUE=$'\033[34m' C_BOLD=$'\033[1m' C_RESET=$'\033[0m'
else
  C_RED="" C_GREEN="" C_YELLOW="" C_BLUE="" C_BOLD="" C_RESET=""
fi

FAILURES=0
WARNINGS=0

step() { printf '\n%s==> %s%s\n' "$C_BOLD$C_BLUE" "$1" "$C_RESET"; }
ok()   { printf '  %s✔%s %s\n' "$C_GREEN" "$C_RESET" "$1"; }
info() { printf '  %s•%s %s\n' "$C_BLUE" "$C_RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$C_YELLOW" "$C_RESET" "$1"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '  %s✘%s %s\n' "$C_RED" "$C_RESET" "$1"; FAILURES=$((FAILURES + 1)); }
hint() { printf '      %s↳ %s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }
die()  { printf '\n%s✘ %s%s\n' "$C_RED$C_BOLD" "$1" "$C_RESET" >&2; exit 1; }

usage() { sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# ------------------------------------------------------------------- .env ---

env_get() {
  # Last assignment wins; strips CR, surrounding quotes, and inline "# comments".
  [[ -f .env ]] || return 0
  awk -v key="$1" '
    { sub(/\r$/, "") }
    $0 ~ "^[[:space:]]*" key "=" {
      val = substr($0, index($0, "=") + 1)
      sub(/[[:space:]]+#.*$/, "", val)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
      if (val ~ /^".*"$/ || val ~ /^'\''.*'\''$/) val = substr(val, 2, length(val) - 2)
      found = val
    }
    END { printf "%s", found }
  ' .env
}

env_set() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { done = 0 }
    $0 ~ "^[[:space:]]*" key "=" { if (!done) { print key "=" value; done = 1 }; next }
    { print }
    END { if (!done) print key "=" value }
  ' .env > "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}

is_true() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

export_dotenv() {
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)= ]] || continue
    key="${BASH_REMATCH[1]}"
    value="$(env_get "$key")"
    export "$key=$value"
  done < .env
}

load_ports() {
  # Host ports docker-compose.yml publishes (overridable in .env).
  API_PORT="$(env_get API_PORT)"; API_PORT="${API_PORT:-8000}"
  LLM_PORT="$(env_get LLM_PORT)"; LLM_PORT="${LLM_PORT:-8080}"
  RPC_PORT="$(env_get RPC_PORT)"; RPC_PORT="${RPC_PORT:-8545}"
  VITE_PORT="$(env_get VITE_PORT)"; VITE_PORT="${VITE_PORT:-5173}"
}

# -------------------------------------------------------------- utilities ---

have() { command -v "$1" >/dev/null 2>&1; }

version_ge() {
  # version_ge 20.1.0 18 -> true
  [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]
}

win_listener_pid() {
  # PID listening on a TCP port, from Windows netstat. A listening socket's
  # foreign address is 0.0.0.0:0 / [::]:0, which (unlike the state column)
  # isn't translated on non-English Windows.
  netstat -ano 2>/dev/null | tr -d '\r' | awk -v port=":$1" '
    $1 == "TCP" && ($3 == "0.0.0.0:0" || $3 == "[::]:0") &&
    substr($2, length($2) - length(port) + 1) == port { print $5; exit }'
}

win_port_reserved() {
  # True if Windows (Hyper-V/WinNAT) reserved the port: Docker can't bind it.
  netsh interface ipv4 show excludedportrange protocol=tcp 2>/dev/null | tr -d '\r' |
    awk -v port="$1" '$1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ && port >= $1 && port <= $2 { found = 1 } END { exit !found }'
}

port_in_use() {
  local port="$1"
  if [[ "$IS_WINDOWS" == 1 ]]; then
    [[ -n "$(win_listener_pid "$port")" ]]
  elif have ss; then
    [[ -n "$(ss -Hltn "sport = :$port" 2>/dev/null)" ]]
  elif have lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
  fi
}

port_owner() {
  local port="$1" pid
  if [[ "$IS_WINDOWS" == 1 ]]; then
    pid="$(win_listener_pid "$port")"
    [[ -n "$pid" ]] || return 0
    printf '%s (PID %s)' "$(tasklist //FI "PID eq $pid" //FO CSV //NH 2>/dev/null | tr -d '\r' | cut -d'"' -f2)" "$pid"
  elif have ss; then
    ss -Hltnp "sport = :$port" 2>/dev/null | grep -o 'users:(("[^"]*"' | head -n1 | sed 's/users:(("//; s/"$//'
  elif have lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1}'
  fi
}

kill_tree() {
  local pid="$1" child winpid
  if [[ "$IS_WINDOWS" == 1 ]]; then
    # Native Windows processes (python.exe, node.exe) don't get MSYS signals:
    # end the whole Windows process tree under this background job instead.
    winpid="$(cat "/proc/$pid/winpid" 2>/dev/null || true)"
    [[ -n "$winpid" ]] && taskkill //F //T //PID "$winpid" >/dev/null 2>&1
    kill "$pid" 2>/dev/null || true
    return 0
  fi
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

compose_running() {
  # compose_running <service> -> true if that service's container is running
  docker compose ps --status running --services 2>/dev/null | grep -qx "$1"
}

open_browser() {
  local url="$1"
  [[ "${OPEN_BROWSER}" == 1 ]] || return 0
  if [[ "$IS_WINDOWS" == 1 ]]; then
    cmd.exe //c start "" "$url" >/dev/null 2>&1 || true
  elif have xdg-open && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif have open && [[ "$(uname -s)" == "Darwin" ]]; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

wait_http() {
  # wait_http <label> <timeout-seconds> <curl args...>
  local label="$1" timeout="$2"
  shift 2
  local start=$SECONDS
  printf '  %s…%s waiting for %s ' "$C_BLUE" "$C_RESET" "$label"
  until curl -fsS -o /dev/null --max-time 5 "$@" 2>/dev/null; do
    if (( SECONDS - start >= timeout )); then
      printf '%stimed out after %ss%s\n' "$C_RED" "$timeout" "$C_RESET"
      return 1
    fi
    printf '.'
    sleep 2
  done
  printf '%sready (%ss)%s\n' "$C_GREEN" "$((SECONDS - start))" "$C_RESET"
}

rpc_call() {
  # rpc_call <method> <params-json> -> raw JSON-RPC response from the local chain
  curl -fsS --max-time 5 "http://localhost:$RPC_PORT" \
    -H 'Content-Type: application/json' \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"$1\",\"params\":$2,\"id\":1}"
}

show_failed_services() {
  docker compose ps -a || true
  local svc
  for svc in "$@"; do
    printf '\n%s--- last 30 log lines: %s ---%s\n' "$C_BOLD" "$svc" "$C_RESET"
    docker compose logs --no-color --tail 30 "$svc" 2>&1 || true
  done
}

# ---------------------------------------------------------------- checks ---

start_docker_desktop() {
  # Windows: launch Docker Desktop and wait up to 3 minutes for its engine.
  local exe
  for exe in "${ProgramFiles:-C:\\Program Files}\\Docker\\Docker\\Docker Desktop.exe" \
             "${LOCALAPPDATA:-}\\Programs\\Docker\\Docker\\Docker Desktop.exe"; do
    [[ -f "$(cygpath -u "$exe" 2>/dev/null)" ]] || continue
    info "Docker Desktop is not running; starting it (this can take a minute)"
    cmd.exe //c start "" "$exe" >/dev/null 2>&1 || true
    local start=$SECONDS
    while (( SECONDS - start < 180 )); do
      sleep 3
      docker info >/dev/null 2>&1 && return 0
    done
    return 1
  done
  return 1
}

check_docker() {
  if ! have docker; then
    fail "docker is not installed"
    if [[ "$IS_WINDOWS" == 1 ]]; then
      hint "Install Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/"
    else
      hint "Install Docker Engine: https://docs.docker.com/engine/install/"
    fi
    return
  fi
  local err
  if ! err="$(docker info 2>&1 >/dev/null)"; then
    if [[ "$IS_WINDOWS" == 1 ]]; then
      if [[ "$AUTO_FIX" != 1 ]] || ! start_docker_desktop; then
        fail "Docker Desktop is not running"
        hint "Start Docker Desktop from the Start menu, wait for \"Engine running\", then re-run"
        return
      fi
    elif grep -qi "permission denied" <<<"$err"; then
      fail "docker daemon is running but this user can't access it"
      hint "sudo usermod -aG docker \"$USER\"  (then log out and back in)"
      return
    else
      fail "docker daemon is not running"
      hint "sudo systemctl start docker"
      return
    fi
  fi
  if [[ "$(docker info --format '{{.OSType}}' 2>/dev/null)" != linux ]]; then
    fail "Docker is in Windows-containers mode; this project needs Linux containers"
    hint "Right-click the Docker tray icon -> \"Switch to Linux containers...\""
    return
  fi
  ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"

  if ! docker compose version >/dev/null 2>&1; then
    fail "docker compose v2 plugin is missing"
    if [[ "$IS_WINDOWS" == 1 ]]; then
      hint "Update Docker Desktop (it bundles Compose v2)"
    else
      hint "Install the compose plugin: https://docs.docker.com/compose/install/linux/"
    fi
    return
  fi
  local compose_version
  compose_version="$(docker compose version --short 2>/dev/null | sed 's/^v//; s/+.*//')"
  if version_ge "$compose_version" "2.20"; then
    ok "docker compose $compose_version"
  else
    fail "docker compose $compose_version is too old (need >= 2.20 for --wait)"
  fi
}

check_curl() {
  if have curl; then ok "curl"; else fail "curl is not installed"; hint "sudo apt install curl"; fi
}

check_env_file() {
  if [[ ! -f .env ]]; then
    if [[ "$AUTO_FIX" != 1 ]]; then
      warn ".env does not exist yet (start will create it from .env.example)"
      return
    fi
    cp .env.example .env
    ok ".env created from .env.example"
  else
    ok ".env present"
  fi

  local key missing=()
  while IFS= read -r key; do
    grep -qE "^[[:space:]]*${key}=" .env || missing+=("$key")
  done < <(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' .env.example | tr -d '=')
  if (( ${#missing[@]} )); then
    warn ".env is missing keys from .env.example (defaults apply): ${missing[*]}"
  fi
}

check_model() {
  # The model isn't in the repo: the "models" service downloads it once into
  # a Docker volume (see docker/models/fetch-models.sh).
  local model_file
  model_file="$(env_get LLAMA_MODEL_FILE)"
  model_file="${model_file:-Qwen2.5-3B-Instruct-Q4_K_M.gguf}"
  if docker volume inspect "$MODELS_VOLUME" >/dev/null 2>&1; then
    ok "model volume $MODELS_VOLUME exists ($model_file is checked on start)"
  else
    info "LLM model $model_file will be downloaded into Docker volume $MODELS_VOLUME on first start (one time, ~2 GB)"
  fi
}

check_port() {
  # check_port <port> <compose-service-or-empty> <label>
  local port="$1" service="$2" label="$3" key="${4:-}"
  if [[ "$IS_WINDOWS" == 1 ]] && win_port_reserved "$port"; then
    fail "port $port ($label) is reserved by Windows (Hyper-V/WinNAT excluded port range)"
    [[ -n "$key" ]] && hint "Use another port: set $key=<port> in .env"
    hint "Or clear the reservation from an admin terminal: net stop winnat && net start winnat"
    return
  fi
  if ! port_in_use "$port"; then
    ok "port $port free ($label)"
    return
  fi
  if [[ -n "$service" ]] && compose_running "$service"; then
    ok "port $port served by running $service container"
    return
  fi
  local owner
  owner="$(port_owner "$port")"
  fail "port $port ($label) is already in use${owner:+ by '$owner'}"
  if [[ -n "$service" ]] && docker compose ps -a --services 2>/dev/null | grep -qx "$service"; then
    hint "If it's this project's stack in a bad state: scripts/start.sh stop"
  fi
  if [[ "$IS_WINDOWS" == 1 ]]; then
    hint "Stop that program${key:+, or set $key=<port> in .env}"
  else
    hint "Find the process: ss -ltnp 'sport = :$port'  (or: lsof -iTCP:$port -sTCP:LISTEN)"
  fi
}

docker_desktop_data_dir() {
  # Windows: folder holding Docker Desktop's virtual disk (images + volumes).
  local settings dir=""
  for settings in "$APPDATA/Docker/settings-store.json" "$APPDATA/Docker/settings.json"; do
    [[ -f "$settings" ]] || continue
    dir="$(grep -oE '"(CustomWslDistroDir|DataFolder)"[[:space:]]*:[[:space:]]*"[^"]+"' "$settings" | head -n1 | sed -E 's/.*:[[:space:]]*"(.*)"/\1/; s/\\\\/\\/g')"
    [[ -n "$dir" ]] && break
  done
  cygpath -u "${dir:-$LOCALAPPDATA\\Docker}"
}

check_resources() {
  local ram_kb=""
  if [[ "$IS_WINDOWS" == 1 ]]; then
    # Containers only get the Docker Desktop VM's memory, not all host RAM.
    ram_kb="$(( $(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0) / 1024 ))"
    if (( ram_kb > 0 && ram_kb / 1024 / 1024 < MIN_RAM_GB )); then
      warn "Docker can use only $(( ram_kb / 1024 / 1024 ))GB of memory; the 3B model plus Qiskit need about ${MIN_RAM_GB}GB"
      hint "WSL 2 backend: add memory=8GB under [wsl2] in %UserProfile%\\.wslconfig, then run: wsl --shutdown"
      ram_kb=""
    elif (( ram_kb > 0 )); then
      ok "Docker can use $(( ram_kb / 1024 / 1024 ))GB of memory"
      ram_kb=""
    fi
  elif [[ -r /proc/meminfo ]]; then
    ram_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  elif have sysctl; then
    ram_kb="$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 ))"
  fi
  if [[ -n "$ram_kb" && "$ram_kb" -gt 0 ]]; then
    local ram_gb=$(( ram_kb / 1024 / 1024 ))
    if (( ram_gb < MIN_RAM_GB )); then
      warn "only ${ram_gb}GB RAM; the 3B model plus Qiskit need about ${MIN_RAM_GB}GB"
    else
      ok "${ram_gb}GB RAM"
    fi
  fi

  local docker_root disk_kb
  if [[ "$IS_WINDOWS" == 1 ]]; then
    docker_root="$(docker_desktop_data_dir)"
  else
    docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
  fi
  disk_kb="$(df -Pk "${docker_root:-$ROOT_DIR}" 2>/dev/null | awk 'NR==2 {print $4}')"
  if [[ -z "$disk_kb" ]]; then
    disk_kb="$(df -Pk "$ROOT_DIR" | awk 'NR==2 {print $4}')"
  fi
  local disk_gb=$(( disk_kb / 1024 / 1024 ))
  if (( disk_gb < MIN_DISK_GB )); then
    warn "only ${disk_gb}GB free disk for Docker images (need about ${MIN_DISK_GB}GB)"
  else
    ok "${disk_gb}GB free disk"
  fi
}

check_data_dir() {
  mkdir -p data/events data/artifacts models/tts 2>/dev/null || true
  local probe="data/events/.write-test-$$"
  if touch "$probe" 2>/dev/null; then
    rm -f "$probe"
    ok "data/ is writable"
  else
    if [[ "$IS_WINDOWS" == 1 ]]; then
      fail "data/ is not writable"
      hint "Check the folder permissions (and Controlled Folder Access in Windows Security)"
    else
      fail "data/ is not writable by $(id -un) (probably created by an old root container)"
      hint "sudo chown -R $(id -u):$(id -g) data"
    fi
  fi
}

check_container_user() {
  # The orchestrator runs as APP_UID:APP_GID so files it writes to ./data stay
  # owned by you. Default to the current user unless .env pins other ids.
  local uid gid env_uid env_gid
  env_uid="$(env_get APP_UID)" env_gid="$(env_get APP_GID)"
  if [[ "$IS_WINDOWS" == 1 ]]; then
    # Docker Desktop doesn't map ownership of Windows folders, and Git Bash's
    # id -u (e.g. 197609) is not a Linux uid: keep the image defaults.
    export APP_UID="${env_uid:-1000}" APP_GID="${env_gid:-1000}"
    ok "container user $APP_UID:$APP_GID (ownership of data/ doesn't matter on Docker Desktop)"
    return
  fi
  uid="$(id -u)" gid="$(id -g)"
  export APP_UID="${env_uid:-$uid}" APP_GID="${env_gid:-$gid}"
  if [[ "$APP_UID" != "$uid" || "$APP_GID" != "$gid" ]]; then
    warn "APP_UID/APP_GID in .env ($APP_UID:$APP_GID) differ from your user ($uid:$gid)"
    hint "Files in data/ may end up unwritable; set APP_UID=$uid APP_GID=$gid in .env"
  else
    ok "container user matches host user ($uid:$gid)"
  fi
}

venv_python() {
  # The project venv's interpreter: bin/python on Linux, Scripts/python.exe on Windows.
  if [[ "$IS_WINDOWS" == 1 ]]; then
    printf '%s' "$ROOT_DIR/.venv/Scripts/python.exe"
  else
    printf '%s' "$ROOT_DIR/.venv/bin/python"
  fi
}

find_python() {
  # Prints a python that can run the host-side helpers. Uses "python -m" style
  # invocations only: venv console-script shebangs break when the drive's mount
  # path changes.
  local candidate
  # On Windows, python3 is usually the Microsoft Store stub, which fails the
  # version probe below and is skipped.
  for candidate in "$(venv_python)" python3 python; do
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

check_anchoring() {
  # Deploy tooling needs no host check: "up" deploys from the orchestrator
  # image (web3 + a pre-fetched solc) and "dev" from the .venv, whose
  # packages check_dev_python verifies.
  if ! is_true "$(env_get CONTRACT_ANCHOR_ENABLED)"; then
    info "blockchain anchoring disabled (CONTRACT_ANCHOR_ENABLED=false)"
    return
  fi

  if [[ -z "$(env_get ETH_FROM_ADDRESS)" || -z "$(env_get ETH_PRIVATE_KEY)" ]]; then
    if [[ "$AUTO_FIX" == 1 ]]; then
      env_set ETH_FROM_ADDRESS "$DEV_CHAIN_ADDRESS"
      env_set ETH_PRIVATE_KEY "$DEV_CHAIN_PRIVATE_KEY"
      ok "anchoring account set to the local dev-chain account in .env"
    else
      warn "ETH_FROM_ADDRESS/ETH_PRIVATE_KEY are empty (start will fill in the local dev-chain account)"
    fi
  else
    ok "anchoring account configured"
  fi
}

check_tts() {
  local mode="$1"
  if ! is_true "$(env_get TTS_ENABLED)"; then
    return
  fi
  if [[ "$mode" == up ]]; then
    ok "TTS enabled (the models service downloads the voice into the models volume)"
    return
  fi
  local voice
  voice="$(env_get TTS_VOICE_MODEL_PATH)"
  voice="${voice:-models/tts/en_US-libritts_r-medium.onnx}"
  if [[ -f "$voice" ]]; then
    ok "TTS voice model $(basename "$voice")"
  else
    warn "TTS_ENABLED=true but $voice is missing (TTS will be disabled)"
    hint "${VENV_PY_REL} scripts/download_tts_voice.py"
  fi
}

check_dev_python() {
  local py
  py="$(venv_python)"
  local imports='import fastapi, uvicorn, requests, httpx, psutil, web3, pydantic, qiskit, qiskit_aer, numpy, scipy, yaml, solcx'
  local setup_hint="uv venv --clear --python 3.11 .venv && uv pip install --python ${VENV_PY_REL} -r requirements.txt"
  # A venv made on the other OS (bin/ vs Scripts/) can't be used or repaired.
  local foreign=0
  if [[ -d .venv && ! -e "$py" ]] && [[ -d .venv/bin || -d .venv/Scripts ]]; then
    foreign=1
  fi
  if [[ "$foreign" == 0 && -x "$py" ]] && ! "$py" -c 'pass' >/dev/null 2>&1; then
    fail ".venv is broken (its interpreter no longer exists)"
    hint "rm -rf .venv && uv venv --python 3.11 .venv && uv pip install --python ${VENV_PY_REL} -r requirements.txt"
    return
  fi
  if [[ -x "$py" ]] && "$py" -c "$imports" >/dev/null 2>&1; then
    ok "python backend deps in .venv ($("$py" -c 'import platform; print(platform.python_version())' | tr -d '\r'))"
    DEV_PYTHON="$py"
    return
  fi
  if [[ "$AUTO_FIX" != 1 ]]; then
    if [[ "$foreign" == 1 ]]; then
      fail ".venv was created on another OS and does not work here"
    else
      fail "python backend dependencies are not installed in .venv"
    fi
    hint "$setup_hint"
    return
  fi
  if ! have uv; then
    fail "python backend dependencies are missing and uv is not installed to install them"
    if [[ "$IS_WINDOWS" == 1 ]]; then
      hint "powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"   (then open a new terminal)"
    else
      hint "curl -LsSf https://astral.sh/uv/install.sh | sh   (then re-run this script)"
    fi
    return
  fi
  if [[ "$foreign" == 1 ]]; then
    info ".venv was created on another OS; recreating it"
    uv venv --clear --python 3.11 .venv
  fi
  info "installing python backend dependencies into .venv (one-time) ..."
  [[ -x "$py" ]] || uv venv --python 3.11 .venv
  if uv pip install --python "$py" -r requirements.txt && "$py" -c "$imports" >/dev/null 2>&1; then
    ok "python backend deps installed"
    DEV_PYTHON="$py"
  else
    fail "installing python dependencies failed (see output above)"
  fi
}

frontend_deps_ok() {
  [[ -d "$FRONTEND_DIR/node_modules" ]] &&
    npm --prefix "$FRONTEND_DIR" ls --depth=0 >/dev/null 2>&1 &&
    (cd "$FRONTEND_DIR" && node -e "require('rollup');require('@swc/core');require('esbuild').transformSync('')" >/dev/null 2>&1)
}

check_dev_node() {
  if ! have node || ! have npm; then
    fail "node and npm are required for the frontend dev server"
    hint "Install Node.js 20 LTS: https://nodejs.org/"
    return
  fi
  local node_version
  node_version="$(node --version | sed 's/^v//')"
  if ! version_ge "$node_version" "18"; then
    fail "node $node_version is too old (need >= 18)"
    return
  fi
  ok "node $node_version"

  # npm ls exits non-zero when anything in package.json is missing or mismatched;
  # the require() probe catches native binaries (esbuild/rollup/swc) installed
  # on another OS, e.g. a node_modules copied over from Linux.
  if frontend_deps_ok; then
    ok "frontend node_modules up to date"
    return
  fi
  if [[ "$AUTO_FIX" != 1 ]]; then
    fail "frontend dependencies are missing, out of date, or built for another OS"
    hint "npm --prefix $FRONTEND_DIR ci"
    return
  fi
  info "installing frontend dependencies (npm ci) ..."
  if npm --prefix "$FRONTEND_DIR" ci --no-audit --no-fund && frontend_deps_ok; then
    ok "frontend dependencies installed"
  else
    fail "npm ci failed (see output above)"
  fi
}

run_checks() {
  local mode="$1"
  FAILURES=0
  WARNINGS=0

  step "Checking tools"
  check_docker
  check_curl
  (( FAILURES == 0 )) || return 0

  step "Checking configuration"
  check_env_file
  load_ports
  check_model
  check_data_dir
  check_anchoring
  check_tts "$mode"

  step "Checking host"
  check_resources
  if [[ "$mode" == up ]]; then
    check_container_user
    check_port "$API_PORT" orchestrator "orchestrator API + UI" API_PORT
  else
    if compose_running orchestrator; then
      if [[ "$AUTO_FIX" == 1 ]]; then
        docker compose stop orchestrator >/dev/null 2>&1
        ok "stopped the Docker orchestrator (dev mode runs the API locally)"
      else
        warn "Docker orchestrator is running on :$API_PORT (dev mode will stop it)"
      fi
    fi
    check_port "$API_PORT" "" "local API" API_PORT
    check_port "$VITE_PORT" "" "Vite dev server" VITE_PORT
  fi
  check_port "$LLM_PORT" llama "llama.cpp server" LLM_PORT
  check_port "$RPC_PORT" blockchain "blockchain RPC" RPC_PORT

  if [[ "$mode" == dev ]]; then
    step "Checking local dev toolchain"
    check_dev_python
    check_dev_node
  fi
}

finish_checks() {
  if (( FAILURES > 0 )); then
    die "$FAILURES check(s) failed. Fix the items marked ✘ above and re-run."
  fi
  if (( WARNINGS > 0 )); then
    printf '\n%sAll required checks passed (%d warning(s)).%s\n' "$C_GREEN" "$WARNINGS" "$C_RESET"
  else
    printf '\n%sAll checks passed.%s\n' "$C_GREEN" "$C_RESET"
  fi
}

# --------------------------------------------------------------- startup ---

compose_build() {
  # Retries only transient registry/DNS failures; anything else is a real error.
  local attempt=1 delay=3 log
  log="$(mktemp)"
  while (( attempt <= 4 )); do
    if docker compose build "$@" 2>&1 | tee "$log"; then
      rm -f "$log"
      return 0
    fi
    if grep -qiE 'registry-1\.docker\.io|server misbehaving|temporary failure in name resolution|no such host|lookup .*:53|TLS handshake timeout|i/o timeout' "$log"; then
      warn "registry/DNS lookup failed (attempt $attempt/4), retrying in ${delay}s"
      sleep "$delay"
      delay=$((delay * 2))
      attempt=$((attempt + 1))
      continue
    fi
    rm -f "$log"
    return 1
  done
  rm -f "$log"
  hint "Check the Docker daemon's DNS settings, then retry"
  return 1
}

fetch_models() {
  # The "models" service downloads the GGUF model (and the Piper voice when
  # TTS_ENABLED=true) into a Docker volume once; run in the foreground here
  # so the download progress is visible.
  step "Preparing models"
  local model_file flags=(--rm)
  model_file="$(env_get LLAMA_MODEL_FILE)"
  model_file="${model_file:-Qwen2.5-3B-Instruct-Q4_K_M.gguf}"
  info "$model_file lives in Docker volume $MODELS_VOLUME (downloaded once, resumable)"
  [[ "$BUILD" == 1 ]] && flags+=(--build)
  # docker.exe can't use Git Bash's terminal as a TTY.
  [[ "$IS_WINDOWS" == 1 || ! -t 1 ]] && flags+=(-T)
  docker compose run "${flags[@]}" models || die "model download failed; re-run to resume it (see output above)"
  ok "model ready: $model_file"
}

start_infra() {
  fetch_models
  step "Starting llama.cpp server and blockchain"
  info "first start loads the model into memory; this can take a minute"
  local build_flag=--build
  [[ "$BUILD" == 1 ]] || build_flag=--no-build
  if ! docker compose up -d "$build_flag" --wait --wait-timeout 600 llama blockchain; then
    show_failed_services llama blockchain
    die "llama/blockchain did not become healthy"
  fi
  ok "llama.cpp server  http://localhost:$LLM_PORT"
  ok "blockchain RPC    http://localhost:$RPC_PORT"
}

ensure_contract() {
  # ensure_contract <up|dev>
  # Sets CONTRACT_CHANGED=1 when a new contract address was written to .env.
  local mode="$1"
  CONTRACT_CHANGED=0
  is_true "$(env_get CONTRACT_ANCHOR_ENABLED)" || return 0

  step "Checking anchor contract"
  local address code
  address="$(env_get ANCHOR_CONTRACT_ADDRESS)"
  if [[ -n "$address" ]]; then
    code="$(rpc_call eth_getCode "[\"$address\",\"latest\"]" 2>/dev/null | grep -o '"result":"[^"]*"' | cut -d'"' -f4 || true)"
    if [[ -n "$code" && "$code" != "0x" ]]; then
      ok "contract deployed at $address"
      return 0
    fi
    warn "no contract code at $address (chain was reset); redeploying"
  fi

  local key output new_address status=0
  key="$(env_get ETH_PRIVATE_KEY)"
  if [[ "$mode" == up ]]; then
    # From the orchestrator image (web3 + a pre-fetched solc): no host Python needed.
    info "deploying RunCommitmentAnchor ..."
    output="$(docker compose run --rm --no-deps -T -e ETH_RPC_URL=http://blockchain:8545 \
      -e ETH_PRIVATE_KEY="${key:-$DEV_CHAIN_PRIVATE_KEY}" orchestrator python scripts/deploy_contract.py 2>&1)" || status=$?
  else
    [[ -n "${DEV_PYTHON:-}" ]] || die "cannot deploy the anchor contract: the .venv is not set up (see checks above)"
    info "deploying RunCommitmentAnchor (first run downloads solc 0.8.17) ..."
    output="$(ETH_RPC_URL="http://localhost:$RPC_PORT" ETH_PRIVATE_KEY="${key:-$DEV_CHAIN_PRIVATE_KEY}" \
      "$DEV_PYTHON" scripts/deploy_contract.py 2>&1)" || status=$?
  fi
  if (( status != 0 )); then
    printf '%s\n' "$output"
    die "anchor contract deployment failed"
  fi
  new_address="$(tr -d '\r' <<<"$output" | awk -F= '/^ANCHOR_CONTRACT_ADDRESS=/ {print $2}' | tail -n1)"
  [[ -n "$new_address" ]] || { printf '%s\n' "$output"; die "could not parse the deployed contract address"; }
  env_set ANCHOR_CONTRACT_ADDRESS "$new_address"
  CONTRACT_CHANGED=1
  ok "contract deployed at $new_address (saved to .env)"
}

print_status_summary() {
  local base="$1" status
  status="$(curl -fsS --max-time 5 "$base/api/status" 2>/dev/null || true)"
  [[ -n "$status" ]] || return 0
  local agents anchoring deployed tts
  agents="$(grep -o '"agents_loaded":[0-9]*' <<<"$status" | cut -d: -f2)"
  anchoring="$(grep -o '"contract_anchor_enabled":[a-z]*' <<<"$status" | cut -d: -f2)"
  deployed="$(grep -o '"contract_deployed":[a-z]*' <<<"$status" | cut -d: -f2)"
  tts="$(grep -o '"tts_enabled":[a-z]*' <<<"$status" | cut -d: -f2)"
  info "agents loaded: ${agents:-?}"
  if [[ "$anchoring" == true && "$deployed" == true ]]; then
    ok "blockchain anchoring active"
  elif is_true "$(env_get CONTRACT_ANCHOR_ENABLED)"; then
    warn "blockchain anchoring enabled but not active (see: scripts/start.sh logs orchestrator)"
  fi
  [[ "$tts" == true ]] && ok "text-to-speech enabled"
  return 0
}

json_eval() {
  # json_eval <python-expr>: evaluates the expression with the JSON from stdin as d.
  # Output is decoded as UTF-8 and stripped of Windows CRs.
  PYTHONIOENCODING=utf-8 "${JSON_PY[@]}" -c "import json,sys; d=json.load(sys.stdin); print($1)" | tr -d '\r'
}

smoke_test() {
  local base="$1"
  step "Smoke test: 1-round, 2-agent debate against the real LLM"
  # Any working host python reads the API's JSON; without one (Windows with
  # Docker only) the orchestrator container's python does it.
  local py
  if py="$(find_python)"; then
    JSON_PY=("$py")
  elif compose_running orchestrator; then
    JSON_PY=(docker compose exec -T orchestrator python)
  else
    warn "no python found to read the API responses; skipping smoke test"
    return 0
  fi

  local api_key auth=()
  api_key="$(env_get API_KEY)"
  [[ -n "$api_key" ]] && auth=(-H "X-API-Key: $api_key")

  local run_id
  run_id="$(curl -fsS --max-time 30 -X POST "$base/api/run_async" ${auth[@]+"${auth[@]}"} \
      -H 'Content-Type: application/json' \
      -d '{"query":"Is it better to learn Python or JavaScript as a first programming language? Give a recommendation.","max_rounds":1,"agent_count":2}' \
    | json_eval 'd["run_id"]')" \
    || die "could not start a smoke-test run"
  info "run $run_id started"

  local result="" status="" start=$SECONDS
  while (( SECONDS - start < 600 )); do
    result="$(curl -fsS --max-time 10 "$base/api/result/$run_id" 2>/dev/null || true)"
    status="$(printf '%s' "$result" | json_eval 'd.get("status","")' 2>/dev/null || true)"
    [[ "$status" == completed || "$status" == failed ]] && break
    sleep 5
  done

  if [[ "$status" != completed ]]; then
    fail "smoke run did not complete (status: ${status:-timeout})"
    [[ -n "$result" ]] && hint "$result"
    die "smoke test failed"
  fi

  local answer
  answer="$(json_eval 'd.get("final_answer") or ""' <<<"$result")"
  if [[ -z "${answer//[[:space:]]/}" ]]; then
    die "smoke run completed with an empty final answer"
  fi
  if [[ "$answer" == "[MOCK LLM]"* ]]; then
    die "smoke run used mock LLM responses (MOCK_LLM=true?)"
  fi
  ok "run completed in $((SECONDS - start))s with a real answer:"
  printf '%s\n' "$answer" | head -n 6 | sed 's/^/      /'

  local events
  events="$(curl -fsS --max-time 10 "$base/api/events/$run_id" | json_eval 'len(d)')"
  ok "$events provenance events recorded"

  if is_true "$(env_get CONTRACT_ANCHOR_ENABLED)"; then
    local verify
    verify="$(curl -fsS --max-time 30 "$base/api/verify/$run_id" 2>/dev/null || true)"
    if grep -qE '"verified": *true' <<<"$verify"; then
      ok "commitment verified on-chain"
    else
      warn "on-chain verification did not confirm: ${verify:-no response}"
    fi
  fi
}

cmd_up() {
  run_checks up
  finish_checks

  if [[ "$BUILD" == 1 ]]; then
    step "Building images"
    compose_build || die "docker compose build failed"
  fi

  start_infra
  ensure_contract up

  step "Starting orchestrator"
  local recreate=()
  [[ "$CONTRACT_CHANGED" == 1 ]] && recreate=(--force-recreate)
  if ! docker compose up -d --no-build --wait --wait-timeout 300 ${recreate[@]+"${recreate[@]}"} orchestrator; then
    show_failed_services orchestrator
    die "orchestrator did not become healthy"
  fi
  wait_http "UI" 60 "http://localhost:$API_PORT/" || die "UI is not being served"
  print_status_summary "http://localhost:$API_PORT"

  [[ "$SMOKE" == 1 ]] && smoke_test "http://localhost:$API_PORT"

  printf '\n%sQ-CONSENSUS is running at http://localhost:%s%s\n' "$C_GREEN$C_BOLD" "$API_PORT" "$C_RESET"
  printf '  logs:  scripts/start.sh logs orchestrator\n  stop:  scripts/start.sh stop\n'
  open_browser "http://localhost:$API_PORT"
}

cmd_dev() {
  run_checks dev
  finish_checks

  start_infra
  ensure_contract dev

  step "Starting local API and frontend (Ctrl+C stops both; containers keep running)"
  export_dotenv
  export LLM_BASE_URL="http://localhost:$LLM_PORT"
  export ETH_RPC_URL="http://localhost:$RPC_PORT"
  export PYTHONPATH="$ROOT_DIR"
  unset FRONTEND_DIST_DIR
  if [[ "$IS_WINDOWS" == 1 ]]; then
    # Native Windows python needs a Windows path, unbuffered output for the
    # [api] stream, and UTF-8 regardless of the console code page.
    PYTHONPATH="$(cygpath -w "$ROOT_DIR")"
    export PYTHONUNBUFFERED=1 PYTHONUTF8=1
    export VITE_API_PROXY_TARGET="http://127.0.0.1:$API_PORT"
  fi

  local pids=()
  trap 'trap - INT TERM EXIT; printf "\nStopping local API and frontend...\n"; for p in "${pids[@]}"; do kill_tree "$p"; done' INT TERM EXIT

  ( "$DEV_PYTHON" -m uvicorn src.qconsensus.web:app --host 127.0.0.1 --port "$API_PORT" \
      --reload --reload-dir src --reload-dir config 2>&1 | sed -u "s/\r\$//; s/^/${C_BLUE}[api]${C_RESET} /" ) &
  pids+=("$!")
  ( npm --prefix "$FRONTEND_DIR" run dev -- --port "$VITE_PORT" 2>&1 | sed -u "s/\r\$//; s/^/${C_YELLOW}[web]${C_RESET} /" ) &
  pids+=("$!")

  wait_http "local API" 180 "http://localhost:$API_PORT/api/status" || die "local API failed to start (see [api] output)"
  wait_http "Vite dev server" 60 "http://localhost:$VITE_PORT/" || die "Vite failed to start (see [web] output)"
  print_status_summary "http://localhost:$API_PORT"

  [[ "$SMOKE" == 1 ]] && smoke_test "http://localhost:$API_PORT"

  printf '\n%sDev mode ready: http://localhost:%s (API on :%s, hot reload on)%s\n' \
    "$C_GREEN$C_BOLD" "$VITE_PORT" "$API_PORT" "$C_RESET"
  open_browser "http://localhost:$VITE_PORT"
  # Returns as soon as either process exits; the EXIT trap then stops the other.
  wait -n 2>/dev/null || true
}

cmd_check() {
  local mode=up
  [[ "$CHECK_DEV" == 1 ]] && mode=dev
  run_checks "$mode"
  finish_checks
}

cmd_status() {
  have docker && docker info >/dev/null 2>&1 || die "docker daemon is not reachable"
  load_ports
  step "Containers"
  docker compose ps -a
  step "Endpoints"
  local name url
  for entry in "UI + API|http://localhost:$API_PORT/api/status" "llama.cpp|http://localhost:$LLM_PORT/health" "Vite dev|http://localhost:$VITE_PORT/"; do
    name="${entry%%|*}" url="${entry#*|}"
    if curl -fsS -o /dev/null --max-time 3 "$url" 2>/dev/null; then ok "$name  $url"; else info "$name  not responding"; fi
  done
  if rpc_call web3_clientVersion '[]' >/dev/null 2>&1; then ok "blockchain  http://localhost:$RPC_PORT"; else info "blockchain  not responding"; fi
  print_status_summary "http://localhost:$API_PORT"
}

# ------------------------------------------------------------------ main ---

COMMAND="up"
SMOKE=0
BUILD=1
OPEN_BROWSER=1
CHECK_DEV=0
AUTO_FIX=1
DEV_PYTHON=""
JSON_PY=()
CONTRACT_CHANGED=0
LOG_ARGS=()

if [[ $# -gt 0 && "$1" != -* ]]; then
  COMMAND="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=1 ;;
    --no-build) BUILD=0 ;;
    --no-open) OPEN_BROWSER=0 ;;
    --dev) CHECK_DEV=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage; die "unknown option: $1" ;;
    *)
      if [[ "$COMMAND" == logs ]]; then LOG_ARGS+=("$1"); else usage; die "unexpected argument: $1"; fi
      ;;
  esac
  shift
done

case "$COMMAND" in
  up) cmd_up ;;
  dev) cmd_dev ;;
  check) AUTO_FIX=0; cmd_check ;;
  status) cmd_status ;;
  logs) docker compose logs -f --tail 100 ${LOG_ARGS[@]+"${LOG_ARGS[@]}"} ;;
  stop) docker compose down ;;
  help) usage ;;
  *) usage; die "unknown command: $COMMAND" ;;
esac
