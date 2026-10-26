param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5114,
    [string]$DatabaseSource = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Executable = Join-Path $ProjectRoot "dist\CondutionTime\CondutionTime.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Executável oficial não encontrado."
}
if (-not $DatabaseSource) {
    $DatabaseSource = Join-Path $env:LOCALAPPDATA `
        "CondutionTime\data\condution_time.db"
}
$DatabaseSource = (Resolve-Path -LiteralPath $DatabaseSource).Path

$ValidationRoot = Join-Path $ProjectRoot (
    ".exe-profile-validation-" + [Guid]::NewGuid().ToString("N")
)
$IsolatedLocalAppData = Join-Path $ValidationRoot "LocalAppData"
$DataDir = Join-Path $IsolatedLocalAppData "CondutionTime\data"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$Database = Join-Path $DataDir "condution_time.db"
Copy-Item -LiteralPath $DatabaseSource -Destination $Database

function Wait-Health([int]$TargetPort) {
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            $Health = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$TargetPort/health" `
                -TimeoutSec 2
            if ($Health.status -eq "ok") {
                return
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    }
    throw "O executável não respondeu ao health check."
}

function Start-IsolatedApp([int]$TargetPort) {
    $PreviousLocalAppData = $env:LOCALAPPDATA
    try {
        $env:LOCALAPPDATA = $IsolatedLocalAppData
        return Start-Process -FilePath $Executable `
            -ArgumentList @("--background", "--port", "$TargetPort") `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        $env:LOCALAPPDATA = $PreviousLocalAppData
    }
}

function Stop-App($Process, [int]$TargetPort) {
    try {
        Invoke-RestMethod `
            -Method Post `
            -Uri "http://127.0.0.1:$TargetPort/api/desktop/exit" `
            -TimeoutSec 3 | Out-Null
    } catch {
    }
    if (-not $Process.WaitForExit(5000)) {
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    }
}

$FirstProcess = Start-IsolatedApp $Port
try {
    Wait-Health $Port
    $BaseUrl = "http://127.0.0.1:$Port"
    $ProfileUpdate = Invoke-RestMethod `
        -Method Patch `
        -Uri "$BaseUrl/api/profile" `
        -ContentType "application/json" `
        -Body '{"name":"Marcos Eduardo","avatar_initials":"ME"}'
    if (
        -not $ProfileUpdate.success -or
        $ProfileUpdate.profile.name -ne "Marcos Eduardo" -or
        $ProfileUpdate.profile.initials -ne "ME"
    ) {
        throw "A identidade não foi atualizada no EXE isolado."
    }
    $GoalsUpdate = Invoke-RestMethod `
        -Method Patch `
        -Uri "$BaseUrl/api/profile/goals" `
        -ContentType "application/json" `
        -Body (
            '{"weekly_study_minutes":300,"weekly_training_count":4,' +
            '"sleep_target_minutes":480,"hydration_target_ml":2500}'
        )
    if (
        -not $GoalsUpdate.success -or
        $GoalsUpdate.goals.goal_values.weekly_study_minutes -ne 300
    ) {
        throw "A meta semanal não foi atualizada no EXE isolado."
    }

    $ApiStatuses = [ordered]@{}
    foreach ($Endpoint in @(
        "overview",
        "study",
        "health",
        "training",
        "sleep",
        "computer",
        "achievements",
        "goals",
        "xp-history"
    )) {
        $Response = Invoke-WebRequest `
            -Uri "$BaseUrl/api/profile/$Endpoint`?period=30d" `
            -UseBasicParsing `
            -TimeoutSec 10
        if ($Response.StatusCode -ne 200) {
            throw "A API de Perfil $Endpoint falhou."
        }
        $ApiStatuses[$Endpoint] = $Response.StatusCode
    }

    $TabStatuses = [ordered]@{}
    foreach ($Tab in @(
        "overview",
        "study",
        "health",
        "training",
        "sleep",
        "computer",
        "achievements",
        "goals"
    )) {
        $Response = Invoke-WebRequest `
            -Uri "$BaseUrl/perfil?tab=$Tab&period=30d" `
            -UseBasicParsing `
            -TimeoutSec 10
        if (
            $Response.StatusCode -ne 200 -or
            $Response.Content -notmatch "data-tab=`"$Tab`"" -or
            $Response.Content -notmatch "Marcos Eduardo" -or
            $Response.Content -notmatch ">\s*ME\s*<"
        ) {
            throw "A aba $Tab não foi renderizada corretamente."
        }
        $TabStatuses[$Tab] = $Response.StatusCode
    }

    $Achievements = Invoke-RestMethod `
        -Uri "$BaseUrl/api/profile/achievements?category=Computador"
    $FirstHour = @(
        $Achievements.items |
            Where-Object { $_.achievement_key -eq "computer_first_hour" }
    )
    if (
        $FirstHour.Count -ne 1 -or
        $FirstHour[0].unit -ne "seconds" -or
        $FirstHour[0].target_label -ne "1h" -or
        $FirstHour[0].progress_percent -gt 100
    ) {
        throw "As unidades ou o limite de progresso das conquistas falharam."
    }
} finally {
    Stop-App $FirstProcess $Port
}

$SecondProcess = Start-IsolatedApp $Port
try {
    Wait-Health $Port
    $PersistedGoals = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/api/profile/goals"
    if ($PersistedGoals.goal_values.weekly_study_minutes -ne 300) {
        throw "A meta semanal não persistiu após reiniciar o EXE."
    }
} finally {
    Stop-App $SecondProcess $Port
}

$DatabaseCheck = py -3.14 -c (
    "import json,sqlite3,sys; " +
    "c=sqlite3.connect(sys.argv[1]); " +
    "print(json.dumps({" +
    "'head':c.execute('select version_num from alembic_version').fetchone()[0]," +
    "'integrity':c.execute('pragma integrity_check').fetchone()[0]," +
    "'name':c.execute('select name from user_profile limit 1').fetchone()[0]," +
    "'study_goal':c.execute('select weekly_study_minutes from user_profile limit 1').fetchone()[0]}))"
) $Database | ConvertFrom-Json
if (
    $DatabaseCheck.head -ne "e6b9c3d7f204" -or
    $DatabaseCheck.integrity -ne "ok" -or
    $DatabaseCheck.name -ne "Marcos Eduardo" -or
    $DatabaseCheck.study_goal -ne 300
) {
    throw "A validação final do banco isolado falhou."
}

[ordered]@{
    executable = $Executable
    validation_root = $ValidationRoot
    database_source = $DatabaseSource
    database_head = $DatabaseCheck.head
    integrity = $DatabaseCheck.integrity
    profile_name = $DatabaseCheck.name
    initials = "ME"
    weekly_study_minutes = $DatabaseCheck.study_goal
    achievement_unit = $FirstHour[0].unit
    achievement_target = $FirstHour[0].target_label
    api_statuses = $ApiStatuses
    tab_statuses = $TabStatuses
} | ConvertTo-Json -Depth 4 -Compress
