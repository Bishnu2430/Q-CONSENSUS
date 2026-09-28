#Requires -Version 5.1
# Q-CONSENSUS launcher for Windows: checks every dependency, then starts the
# project. Run it through scripts\start.cmd (works regardless of the
# PowerShell execution policy) or directly as .\scripts\start.ps1.
#
# Written for Windows PowerShell 5.1 (ships with Windows) and PowerShell 7.
# Keep this file ASCII-only: 5.1 reads BOM-less scripts as ANSI.

# Native tools write progress to stderr; with 'Stop', Windows PowerShell 5.1
# turns redirected stderr lines into terminating errors. Failures are
# detected through exit codes instead.
$ErrorActionPreference = 'Continue'
# Invoke-WebRequest's progress bar makes every request crawl in 5.1.
$ProgressPreference = 'SilentlyContinue'

$RootDir = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $RootDir 'consensus-command-main'
$EnvFile = Join-Path $RootDir '.env'
$ModelsVolume = 'qconsensus_models'
$MinDockerRamGB = 6
$MinDiskGB = 8
# .env keys that docker-compose.yml now sets itself (so a value in .env is
# ignored), and keys that nothing reads at all.
$ComposeWiredKeys = @('LLM_BASE_URL', 'ETH_RPC_URL', 'ETH_CHAIN_ID', 'ETH_FROM_ADDRESS', 'ETH_PRIVATE_KEY', 'ANCHOR_CONTRACT_ADDRESS')
$UnusedKeys = @('POSTGRES_URL', 'ETH_ANCHOR_ENABLED', 'ANCHOR_CONTRACT_OWNER', 'ARTIFACT_STORE_DIR', 'APP_UID', 'APP_GID')
$UseColor = -not $env:NO_COLOR

$script:Failures = 0
$script:Warnings = 0
$script:AutoFix = $true
$script:Build = $true
$script:Smoke = $false
$script:OpenBrowser = $true
$script:CheckDev = $false
$script:DevPython = ''
$script:ContractChanged = $false
$script:ContractAddress = ''
$script:StackConfig = $null
$script:StackConfigError = ''
$script:RunningServices = @()
$script:ExcludedRanges = $null
$script:DevProcs = @()
$ApiPort = 8000
$LlmPort = 8080
$RpcPort = 8545
$VitePort = 5173


# ---------------------------------------------------------------- output ---

function Write-Colored([string]$Text, [ConsoleColor]$Color, [switch]$NoNewline) {
  if ($UseColor) { Write-Host $Text -ForegroundColor $Color -NoNewline:$NoNewline }
  else { Write-Host $Text -NoNewline:$NoNewline }
}

function Write-Step([string]$Text) { Write-Host ''; Write-Colored "==> $Text" Cyan }
function Write-Ok([string]$Text) { Write-Colored '  [ OK ] ' Green -NoNewline; Write-Host $Text }
function Write-Info([string]$Text) { Write-Colored '  [INFO] ' DarkCyan -NoNewline; Write-Host $Text }
function Write-Warn([string]$Text) { Write-Colored '  [WARN] ' Yellow -NoNewline; Write-Host $Text; $script:Warnings++ }
function Write-Fail([string]$Text) { Write-Colored '  [FAIL] ' Red -NoNewline; Write-Host $Text; $script:Failures++ }
function Write-Hint([string]$Text) { Write-Colored "         -> $Text" Yellow }

function Stop-WithError([string]$Text) {
  Write-Host ''
  Write-Colored "[FAIL] $Text" Red
  exit 1
}

function Show-Usage {
  Write-Host @'
Q-CONSENSUS launcher: checks every dependency, then starts the project.

Usage: scripts\start.cmd [command] [options]
   or: .\scripts\start.ps1 [command] [options]

Commands:
  up        (default) build and start the full Docker stack at http://localhost:8000
  dev       llama + blockchain in Docker; API and frontend run locally with hot reload
  check     run the dependency checks only (for "up"; add --dev for dev mode)
  status    show container state and endpoint health
  logs      follow container logs (optionally: logs <service>)
  stop      stop the Docker stack (the model and chain volumes are kept)

Options:
  --smoke      after startup, run a short real debate and verify it produced an answer
  --no-build   start with the existing images (skip docker compose build)
  --no-open    don't open the browser
  --dev        with "check": check dev-mode dependencies instead of Docker-mode ones
  -h, --help   show this help
'@
}


# --------------------------------------------------------------- settings ---
# docker-compose.yml (with the optional .env merged in) is the single source
# of truth: settings are read from "docker compose config", and this script
# never writes .env.

function Get-StackConfig {
  if ($null -eq $script:StackConfig) {
    $result = Invoke-Captured docker @('compose', 'config', '--format', 'json')
    if ($result.Code -ne 0) {
      $script:StackConfigError = $result.Output
      return $null
    }
    $script:StackConfig = $result.Output | ConvertFrom-Json
  }
  return $script:StackConfig
}

function Get-ServiceEnv([string]$Service) {
  # The environment Compose gives a service: its .env entries overlaid with
  # the values docker-compose.yml sets.
  $map = @{}
  $config = Get-StackConfig
  if ($config) {
    $environment = $config.services.$Service.environment
    if ($environment) {
      foreach ($property in $environment.PSObject.Properties) { $map[$property.Name] = [string]$property.Value }
    }
  }
  return $map
}

function Get-Setting([string]$Service, [string]$Key, [string]$Default = '') {
  $value = (Get-ServiceEnv $Service)[$Key]
  if ($value) { return $value }
  return $Default
}

