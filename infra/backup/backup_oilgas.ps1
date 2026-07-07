# Weekly full dump of the Supabase `oilgas` warehouse -> local + OneDrive offsite.
#
#   Manual:   powershell -NoProfile -ExecutionPolicy Bypass -File infra\backup\backup_oilgas.ps1
#   Schedule (weekly, Sunday 03:00 - after the nightly ETL settles):
#     $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#          -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\MichaelMast\Projects\engineering_db\infra\backup\backup_oilgas.ps1"
#     $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
#     $p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
#     Register-ScheduledTask -TaskName "OilgasBackup" -Action $a -Trigger $t -Principal $p
#
# SCOPE: dumps the SOURCE schemas only (raw_novi, raw_enverus, raw_novi_intel,
# ref, meta) - the same set the migration dump used. `curated.*` is excluded on
# purpose: it is 100% rebuildable from raw+ref via sql/*.sql + refresh_all(), so
# dumping ~11 GB of matviews weekly over the WAN is wasted bytes. Restore path:
# docs/supabase_migration_runbook.md.
#
# CONNECTION: tries the DIRECT connection first (db.<ref>.supabase.co:5432,
# user postgres) because it honors `statement_timeout=0` via PGOPTIONS - the
# pooler STRIPS PGOPTIONS, so its 2-min statement_timeout kills the 73M-row
# raw_novi_intel.forecast COPY. If the direct host is unreachable (it is
# IPv6-only and has been flaky), it falls back to the pooler from .env and
# WARNS that the big-table COPY may time out there.
[CmdletBinding()]
param(
    [int]$KeepWeeks = 4,
    [string]$EnvFile   = "C:\Users\MichaelMast\Projects\engineering_db\.env",
    [string]$DumpsDir  = "C:\Users\MichaelMast\db_dumps",
    [string]$OffsiteDir = $(if ($env:BACKUP_OFFSITE_DIR_OILGAS) { $env:BACKUP_OFFSITE_DIR_OILGAS } else { "C:\Users\MichaelMast\Blue Ox Resources\Engineering - General\Backup\oilgas" }),
    # pg_dump from the PG17 install (Supabase is PG 17.x; match the server major).
    [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin"
)

$ErrorActionPreference = "Stop"

# --- Load .env (KEY=VALUE lines) ---
if (-not (Test-Path $EnvFile)) { Write-Error "No .env at $EnvFile"; exit 1 }
$envMap = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $k, $v = $line -split "=", 2
        $envMap[$k.Trim()] = $v.Trim()
    }
}
$PoolHost = $envMap["DB_HOST"]; $PoolPort = $envMap["DB_PORT"]
$DbName   = $envMap["DB_NAME"]; $PoolUser = $envMap["DB_USER"]
$DbPass   = $envMap["DB_PASSWORD"]
if (-not $PoolHost -or -not $DbPass) { Write-Error ".env missing DB_HOST/DB_PASSWORD"; exit 1 }

# --- Derive the DIRECT connection from the pooler user (postgres.<ref>) ---
# Pooler user is `postgres.<ref>`; direct host is `db.<ref>.supabase.co`, user `postgres`.
$Direct = $null
if ($PoolUser -match '^postgres\.([a-z0-9]+)$') {
    $ref = $Matches[1]
    $Direct = @{ DbHost = "db.$ref.supabase.co"; Port = "5432"; User = "postgres" }
}

$Stamp    = Get-Date -Format "yyyyMMdd-HHmmss"
$FileName = "oilgas_$Stamp.dump"
$OutFile  = Join-Path $DumpsDir $FileName
if (-not (Test-Path $DumpsDir)) { New-Item -ItemType Directory -Path $DumpsDir -Force | Out-Null }

$env:PGPASSWORD = $DbPass  # in-process only; never on the command line

