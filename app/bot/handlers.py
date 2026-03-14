from __future__ import annotations

import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramNetworkError

from app.bot.keyboards import (
    BUTTON_TEXTS,
    BUTTON_TO_CATEGORY,
    control_menu_kb,
    game_menu_kb,
    main_menu_kb,
    profile_menu_kb,
    topics_menu_kb,
)
from app.config import settings
from app.core.game_manager import GameManager
from app.core.health_service import HealthService
from app.core.last_game_service import LastGameService
from app.core.leaderboard_service import LeaderboardService
from app.providers.web_search_provider import WebSearchProvider
from app.storage.db import Database
from app.utils.ops_log import log_operation
from app.utils.retry import retry_async

logger = logging.getLogger(__name__)


def build_router(game_manager: GameManager, db: Database) -> Router:
    router = Router()
    bot_username_cache: dict[str, str | None] = {'value': None}
    web_search = WebSearchProvider()
    health_service = HealthService()
    last_game_service = LastGameService(game_manager.quiz_engine)
    leaderboard_service = LeaderboardService()

    async def _get_bot_username(message: Message) -> str:
        if bot_username_cache['value']:
            return bot_username_cache['value'] or ''
        me = await message.bot.get_me()
        bot_username_cache['value'] = (me.username or '').lower()
        return bot_username_cache['value'] or ''

    async def _is_admin(message: Message) -> bool:
        if not message.from_user:
            return False
        try:
            member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {'administrator', 'creator'}
        except Exception:
            return False

    def _should_retry_telegram(exc: Exception) -> bool:
        return isinstance(exc, TelegramNetworkError)

    async def _safe_answer(message: Message, text: str, **kwargs: object) -> None:
        try:
            await retry_async(
                lambda: message.answer(text, **kwargs),
                retries=2,
                base_delay_sec=0.8,
                should_retry=_should_retry_telegram,
            )
        except Exception as exc:
            logger.warning('message.answer failed after retries chat_id=%s error=%s', message.chat.id, type(exc).__name__)

    async def _ensure_admin_for_setting(message: Message) -> bool:
        if await _is_admin(message):
            return True
        await _safe_answer(message, '⚠️ Менять настройки чата может только администратор.', reply_markup=main_menu_kb())
        return False

    async def _ensure_control_allowed(message: Message) -> bool:
        cfg = game_manager.get_chat_settings(message.chat.id)
        if not cfg.admin_only_control:
            return True
        if await _is_admin(message):
            return True
        await _safe_answer(message, '⚠️ В этом чате запускать и останавливать игру может только администратор.', reply_markup=main_menu_kb())
        return False

    async def _is_addressed_to_bot(message: Message) -> bool:
        if not message.text:
            return False

        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == message.bot.id:
                return True

        text = message.text.lower()
        bot_username = await _get_bot_username(message)

        if bot_username and f'@{bot_username}' in text:
            return True

        aliases = [item.strip().lower() for item in settings.alisa_name_aliases.split(',') if item.strip()]
        canonical_name = settings.alisa_name.strip().lower()
        if canonical_name and canonical_name not in aliases:
            aliases.append(canonical_name)
        for alias in aliases:
            if re.search(rf'(?<!\\w){re.escape(alias)}(?!\\w)', text, flags=re.IGNORECASE):
                return True
        return False

    async def _addressing_signals(message: Message) -> tuple[bool, bool, bool]:
        is_reply_to_alisa = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == message.bot.id
        )
        has_bot_mention = False
        if message.text:
            bot_username = await _get_bot_username(message)
            has_bot_mention = bool(bot_username and f'@{bot_username}' in message.text.lower())
        has_name = await _is_addressed_to_bot(message)
        return is_reply_to_alisa, has_bot_mention, has_name

    def _help_text(chat_id: int) -> str:
        return (
            'Я бот-ведущий для квиза.\n\n'
            f'Текущая тема: {game_manager.get_preferred_category(chat_id)}\n'
            f'{game_manager.get_settings_text(chat_id)}\n\n'
            'Теперь у квиза есть продуктовая версия:\n'
            '— режимы матчей\n'
            '— сезонные очки\n'
            '— титулы\n'
            '— ачивки\n'
            '— профиль игрока\n'
            '— сезонный рейтинг\n\n'
            '/season — сезонный топ\n'
            '/weekly — недельный топ\n'
            '/last_game — последняя завершённая игра\n'
            '/me — твой профиль\n'
            '/team_alpha /team_beta — выбор команды 2v2\n'
            '/team_lobby — состав команд 2v2\n'
            '/team_start — старт командной игры'
        )

    async def _start_quiz(message: Message, question_limit: int, quiz_mode: str) -> None:
        private_allowed_modes = {'solo_adaptive', 'daily'}
        if message.chat.type == 'private' and quiz_mode not in private_allowed_modes:
            await _safe_answer(message, 'Этот бот лучше использовать в групповом чате.', reply_markup=main_menu_kb())
            return

        if not message.from_user:
            await _safe_answer(message, 'Не удалось определить пользователя.', reply_markup=main_menu_kb())
            return

        if not await _ensure_control_allowed(message):
            return

        text = await game_manager.start_game(
            bot=message.bot,
            chat_id=message.chat.id,
            started_by_user_id=message.from_user.id,
            question_limit=question_limit,
            quiz_mode=quiz_mode,
        )
        if text != 'OK':
            await _safe_answer(message, text, reply_markup=main_menu_kb())

    async def _reply_if_error(message: Message, text: str) -> None:
        if text != 'OK':
            await _safe_answer(message, text, reply_markup=main_menu_kb())

    def _sender_username(message: Message) -> str | None:
        if not message.from_user:
            return None
        return message.from_user.username or message.from_user.full_name.replace(' ', '_')

    async def _send_top(message: Message) -> None:
        rows = await db.get_top_players(message.chat.id, limit=10)
        await _safe_answer(message, leaderboard_service.format_chat_top(rows), reply_markup=main_menu_kb())

    async def _send_season(message: Message) -> None:
        text = await game_manager.get_season_product_text(message.chat.id)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    async def _send_weekly(message: Message) -> None:
        rows = await db.get_weekly_top_players(message.chat.id, limit=10)
        await _safe_answer(message, leaderboard_service.format_weekly_top(rows), reply_markup=main_menu_kb())

    async def _send_profile(message: Message) -> None:
        username = _sender_username(message)
        if not message.from_user or not username:
            return
        text = await game_manager.get_player_product_text(message.chat.id, message.from_user.id, username)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    async def _send_last_game(message: Message) -> None:
        data = await db.get_last_game_result(message.chat.id)
        text = last_game_service.format_last_game_text(data)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    async def _set_team_and_reply(message: Message, team: str) -> None:
        username = _sender_username(message)
        if not message.from_user or not username:
            return
        text = game_manager.set_team_choice(message.chat.id, message.from_user.id, username, team)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    async def _send_web_search(message: Message, raw_text: str) -> None:
        username = _sender_username(message)
        if not username:
            return
        result = await web_search.search_and_summarize(
            chat_title=message.chat.title or 'Чат',
            username=username,
            raw_text=raw_text,
        )
        await _safe_answer(message, result, reply_markup=main_menu_kb(), disable_web_page_preview=True)

    async def _send_score(message: Message) -> None:
        await _safe_answer(message, game_manager.get_score_text(message.chat.id), reply_markup=main_menu_kb())

    async def _send_status(message: Message) -> None:
        await _safe_answer(message, game_manager.get_status_text(message.chat.id), reply_markup=main_menu_kb())

    async def _send_settings(message: Message) -> None:
        await _safe_answer(message, game_manager.get_settings_text(message.chat.id), reply_markup=main_menu_kb())

    async def _send_hint(message: Message) -> None:
        text = await game_manager.give_hint(message.bot, message.chat.id)
        await _reply_if_error(message, text)

    async def _send_skip(message: Message) -> None:
        text = await game_manager.skip_question(message.bot, message.chat.id)
        await _reply_if_error(message, text)

    async def _stop_quiz(message: Message, reason: str) -> None:
        if not await _ensure_control_allowed(message):
            return
        text = await game_manager.stop_game(message.bot, message.chat.id, reason)
        await _reply_if_error(message, text)

    async def _toggle_setting(message: Message, toggler, label: str) -> None:
        if not await _ensure_admin_for_setting(message):
            return
        enabled = toggler(message.chat.id)
        await _safe_answer(message, f'{label}: {"вкл" if enabled else "выкл"}', reply_markup=main_menu_kb())

    @router.message(Command('start'))
    async def cmd_start(message: Message) -> None:
        await _safe_answer(message, _help_text(message.chat.id), reply_markup=main_menu_kb())

    @router.message(Command('season'))
    async def cmd_season(message: Message) -> None:
        await _send_season(message)

    @router.message(Command('weekly'))
    async def cmd_weekly(message: Message) -> None:
        await _send_weekly(message)

    @router.message(Command('me'))
    async def cmd_me(message: Message) -> None:
        await _send_profile(message)

    @router.message(Command('last_game'))
    async def cmd_last_game(message: Message) -> None:
        await _send_last_game(message)

    @router.message(Command('quiz_start'))
    async def cmd_quiz_start(message: Message, command: CommandObject) -> None:
        question_limit = settings.default_question_count
        if command.args:
            try:
                parsed = int(command.args.strip())
                if parsed in {5, 7, 10, 12, 15, 25}:
                    question_limit = parsed
            except ValueError:
                pass

        await _start_quiz(message, question_limit, 'classic')

    @router.message(Command('quiz_stop'))
    async def cmd_quiz_stop(message: Message) -> None:
        await _stop_quiz(message, 'Игра остановлена командой.')

    @router.message(Command('team_alpha'))
    async def cmd_team_alpha(message: Message) -> None:
        await _set_team_and_reply(message, 'alpha')

    @router.message(Command('team_beta'))
    async def cmd_team_beta(message: Message) -> None:
        await _set_team_and_reply(message, 'beta')

    @router.message(Command('team_lobby'))
    async def cmd_team_lobby(message: Message) -> None:
        await _safe_answer(message, game_manager.get_team_lobby_text(message.chat.id), reply_markup=main_menu_kb())

    @router.message(Command('team_start'))
    async def cmd_team_start(message: Message) -> None:
        await _start_quiz(message, 10, 'team2v2')

    @router.message(Command('team_stop'))
    async def cmd_team_stop(message: Message) -> None:
        await _stop_quiz(message, 'Командная игра остановлена командой.')

    @router.message(Command('quiz_status'))
    async def cmd_quiz_status(message: Message) -> None:
        await _send_status(message)

    @router.message(Command('quiz_profile'))
    async def cmd_quiz_profile(message: Message, command: CommandObject) -> None:
        if not command.args:
            profile = game_manager.get_game_profile(message.chat.id)
            await _safe_answer(message, 
                'Профиль игры: '
                f'{game_manager.quiz_engine.game_profile_label(profile)}\n'
                'Изменить: /quiz_profile casual|standard|hardcore',
                reply_markup=main_menu_kb(),
            )
            return

        if not await _ensure_admin_for_setting(message):
            return

        profile = command.args.strip().lower()
        if not game_manager.set_game_profile(message.chat.id, profile):
            await _safe_answer(message, 
                'Неверный профиль. Используй: casual, standard или hardcore.',
                reply_markup=main_menu_kb(),
            )
            return

        await _safe_answer(message, 
            'Профиль игры обновлён: '
            f'{game_manager.quiz_engine.game_profile_label(profile)}',
            reply_markup=main_menu_kb(),
        )

    @router.message(Command('hint'))
    async def cmd_hint(message: Message) -> None:
        await _send_hint(message)

    @router.message(Command('skip'))
    async def cmd_skip(message: Message) -> None:
        await _send_skip(message)

    @router.message(Command('score'))
    async def cmd_score(message: Message) -> None:
        await _send_score(message)

    @router.message(Command('stats'))
    async def cmd_stats(message: Message) -> None:
        await _send_top(message)

    @router.message(Command('web'))
    async def cmd_web(message: Message) -> None:
        if not message.text:
            return
        await _send_web_search(message, message.text)

    @router.message(Command('settings'))
    async def cmd_settings(message: Message) -> None:
        await _send_settings(message)

    @router.message(Command('health'))
    async def cmd_health(message: Message) -> None:
        if not await _is_admin(message):
            await _safe_answer(message, '⚠️ Команда /health доступна только администратору.', reply_markup=main_menu_kb())
            return
        llm_configured = bool(settings.openai_api_key and settings.openai_model and settings.openai_base_url)
        web_search_enabled = bool(settings.yandex_search_api_key and settings.yandex_search_folder_id)

        snapshot = await health_service.check(
            chat_id=message.chat.id,
            db=db,
            llm_configured=llm_configured,
            web_search_enabled=web_search_enabled,
            logger=logger,
        )
        text = health_service.format_text(snapshot)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    @router.message(Command('buffer_status'))
    async def cmd_buffer_status(message: Message) -> None:
        cache_size = await db.get_valid_llm_questions_count()
        if cache_size < game_manager.quiz_engine.LOW_WATERMARK_CACHE_SIZE:
            asyncio.create_task(
                game_manager.quiz_engine.maybe_start_background_cache_refill(
                    chat_id=message.chat.id,
                    quiz_mode='classic',
                    preferred_category=game_manager.get_preferred_category(message.chat.id),
                )
            )
            await asyncio.sleep(0)
        text = await game_manager.quiz_engine.get_refill_status_text(message.chat.id)
        await _safe_answer(message, text, reply_markup=main_menu_kb())

    @router.message(F.text == '🎯 Классика 25')
    async def btn_classic(message: Message) -> None:
        await _start_quiz(message, 25, 'classic')

    @router.message(F.text == '🏠 Главное меню')
    async def btn_home_menu(message: Message) -> None:
        await _safe_answer(message, 'Открываю главное меню.', reply_markup=main_menu_kb())

    @router.message(F.text == '🎮 Игровое меню')
    async def btn_game_menu(message: Message) -> None:
        await _safe_answer(message, 'Игровой раздел.', reply_markup=game_menu_kb())

    @router.message(F.text == '🧩 Темы')
    async def btn_topics_menu(message: Message) -> None:
        await _safe_answer(message, 'Выбери тему вопросов.', reply_markup=topics_menu_kb())

    @router.message(F.text == '👤 Профиль и рейтинг')
    async def btn_profile_menu(message: Message) -> None:
        await _safe_answer(message, 'Профиль и рейтинг.', reply_markup=profile_menu_kb())

    @router.message(F.text == '⚙️ Управление')
    async def btn_control_menu(message: Message) -> None:
        await _safe_answer(message, 'Раздел настроек и диагностики.', reply_markup=control_menu_kb())

    @router.message(F.text == '🔥 Блиц 7')
    async def btn_blitz(message: Message) -> None:
        await _start_quiz(message, 7, 'blitz')

    @router.message(F.text == '👑 Эпик 12')
    async def btn_epic(message: Message) -> None:
        await _start_quiz(message, 12, 'epic')

    @router.message(F.text == '🏅 Сезон')
    async def btn_season(message: Message) -> None:
        await _send_season(message)

    @router.message(F.text == '🗓 Неделя')
    async def btn_weekly(message: Message) -> None:
        await _send_weekly(message)

    @router.message(F.text == '🕘 Последняя игра')
    async def btn_last_game(message: Message) -> None:
        await _send_last_game(message)

    @router.message(F.text == '🙋 Профиль')
    async def btn_profile(message: Message) -> None:
        await _send_profile(message)

    @router.message(F.text == '🟥 Team Alpha')
    async def btn_team_alpha(message: Message) -> None:
        await _set_team_and_reply(message, 'alpha')

    @router.message(F.text == '🟦 Team Beta')
    async def btn_team_beta(message: Message) -> None:
        await _set_team_and_reply(message, 'beta')

    @router.message(F.text == '🤝 Лобби 2v2')
    async def btn_team_lobby(message: Message) -> None:
        await _safe_answer(message, game_manager.get_team_lobby_text(message.chat.id), reply_markup=main_menu_kb())

    @router.message(F.text == '🚀 Старт 2v2')
    async def btn_team_start(message: Message) -> None:
        await _start_quiz(message, 10, 'team2v2')

    @router.message(F.text == '🛑 Стоп 2v2')
    async def btn_team_stop(message: Message) -> None:
        await _stop_quiz(message, 'Командная игра остановлена кнопкой.')

    @router.message(F.text.in_(list(BUTTON_TO_CATEGORY.keys())))
    async def btn_set_category(message: Message) -> None:
        category = BUTTON_TO_CATEGORY[message.text]
        game_manager.set_preferred_category(message.chat.id, category)
        topics = [] if category == 'Случайно' else [category]
        game_manager.chat_config.set_preferred_topics(message.chat.id, topics)
        await _safe_answer(message, 
            f'🎯 Тема для следующей игры: {category}',
            reply_markup=main_menu_kb(),
        )

    @router.message(F.text == '⚙️ Настройки')
    async def btn_settings(message: Message) -> None:
        await _send_settings(message)

    @router.message(F.text == '⏱ Таймер')
    async def btn_timeout(message: Message) -> None:
        if not await _ensure_admin_for_setting(message):
            return
        value = game_manager.cycle_timeout(message.chat.id)
        await _safe_answer(message, f'⏱ Новый таймер: {value} сек.', reply_markup=main_menu_kb())

    @router.message(F.text == '🖼 Картинки')
    async def btn_images(message: Message) -> None:
        await _toggle_setting(message, game_manager.toggle_image_rounds, '🖼 Картинки')

    @router.message(F.text == '🎧 Музыка-раунды')
    async def btn_music(message: Message) -> None:
        await _toggle_setting(message, game_manager.toggle_music_rounds, '🎧 Музыка-раунды')

    @router.message(F.text == '👮 Админ-режим')
    async def btn_admin_mode(message: Message) -> None:
        await _toggle_setting(message, game_manager.toggle_admin_only_control, '👮 Только админ может старт/стоп')

    @router.message(F.text == '🤖 Host-режим')
    async def btn_host_mode(message: Message) -> None:
        await _toggle_setting(message, game_manager.toggle_host_mode, '🤖 Host-режим')

    @router.message(F.text == '🩺 Health')
    async def btn_health(message: Message) -> None:
        await cmd_health(message)

    @router.message(F.text == '📦 Буфер LLM')
    async def btn_buffer_status(message: Message) -> None:
        await cmd_buffer_status(message)

    @router.message(F.text == '💡 Подсказка')
    async def btn_hint(message: Message) -> None:
        await _send_hint(message)

    @router.message(F.text == '⏭ Пропустить')
    async def btn_skip(message: Message) -> None:
        await _send_skip(message)

    @router.message(F.text == '🏆 Очки')
    async def btn_score(message: Message) -> None:
        await _send_score(message)

    @router.message(F.text == '📊 Статус')
    async def btn_status(message: Message) -> None:
        await _send_status(message)

    @router.message(F.text == '👥 Топ')
    async def btn_stats(message: Message) -> None:
        await _send_top(message)

    @router.message(F.text == '⛔ Стоп')
    async def btn_stop(message: Message) -> None:
        await _stop_quiz(message, 'Игра остановлена кнопкой.')


    @router.message(Command('solo_start'))
    async def cmd_solo_start(message: Message) -> None:
        if message.chat.type != 'private':
            await _safe_answer(message, 'Эта команда предназначена для личного режима.')
            return
        await _start_quiz(message, 7, 'solo_adaptive')

    @router.message(Command('daily'))
    async def cmd_daily(message: Message) -> None:
        await _start_quiz(message, 5, 'daily')

    @router.message(Command('profile'))
    async def cmd_profile(message: Message) -> None:
        await _send_profile(message)

    @router.message(Command('my_level'))
    async def cmd_my_level(message: Message) -> None:
        if not message.from_user:
            return
        snapshot = await db.get_player_skill_profile(message.from_user.id)
        await _safe_answer(message, 
            f'🧠 Твой уровень: {snapshot.current_band}\n'
            f'Accuracy: {snapshot.recent_accuracy:.0%}\n'
            f'Текущая серия: {snapshot.current_streak}\n'
            f'Лучшая серия: {snapshot.best_streak}',
            reply_markup=main_menu_kb(),
        )

    @router.message(Command('quiz_mode'))
    async def cmd_quiz_mode(message: Message) -> None:
        await _safe_answer(message, 'Режимы: classic, blitz, epic, team2v2, solo_adaptive, daily', reply_markup=main_menu_kb())

    @router.message(Command('quiz_topics'))
    async def cmd_quiz_topics(message: Message, command: CommandObject) -> None:
        topics = []
        if command.args:
            topics = [item.strip() for item in command.args.split(',')]
        game_manager.chat_config.set_preferred_topics(message.chat.id, topics)
        await _safe_answer(message, f'Темы обновлены: {", ".join(topics) if topics else "без фокуса"}', reply_markup=main_menu_kb())

    @router.message(Command('quiz_level_policy'))
    async def cmd_quiz_level_policy(message: Message) -> None:
        cfg = game_manager.get_chat_settings(message.chat.id)
        await _safe_answer(message, f'Adaptive policy: {"on" if cfg.adaptive_mode_enabled else "off"}', reply_markup=main_menu_kb())

    @router.message(Command('leaderboard'))
    async def cmd_leaderboard(message: Message) -> None:
        await _send_top(message)

    @router.message(Command('quiz_settings'))
    async def cmd_quiz_settings(message: Message) -> None:
        await _send_settings(message)

    @router.message(Command('quiz_timezone'))
    async def cmd_quiz_timezone(message: Message, command: CommandObject) -> None:
        if not command.args:
            await _safe_answer(message, 'Использование: /quiz_timezone UTC или /quiz_timezone Europe/Berlin', reply_markup=main_menu_kb())
            return
        requested_timezone = command.args.strip()
        if game_manager.daily_challenge.is_timezone_supported(requested_timezone):
            game_manager.chat_config.set_timezone(message.chat.id, requested_timezone)
            await _safe_answer(message, f'Таймзона обновлена: {requested_timezone}', reply_markup=main_menu_kb())
            return

        game_manager.chat_config.set_timezone(message.chat.id, 'UTC')
        await _safe_answer(message, 
            'Не удалось применить эту таймзону в текущем окружении. '
            'Поставил UTC как универсальный fallback.',
            reply_markup=main_menu_kb(),
        )

    @router.message(Command('quiz_repeat_rules'))
    async def cmd_quiz_repeat_rules(message: Message, command: CommandObject) -> None:
        days = 5
        raw_args = (command.args or '').strip()
        if not raw_args and message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) > 1:
                raw_args = parts[1].strip()
        if raw_args:
            try:
                days = int(raw_args)
            except ValueError:
                days = 5
        game_manager.chat_config.set_repeat_rules(message.chat.id, days, True)
        await _safe_answer(message, f'Окно анти-повторов: {days} дней', reply_markup=main_menu_kb())

    @router.message(F.text)
    async def answer_listener(message: Message) -> None:
        if not message.from_user or not message.text:
            return

        if (message.text.startswith('/') and not message.text.startswith('/web')) or message.text in BUTTON_TEXTS:
            return

        username = _sender_username(message)
        if not username:
            return
        is_reply_to_alisa, has_bot_mention, has_name = await _addressing_signals(message)
        addressed = is_reply_to_alisa or has_bot_mention or has_name

        if web_search.looks_like_web_request(message.text, addressed=addressed):
            await _send_web_search(message, message.text)
            return

        answered = await game_manager.handle_answer(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            username=username,
            text=message.text,
        )
        if answered:
            return

        await game_manager.handle_chat_participation(
            bot=message.bot,
            chat_id=message.chat.id,
            chat_title=message.chat.title or 'Чат',
            user_id=message.from_user.id,
            username=username,
            text=message.text,
            is_reply_to_alisa=is_reply_to_alisa,
            has_bot_mention=has_bot_mention,
        )

    return router
