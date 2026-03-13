# Как быстро проверить синхронизацию локального кода и GitHub

Если кажется, что локально и на GitHub разный код, сделай так.

## 1) Проверка в 1 команду (PowerShell)

```powershell
pwsh -File .\scripts\check_sync.ps1
```

Скрипт покажет:
- какие коммиты есть на GitHub, но нет локально;
- какие коммиты есть локально, но нет на GitHub;
- общее расхождение веток.

## 2) Если нужен полный «чистый» sync с GitHub

⚠️ Команды ниже удалят локальные незакоммиченные изменения.

```powershell
git checkout main
git fetch origin
git reset --hard origin/main
git clean -fd
```

## 3) Проверка, что запускается нужный файл handlers.py

```powershell
python -c "import app.bot.handlers as h; print(h.__file__)"
```

## 4) Быстрая проверка синтаксиса после sync

```powershell
python -m py_compile .\app\bot\handlers.py
```

