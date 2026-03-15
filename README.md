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
- поддерживает persona-режим «Алиса» для живого общения в чате

## Persona-режим «Алиса» (Sprint 1)
- Реактивный ответ только при адресации:
  - по имени «Алиса» (или алиасы из конфига)
  - reply на сообщение бота
  - mention `@bot_username`
- Есть короткое follow-up окно после явного обращения (чтобы фразы типа «ты как?» не терялись сразу после «Алиса, ...»).
- Есть инициативный режим: Алиса может сама вступить в беседу при достаточной активности чата и низком напряжении.
- Generic-триггеры «бот / квиз-бот / ведущий» в persona-режиме отключены.
- Добавлены reason-codes для решений (ответ/молчание/подавление).
- Введён базовый anti-AI-валидатор:
  - фильтр стоп-фраз ассистентского стиля
  - clamp по длине и количеству предложений
  - quiz-safe rewrite в рисковых местах
- Расширена память отношений (rapport/hostility/banter и краткие summary).

## Команды
- `/quiz_start`
- `/quiz_start 5`
- `/quiz_start 10`
- `/quiz_start 15`
- `/quiz_stop`
- `/quiz_status`
- `/team_alpha` / `/team_beta` (выбор команды)
- `/team_lobby`
- `/team_start`
- `/team_stop`
- `/last_game`
- `/hint`
- `/skip`
- `/score`
- `/stats`
- `/web <запрос>`
- `/health` (только админ)

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

## Новые переменные окружения для Алисы
Смотри `.env.example` — там полный список.

Ключевые:
- `ALISA_ENABLED` — включить persona-режим.
- `ALISA_NAME` / `ALISA_NAME_ALIASES` — имя и алиасы для адресации.
- `ALISA_ALLOW_REPLY_TO_MESSAGE` / `ALISA_ALLOW_MENTION` — разрешённые каналы адресации.
- `ALISA_DISABLE_GENERIC_BOT_TRIGGERS` — отключить старые generic-триггеры.
- `ALISA_REPLY_MAX_SENTENCES` / `ALISA_REPLY_MAX_CHARS` — жёсткие лимиты ответа.
- `ALISA_AI_PHRASE_FILTER` / `ALISA_SELF_CHECK_ENABLED` — anti-AI фильтрация.
- `ALISA_COOLDOWN_ADDRESSED_SECONDS` — кулдаун реактивных ответов.
- `ALISA_HISTORY_WINDOW_SIZE` — окно истории для контекста.

## Замена архива вопросов (100k -> 30k) через VSCode

1) Открой терминал PowerShell в корне репозитория.

2) Запусти скрипт замены:

```powershell
./scripts/replace_quiz_bundle.ps1
```

Что он делает:
- копирует `C:\Users\elzho\Documents\налоговая\quiz_30000_sticky_v1_bundle.zip` в корень репозитория;
- удаляет старый архив `quiz_bank_100k_ru_bundle.zip` (если есть);
- добавляет изменения в git (`git add` / `git rm`);
- если файл лежит не в `Documents\налоговая`, скрипт сам пробует найти его в `Documents`, `Downloads`
  и через поиск по `C:\Users\<твой_пользователь>`.

3) Импорт в базу остаётся по той же логике:

```powershell
python -m scripts.import_quiz_bundle --zip-path ".\quiz_30000_sticky_v1_bundle.zip" --db-path ".\quiz.db"
