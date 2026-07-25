# deploy_addon.ps1
# Deploys runtime\assets\nt8\AntigravityBridgeAddOn.cs to the live NinjaTrader 8
# AddOns folder, backing up any existing copy first. Touches no other file in
# that folder.
#
# Manual step after this script runs: in NinjaTrader 8, use Control Center menu,
# New, then NinjaScript Editor. Inside the editor, press F5 to compile.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "runtime\assets\nt8\AntigravityBridgeAddOn.cs"

if (-not (Test-Path $source)) {
    Write-Error "Source file not found: $source"
    exit 1
}

$nt8AddOnsDir = Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom\AddOns"

if (-not (Test-Path $nt8AddOnsDir)) {
    New-Item -ItemType Directory -Path $nt8AddOnsDir -Force | Out-Null
    Write-Host "Created directory: $nt8AddOnsDir"
}

$dest = Join-Path $nt8AddOnsDir "AntigravityBridgeAddOn.cs"

if (Test-Path $dest) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $bak = Join-Path $nt8AddOnsDir "AntigravityBridgeAddOn.cs.$timestamp.bak"
    Copy-Item -Path $dest -Destination $bak -Force
    Write-Host "Backed up existing file to: $bak"
}

Copy-Item -Path $source -Destination $dest -Force

$sourceHash = (Get-FileHash -Path $source -Algorithm SHA256).Hash
$destHash = (Get-FileHash -Path $dest -Algorithm SHA256).Hash

if ($sourceHash -ne $destHash) {
    Write-Error "Copy verification failed: hash of $dest does not match $source."
    exit 1
}

Write-Host ""
Write-Host "Deployed AntigravityBridgeAddOn.cs to:"
Write-Host "  $dest"
Write-Host "Hash verified (SHA256 matches source): $destHash"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open NinjaTrader 8"
Write-Host "  2. In Control Center, open the menu, choose New, then NinjaScript Editor"
Write-Host "  3. Inside the NinjaScript Editor, press F5 to compile"
Write-Host "  4. The Antigravity Bridge will start automatically on port 8089"
