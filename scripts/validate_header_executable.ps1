param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5112,
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
    ".exe-header-validation-" + [Guid]::NewGuid().ToString("N")
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
    $ProfileBody = @{
        name = "Marcos Eduardo"
        avatar_initials = $null
    } | ConvertTo-Json
    $ProfileUpdate = Invoke-RestMethod `
        -Method Patch `
        -Uri "$BaseUrl/api/profile" `
        -ContentType "application/json" `
        -Body $ProfileBody
    if (
        -not $ProfileUpdate.success -or
        $ProfileUpdate.profile.name -ne "Marcos Eduardo" -or
        $ProfileUpdate.profile.initials -ne "ME"
    ) {
        throw "A identidade real não foi atualizada no EXE isolado."
    }

    $Before = Invoke-RestMethod -Uri "$BaseUrl/api/hydration/today"
    $Added = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/hydration/quick" `
        -ContentType "application/json" `
        -Body '{"amount_ml":300}'
    $After = Invoke-RestMethod -Uri "$BaseUrl/api/hydration/today"
    if ($After.total_ml -ne ($Before.total_ml + 300)) {
        throw "O total de hidratação não aumentou em 300 ml."
    }
    if ($Added.message -ne "300 ml registrados") {
        throw "O retorno da hidratação rápida é inesperado."
    }

    $Pause = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/computer-monitor/pause"
    $Notifications = Invoke-RestMethod -Uri "$BaseUrl/api/notifications?per_page=5"
    $PausedNotification = @(
        $Notifications.items |
            Where-Object { $_.type -eq "monitoring_paused" }
    )
    if ($PausedNotification.Count -ne 1) {
        throw "A pausa manual não gerou uma notificação deduplicada."
    }
    $UnreadBefore = $Notifications.unread_count
    $Read = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/notifications/$($PausedNotification[0].id)/read"
    if ($Read.unread_count -ne ($UnreadBefore - 1)) {
        throw "O contador não foi atualizado ao marcar como lida."
    }
    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/notifications/read-all" | Out-Null
    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/computer-monitor/resume" | Out-Null

    $RouteChecks = [ordered]@{}
    foreach ($Route in @(
        "/",
        "/alimentacao",
        "/perfil",
        "/configuracoes",
        "/notificacoes"
    )) {
        $Response = Invoke-WebRequest `
            -Uri "$BaseUrl$Route" `
            -UseBasicParsing `
            -TimeoutSec 5
        $RouteChecks[$Route] = $Response.StatusCode
        if ($Response.StatusCode -ne 200) {
            throw "A rota $Route não respondeu com HTTP 200."
        }
        if ($Response.Content -notmatch "water-bottle-icon") {
            throw "O componente global não apareceu em $Route."
        }
    }
    $ProfileHtml = (
        Invoke-WebRequest -Uri "$BaseUrl/perfil" -UseBasicParsing
    ).Content
    if (
        $ProfileHtml -notmatch "Marcos Eduardo" -or
        $ProfileHtml -notmatch ">\s*ME\s*<" -or
        $ProfileHtml -notmatch ([regex]::Escape("$($After.total_ml) ml"))
    ) {
        throw "Perfil, iniciais ou total do header não apareceram no EXE."
    }
} finally {
    Stop-App $FirstProcess $Port
}

$SecondProcess = Start-IsolatedApp $Port
try {
    Wait-Health $Port
    $Persisted = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/api/hydration/today"
    if ($Persisted.total_ml -ne $After.total_ml) {
        throw "A hidratação não persistiu após reiniciar o EXE."
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
    "'name':c.execute('select name from user_profile limit 1').fetchone()[0]}))"
) $Database | ConvertFrom-Json
if (
    $DatabaseCheck.head -ne "e6b9c3d7f204" -or
    $DatabaseCheck.integrity -ne "ok" -or
    $DatabaseCheck.name -ne "Marcos Eduardo"
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
    hydration_before_ml = $Before.total_ml
    hydration_after_ml = $After.total_ml
    persisted_after_restart_ml = $Persisted.total_ml
    notification_type = "monitoring_paused"
    unread_after_read_all = 0
    routes = $RouteChecks
} | ConvertTo-Json -Depth 4 -Compress
