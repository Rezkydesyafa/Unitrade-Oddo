param(
    [ValidateSet("doctor", "config", "install-node", "build", "watch", "install", "upgrade", "run", "seed-dry", "seed", "setup")]
    [string]$Task = "doctor",

    [string]$OdooHome,
    [string]$OdooPython,
    [string]$OdooBin,
    [string]$OdooConf,
    [string]$ConfigOut,

    [string]$Database,
    [string]$PgHost,
    [int]$PgPort = 5432,
    [string]$PgUser,
    [string]$PgPassword,
    [string]$AdminPasswd,

    [int]$Port = 8069,
    [string[]]$Modules,
    [string]$DataDir,
    [string]$LogDir,
    [switch]$NoDev,
    [bool]$SeedTransactions = $true,
    [string]$SeedPassword
)

$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

$DefaultModules = @(
    "unitrade",
    "unitrade_theme",
    "unitrade_seller",
    "unitrade_product_ext",
    "unitrade_payment",
    "unitrade_delivery",
    "unitrade_dispute",
    "unitrade_wishlist",
    "unitrade_review",
    "unitrade_chat",
    "unitrade_notification"
)

function Use-Default {
    param([string]$Value, [string]$EnvName, [string]$Default)
    if ($Value) {
        return $Value
    }
    $envValue = [Environment]::GetEnvironmentVariable($EnvName)
    if ($envValue) {
        return $envValue
    }
    return $Default
}

function Get-FullPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Path))
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Missing {
    param([string]$Message)
    Write-Host "[MISSING] $Message" -ForegroundColor Red
}

function Find-Npm {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $cmd = Get-Command npm -ErrorAction SilentlyContinue
    }
    return $cmd
}

function Assert-File {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label tidak ditemukan: $Path"
    }
}

function Assert-OdooRuntime {
    Assert-File -Path $OdooPython -Label "Odoo Python"
    Assert-File -Path $OdooBin -Label "odoo-bin"
    Assert-File -Path $OdooConf -Label "odoo.conf. Jalankan Task config dulu atau isi -OdooConf"
    Ensure-Directory -Path $DataDir
    Ensure-Directory -Path $LogDir
}

function Normalize-Modules {
    param([string[]]$Items)
    $result = @()
    foreach ($item in $Items) {
        if (-not $item) {
            continue
        }
        $result += ($item -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    if (-not $result) {
        $result = $DefaultModules
    }
    return ($result -join ",")
}

function Invoke-Npm {
    param([string[]]$Arguments)
    $npm = Find-Npm
    if (-not $npm) {
        throw "npm tidak ditemukan. Install Node.js LTS lalu buka terminal baru."
    }
    Push-Location $ProjectRoot
    try {
        & $npm.Source @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "npm gagal dengan exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-Odoo {
    param([string[]]$Arguments)
    & $OdooPython $OdooBin @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Odoo command gagal dengan exit code $LASTEXITCODE"
    }
}

function New-UnitradeConfig {
    Ensure-Directory -Path (Split-Path -Parent $ConfigOut)
    Ensure-Directory -Path $DataDir
    Ensure-Directory -Path $LogDir

    $addonsPath = @(
        (Join-Path $OdooHome "server\odoo\addons"),
        (Join-Path $OdooHome "server\addons"),
        $ProjectRoot
    ) -join ","

    $config = @"
[options]
addons_path = $addonsPath
admin_passwd = $AdminPasswd
bin_path = $(Join-Path $OdooHome "thirdparty")
data_dir = $DataDir
db_host = $PgHost
db_port = $PgPort
db_user = $PgUser
db_password = $PgPassword
db_name = False
http_port = $Port
logfile = $(Join-Path $LogDir "odoo.log")
log_level = info
server_wide_modules = base,web
workers = 0
list_db = True
proxy_mode = False
"@

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ConfigOut, $config, $utf8NoBom)
    $script:OdooConf = $ConfigOut
    Write-Ok "Config dibuat: $ConfigOut"
}

function Show-Doctor {
    Write-Step "Cek environment UniTrade"
    Write-Host "ProjectRoot : $ProjectRoot"
    Write-Host "Database    : $Database"
    Write-Host "OdooHome    : $OdooHome"
    Write-Host "OdooPython  : $OdooPython"
    Write-Host "OdooBin     : $OdooBin"
    Write-Host "OdooConf    : $OdooConf"
    Write-Host "DataDir     : $DataDir"
    Write-Host "LogDir      : $LogDir"

    $missing = 0
    if (Test-Path -LiteralPath $OdooPython -PathType Leaf) { Write-Ok "Odoo Python ditemukan" } else { Write-Missing "Odoo Python: $OdooPython"; $missing++ }
    if (Test-Path -LiteralPath $OdooBin -PathType Leaf) { Write-Ok "odoo-bin ditemukan" } else { Write-Missing "odoo-bin: $OdooBin"; $missing++ }
    if (Test-Path -LiteralPath $OdooConf -PathType Leaf) { Write-Ok "odoo.conf ditemukan" } else { Write-Missing "odoo.conf: $OdooConf"; $missing++ }

    $npm = Find-Npm
    if ($npm) { Write-Ok "npm ditemukan: $($npm.Source)" } else { Write-Missing "npm tidak ditemukan"; $missing++ }

    if (Test-Path -LiteralPath (Join-Path $ProjectRoot "package-lock.json") -PathType Leaf) {
        Write-Ok "package-lock.json ditemukan"
    }

    if ($missing -gt 0) {
        throw "Doctor menemukan $missing item yang belum siap."
    }
}

function Install-NodeDependencies {
    Write-Step "Install dependency Node.js"
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot "package-lock.json") -PathType Leaf) {
        Invoke-Npm -Arguments @("ci")
        return
    }
    Invoke-Npm -Arguments @("install")
}

