# Где искать изменения по спринтам

Если в локальном проекте «не видно» доработок, проверь по карте ниже.

## Карта изменений

- `/web` и `/health` команды: `app/bot/handlers.py`
- Вынесенная логика режимов: `app/core/quiz_engine_service.py`
- Интеграция сервиса режимов: `app/core/game_manager.py`
- Retry helper: `app/utils/retry.py`
- Ops-логирование: `app/utils/ops_log.py`
- Retry + логирование в LLM: `app/providers/llm_provider.py`
- Retry + логирование в web search: `app/providers/web_search_provider.py`
- DB healthcheck: `app/storage/db.py`
- CI: `.github/workflows/ci.yml`
- Тесты: `tests/test_quiz_engine_service.py`, `tests/test_retry.py`
- Проверка рассинхрона локалки и GitHub: `scripts/check_sync.ps1` и `docs/local_vs_github_sync.md`

## Быстрые команды проверки (PowerShell)

```powershell
git log --oneline -n 15
git show --name-only --oneline HEAD
pwsh -File .\scripts\check_sync.ps1
```

## Если хочешь просто открыть нужные файлы

```powershell
code .\app\bot\handlers.py
code .\app\core\quiz_engine_service.py
code .\app\utils\retry.py
code .\app\utils\ops_log.py
code .\app\providers\llm_provider.py
code .\app\providers\web_search_provider.py
code .\app\storage\db.py
code .\.github\workflows\ci.yml
```

