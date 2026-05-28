param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$RunDir = Join-Path $ProjectRoot ".run"
$PidFile = Join-Path $RunDir "jianying-cache-extractor.pid"
$Python = "python"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($ExistingPid -match "^\d+$") {
        $Existing = Get-CimInstance Win32_Process -Filter "ProcessId = $ExistingPid" -ErrorAction SilentlyContinue
        if ($Existing -and $Existing.CommandLine -like "*jianying_controller*") {
            Write-Host "JianYing cache extractor is already running. PID: $ExistingPid"
            exit 0
        }
    }
}

if ($Console) {
    Set-Location -LiteralPath $ProjectRoot
    & $Python -m jianying_controller
    exit $LASTEXITCODE
}

$GuiPython = $Python
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($PythonCommand) {
    $Pythonw = Join-Path (Split-Path -Parent $PythonCommand.Source) "pythonw.exe"
    if (Test-Path -LiteralPath $Pythonw) {
        $GuiPython = $Pythonw
    }
}

$Process = Start-Process `
    -FilePath $GuiPython `
    -ArgumentList @("-m", "jianying_controller") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -PassThru
Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ascii
Write-Host "Started JianYing cache extractor. PID: $($Process.Id)"