function Get-DotEnvKeys {
  $keys = @()
  if (Test-Path -LiteralPath $EnvFile) {
    foreach ($line in [IO.File]::ReadAllLines($EnvFile)) {
      if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $keys += [pscustomobject]@{ Key = $Matches[1]; Value = $Matches[2].Trim() }
      }
    }
  }
  return $keys
}

function Test-True([string]$Value) {
  return @('1', 'true', 'yes', 'on') -contains "$Value".Trim().ToLowerInvariant()
}

function Get-PublishedPort([string]$Service, [int]$Default) {
  $config = Get-StackConfig
  $number = 0
  if ($config -and $config.services.$Service.ports -and
      [int]::TryParse([string]@($config.services.$Service.ports)[0].published, [ref]$number)) {
    return $number
  }
  return $Default
}

function Update-Ports {
  $script:ApiPort = Get-PublishedPort 'orchestrator' 8000
  $script:LlmPort = Get-PublishedPort 'llama' 8080
  $script:RpcPort = Get-PublishedPort 'blockchain' 8545
  # Vite runs outside Docker, so its port comes straight from .env.
  $script:VitePort = 5173
  $number = 0
  $vite = @(Get-DotEnvKeys | Where-Object { $_.Key -eq 'VITE_PORT' }) | Select-Object -Last 1
  if ($vite -and [int]::TryParse($vite.Value, [ref]$number) -and $number -gt 0 -and $number -lt 65536) {
    $script:VitePort = $number
  }
}


# -------------------------------------------------------------- utilities ---

