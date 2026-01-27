param(
  [string]$Path = "dbt\seeds\config_irs_limits.csv"
)

if (-not (Test-Path -Path $Path)) {
  Write-Error "File not found: $Path"
  exit 1
}

# Normalize to UTF-8 (no BOM) with LF line endings.
$content = Get-Content -Path $Path -Raw
$content = $content -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
  $Path,
  $content,
  (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Normalized seed file: $Path"
