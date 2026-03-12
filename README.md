# Telegram Quiz Bot MVP

Рабочий MVP Telegram-бота-ведущего для группового квиза.

## Что умеет
- запускает игру в групповом чате
- задает вопросы через LLM API
- если LLM/API временно не отвечает, берет вопрос из резервного набора
- принимает ответы обычными сообщениями
- выдает подсказку
- ведет счет
- сохраняет статистику чата в SQLite

## Команды
- `/quiz_start`
- `/quiz_start 5`
- `/quiz_start 10`
- `/quiz_start 15`
- `/quiz_stop`
- `/quiz_status`
- `/hint`
- `/skip`
- `/score`
- `/stats`

## Требования
- Python 3.10+
- Telegram bot token
- OpenAI-compatible API key

## Установка
1. Распаковать архив.
2. Открыть папку проекта.
3. Создать `.env` из `.env.example`.
4. Заполнить `BOT_TOKEN` и `OPENAI_API_KEY`.
5. Создать venv:
   - `python -m venv .venv`
6. Активировать venv:
   - PowerShell: `./.venv/Scripts/Activate.ps1`
7. Установить зависимости:
   - `python -m pip install -r requirements.txt`
8. Запустить:
   - `python -m app.main`

## Важно для групп
В BotFather у бота нужно отключить **Group Privacy**,
иначе бот не увидит обычные ответы игроков в групповом чате.

## Структура
- `app/main.py` — точка входа
- `app/bot/handlers.py` — команды и обработчики
- `app/core/game_manager.py` — логика игры
- `app/providers/llm_provider.py` — генерация вопросов
- `app/storage/db.py` — SQLite статистика
- `app/utils/text.py` — нормализация ответов

## Примечания
- По умолчанию используется модель `gpt-4o-mini`, потому что она обычно доступнее для API-проектов.
- Если хочешь использовать другой OpenAI-compatible endpoint, поменяй `OPENAI_BASE_URL` и `OPENAI_MODEL` в `.env`.
