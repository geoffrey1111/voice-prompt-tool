param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $DesktopArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$StartupLog = Join-Path $LogDir "startup.log"
$StartHidden = $DesktopArgs -contains "--start-hidden"

if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-StartupLog([string] $Message) {
    $Line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $StartupLog -Value $Line -Encoding UTF8
    if (-not $StartHidden) {
        Write-Host $Message
    }
}

function Write-ProcessOutput($Output) {
    foreach ($Line in $Output) {
        $Text = ([string] $Line) -replace "`0", ""
        if (-not [string]::IsNullOrWhiteSpace($Text)) {
            Write-StartupLog $Text
        }
    }
}

function Assert-RequiredPath([string] $RelativePath, [string] $Description) {
    $Path = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Package is incomplete: missing $Description ($RelativePath). Re-extract the full folder and try again."
    }
}

function Assert-PythonRuntime {
    $PortablePython = Join-Path $Root "runtime\python\python.exe"
    $PortablePackages = Join-Path $Root "runtime\site-packages"
    if ((Test-Path -LiteralPath $PortablePython) -and (Test-Path -LiteralPath $PortablePackages)) {
        Write-StartupLog "Portable Python runtime found."
        return
    }

    $DevPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $DevPython) {
        Write-StartupLog "Portable Python runtime not found; using development .venv."
        return
    }

    throw "Python runtime is missing. Re-extract the full package folder. Users do not need to install Python separately."
}

function Get-TotalMemoryGB {
    try {
        $Computer = Get-CimInstance Win32_ComputerSystem
        return [Math]::Round($Computer.TotalPhysicalMemory / 1GB, 1)
    } catch {
        return $null
    }
}

try {
    $Header = "[{0}] Voice Prompt Tool startup" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Set-Content -LiteralPath $StartupLog -Value $Header -Encoding UTF8
    Write-StartupLog "Starting Voice Prompt Tool..."
    Write-StartupLog "App folder: $Root"

    Assert-RequiredPath "desktop.ps1" "desktop startup script"
    Assert-RequiredPath "ensure-models.ps1" "model check script"
    Assert-RequiredPath "src" "application source folder"
    Assert-RequiredPath "assets" "application assets folder"
    Assert-RequiredPath "ollama\ollama.exe" "local Ollama executable"
    Assert-PythonRuntime

    $MemoryGB = Get-TotalMemoryGB
    if ($null -ne $MemoryGB) {
        Write-StartupLog "Detected memory: $MemoryGB GB"
        if ($MemoryGB -lt 8) {
            Write-StartupLog "Warning: memory is below 8GB. Local models may load slowly or fail to load."
        } elseif ($MemoryGB -lt 12) {
            Write-StartupLog "Notice: memory is below 12GB. First model load may take longer."
        }
    } else {
        Write-StartupLog "Could not read memory information; continuing startup."
    }

    Write-StartupLog "Checking local models and runtime folders. First launch may take a while."
    $DesktopScript = Join-Path $Root "desktop.ps1"
    $DesktopOutput = & $DesktopScript @DesktopArgs 2>&1
    $ExitCode = $LASTEXITCODE
    Write-ProcessOutput $DesktopOutput
    if ($ExitCode -ne 0) {
        throw "Desktop app exit code: $ExitCode"
    }
    exit 0
} catch {
    $Message = $_.Exception.Message
    Write-StartupLog "Startup failed: $Message"
    if (-not $StartHidden) {
        Write-Host ""
        Write-Host "Startup failed: $Message" -ForegroundColor Red
        Write-Host "Log file: $StartupLog"
        Write-Host "Send startup.log to the developer for troubleshooting."
        Read-Host "Press Enter to close"
    }
    exit 1
}
