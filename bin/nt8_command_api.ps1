# nt8_command_api.ps1
# Thin PowerShell wrapper over POST http://localhost:8088/v1/nt8/command.
# No file paths are hardcoded here, the only project reference is the port,
# which defaults to NT8_API_PORT or 8088 to match runtime\__main__.py.

param(
    [Parameter(Mandatory=$true)]
    [string]$Command,

    [string]$ArgsJson = "{}",
    [string]$Backend = "auto",
    [Alias("Timeout")]
    [int]$TimeoutSec = 120,
    [string]$ApiHost = "127.0.0.1",
    [int]$Port = 0,
    [string]$RequestId = "",
    [string]$ResponseMode = "normal"
)

$ErrorActionPreference = "Stop"

if ($Port -eq 0) {
    $Port = if ($env:NT8_API_PORT) { [int]$env:NT8_API_PORT } else { 8088 }
}

# Parse ArgsJson
try {
    $parsedArgs = $ArgsJson | ConvertFrom-Json
} catch {
    @{ ok = $false; error = "Invalid ArgsJson: $($_.Exception.Message)" } | ConvertTo-Json -Depth 5
    exit 1
}

# Build request body
$bodyObj = @{
    command = $Command
    args = $parsedArgs
    backend = $Backend
    timeout_seconds = $TimeoutSec
    response_mode = $ResponseMode
}

if ($RequestId -ne "") {
    $bodyObj.request_id = $RequestId
}

$body = $bodyObj | ConvertTo-Json -Depth 10

$uri = "http://${ApiHost}:${Port}/v1/nt8/command"

try {
    $response = Invoke-RestMethod -Uri $uri `
        -Method POST `
        -Body $body `
        -ContentType "application/json; charset=utf-8" `
        -TimeoutSec $TimeoutSec

    $response | ConvertTo-Json -Depth 10
} catch {
    $errMsg = $_.Exception.Message
    if ($_.Exception.Response) {
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $errBody = $reader.ReadToEnd()
            $reader.Close()
            $errMsg = $errBody
        } catch {}
    }
    @{
        ok = $false
        error = $errMsg
        command = $Command
        backend = $Backend
    } | ConvertTo-Json -Depth 5
}