$DumpArgs = @(
    "--no-owner", "--no-privileges", "--no-tablespaces", "-Fc",
    "--schema=raw_novi", "--schema=raw_enverus", "--schema=raw_novi_intel",
    "--schema=ref", "--schema=meta",
    "-d", $DbName, "-f", $OutFile
)

function Invoke-Dump($DbHost, $Port, $User, $Label, $AllowTimeoutOverride) {
    Write-Host "pg_dump via $Label -> ${DbHost}:$Port as $User"
    if ($AllowTimeoutOverride) { $env:PGOPTIONS = "-c statement_timeout=0" } else { Remove-Item Env:\PGOPTIONS -ErrorAction SilentlyContinue }
    & "$PgBin\pg_dump.exe" @DumpArgs "-h" $DbHost "-p" $Port "-U" $User
    return $LASTEXITCODE
}

# Direct first (statement_timeout=0 honored); pooler fallback (may time out on big COPY).
$rc = 1
if ($Direct) {
    $rc = Invoke-Dump $Direct.DbHost $Direct.Port $Direct.User "DIRECT" $true
    if ($rc -ne 0) { Write-Warning "Direct dump failed (rc=$rc) - is IPv6 up? Falling back to the pooler." }
}
if ($rc -ne 0) {
    Write-Warning "POOLER fallback: PGOPTIONS is stripped here, so statement_timeout stays 2min - the 73M-row COPY may fail."
    $rc = Invoke-Dump $PoolHost $PoolPort $PoolUser "POOLER" $false
}
if ($rc -ne 0) { Write-Error "pg_dump failed on both direct and pooler (rc=$rc)"; exit 1 }

# --- Verify the archive is readable (TOC lists) before trusting it ---
& "$PgBin\pg_restore.exe" -l $OutFile > $null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $OutFile) -or (Get-Item $OutFile).Length -lt 1MB) {
    Write-Error "Dump missing or unreadable by pg_restore -l: $OutFile"; exit 1
}
$size_gb = (Get-Item $OutFile).Length / 1GB
Write-Host ("Wrote + verified {0:N2} GB -> {1}" -f $size_gb, $OutFile)

# --- Offsite mirror (OneDrive) ---
if ($OffsiteDir -ne "") {
    if (-not (Test-Path $OffsiteDir)) { New-Item -ItemType Directory -Path $OffsiteDir -Force | Out-Null }
    $OffsiteFile = Join-Path $OffsiteDir $FileName
    Write-Host "Mirroring offsite -> $OffsiteFile"
    Copy-Item -Path $OutFile -Destination $OffsiteFile -Force
    if (-not (Test-Path $OffsiteFile) -or (Get-Item $OffsiteFile).Length -ne (Get-Item $OutFile).Length) {
        Write-Error "Offsite mirror failed or size mismatch: $OffsiteFile"; exit 1
    }
    Write-Host "Offsite mirror OK"
}

# --- Prune (both local and offsite) older than KeepWeeks ---
$Cutoff = (Get-Date).AddDays(-7 * $KeepWeeks)
foreach ($dir in @($DumpsDir, $OffsiteDir)) {
    if ($dir -and (Test-Path $dir)) {
        Get-ChildItem $dir -Filter "oilgas_*.dump" |
            Where-Object { $_.LastWriteTime -lt $Cutoff } |
            ForEach-Object { Write-Host "Pruning $($_.FullName)"; Remove-Item $_.FullName }
    }
}

# --- Dead-man ping (optional) ---
$Hc = if ($env:BACKUP_HEALTHCHECKS_URL) { $env:BACKUP_HEALTHCHECKS_URL } else { $envMap["BACKUP_HEALTHCHECKS_URL"] }
if ($Hc) { try { Invoke-RestMethod -Uri $Hc -TimeoutSec 10 | Out-Null } catch { Write-Warning "healthcheck ping failed: $_" } }

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:\PGOPTIONS  -ErrorAction SilentlyContinue
Write-Host "oilgas backup complete."
