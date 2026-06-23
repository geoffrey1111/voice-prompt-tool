param(
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OllamaExe = Join-Path $Root "ollama\ollama.exe"
$ModelsTarget = Join-Path $Root "ollama-models"
$AsciiPrefix = Split-Path -Leaf $Root
$ModelsDir = "D:\desktop\${AsciiPrefix}_ollama_models"
$LogDir = Join-Path $Root "logs"

if (-not (Test-Path -LiteralPath $OllamaExe)) {
    throw "Ollama executable not found at $OllamaExe"
}

foreach ($Dir in @($ModelsTarget, $LogDir)) {
    if (-not (Test-Path -LiteralPath $Dir)) {
        New-Item -ItemType Directory -Path $Dir | Out-Null
    }
}

function Ensure-Junction([string] $LinkPath, [string] $TargetPath) {
    if (Test-Path -LiteralPath $LinkPath) {
        $Item = Get-Item -LiteralPath $LinkPath -Force
        if ($Item.LinkType -eq "Junction" -and [string]$Item.Target -eq $TargetPath) {
            return
        }
        if ($Item.LinkType -ne "Junction") {
            throw "Path exists and is not a junction: $LinkPath"
        }
        Remove-Item -LiteralPath $LinkPath -Force
    }
    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
}
Ensure-Junction $ModelsDir $ModelsTarget

$env:OLLAMA_MODELS = $ModelsDir
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_KEEP_ALIVE = "30m"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"

try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
    if (-not $Quiet) { Write-Host "Ollama server already running." }
    return
} catch {
}

Start-Process `
    -FilePath $OllamaExe `
    -ArgumentList "serve" `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir "ollama.out.log") `
    -RedirectStandardError (Join-Path $LogDir "ollama.err.log") | Out-Null

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        if (-not $Quiet) { Write-Host "Ollama server started." }
        return
    } catch {
    }
}

throw "Ollama server did not become ready. Check $LogDir\ollama.err.log"
