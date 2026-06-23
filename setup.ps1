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
$env:OLLAMA_KEEP_ALIVE = "30m"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR = "D:\desktop\${AsciiPrefix}_sensevoice_model"
$env:VOICE_PROMPT_RECORDINGS_ASCII = "D:\desktop\${AsciiPrefix}_recordings"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()

$OllamaModelsTarget = Join-Path $Root "ollama-models"
$SenseVoiceModelTarget = Join-Path $Root "cache\hf-models\SenseVoiceSmall"
$RecordingsTarget = Join-Path $Root "recordings"

foreach ($Dir in @($CacheRoot, $TempRoot, $env:UV_CACHE_DIR, $env:PIP_CACHE_DIR, $env:HF_HOME, $env:HUGGINGFACE_HUB_CACHE, $env:MODELSCOPE_CACHE, $env:XDG_CACHE_HOME, $OllamaModelsTarget, $SenseVoiceModelTarget, $RecordingsTarget)) {
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
Ensure-Junction $env:OLLAMA_MODELS $OllamaModelsTarget
Ensure-Junction $env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR $SenseVoiceModelTarget
Ensure-Junction $env:VOICE_PROMPT_RECORDINGS_ASCII $RecordingsTarget

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. This machine previously reported uv at D:\apps\uv\bin\uv.exe; make sure it is on PATH."
}

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    uv venv (Join-Path $Root ".venv") --python 3.12
}

uv pip install --python $PythonExe -e $Root
uv pip install --python $PythonExe funasr modelscope
uv pip install --python $PythonExe torch torchaudio --index-url https://download.pytorch.org/whl/cpu

$SenseVoiceModelFile = Join-Path $SenseVoiceModelTarget "model.pt"
if (-not (Test-Path -LiteralPath $SenseVoiceModelFile)) {
    & (Join-Path $Root ".venv\Scripts\hf.exe") download FunAudioLLM/SenseVoiceSmall --local-dir $SenseVoiceModelTarget
}

Write-Host "Setup complete."
Write-Host "Run: powershell -ExecutionPolicy Bypass -File `"$Root\run.ps1`""