function Build-Tailwind {
    Write-Step "Build Tailwind CSS"
    Invoke-Npm -Arguments @("run", "build")
}

function Watch-Tailwind {
    Write-Step "Watch Tailwind CSS"
    Invoke-Npm -Arguments @("run", "watch")
}

function Invoke-ModuleCommand {
    param([ValidateSet("install", "upgrade")][string]$Mode)
    Assert-OdooRuntime
    $moduleList = Normalize-Modules -Items $Modules
    $flag = if ($Mode -eq "install") { "-i" } else { "-u" }
    $logFile = Join-Path $LogDir "$Mode`_unitrade_modules.log"

    Write-Step "$Mode modul Odoo: $moduleList"
    Invoke-Odoo -Arguments @(
        "-c", $OdooConf,
        "-d", $Database,
        $flag, $moduleList,
        "--stop-after-init",
        "--no-http",
        "--data-dir=$DataDir",
        "--logfile=$logFile"
    )
    Write-Ok "Log: $logFile"
}

function Run-OdooServer {
    Assert-OdooRuntime
    $logFile = Join-Path $LogDir "odoo_run_$Port.log"
    $args = @(
        "-c", $OdooConf,
        "-d", $Database,
        "--http-port=$Port",
        "--data-dir=$DataDir",
        "--logfile=$logFile"
    )
    if (-not $NoDev) {
        $args += "--dev=xml,qweb,assets"
    }

    Write-Step "Jalankan Odoo di http://127.0.0.1:$Port"
    Invoke-Odoo -Arguments $args
}

function Restore-EnvValue {
    param([string]$Name, [string]$Value)
    if ($null -eq $Value) {
        Remove-Item -Path "Env:\$Name" -ErrorAction SilentlyContinue
        return
    }
    Set-Item -Path "Env:\$Name" -Value $Value
}

