param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $DesktopArgs
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
$env:OLLAMA_MODELS = Join-Path $RuntimeLinkRoot "ollama_models"
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_KEEP_ALIVE = "0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:VOICE_PROMPT_SENSEVOICE_MODEL_DIR = Join-Path $RuntimeLinkRoot "sensevoice_model"
$env:VOICE_PROMPT_RECORDINGS_ASCII = Join-Path $RuntimeLinkRoot "recordings"
$env:PYTHONPATH = Join-Path $Root "src"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()

$OllamaModelsTarget = Join-Path $Root "ollama-models"
$SenseVoiceModelTarget = Join-Path $Root "cache\hf-models\SenseVoiceSmall"
$RecordingsTarget = Join-Path $Root "recordings"
foreach ($Dir in @($CacheRoot, $TempRoot, $OllamaModelsTarget, $SenseVoiceModelTarget, $RecordingsTarget)) {
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

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$PythonwExe = Join-Path $Root ".venv\Scripts\pythonw.exe"
$PortablePython = Join-Path $Root "runtime\python\python.exe"
$PortablePythonw = Join-Path $Root "runtime\python\pythonw.exe"
$PortableSitePackages = Join-Path $Root "runtime\site-packages"
$UseConsolePython = $DesktopArgs -contains "--smoke"

if (Test-Path -LiteralPath $PortablePython) {
    $env:PYTHONPATH = "$($env:PYTHONPATH);$PortableSitePackages"
    $PythonExe = $PortablePython
    $PythonwExe = if (Test-Path -LiteralPath $PortablePythonw) { $PortablePythonw } else { $PortablePython }
} elseif (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python runtime not found. Run setup.ps1 first or use the packaged runtime."
}

if (-not $UseConsolePython) {
    & (Join-Path $Root "ensure-models.ps1")
}

$Runner = if ($UseConsolePython) { $PythonExe } else { $PythonwExe }
& $Runner -m voice_prompt_tool.desktop_app --root $Root @DesktopArgs
exit $LASTEXITCODE
