param(
    [switch]$Background,
    [switch]$Open,
    [switch]$NoTray,
    [ValidateRange(1024, 65535)]
    [int]$Port
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

if ((Test-Path -LiteralPath $VenvPython) -and (Test-Path -LiteralPath $VenvPip)) {
    $Python = $VenvPython
    $PythonArgs = @()
} else {
    $Python = "py"
    $PythonArgs = @("-3.14")
}

$DesktopArgs = @("-m", "desktop.launcher")
if ($Background) { $DesktopArgs += "--background" }
if ($Open) { $DesktopArgs += "--open" }
if ($NoTray) { $DesktopArgs += "--no-tray" }
if ($Port) { $DesktopArgs += @("--port", "$Port") }

Push-Location $ProjectRoot
try {
    & $Python @PythonArgs @DesktopArgs
} finally {
    Pop-Location
}
