param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $VoicePromptArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$CacheRoot = Join-Path $Root "cache"
$TempRoot = Join-Path $CacheRoot "temp"

$env:VOICE_PROMPT_ROOT = $Root
$env:UV_CACHE_DIR = Join-Path $CacheRoot "uv"
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:MODELSCOPE_CACHE = Join-Path $CacheRoot "modelscope"
$env:XDG_CACHE_HOME = Join-Path $CacheRoot "xdg"
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:PYTHONUTF8 = "1"
$AsciiPrefix = Split-Path -Leaf $Root
$env:OLLAMA_MODELS = "D:\desktop\${AsciiPrefix}_ollama_models"
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_KEEP_ALIVE = "0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR = "D:\desktop\${AsciiPrefix}_sensevoice_model"
$env:VOICE_PROMPT_RECORDINGS_ASCII = "D:\desktop\${AsciiPrefix}_recordings"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()

$SenseVoiceModelTarget = Join-Path $Root "cache\hf-models\SenseVoiceSmall"
$RecordingsTarget = Join-Path $Root "recordings"
foreach ($Dir in @($TempRoot, $env:MODELSCOPE_CACHE, $SenseVoiceModelTarget, $RecordingsTarget)) {
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
Ensure-Junction $env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR $SenseVoiceModelTarget
Ensure-Junction $env:VOICE_PROMPT_RECORDINGS_ASCII $RecordingsTarget

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$PortablePython = Join-Path $Root "runtime\python\python.exe"
$PortableSitePackages = Join-Path $Root "runtime\site-packages"
if (Test-Path -LiteralPath $PortablePython) {
    $env:PYTHONPATH = "$(Join-Path $Root 'src');$PortableSitePackages"
    $PythonExe = $PortablePython
} elseif (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Virtual environment not found. Run setup.ps1 first."
}

$UseOllama = -not ($VoicePromptArgs -contains "--no-ollama")
$StartOllama = Join-Path $Root "start-ollama.ps1"
$StopOllama = Join-Path $Root "stop-ollama.ps1"
$OllamaWasRunning = $false
if ($UseOllama -and (Test-Path -LiteralPath $StartOllama)) {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        $OllamaWasRunning = $true
    } catch {
        $OllamaWasRunning = $false
    }
    & $StartOllama -Quiet
}

$ExitCode = 0
try {
    & $PythonExe -m voice_prompt_tool.cli @VoicePromptArgs
    $ExitCode = $LASTEXITCODE
} finally {
    if ($UseOllama -and -not $OllamaWasRunning -and (Test-Path -LiteralPath $StopOllama)) {
        & $StopOllama -Quiet
    }
}

exit $ExitCode
