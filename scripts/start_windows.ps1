# Start FinAlly locally via docker compose. Idempotent.
#   -Build : force rebuild
#   -Open  : open http://localhost:8000 in the default browser

param(
    [switch]$Build,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[start] .env was missing - copied from .env.example. Fill in OPENROUTER_API_KEY."
    } else {
        Write-Error "[start] .env missing and no .env.example to copy from."
        exit 1
    }
}

$composeArgs = @("compose", "up", "-d")
if ($Build) { $composeArgs += "--build" }

Write-Host "[start] Bringing up FinAlly..."
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$url = "http://localhost:8000"
Write-Host "[start] Waiting for health at $url/api/health..."
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Host "[start] Ready at $url"
            if ($Open) { Start-Process $url }
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Error "[start] Timed out waiting for health. Check: docker compose logs -f"
exit 1
