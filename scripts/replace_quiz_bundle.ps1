$ErrorActionPreference = 'Stop'

$fileName = 'quiz_30000_sticky_v1_bundle.zip'
$sourceCandidates = @(
    "C:\Users\$env:USERNAME\Documents\налоговая\$fileName",
    "C:\Users\$env:USERNAME\Documents\$fileName",
    "C:\Users\$env:USERNAME\Downloads\$fileName"
)

$sourcePath = $null
foreach ($candidate in $sourceCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $sourcePath = $candidate
        break
    }
}

if (-not $sourcePath) {
    $homeDir = "C:\Users\$env:USERNAME"
    $found = Get-ChildItem -LiteralPath $homeDir -Recurse -File -Filter $fileName -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) {
        $sourcePath = $found.FullName
    }
}

if (-not $sourcePath) {
    throw "Не найден исходный архив '$fileName'. Положи его в Documents/Downloads или укажи путь в скрипте."
}

$repoRoot = (Get-Location).Path
$targetName = $fileName
$targetPath = Join-Path $repoRoot $targetName

$oldBundles = @(
    'quiz_bank_100k_ru_bundle.zip'
)

Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Копирование не удалось: $targetPath"
}

if (-not (Get-Item -LiteralPath $targetPath).Length) {
    throw "Скопированный архив пустой: $targetPath"
}

Write-Host "Найден исходный архив: $sourcePath"
Write-Host "Скопирован новый архив: $targetPath"

foreach ($oldName in $oldBundles) {
    $oldPath = Join-Path $repoRoot $oldName
    if (Test-Path -LiteralPath $oldPath) {
        git rm -- "$oldName" | Out-Null
        Write-Host "Удалён старый архив из git: $oldName"
    }
}

git add -- "$targetName"

$stagedLine = git status --short -- "$targetName"
if (-not $stagedLine) {
    throw "Файл не попал в staged: $targetName"
}

Write-Host ''
Write-Host 'Готово. Дальше проверь:'
Write-Host '  git status'
Write-Host ''
Write-Host 'Потом коммит и push:'
Write-Host '  git commit -m "Replace quiz bundle 100k -> 30k sticky v1"'
Write-Host '  git pull --rebase origin main'
Write-Host '  git push origin main'
Write-Host ''
Write-Host 'Импорт в базу (та же логика):'
Write-Host '  python -m scripts.import_quiz_bundle --zip-path ".\quiz_30000_sticky_v1_bundle.zip" --db-path ".\quiz.db"'