function Invoke-Seed {
    param([bool]$Execute)
    Assert-OdooRuntime
    $seedScript = Join-Path $ProjectRoot "scripts\seed_unitrade_test_data.py"
    Assert-File -Path $seedScript -Label "Seed script"

    $logName = if ($Execute) { "seed_unitrade_test_data_execute.log" } else { "seed_unitrade_test_data_dry_run.log" }
    $logFile = Join-Path $LogDir $logName
    $oldReset = $env:UNITRADE_RESET_TEST_DATA
    $oldTransactions = $env:UNITRADE_SEED_SAMPLE_TRANSACTIONS
    $oldPassword = $env:UNITRADE_SEED_PASSWORD

    try {
        if ($Execute) {
            $env:UNITRADE_RESET_TEST_DATA = "YES"
        }
        else {
            Remove-Item -Path "Env:\UNITRADE_RESET_TEST_DATA" -ErrorAction SilentlyContinue
        }

        if ($SeedTransactions) {
            $env:UNITRADE_SEED_SAMPLE_TRANSACTIONS = "YES"
        }
        else {
            $env:UNITRADE_SEED_SAMPLE_TRANSACTIONS = "NO"
        }

        if ($SeedPassword) {
            $env:UNITRADE_SEED_PASSWORD = $SeedPassword
        }

        $mode = if ($Execute) { "execute reset + seed" } else { "dry-run seed" }
        Write-Step $mode
        Get-Content -LiteralPath $seedScript | & $OdooPython $OdooBin shell -c $OdooConf -d $Database --no-http "--data-dir=$DataDir" "--logfile=$logFile"
        if ($LASTEXITCODE -ne 0) {
            throw "Seed gagal dengan exit code $LASTEXITCODE"
        }
        Write-Ok "Log: $logFile"
    }
    finally {
        Restore-EnvValue -Name "UNITRADE_RESET_TEST_DATA" -Value $oldReset
        Restore-EnvValue -Name "UNITRADE_SEED_SAMPLE_TRANSACTIONS" -Value $oldTransactions
        Restore-EnvValue -Name "UNITRADE_SEED_PASSWORD" -Value $oldPassword
    }
}

$OdooHome = Use-Default -Value $OdooHome -EnvName "UNITRADE_ODOO_HOME" -Default "C:\Program Files\Odoo 17.0.20260217"
$OdooPython = Use-Default -Value $OdooPython -EnvName "UNITRADE_ODOO_PYTHON" -Default (Join-Path $OdooHome "python\python.exe")
$OdooBin = Use-Default -Value $OdooBin -EnvName "UNITRADE_ODOO_BIN" -Default (Join-Path $OdooHome "server\odoo-bin")
$ConfigOut = Get-FullPath (Use-Default -Value $ConfigOut -EnvName "UNITRADE_CONFIG_OUT" -Default "tmp\odoo.unitrade.conf")

if (-not $OdooConf) {
    $envConf = [Environment]::GetEnvironmentVariable("UNITRADE_ODOO_CONF")
    if ($envConf) {
        $OdooConf = $envConf
    }
    elseif (Test-Path -LiteralPath $ConfigOut -PathType Leaf) {
        $OdooConf = $ConfigOut
    }
    else {
        $OdooConf = Join-Path $OdooHome "server\odoo.conf"
    }
}

$Database = Use-Default -Value $Database -EnvName "UNITRADE_DB_NAME" -Default "unitrade_db"
$PgHost = Use-Default -Value $PgHost -EnvName "UNITRADE_DB_HOST" -Default "localhost"
$PgUser = Use-Default -Value $PgUser -EnvName "UNITRADE_DB_USER" -Default "openpg"
$PgPassword = Use-Default -Value $PgPassword -EnvName "UNITRADE_DB_PASSWORD" -Default "admin"
$AdminPasswd = Use-Default -Value $AdminPasswd -EnvName "UNITRADE_ADMIN_PASSWD" -Default "admin123"
$DataDir = Get-FullPath (Use-Default -Value $DataDir -EnvName "UNITRADE_DATA_DIR" -Default "odoo_data")
$LogDir = Get-FullPath (Use-Default -Value $LogDir -EnvName "UNITRADE_LOG_DIR" -Default "logs")

if (-not $Modules) {
    $moduleEnv = [Environment]::GetEnvironmentVariable("UNITRADE_MODULES")
    if ($moduleEnv) {
        $Modules = @($moduleEnv)
    }
    else {
        $Modules = $DefaultModules
    }
}

switch ($Task) {
    "doctor" { Show-Doctor }
    "config" { New-UnitradeConfig }
    "install-node" { Install-NodeDependencies }
    "build" { Build-Tailwind }
    "watch" { Watch-Tailwind }
    "install" { Invoke-ModuleCommand -Mode "install" }
    "upgrade" { Invoke-ModuleCommand -Mode "upgrade" }
    "run" { Run-OdooServer }
    "seed-dry" { Invoke-Seed -Execute:$false }
    "seed" { Invoke-Seed -Execute:$true }
    "setup" {
        New-UnitradeConfig
        Install-NodeDependencies
        Build-Tailwind
        Invoke-ModuleCommand -Mode "install"
    }
}
