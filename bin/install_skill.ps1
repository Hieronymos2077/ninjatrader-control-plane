# install_skill.ps1
# Installs the nt8-api-control skill for Claude Code by copying SKILL.md, docs\,
# and bin\ into . The runtime\
# folder is never copied there, the skill only points at the project root, the
# actual server keeps running from this project.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$skillMd = Join-Path $root "SKILL.md"
$docsDir = Join-Path $root "docs"
$binDir = Join-Path $root "bin"

foreach ($required in @($skillMd, $docsDir, $binDir)) {
    if (-not (Test-Path $required)) {
        Write-Error "Required source not found: $required. Aborting before touching the skills directory."
        exit 1
    }
}

$targetDir = Join-Path $env:USERPROFILE ".claude\skills\nt8-api-control"

if (Test-Path $targetDir) {
    Write-Host "Removing stale contents of: $targetDir"
    Get-ChildItem -Path $targetDir -Force | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Write-Host "Created: $targetDir"
}

$writtenPaths = @()

$destSkillMd = Join-Path $targetDir "SKILL.md"
Copy-Item -Path $skillMd -Destination $destSkillMd -Force
$writtenPaths += $destSkillMd

$destDocs = Join-Path $targetDir "docs"
Copy-Item -Path $docsDir -Destination $destDocs -Recurse -Force
$writtenPaths += $destDocs

$destBin = Join-Path $targetDir "bin"
Copy-Item -Path $binDir -Destination $destBin -Recurse -Force
$writtenPaths += $destBin

$pointerFile = Join-Path $targetDir "RUNTIME_LOCATION.txt"
$pointerContent = @"
This skill's runtime lives outside the Claude Code skills directory.
Project root: $root
Runtime package: $root\runtime
Start the server: $root\bin\start_nt8_api_server.ps1
The bin\ scripts copied alongside this file are reference copies. The scripts
that actually run against a live server should be invoked from the project
root above, since only that copy sits next to runtime\.
"@
Set-Content -Path $pointerFile -Value $pointerContent -Encoding UTF8
$writtenPaths += $pointerFile

Write-Host ""
Write-Host "Skill installed to: $targetDir"
Write-Host "Paths written:"
foreach ($p in $writtenPaths) {
    Write-Host "  $p"
}
