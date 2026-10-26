param(
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [switch]$PromoteOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

$VenvReady = (
    (Test-Path -LiteralPath $VenvPython) -and
    (Test-Path -LiteralPath $VenvPip)
)
if ($VenvReady) {
    & $VenvPython -c "import PyInstaller" 2>$null
    $VenvReady = $LASTEXITCODE -eq 0
}

if ($VenvReady) {
    $Python = $VenvPython
    $PythonArgs = @()
} else {
    $Python = "py"
    $PythonArgs = @("-3.14")
}

function Remove-BuildDirectory([string]$Name) {
    $Target = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Name))
    $ExpectedParent = [System.IO.Path]::GetFullPath($ProjectRoot) +
        [System.IO.Path]::DirectorySeparatorChar
    if (-not $Target.StartsWith($ExpectedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Diretório de build fora do projeto: $Target"
    }
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

Push-Location $ProjectRoot
try {
    $CandidateRoot = Join-Path $ProjectRoot (
        ".build-candidate-" + [Guid]::NewGuid().ToString("N")
    )
    $Candidate = Join-Path $CandidateRoot "CondutionTime"
    $Official = Join-Path $ProjectRoot "dist\CondutionTime"

    if (-not $PromoteOnly) {
        if (-not $SkipInstall) {
            & $Python @PythonArgs -m pip install -r requirements.txt
        }
        if (-not $SkipTests) {
            & $Python @PythonArgs -m pytest -p no:cacheprovider -q
        }
        Remove-BuildDirectory "build"
        & $Python @PythonArgs -m PyInstaller --noconfirm `
            --distpath $CandidateRoot CondutionTime.spec
    }

    $CandidateExecutable = Join-Path $Candidate "CondutionTime.exe"
    if (-not (Test-Path -LiteralPath $CandidateExecutable)) {
        throw "O executável candidato não foi gerado."
    }
    if (-not (Test-Path -LiteralPath $Official)) {
        New-Item -ItemType Directory -Path $Official | Out-Null
    }
    & robocopy.exe $Candidate $Official /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS
    $RobocopyExitCode = $LASTEXITCODE
    if ($RobocopyExitCode -ge 8) {
        throw "Falha ao promover o pacote candidato (robocopy $RobocopyExitCode)."
    }
    $CandidateHash = (Get-FileHash -Algorithm SHA256 $CandidateExecutable).Hash
    $OfficialExecutable = Join-Path $Official "CondutionTime.exe"
    $OfficialHash = (Get-FileHash -Algorithm SHA256 $OfficialExecutable).Hash
    if ($CandidateHash -ne $OfficialHash) {
        throw "O executável oficial não corresponde ao candidato."
    }
    Write-Host "Build concluído: $OfficialExecutable"
} finally {
    Pop-Location
}
