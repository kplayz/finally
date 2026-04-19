# Stop FinAlly. Does NOT remove the data volume.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
& docker compose down
Write-Host "[stop] Container stopped. Volume 'finally-data' preserved."
