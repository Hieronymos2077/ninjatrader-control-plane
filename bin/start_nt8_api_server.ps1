# start_nt8_api_server.ps1
# Starts the NT8 API server as a real Python package (python -m runtime), not the
# old runtime\server.py path (that file has no main block and exits instantly while
# still reporting a fake success).
#
# Canonical windowless chain: for scheduled tasks or unattended launch, do not rely
# on the -Hidden switch below. Follow the user's global standard instead: run the
# base GUI pythonw.exe on a tiny launcher that spawns the venv python.exe with
# CREATE_NO_WINDOW and stdout/stderr redirected to DEVNULL. The -Hidden switch here
# is only a manual convenience for foreground use, it still allocates a console
# briefly via Start-Process WindowStyle Hidden.

param(
    [int]$Port = 8088,
    [int]$AddonPort = 8089,
    [switch]$Hidden,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
$logFile = Join-Path $logDir "nt8_api_server.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Get-ListenerProcess {
    param([int]$TargetPort)
    try {
        $conns = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    } catch {
        $conns = $null
    }
    if (-not $conns) {
        return $null
    }
    $ownerPid = ($conns | Select-Object -First 1).OwningProcess
    try {
        return Get-Process -Id $ownerPid -ErrorAction Stop
    } catch {
        return $null
    }
}

if ($Stop) {
    $proc = Get-ListenerProcess -TargetPort $Port
    if (-not $proc) {
        Write-Host "No process is listening on port $Port. Nothing to stop."
        exit 0
    }

    $isPython = $proc.ProcessName -ieq "python"
    $isThisVenv = $false
    try {
        $isThisVenv = $proc.Path -and ($proc.Path -ieq $venvPython)
    } catch {
        $isThisVenv = $false
    }

    if (-not ($isPython -and $isThisVenv)) {
        Write-Error "Refusing to stop PID $($proc.Id) ($($proc.ProcessName)) on port $Port, it is not python.exe from this project's venv ($venvPython). Stop it manually if that is intended."
        exit 1
    }

    Stop-Process -Id $proc.Id -Force
    Write-Host "Stopped PID $($proc.Id), the python.exe from this project's venv that owned port $Port."
    exit 0
}

if (-not (Test-Path $venvPython)) {
    Write-Error "Venv python not found at: $venvPython. Create the venv first (python -m venv .venv from the project root)."
    exit 1
}

$runtimeInit = Join-Path $root "runtime\__main__.py"
if (-not (Test-Path $runtimeInit)) {
    Write-Error "runtime package entry point not found at: $runtimeInit"
    exit 1
}

$existing = Get-ListenerProcess -TargetPort $Port
if ($existing) {
    Write-Warning "Port $Port is already in use by PID $($existing.Id) ($($existing.ProcessName)). Use -Stop first if you want to restart."
}

$env:NT8_API_PORT = "$Port"
$env:NT8_ADDON_PORT = "$AddonPort"

Write-Host "Starting NT8 API Server on port $Port (addon port $AddonPort)..."
Write-Host "  Interpreter: $venvPython"
Write-Host "  Working dir: $root"
Write-Host "  Log: $logFile"

# Merge stdout and stderr into a single log file via a cmd.exe wrapper, since
# Start-Process cannot redirect both streams to the same file directly.
$cmdArgs = "/c `"`"$venvPython`" -m runtime >> `"$logFile`" 2>&1`""

if ($Hidden) {
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru
} else {
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -WorkingDirectory $root -NoNewWindow -PassThru
}

Write-Host "Launcher PID: $($process.Id) (cmd.exe wrapper, the real python.exe PID is discovered by port below)"

$healthUrl = "http://127.0.0.1:$Port/v1/nt8/health"
$deadline = (Get-Date).AddSeconds(15)
$healthy = $false
$lastError = ""

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method GET -TimeoutSec 3
        if ($response.ok -eq $true) {
            $healthy = $true
            break
        }
    } catch {
        $lastError = $_.Exception.Message
    }
    Start-Sleep -Milliseconds 500
}

if ($healthy) {
    $listener = Get-ListenerProcess -TargetPort $Port
    Write-Host ""
    Write-Host "Server is up and answering at $healthUrl"
    if ($listener) {
        Write-Host "  Listening PID: $($listener.Id) ($($listener.Path))"
    }
    exit 0
} else {
    Write-Host ""
    Write-Error "Server did NOT answer $healthUrl within 15 seconds. Last error: $lastError"
    if (Test-Path $logFile) {
        Write-Host ""
        Write-Host "Last 40 lines of $logFile :"
        Get-Content -Path $logFile -Tail 40
    } else {
        Write-Host "No log file was written at $logFile, the process may have failed to start at all."
    }
    exit 1
}
