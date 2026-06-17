param(
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Processes = Get-Process | Where-Object {
    $_.Path -and $_.Path.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase) -and
    $_.ProcessName -in @("python", "pythonw", "ollama", "llama-server")
}

if (-not $Processes) {
    if (-not $Quiet) { Write-Host "No desktop package processes found." }
    return
}

$Processes | Stop-Process -Force
if (-not $Quiet) { Write-Host "Stopped desktop package processes." }
