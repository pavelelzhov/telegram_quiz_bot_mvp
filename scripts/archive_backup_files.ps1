param(
    [string]$SourceRoot = "app",
    [string]$ArchiveRoot = ".backup_archive"
)

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targetBase = Join-Path $ArchiveRoot $timestamp

Write-Host "Архив backup-файлов в: $targetBase"

$files = Get-ChildItem -Path $SourceRoot -Recurse -File | Where-Object { $_.Name -like "*.bak_*" }
if (-not $files) {
    Write-Host "backup-файлы не найдены"
    exit 0
}

foreach ($file in $files) {
    $relative = $file.FullName.Substring((Resolve-Path ".").Path.Length).TrimStart('\\', '/')
    $target = Join-Path $targetBase $relative
    $targetDir = Split-Path $target -Parent
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Move-Item -Path $file.FullName -Destination $target -Force
}

Write-Host "Готово. Перемещено файлов: $($files.Count)"

