param(
    [string] $OllamaModel = "qwen3:4b-instruct",
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$CacheRoot = Join-Path $Root "cache"
$TempRoot = Join-Path $CacheRoot "temp"
$OllamaModelsTarget = Join-Path $Root "ollama-models"
$SenseVoiceModelTarget = Join-Path $Root "cache\hf-models\SenseVoiceSmall"
$AsciiPrefix = Split-Path -Leaf $Root
$SafePrefix = $AsciiPrefix -replace '[^A-Za-z0-9_.-]', '_'
if ([string]::IsNullOrWhiteSpace($SafePrefix)) {
    $SafePrefix = "voice_prompt_tool"
}
$RootDrive = [System.IO.Path]::GetPathRoot($Root)
$RuntimeCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($RootDrive)) {
    $RuntimeCandidates += (Join-Path $RootDrive "voice_prompt_tool_runtime\$SafePrefix")
}
if (-not [string]::IsNullOrWhiteSpace($env:PUBLIC)) {
    $RuntimeCandidates += (Join-Path $env:PUBLIC "VoicePromptToolRuntime\$SafePrefix")
}
$RuntimeCandidates += (Join-Path $Root "ascii-runtime")
$RuntimeLinkRoot = $null
foreach ($Candidate in $RuntimeCandidates) {
    try {
        if (-not (Test-Path -LiteralPath $Candidate)) {
            New-Item -ItemType Directory -Path $Candidate -Force | Out-Null
        }
        $Item = Get-Item -LiteralPath $Candidate -Force
        if ($Item.PSIsContainer) {
            $RuntimeLinkRoot = $Candidate
            break
        }
    } catch {
        continue
    }
}
if (-not $RuntimeLinkRoot) {
    throw "Cannot create a writable runtime link directory."
}
$OllamaModelsLink = Join-Path $RuntimeLinkRoot "ollama_models"
$SenseVoiceModelLink = Join-Path $RuntimeLinkRoot "sensevoice_model"

foreach ($Dir in @($CacheRoot, $TempRoot, $OllamaModelsTarget, $SenseVoiceModelTarget)) {
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

Ensure-Junction $OllamaModelsLink $OllamaModelsTarget
Ensure-Junction $SenseVoiceModelLink $SenseVoiceModelTarget

$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:MODELSCOPE_CACHE = Join-Path $CacheRoot "modelscope"
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:PYTHONUTF8 = "1"
$env:OLLAMA_MODELS = $OllamaModelsLink
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_KEEP_ALIVE = "0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR = $SenseVoiceModelLink

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$PortablePython = Join-Path $Root "runtime\python\python.exe"
$PortableSitePackages = Join-Path $Root "runtime\site-packages"
if (Test-Path -LiteralPath $PortablePython) {
    $PythonExe = $PortablePython
    $env:PYTHONPATH = "$Root\src;$PortableSitePackages"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python runtime not found. Run setup.ps1 first or use a package with runtime."
}

$SenseVoiceModelFile = Join-Path $SenseVoiceModelTarget "model.pt"
$DownloadedAnyModel = $false
if (-not (Test-Path -LiteralPath $SenseVoiceModelFile)) {
    if (-not $Quiet) { Write-Host "Downloading SenseVoiceSmall ASR model..." }
    $DownloadedAnyModel = $true
    @'
import sys
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="FunAudioLLM/SenseVoiceSmall",
    local_dir=sys.argv[1],
    local_dir_use_symlinks=False,
)
'@ | & $PythonExe - $SenseVoiceModelTarget
}

$OllamaExe = Join-Path $Root "ollama\ollama.exe"
if (-not (Test-Path -LiteralPath $OllamaExe)) {
    throw "Ollama executable not found at $OllamaExe"
}

$OllamaParts = $OllamaModel.Split(":")
$OllamaName = $OllamaParts[0]
$OllamaTag = if ($OllamaParts.Length -gt 1) { $OllamaParts[1] } else { "latest" }
$OllamaManifest = Join-Path $OllamaModelsTarget "manifests\registry.ollama.ai\library\$OllamaName\$OllamaTag"
if (-not (Test-Path -LiteralPath $OllamaManifest)) {
    if (-not $Quiet) { Write-Host "Downloading Ollama model $OllamaModel..." }
    $DownloadedAnyModel = $true
    & (Join-Path $Root "start-ollama.ps1") -Quiet
    & $OllamaExe pull $OllamaModel
    & (Join-Path $Root "stop-ollama.ps1") -Quiet
}

if (-not $Quiet -and $DownloadedAnyModel) { Write-Host "Local models are ready." }
