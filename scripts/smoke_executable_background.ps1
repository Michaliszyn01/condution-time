param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5110
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Executable = Join-Path $ProjectRoot "dist\CondutionTime\CondutionTime.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Executável oficial não encontrado."
}

$Process = Start-Process -FilePath $Executable `
    -ArgumentList @("--background", "--port", "$Port") `
    -WindowStyle Hidden `
    -PassThru
try {
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    $Health = $null
    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            $Health = Invoke-WebRequest `
                -Uri "http://127.0.0.1:$Port/health" `
                -UseBasicParsing `
                -TimeoutSec 2
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $Health -or $Health.StatusCode -ne 200) {
        throw "O executável não respondeu ao health check."
    }
    $Routes = @(
        "/estudo?date=2026-07-27",
        "/treino?date=2026-07-27",
        "/sono?date=2026-07-28",
        "/computador?date=2026-07-27"
    )
    $Statuses = @{}
    foreach ($Route in $Routes) {
        $Response = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port$Route" `
            -UseBasicParsing `
            -TimeoutSec 5
        $Statuses[$Route] = $Response.StatusCode
    }
    [ordered]@{
        executable = $Executable
        process_id = $Process.Id
        health = $Health.StatusCode
        routes = $Statuses
    } | ConvertTo-Json -Depth 4 -Compress
} finally {
    & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
}
