$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$RunDir = Join-Path $ProjectRoot ".run"
$PidFile = Join-Path $RunDir "jianying-cache-extractor.pid"

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "JianYing cache extractor is not running: PID file not found."
    exit 0
}

$PidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($PidText -notmatch "^\d+$") {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Removed invalid PID file."
    exit 0
}

$ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $PidText" -ErrorAction SilentlyContinue
if (-not $ProcessInfo) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "JianYing cache extractor is not running."
    exit 0
}

if ($ProcessInfo.CommandLine -notlike "*jianying_controller*") {
    Write-Host "PID $PidText does not belong to this tool. Refusing to stop it."
    exit 1
}

Stop-Process -Id ([int]$PidText) -Force
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "Stopped JianYing cache extractor. PID: $PidText"
