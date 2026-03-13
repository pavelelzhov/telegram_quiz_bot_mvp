param(
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/6] Проверяю, что git доступен..."
git --version | Out-Null

Write-Host "[2/6] Обновляю ссылки на удалённый репозиторий ($Remote)..."
git fetch $Remote --prune

Write-Host "[3/6] Локальная ветка и статус:"
git branch -vv
git status --short

Write-Host "[4/6] Проверяю расхождения с $Remote/$Branch..."
$aheadBehind = git rev-list --left-right --count "$Remote/$Branch...HEAD"
Write-Host "ahead/behind (удалённая/локальная): $aheadBehind"

Write-Host "[5/6] Коммиты, которых нет у локальной ветки:"
git log --oneline "HEAD..$Remote/$Branch" -n 30

Write-Host "[6/6] Коммиты, которых нет у удалённой ветки:"
git log --oneline "$Remote/$Branch..HEAD" -n 30

Write-Host "Готово. Если есть расхождение, для жёсткой синхронизации на main:"
Write-Host "  git checkout main"
Write-Host "  git fetch origin"
Write-Host "  git reset --hard origin/main"
Write-Host "  git clean -fd"

