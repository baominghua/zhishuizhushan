$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

if (-not $env:REMOTE_SENSING_DATA_DIR) {
  $env:REMOTE_SENSING_DATA_DIR = Join-Path $root "data\remote-sensing"
}
if (-not $env:REMOTE_SENSING_CORS_ORIGINS) {
  $env:REMOTE_SENSING_CORS_ORIGINS = "*"
}
if (-not $env:REMOTE_SENSING_SERVE_STATIC) {
  $env:REMOTE_SENSING_SERVE_STATIC = "1"
}
if (-not $env:REMOTE_SENSING_STATIC_DIR) {
  $env:REMOTE_SENSING_STATIC_DIR = $root
}
if (-not $env:REMOTE_SENSING_IMPORT_DIRS) {
  $env:REMOTE_SENSING_IMPORT_DIRS = Join-Path $env:REMOTE_SENSING_DATA_DIR "inbox"
}
if (-not $env:REMOTE_SENSING_TASK_WORKERS) {
  $env:REMOTE_SENSING_TASK_WORKERS = "1"
}
if (-not $env:REMOTE_SENSING_TILE_CACHE) {
  $env:REMOTE_SENSING_TILE_CACHE = "1"
}
if (-not $env:REMOTE_SENSING_TIANDITU_TIMEOUT) {
  $env:REMOTE_SENSING_TIANDITU_TIMEOUT = "8"
}
$port = if ($env:REMOTE_SENSING_PORT) { $env:REMOTE_SENSING_PORT } else { "8010" }

.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port $port
