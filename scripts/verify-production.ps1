param(
  [switch]$MigrateJson,
  [switch]$BenchmarkMillionAcre,
  [double]$MinimumAreaMu = 1000000,
  [double]$MaximumP95Ms = 500,
  [int]$BenchmarkIterations = 20,
  [int]$ImportWriteRows = 1000,
  [int]$ImportWriteIterations = 3,
  [double]$MinimumImportWriteRowsPerSecond = 500,
  [int]$RelationLinkRows = 1000,
  [int]$RelationLinkIterations = 3,
  [double]$MinimumRelationLinkRowsPerSecond = 1000,
  [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required. Install Docker Desktop or run this script on the deployment server."
  }

  & docker compose config | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "docker compose config failed" }

  & docker compose up --build -d
  if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

  $appPort = if ($env:SMART_BAMBOO_APP_PORT) { $env:SMART_BAMBOO_APP_PORT } else { "8010" }
  $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
  do {
    Start-Sleep -Seconds 2
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$appPort/api/health" -TimeoutSec 5
    } catch {
      $health = $null
    }
  } until ($health -or (Get-Date) -ge $deadline)
  if (-not $health) { throw "Application health endpoint did not become available." }
  if ($health.deployment.readiness.status -ne "ready") {
    $issues = @($health.deployment.readiness.blockingIssues) + @($health.deployment.readiness.warnings)
    $issueText = ($issues | ForEach-Object { $_.message }) -join "; "
    throw "Production readiness is not ready: $issueText"
  }
  $importTuning = $health.deployment.smartBamboo.importTuning
  if (
    -not $importTuning -or
    $importTuning.strategy -ne "incremental-batch" -or
    [int]$importTuning.mysqlWriteBatchSize -lt 1 -or
    [int]$importTuning.identityLookupBatchSize -lt 1 -or
    $importTuning.singleTransaction -ne $true -or
    $importTuning.mysqlReportTargets -ne "normalized-relational" -or
    $importTuning.databaseReportCache -ne "disabled" -or
    $importTuning.mysqlTargetRead -ne "paginated-relational" -or
    $importTuning.mysqlRollback -ne "targeted-relational" -or
    $importTuning.mysqlSceneLink -ne "insert-select-relational" -or
    $importTuning.mysqlSceneCoverage -ne "aggregate-bounded-samples" -or
    $importTuning.mysqlLayerLink -ne "copy-relational" -or
    $importTuning.mysqlLayerTargets -ne "paginated-summary" -or
    $importTuning.mysqlLayerCrud -ne "targeted-scalar" -or
    $importTuning.mysqlBusinessTargets -ne "paginated-summary" -or
    $importTuning.mysqlBusinessCrud -ne "targeted-scalar" -or
    $importTuning.mysqlBusinessDashboard -ne "aggregate-bounded-rows" -or
    $importTuning.mysqlRightTargets -ne "paginated-summary" -or
    $importTuning.mysqlRightCrud -ne "targeted-scalar"
  ) {
    throw "MySQL import tuning is not production-ready. Expected incremental batching, normalized targets, bounded scene coverage, and relational scene/layer linking."
  }

  & docker compose exec -T app python server/scripts/verify_mysql_production.py --initialize
  if ($LASTEXITCODE -ne 0) { throw "MySQL production verification failed" }

  & docker compose exec -T app python server/scripts/backfill_mysql_business_attributes.py
  if ($LASTEXITCODE -ne 0) { throw "MySQL business attribute backfill failed" }

  & docker compose exec -T app python server/scripts/migrate_json_to_mysql.py --dry-run
  if ($LASTEXITCODE -ne 0) { throw "JSON migration inventory failed" }

  if ($MigrateJson) {
    & docker compose exec -T app python server/scripts/migrate_json_to_mysql.py
    if ($LASTEXITCODE -ne 0) { throw "JSON to MySQL migration failed" }
  }

  if ($BenchmarkMillionAcre) {
    & docker compose exec -T app python server/scripts/benchmark_mysql_forest_blocks.py `
      --min-area-mu $MinimumAreaMu `
      --max-p95-ms $MaximumP95Ms `
      --iterations $BenchmarkIterations `
      --import-write-rows $ImportWriteRows `
      --import-write-iterations $ImportWriteIterations `
      --min-import-write-rows-per-second $MinimumImportWriteRowsPerSecond `
      --relation-link-rows $RelationLinkRows `
      --relation-link-iterations $RelationLinkIterations `
      --min-relation-link-rows-per-second $MinimumRelationLinkRowsPerSecond
    if ($LASTEXITCODE -ne 0) { throw "Million-acre MySQL benchmark acceptance failed" }
  }

  $health | ConvertTo-Json -Depth 8
} finally {
  Pop-Location
}
