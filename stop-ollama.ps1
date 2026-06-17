param(
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OllamaExe = Join-Path $Root "ollama\ollama.exe"
$LlamaServerExe = Join-Path $Root "ollama\lib\ollama\llama-server.exe"
$Processes = Get-Process | Where-Object {
    ($_.ProcessName -eq "ollama" -and $_.Path -eq $OllamaExe) -or
    ($_.ProcessName -eq "llama-server" -and $_.Path -eq $LlamaServerExe)
}

if (-not $Processes) {
    if (-not $Quiet) { Write-Host "No local Ollama process found for this tool." }
    return
}

$Processes | Stop-Process -Force
if (-not $Quiet) { Write-Host "Stopped local Ollama processes." }