function Test-Command([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Captured([string]$FilePath, [string[]]$ArgumentList = @()) {
  # Runs a native command and returns its exit code and combined output.
  $output = & $FilePath @ArgumentList 2>&1 | ForEach-Object { "$_" }
  return [pscustomobject]@{ Code = $LASTEXITCODE; Output = (@($output) -join "`n") }
}

function Invoke-Json {
  # JSON over HTTP, decoded as UTF-8 (5.1's Invoke-RestMethod assumes
  # ISO-8859-1 when the server sends no charset).
  param([string]$Uri, [string]$Method = 'Get', [string]$Body = '', [hashtable]$Headers = @{}, [int]$TimeoutSec = 10)
  $params = @{ Uri = $Uri; Method = $Method; Headers = $Headers; TimeoutSec = $TimeoutSec; UseBasicParsing = $true; ErrorAction = 'Stop' }
  if ($Body) {
    $params.ContentType = 'application/json'
    $params.Body = [Text.Encoding]::UTF8.GetBytes($Body)
  }
  $response = Invoke-WebRequest @params
  return ([Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray()) | ConvertFrom-Json)
}

function Test-Http([string]$Url, [int]$TimeoutSec = 5) {
  try {
    $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Invoke-Rpc([string]$Method, [object[]]$Params = @()) {
  # Raw JSON-RPC call against the local chain.
  $body = @{ jsonrpc = '2.0'; method = $Method; params = $Params; id = 1 } | ConvertTo-Json -Compress
  return Invoke-Json -Uri "http://127.0.0.1:$RpcPort" -Method Post -Body $body -TimeoutSec 5
}

function Get-RunningServices {
  $result = Invoke-Captured docker @('compose', 'ps', '--status', 'running', '--services')
  if ($result.Code -ne 0) { return @() }
  return @($result.Output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-ComposeService([string]$Service) {
  $result = Invoke-Captured docker @('compose', 'ps', '-a', '--services')
  return ($result.Code -eq 0) -and (@($result.Output -split "`n" | ForEach-Object { $_.Trim() }) -contains $Service)
}

function Open-Browser([string]$Url) {
  if ($script:OpenBrowser) { Start-Process $Url }
}

function Wait-Http([string]$Label, [int]$TimeoutSec, [string]$Url) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  # Dev-mode server output is streamed while waiting, so skip the dots there.
  $dots = $script:DevProcs.Count -eq 0
  if ($dots) { Write-Colored '  [....] ' DarkCyan -NoNewline; Write-Host "waiting for $Label " -NoNewline }
  else { Write-Info "waiting for $Label ..." }
  while (-not (Test-Http $Url)) {
    Update-DevLogs
    $exited = @($script:DevProcs | Where-Object { $_.Process.HasExited })
    if ($sw.Elapsed.TotalSeconds -ge $TimeoutSec -or $exited.Count -gt 0) {
      if ($dots) { Write-Colored "timed out after ${TimeoutSec}s" Red }
      return $false
    }
    if ($dots) { Write-Host '.' -NoNewline }
    Start-Sleep -Seconds 2
  }
  $elapsed = [int]$sw.Elapsed.TotalSeconds
  if ($dots) { Write-Colored "ready (${elapsed}s)" Green }
  else { Write-Ok "$Label ready (${elapsed}s)" }
  return $true
}

function Show-FailedServices([string[]]$Services) {
  & docker compose ps -a
  foreach ($service in $Services) {
    Write-Host ''
    Write-Host "--- last 30 log lines: $service ---"
    & docker compose logs --no-color --tail 30 $service
  }
}


# ------------------------------------------------------------------ ports ---

function Get-ExcludedPortRanges {
  # Hyper-V/WinNAT reserve blocks of ports (often shifting after a reboot);
  # Docker can't publish anything inside them.
  if ($null -eq $script:ExcludedRanges) {
    $ranges = @()
    $result = Invoke-Captured netsh @('interface', 'ipv4', 'show', 'excludedportrange', 'protocol=tcp')
    if ($result.Code -eq 0) {
      foreach ($line in $result.Output -split "`n") {
        if ($line -match '^\s*(\d+)\s+(\d+)') {
          $ranges += [pscustomobject]@{ Start = [int]$Matches[1]; End = [int]$Matches[2] }
        }
      }
    }
    $script:ExcludedRanges = $ranges
  }
  return $script:ExcludedRanges
}

function Test-PortReserved([int]$Port) {
  foreach ($range in @(Get-ExcludedPortRanges)) {
    if ($Port -ge $range.Start -and $Port -le $range.End) { return $true }
  }
  return $false
}

function Get-PortOwner([int]$Port) {
  try {
    $conn = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop)[0]
  } catch {
    return $null
  }
  $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
  if ($proc) { return "$($proc.ProcessName) (PID $($conn.OwningProcess))" }
  return "PID $($conn.OwningProcess)"
}

function Test-PortBindable([int]$Port) {
  $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
  try {
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    $listener.Stop()
  }
}

function Test-Port([int]$Port, [string]$Service, [string]$Label, [string]$EnvKey) {
  if ($Service -and ($script:RunningServices -contains $Service)) {
    Write-Ok "port $Port served by running $Service container"
    return
  }
  if (Test-PortReserved $Port) {
    Write-Fail "port $Port ($Label) is reserved by Windows (Hyper-V/WinNAT excluded port range)"
    Write-Hint "Use another port: set $EnvKey=<port> in .env"
    Write-Hint 'Or clear the reservation from an admin terminal: net stop winnat; net start winnat'
    return
  }
  $owner = Get-PortOwner $Port
  if (-not $owner -and (Test-PortBindable $Port)) {
    Write-Ok "port $Port free ($Label)"
    return
  }
  $by = ''
  if ($owner) { $by = " by $owner" }
  Write-Fail "port $Port ($Label) is already in use$by"
  if ($Service -and (Test-ComposeService $Service)) {
    Write-Hint "If it's this project's stack in a bad state: scripts\start.cmd stop"
  }
  Write-Hint "Stop that program, or set $EnvKey=<port> in .env"
}


# ---------------------------------------------------------------- checks ---

function Start-DockerDesktop {
  $exe = @(
    (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\Docker Desktop.exe')
  ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $exe) { return $false }
  Write-Info 'Docker Desktop is not running; starting it (this can take a minute)'
  Start-Process -FilePath $exe | Out-Null
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt 180) {
    Start-Sleep -Seconds 3
    if ((Invoke-Captured docker @('info', '--format', '{{.OSType}}')).Code -eq 0) { return $true }
  }
  return $false
}

function Test-Docker {
  if (-not (Test-Command docker)) {
    Write-Fail 'docker is not installed'
    Write-Hint 'Install Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/'
    return
  }
  $info = Invoke-Captured docker @('info', '--format', '{{.OSType}}')
  if ($info.Code -ne 0 -and $script:AutoFix -and (Start-DockerDesktop)) {
    $info = Invoke-Captured docker @('info', '--format', '{{.OSType}}')
  }
  if ($info.Code -ne 0) {
    Write-Fail 'Docker Desktop is not running'
    Write-Hint 'Start Docker Desktop from the Start menu, wait for "Engine running", then re-run'
    return
  }
  if ($info.Output.Trim() -ne 'linux') {
    Write-Fail 'Docker is in Windows-containers mode; this project needs Linux containers'
    Write-Hint 'Right-click the Docker tray icon -> "Switch to Linux containers..."'
    return
  }
  Write-Ok "docker $((Invoke-Captured docker @('version', '--format', '{{.Server.Version}}')).Output.Trim())"

  $compose = Invoke-Captured docker @('compose', 'version', '--short')
  if ($compose.Code -ne 0) {
    Write-Fail 'docker compose is missing'
    Write-Hint 'Update Docker Desktop (it bundles Compose v2)'
    return
  }
  $composeVersion = $compose.Output.Trim()
  if ($composeVersion -match '^v?(\d+)\.(\d+)' -and ([int]$Matches[1] -gt 2 -or ([int]$Matches[1] -eq 2 -and [int]$Matches[2] -ge 20))) {
    Write-Ok "docker compose $composeVersion"
  } else {
    Write-Fail "docker compose $composeVersion is too old (need >= 2.20 for --wait)"
    Write-Hint 'Update Docker Desktop'
  }
}

function Test-Settings {
  if (-not (Get-StackConfig)) {
    Write-Fail 'docker compose cannot read the configuration'
    Write-Hint $script:StackConfigError
    return
  }
  if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Ok 'no .env; using the defaults (copy .env.example to .env to change settings)'
    return
  }
  Write-Ok '.env present (optional settings)'
  $keys = @(Get-DotEnvKeys | ForEach-Object { $_.Key })
  $wired = @($keys | Where-Object { $ComposeWiredKeys -contains $_ } | Select-Object -Unique)
  $unused = @($keys | Where-Object { $UnusedKeys -contains $_ } | Select-Object -Unique)
  if ($wired.Count -gt 0) {
    Write-Info ".env sets $($wired -join ', '); docker-compose.yml sets these itself, so they're ignored (safe to delete)"
  }
  if ($unused.Count -gt 0) {
    Write-Info ".env sets $($unused -join ', '), which nothing uses (safe to delete)"
  }
}

function Test-Model {
  $file = Get-Setting 'models' 'LLAMA_MODEL_FILE'
  if ((Invoke-Captured docker @('volume', 'inspect', $ModelsVolume)).Code -eq 0) {
    Write-Ok "model volume $ModelsVolume exists ($file is checked on start)"
  } else {
    Write-Info "LLM model $file will be downloaded into Docker volume $ModelsVolume on first start (one time, ~2 GB)"
  }
}

function Test-DataDir {
  New-Item -ItemType Directory -Force -Path (Join-Path $RootDir 'data\events') | Out-Null
  $probe = Join-Path $RootDir "data\events\.write-test-$PID"
  try {
    [IO.File]::WriteAllText($probe, 'ok')
    Remove-Item -LiteralPath $probe -Force
    Write-Ok 'data\ is writable'
  } catch {
    Write-Fail "data\ is not writable: $($_.Exception.Message)"
    Write-Hint 'Check the folder permissions (and Controlled Folder Access in Windows Security)'
  }
}

function Test-Anchoring {
  if (Test-True (Get-Setting 'orchestrator' 'CONTRACT_ANCHOR_ENABLED')) {
    Write-Ok 'blockchain anchoring enabled (the contract service deploys the contract)'
  } else {
    Write-Info 'blockchain anchoring disabled (CONTRACT_ANCHOR_ENABLED=false)'
  }
}

function Test-Tts([string]$Mode) {
  if (-not (Test-True (Get-Setting 'orchestrator' 'TTS_ENABLED'))) { return }
  if ($Mode -eq 'up') {
    Write-Ok 'TTS enabled (the voice is downloaded into the models volume on start)'
    return
  }
  $voice = Get-Setting 'orchestrator' 'TTS_VOICE_MODEL_PATH' 'models/tts/en_US-libritts_r-medium.onnx'
  $voicePath = $voice
  if (-not [IO.Path]::IsPathRooted($voice)) { $voicePath = Join-Path $RootDir $voice }
  if (Test-Path -LiteralPath $voicePath) {
    Write-Ok "TTS voice model $(Split-Path -Leaf $voicePath)"
  } else {
    Write-Warn "TTS_ENABLED=true but $voice is missing (TTS will be disabled)"
    Write-Hint '.venv\Scripts\python scripts\download_tts_voice.py'
  }
}

function Get-DockerDataDir {
  # Docker Desktop keeps images and volumes in a virtual disk under this folder.
  foreach ($name in 'settings-store.json', 'settings.json') {
    $path = Join-Path $env:APPDATA "Docker\$name"
    if (-not (Test-Path -LiteralPath $path)) { continue }
    try { $settings = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { continue }
    foreach ($property in 'CustomWslDistroDir', 'DataFolder') {
      $value = $settings.$property
      if ($value) { return [string]$value }
    }
  }
  return (Join-Path $env:LOCALAPPDATA 'Docker')
}

function Test-DockerResources {
  $mem = Invoke-Captured docker @('info', '--format', '{{.MemTotal}}')
  $bytes = 0L
  if ($mem.Code -eq 0 -and [long]::TryParse($mem.Output.Trim(), [ref]$bytes) -and $bytes -gt 0) {
    $gb = [math]::Round($bytes / 1GB, 1)
    if ($gb -lt $MinDockerRamGB) {
      Write-Warn "Docker can use only ${gb}GB of memory; the 3B model plus Qiskit need about ${MinDockerRamGB}GB"
      Write-Hint 'WSL 2 backend: add memory=8GB under [wsl2] in %UserProfile%\.wslconfig, then run: wsl --shutdown'
      Write-Hint 'Hyper-V backend: Docker Desktop > Settings > Resources > Memory'
    } else {
      Write-Ok "Docker can use ${gb}GB of memory"
    }
  }

  try {
    $root = [IO.Path]::GetPathRoot((Get-DockerDataDir))
    $freeGB = [math]::Floor((New-Object IO.DriveInfo($root)).AvailableFreeSpace / 1GB)
    if ($freeGB -lt $MinDiskGB) {
      Write-Warn "only ${freeGB}GB free on $root (Docker Desktop's disk); images plus the model need about ${MinDiskGB}GB"
    } else {
      Write-Ok "${freeGB}GB free on $root for Docker images and the model"
    }
  } catch {
    Write-Info "could not determine free disk space: $($_.Exception.Message)"
  }
}

function Test-DevPython {
  $venv = Join-Path $RootDir '.venv'
  $py = Join-Path $venv 'Scripts\python.exe'
  $imports = 'import fastapi, uvicorn, requests, httpx, psutil, web3, pydantic, qiskit, qiskit_aer, numpy, scipy, yaml'
  $venvHint = 'uv venv --clear --python 3.11 .venv; uv pip install --python .venv\Scripts\python.exe -r requirements.txt'

  if ((Test-Path -LiteralPath $py) -and (Invoke-Captured $py @('-c', $imports)).Code -eq 0) {
    $version = (Invoke-Captured $py @('-c', 'import platform; print(platform.python_version())')).Output.Trim()
    Write-Ok "python backend deps in .venv ($version)"
    $script:DevPython = $py
    return
  }
  # A venv created on Linux (bin\ instead of Scripts\) or pointing at a
  # removed interpreter can't be repaired in place.
  $foreign = (Test-Path -LiteralPath (Join-Path $venv 'bin')) -and -not (Test-Path -LiteralPath $py)
  $broken = (Test-Path -LiteralPath $py) -and (Invoke-Captured $py @('-c', 'pass')).Code -ne 0
  if (-not $script:AutoFix) {
    if ($foreign) { Write-Fail '.venv was created on another OS (Linux) and does not work on Windows' }
    elseif ($broken) { Write-Fail '.venv is broken (its interpreter no longer exists)' }
    else { Write-Fail 'python backend dependencies are not installed in .venv' }
    Write-Hint $venvHint
    return
  }
  if (-not (Test-Command uv)) {
    Write-Fail 'python backend dependencies are missing and uv is not installed to install them'
    Write-Hint 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   (then open a new terminal)'
    return
  }
  if ($foreign -or $broken -or -not (Test-Path -LiteralPath $py)) {
    if ($foreign) { Write-Info '.venv was created on Linux; recreating it for Windows' }
    elseif ($broken) { Write-Info '.venv is broken; recreating it' }
    & uv venv --clear --python 3.11 $venv
    if ($LASTEXITCODE -ne 0) { Write-Fail 'creating .venv failed (see output above)'; return }
  }
  Write-Info 'installing python backend dependencies into .venv (one-time) ...'
  & uv pip install --python $py -r (Join-Path $RootDir 'requirements.txt')
  if ($LASTEXITCODE -eq 0 -and (Invoke-Captured $py @('-c', $imports)).Code -eq 0) {
    Write-Ok 'python backend deps installed'
    $script:DevPython = $py
  } else {
    Write-Fail 'installing python dependencies failed (see output above)'
  }
}

function Test-FrontendDeps {
  # npm ls catches missing/mismatched packages; the require() probe catches
  # native binaries built for another OS (a node_modules copied from Linux
  # has esbuild/rollup/swc binaries that can't load on Windows).
  if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'node_modules'))) { return $false }
  Push-Location -LiteralPath $FrontendDir
  try {
    if ((Invoke-Captured npm @('ls', '--depth=0')).Code -ne 0) { return $false }
    $probe = "require('rollup');require('@swc/core');require('esbuild').transformSync('')"
    return (Invoke-Captured node @('-e', $probe)).Code -eq 0
  } finally {
    Pop-Location
  }
}

function Test-DevNode {
  if (-not (Test-Command node) -or -not (Test-Command npm)) {
    Write-Fail 'node and npm are required for the frontend dev server'
    Write-Hint 'Install Node.js 20 LTS: https://nodejs.org/  (or: winget install OpenJS.NodeJS.LTS)'
    return
  }
  $nodeVersion = (Invoke-Captured node @('--version')).Output.Trim().TrimStart('v')
  if (-not ($nodeVersion -match '^(\d+)\.') -or [int]$Matches[1] -lt 18) {
    Write-Fail "node $nodeVersion is too old (need >= 18)"
    return
  }
  Write-Ok "node $nodeVersion"

  if (Test-FrontendDeps) {
    Write-Ok 'frontend node_modules up to date'
    return
  }
  if (-not $script:AutoFix) {
    Write-Fail 'frontend dependencies are missing, out of date, or built for another OS'
    Write-Hint "npm --prefix consensus-command-main ci"
    return
  }
  Write-Info 'installing frontend dependencies (npm ci) ...'
  & npm --prefix $FrontendDir ci --no-audit --no-fund
  if ($LASTEXITCODE -eq 0 -and (Test-FrontendDeps)) {
    Write-Ok 'frontend dependencies installed'
  } else {
    Write-Fail 'npm ci failed (see output above)'
  }
}

function Invoke-Checks([string]$Mode) {
  $script:Failures = 0
  $script:Warnings = 0

  Write-Step 'Checking tools'
  Test-Docker
  if ($script:Failures -gt 0) { return }

  Write-Step 'Checking configuration'
  Test-Settings
  if ($script:Failures -gt 0) { return }
  Update-Ports
  Test-Model
  Test-DataDir
  Test-Anchoring
  Test-Tts $Mode

  Write-Step 'Checking host'
  Test-DockerResources
  $script:RunningServices = Get-RunningServices
  if ($Mode -eq 'up') {
    Test-Port $ApiPort 'orchestrator' 'orchestrator API + UI' 'API_PORT'
  } else {
    $apiBusy = $false
    if ($script:RunningServices -contains 'orchestrator') {
      if ($script:AutoFix) {
        $null = Invoke-Captured docker @('compose', 'stop', 'orchestrator')
        Write-Ok 'stopped the Docker orchestrator (dev mode runs the API locally)'
      } else {
        Write-Warn "Docker orchestrator is running on :$ApiPort (dev mode will stop it)"
        $apiBusy = $true
      }
    }
    if (-not $apiBusy) { Test-Port $ApiPort '' 'local API' 'API_PORT' }
    Test-Port $VitePort '' 'Vite dev server' 'VITE_PORT'
  }
  Test-Port $LlmPort 'llama' 'llama.cpp server' 'LLM_PORT'
  Test-Port $RpcPort 'blockchain' 'blockchain RPC' 'RPC_PORT'

  if ($Mode -eq 'dev') {
    Write-Step 'Checking local dev toolchain'
    Test-DevPython
    Test-DevNode
  }
}

function Complete-Checks {
  if ($script:Failures -gt 0) {
    Stop-WithError "$($script:Failures) check(s) failed. Fix the items marked [FAIL] above and re-run."
  }
  Write-Host ''
  if ($script:Warnings -gt 0) { Write-Colored "All required checks passed ($($script:Warnings) warning(s))." Green }
  else { Write-Colored 'All checks passed.' Green }
}


# --------------------------------------------------------------- startup ---

function Invoke-ComposeBuild([string[]]$Services = @()) {
  # Retries only transient registry/DNS failures; anything else is a real error.
  $delay = 3
  for ($attempt = 1; $attempt -le 4; $attempt++) {
    $lines = New-Object System.Collections.Generic.List[string]
    & docker compose build @Services 2>&1 | ForEach-Object { $line = "$_"; Write-Host $line; $lines.Add($line) }
    if ($LASTEXITCODE -eq 0) { return $true }
    if (($lines -join "`n") -notmatch 'registry-1\.docker\.io|server misbehaving|no such host|temporary failure in name resolution|lookup .*:53|TLS handshake timeout|i/o timeout') {
      return $false
    }
    Write-Warn "registry/DNS lookup failed (attempt $attempt/4), retrying in ${delay}s"
    Start-Sleep -Seconds $delay
    $delay *= 2
  }
  Write-Hint "Check Docker Desktop's network/proxy settings, then retry"
  return $false
}

function Invoke-ModelFetch {
  Write-Step 'Preparing models'
  $file = Get-Setting 'models' 'LLAMA_MODEL_FILE'
  Write-Info "$file lives in Docker volume $ModelsVolume (downloaded once, resumable)"
  $tty = @()
  if ([Console]::IsOutputRedirected) { $tty = @('-T') }
  & docker compose run --rm @tty models
  if ($LASTEXITCODE -ne 0) {
    Stop-WithError 'model download failed; re-run to resume it (see output above)'
  }
  Write-Ok "model ready: $file"
}

function Start-Infra {
  Invoke-ModelFetch
  Write-Step 'Starting llama.cpp server and blockchain'
  Write-Info 'first start loads the model into memory; this can take a minute'
  & docker compose up -d --no-build --wait --wait-timeout 600 llama blockchain
  if ($LASTEXITCODE -ne 0) {
    Show-FailedServices @('llama', 'blockchain')
    Stop-WithError 'llama/blockchain did not become healthy'
  }
  Write-Ok "llama.cpp server  http://localhost:$LlmPort"
  Write-Ok "blockchain RPC    http://localhost:$RpcPort"
}

function Invoke-ContractService {
  # Runs the one-shot contract service, which keeps the deployed anchor
  # contract (redeploying after a chain reset) and saves its address in the
  # anchor volume. Sets ContractAddress, and ContractChanged when it deployed.
  $script:ContractChanged = $false
  $script:ContractAddress = ''
  if (-not (Test-True (Get-Setting 'orchestrator' 'CONTRACT_ANCHOR_ENABLED'))) { return }

  Write-Step 'Checking anchor contract'
  $result = Invoke-Captured docker @('compose', 'run', '--rm', '-T', 'contract')
  # Drop compose's own "Container ... Running" progress lines.
  $lines = @($result.Output -split "`n" | Where-Object { $_.Trim() -and $_ -notmatch '^\s*(Container|Network|Volume) \S+ \w+\s*$' })
  if ($result.Code -ne 0) {
    $lines | ForEach-Object { Write-Host "      $_" }
    Stop-WithError 'the contract service failed (see output above)'
  }
  $address = ''
  $status = ''
  foreach ($line in $lines) {
    if ($line -match '^ANCHOR_CONTRACT_ADDRESS=(0x[0-9a-fA-F]{40})') { $address = $Matches[1] }
    elseif ($line -match '^CONTRACT_STATUS=(\w+)') { $status = $Matches[1] }
    elseif ($line -match 'no contract code') { Write-Warn $line.Trim() }
  }
  if (-not $address) {
    $lines | ForEach-Object { Write-Host "      $_" }
    Stop-WithError 'the contract service did not report a contract address'
  }
  $script:ContractAddress = $address
  if ($status -eq 'deployed') {
    $script:ContractChanged = $true
    Write-Ok "contract deployed at $address"
  } else {
    Write-Ok "contract already deployed at $address"
  }
}

function Show-StatusSummary([string]$Base, [string]$LogsHint) {
  try { $status = Invoke-Json -Uri "$Base/api/status" -TimeoutSec 5 } catch { return }
  Write-Info "agents loaded: $($status.agents_loaded)"
  if ($status.contract_anchor_enabled -eq $true -and $status.contract_deployed -eq $true) {
    Write-Ok 'blockchain anchoring active'
  } elseif (Test-True (Get-Setting 'orchestrator' 'CONTRACT_ANCHOR_ENABLED')) {
    Write-Warn "blockchain anchoring enabled but not active (see: $LogsHint)"
  }
  if ($status.tts_enabled -eq $true) { Write-Ok 'text-to-speech enabled' }
}

function Invoke-SmokeTest([string]$Base) {
  Write-Step 'Smoke test: 1-round, 2-agent debate against the real LLM'
  $headers = @{}
  $apiKey = Get-Setting 'orchestrator' 'API_KEY'
  if ($apiKey) { $headers['X-API-Key'] = $apiKey }
  $body = @{
    query = 'Is it better to learn Python or JavaScript as a first programming language? Give a recommendation.'
    max_rounds = 1
    agent_count = 2
  } | ConvertTo-Json -Compress

  try {
    $runId = (Invoke-Json -Uri "$Base/api/run_async" -Method Post -Body $body -Headers $headers -TimeoutSec 30).run_id
  } catch {
    Stop-WithError "could not start a smoke-test run: $($_.Exception.Message)"
  }
  Write-Info "run $runId started"

  $sw = [Diagnostics.Stopwatch]::StartNew()
  $result = $null
  $status = ''
  while ($sw.Elapsed.TotalSeconds -lt 600) {
    try {
      $result = Invoke-Json -Uri "$Base/api/result/$runId" -TimeoutSec 10
      $status = "$($result.status)"
    } catch { }
    if ($status -eq 'completed' -or $status -eq 'failed') { break }
    Update-DevLogs
    Start-Sleep -Seconds 5
  }

  if ($status -ne 'completed') {
    $shown = $status
    if (-not $shown) { $shown = 'timeout' }
    Write-Fail "smoke run did not complete (status: $shown)"
    if ($result -and $result.error) { Write-Hint "$($result.error)" }
    Stop-WithError 'smoke test failed'
  }

  $answer = "$($result.final_answer)"
  if (-not $answer.Trim()) { Stop-WithError 'smoke run completed with an empty final answer' }
  if ($answer.StartsWith('[MOCK LLM]')) { Stop-WithError 'smoke run used mock LLM responses (MOCK_LLM=true?)' }
  Write-Ok "run completed in $([int]$sw.Elapsed.TotalSeconds)s with a real answer:"
  $answer -split "`r?`n" | Select-Object -First 6 | ForEach-Object { Write-Host "      $_" }

  $events = @(Invoke-Json -Uri "$Base/api/events/$runId" -TimeoutSec 10)
  Write-Ok "$($events.Count) provenance events recorded"

  if (Test-True (Get-Setting 'orchestrator' 'CONTRACT_ANCHOR_ENABLED')) {
    $verify = $null
    try { $verify = Invoke-Json -Uri "$Base/api/verify/$runId" -TimeoutSec 30 } catch { }
    if ($verify -and $verify.verified -eq $true) {
      Write-Ok 'commitment verified on-chain'
    } else {
      $detail = 'no response'
      if ($verify) { $detail = $verify | ConvertTo-Json -Compress }
      Write-Warn "on-chain verification did not confirm: $detail"
    }
  }
}


# -------------------------------------------------------------- dev mode ---

function Start-DevProcess([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [ConsoleColor]$Color) {
  # Output goes to data\logs\dev-<name>.*.log and is streamed to the console
  # with a [name] prefix by Update-DevLogs.
  $logDir = Join-Path $RootDir 'data\logs'
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $outLog = Join-Path $logDir "dev-$Name.out.log"
  $errLog = Join-Path $logDir "dev-$Name.err.log"
  # 5.1's Start-Process joins -ArgumentList without quoting, so quote here.
  $argLine = ($Arguments | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
  $proc = Start-Process -FilePath $FilePath -ArgumentList $argLine -WorkingDirectory $WorkingDirectory `
    -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
  $null = $proc.Handle  # keeps ExitCode readable after the process exits
  $readers = @(foreach ($path in $outLog, $errLog) {
    $stream = New-Object IO.FileStream($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
  })
  $entry = [pscustomobject]@{ Name = $Name; Color = $Color; Process = $proc; Readers = $readers }
  $script:DevProcs += $entry
}

function Update-DevLogs {
  foreach ($entry in $script:DevProcs) {
    foreach ($reader in $entry.Readers) {
      while ($null -ne ($line = $reader.ReadLine())) {
        Write-Colored "[$($entry.Name)] " $entry.Color -NoNewline
        Write-Host $line
      }
    }
  }
}

function Stop-DevProcesses {
  if ($script:DevProcs.Count -eq 0) { return }
  Write-Host ''
  Write-Host 'Stopping local API and frontend...'
  foreach ($entry in $script:DevProcs) {
    # /T takes the whole tree: uvicorn's reloader + worker, vite + esbuild.
    if (-not $entry.Process.HasExited) {
      $null = Invoke-Captured taskkill @('/PID', "$($entry.Process.Id)", '/T', '/F')
    }
    foreach ($reader in $entry.Readers) { $reader.Dispose() }
  }
  $script:DevProcs = @()
}


# --------------------------------------------------------------- commands ---

function Invoke-Up {
  Invoke-Checks 'up'
  Complete-Checks

  if ($script:Build) {
    Write-Step 'Building images'
    if (-not (Invoke-ComposeBuild)) { Stop-WithError 'docker compose build failed' }
  }

  Start-Infra
  Invoke-ContractService

  Write-Step 'Starting orchestrator'
  # Its dependencies have all run above; --no-deps keeps them untouched when
  # the orchestrator is recreated to read a newly deployed contract address.
  $recreate = @()
  if ($script:ContractChanged) { $recreate = @('--force-recreate') }
  & docker compose up -d --no-build --no-deps --wait --wait-timeout 300 @recreate orchestrator
  if ($LASTEXITCODE -ne 0) {
    Show-FailedServices @('orchestrator')
    Stop-WithError 'orchestrator did not become healthy'
  }
  $base = "http://127.0.0.1:$ApiPort"
  if (-not (Wait-Http 'UI' 60 "$base/")) { Stop-WithError 'UI is not being served' }
  Show-StatusSummary $base 'scripts\start.cmd logs orchestrator'

  if ($script:Smoke) { Invoke-SmokeTest $base }

  Write-Host ''
  Write-Colored "Q-CONSENSUS is running at http://localhost:$ApiPort" Green
  Write-Host '  logs:  scripts\start.cmd logs orchestrator'
  Write-Host '  stop:  scripts\start.cmd stop'
  Open-Browser "http://localhost:$ApiPort"
}

function Invoke-Dev {
  Invoke-Checks 'dev'
  Complete-Checks

  if ($script:Build) {
    Write-Step 'Building images'
    # "contract" builds the orchestrator image, which the contract service runs.
    if (-not (Invoke-ComposeBuild @('models', 'blockchain', 'contract'))) { Stop-WithError 'docker compose build failed' }
  }

  Start-Infra
  Invoke-ContractService

  Write-Step 'Starting local API and frontend (Ctrl+C stops both; containers keep running)'
  # Same environment the orchestrator container gets, with the container
  # hostnames pointed at the published ports and the contract address passed
  # directly (the anchor volume only exists inside Docker).
  $containerEnv = Get-ServiceEnv 'orchestrator'
  foreach ($key in $containerEnv.Keys) {
    $value = $containerEnv[$key] -replace '//llama:8080', "//127.0.0.1:$LlmPort" -replace '//blockchain:8545', "//127.0.0.1:$RpcPort"
    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
  }
  [Environment]::SetEnvironmentVariable('ANCHOR_CONTRACT_ADDRESS_FILE', $null, 'Process')
  [Environment]::SetEnvironmentVariable('ANCHOR_CONTRACT_ADDRESS', $script:ContractAddress, 'Process')
  $env:PYTHONPATH = $RootDir
  $env:PYTHONUNBUFFERED = '1'
  $env:PYTHONUTF8 = '1'
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
  Remove-Item Env:FRONTEND_DIST_DIR -ErrorAction SilentlyContinue

  try {
    Start-DevProcess 'api' $script:DevPython @('-m', 'uvicorn', 'src.qconsensus.web:app', '--host', '127.0.0.1',
      '--port', "$ApiPort", '--reload', '--reload-dir', 'src', '--reload-dir', 'config') $RootDir Cyan
    Start-DevProcess 'web' (Get-Command node).Source @('node_modules/vite/bin/vite.js', '--port', "$VitePort",
      '--strictPort') $FrontendDir Yellow

    if (-not (Wait-Http 'local API' 180 "http://127.0.0.1:$ApiPort/api/status")) {
      Update-DevLogs
      Stop-WithError 'local API failed to start (see [api] output above)'
    }
    if (-not (Wait-Http 'Vite dev server' 60 "http://127.0.0.1:$VitePort/")) {
      Update-DevLogs
      Stop-WithError 'Vite failed to start (see [web] output above)'
    }
    Show-StatusSummary "http://127.0.0.1:$ApiPort" '[api] output'

    if ($script:Smoke) { Invoke-SmokeTest "http://127.0.0.1:$ApiPort" }

    Write-Host ''
    Write-Colored "Dev mode ready: http://localhost:$VitePort (API on :$ApiPort, hot reload on)" Green
    Write-Host "  logs are also written to data\logs\dev-*.log"
    Open-Browser "http://localhost:$VitePort"

    # Runs until Ctrl+C or until either process exits; finally stops both.
    while ($true) {
      Update-DevLogs
      $exited = @($script:DevProcs | Where-Object { $_.Process.HasExited })
      if ($exited.Count -gt 0) {
        Update-DevLogs
        foreach ($entry in $exited) { Write-Warn "$($entry.Name) exited with code $($entry.Process.ExitCode)" }
        break
      }
      Start-Sleep -Milliseconds 300
    }
  } finally {
    Stop-DevProcesses
  }
}

function Invoke-Status {
  if ((Invoke-Captured docker @('info')).Code -ne 0) { Stop-WithError 'Docker is not reachable (is Docker Desktop running?)' }
  Update-Ports
  Write-Step 'Containers'
  & docker compose ps -a
  Write-Step 'Endpoints'
  $endpoints = [ordered]@{
    'UI + API' = "http://127.0.0.1:$ApiPort/api/status"
    'llama.cpp' = "http://127.0.0.1:$LlmPort/health"
    'Vite dev' = "http://127.0.0.1:$VitePort/"
  }
  foreach ($endpoint in $endpoints.GetEnumerator()) {
    $shown = $endpoint.Value -replace '127\.0\.0\.1', 'localhost'
    if (Test-Http $endpoint.Value 3) { Write-Ok "$($endpoint.Key)  $shown" }
    else { Write-Info "$($endpoint.Key)  not responding" }
  }
  $chainUp = $false
  try { $chainUp = [bool](Invoke-Rpc 'web3_clientVersion').result } catch { }
  if ($chainUp) { Write-Ok "blockchain  http://localhost:$RpcPort" } else { Write-Info 'blockchain  not responding' }
  Show-StatusSummary "http://127.0.0.1:$ApiPort" 'scripts\start.cmd logs orchestrator'
}


# ------------------------------------------------------------------- main ---

$Command = 'up'
$LogArgs = @()
$rest = @($args | ForEach-Object { "$_" })
if ($rest.Count -gt 0 -and $rest[0] -notmatch '^[-/]') {
  $Command = $rest[0].ToLowerInvariant()
  $rest = @($rest | Select-Object -Skip 1)
}
foreach ($arg in $rest) {
  switch -Regex ($arg) {
    '^--?smoke$' { $script:Smoke = $true; continue }
    '^--?no-?build$' { $script:Build = $false; continue }
    '^--?no-?open$' { $script:OpenBrowser = $false; continue }
    '^--?dev$' { $script:CheckDev = $true; continue }
    '^(-h|--help|-\?|/\?)$' { Show-Usage; exit 0 }
    '^-' { Show-Usage; Stop-WithError "unknown option: $arg" }
    default {
      if ($Command -eq 'logs') { $LogArgs += $arg }
      else { Show-Usage; Stop-WithError "unexpected argument: $arg" }
    }
  }
}

$exitCode = 0
Push-Location -LiteralPath $RootDir
[Environment]::CurrentDirectory = $RootDir
try {
  switch ($Command) {
    'up' { Invoke-Up }
    'dev' { Invoke-Dev }
    'check' {
      $script:AutoFix = $false
      $mode = 'up'
      if ($script:CheckDev) { $mode = 'dev' }
      Invoke-Checks $mode
      Complete-Checks
    }
    'status' { Invoke-Status }
    'logs' { & docker compose logs -f --tail 100 @LogArgs; $exitCode = $LASTEXITCODE }
    'stop' { & docker compose down; $exitCode = $LASTEXITCODE }
    'help' { Show-Usage }
    default { Show-Usage; Stop-WithError "unknown command: $Command" }
  }
} finally {
  Pop-Location
}
exit $exitCode
