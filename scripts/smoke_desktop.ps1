param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Executable = Join-Path $ProjectRoot "dist\CondutionTime\CondutionTime.exe"

if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Execute scripts\build_windows.ps1 antes do smoke test."
}

Write-Host "Abrindo o aplicativo na porta preferida $Port."
Write-Host "1. Feche a janela no X e confirme que ela permanece na bandeja."
Write-Host "2. Execute este script novamente e confirme que a mesma janela reaparece."
Write-Host "3. Repita a restauração e encerre usando Sair no menu da bandeja."
Write-Host "4. Confirme que uma nova execução após Sair inicia normalmente."
Start-Process -FilePath $Executable -ArgumentList @("--open", "--port", "$Port")
