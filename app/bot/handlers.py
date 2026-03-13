from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot.keyboards import BUTTON_TEXTS, BUTTON_TO_CATEGORY, main_menu_kb
from app.config import settings
from app.core.game_manager import GameManager
from app.core.health_service import HealthService
from app.core.last_game_service import LastGameService
from app.providers.web_search_provider import WebSearchProvider
from app.storage.db import Database
from app.utils.ops_log import log_operation


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


def build_router(game_manager: GameManager, db: Database) -> Router:
    router = Router()
    bot_username_cache: dict[str, str | None] = {'value': None}
    web_search = WebSearchProvider()
    health_service = HealthService()
    last_game_service = LastGameService(game_manager.quiz_engine)

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

    async def _ensure_admin_for_setting(message: Message) -> bool:
        if await _is_admin(message):
            return True
        await message.answer('⚠️ Менять настройки чата может только администратор.', reply_markup=main_menu_kb())
        return False

    async def _ensure_control_allowed(message: Message) -> bool:
        cfg = game_manager.get_chat_settings(message.chat.id)
        if not cfg.admin_only_control:
            return True
        if await _is_admin(message):
            return True
        await message.answer('⚠️ В этом чате запускать и останавливать игру может только администратор.', reply_markup=main_menu_kb())
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

        triggers = ['бот', 'квиз бот', 'квиз-бот', 'ведущий']
        return any(token in text for token in triggers)

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
        if message.chat.type == 'private':
            await message.answer('Этот бот лучше использовать в групповом чате.', reply_markup=main_menu_kb())
            return

        if not message.from_user:
            await message.answer('Не удалось определить пользователя.', reply_markup=main_menu_kb())
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
            await message.answer(text, reply_markup=main_menu_kb())

    async def _reply_if_error(message: Message, text: str) -> None:
        if text != 'OK':
            await message.answer(text, reply_markup=main_menu_kb())

    async def _send_top(message: Message) -> None:
        rows = await db.get_top_players(message.chat.id, limit=10)
        if not rows:
            await message.answer('Пока статистики по этому чату нет.', reply_markup=main_menu_kb())
            return

        lines = ['📈 Топ игроков чата:']
        for idx, (username, total_points, wins, games_played) in enumerate(rows, start=1):
            lines.append(f'{idx}. @{username} — очки: {total_points}, победы: {wins}, игр: {games_played}')
        await message.answer('\n'.join(lines), reply_markup=main_menu_kb())

    async def _send_season(message: Message) -> None:
        text = await game_manager.get_season_product_text(message.chat.id)
        await message.answer(text, reply_markup=main_menu_kb())

    async def _send_weekly(message: Message) -> None:
        rows = await db.get_weekly_top_players(message.chat.id, limit=10)
        if not rows:
            await message.answer('За эту неделю пока нет результатов.', reply_markup=main_menu_kb())
            return

        lines = ['🗓 Недельный топ игроков:']
        for idx, (username, total_points, wins, games_played) in enumerate(rows, start=1):
            lines.append(f'{idx}. @{username} — очки: {total_points}, победы: {wins}, игр: {games_played}')
        await message.answer('\n'.join(lines), reply_markup=main_menu_kb())

    async def _send_profile(message: Message) -> None:
        if not message.from_user:
            return
        username = message.from_user.username or message.from_user.full_name.replace(' ', '_')
        text = await game_manager.get_player_product_text(message.chat.id, message.from_user.id, username)
        await message.answer(text, reply_markup=main_menu_kb())

    async def _send_last_game(message: Message) -> None:
        data = await db.get_last_game_result(message.chat.id)
        text = last_game_service.format_last_game_text(data)
        await message.answer(text, reply_markup=main_menu_kb())

    async def _set_team_and_reply(message: Message, team: str) -> None:
        if not message.from_user:
            return
        username = message.from_user.username or message.from_user.full_name.replace(' ', '_')
        text = game_manager.set_team_choice(message.chat.id, message.from_user.id, username, team)
        await message.answer(text, reply_markup=main_menu_kb())

    async def _send_web_search(message: Message, raw_text: str) -> None:
        if not message.from_user:
            return
        username = message.from_user.username or message.from_user.full_name.replace(' ', '_')
        result = await web_search.search_and_summarize(
            chat_title=message.chat.title or 'Чат',
            username=username,
            raw_text=raw_text,
        )
        await message.answer(result, reply_markup=main_menu_kb(), disable_web_page_preview=True)

    async def _send_score(message: Message) -> None:
        await message.answer(game_manager.get_score_text(message.chat.id), reply_markup=main_menu_kb())

    async def _send_status(message: Message) -> None:
        await message.answer(game_manager.get_status_text(message.chat.id), reply_markup=main_menu_kb())

    async def _send_settings(message: Message) -> None:
        await message.answer(game_manager.get_settings_text(message.chat.id), reply_markup=main_menu_kb())

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
        await message.answer(f'{label}: {"вкл" if enabled else "выкл"}', reply_markup=main_menu_kb())

    @router.message(Command('start'))
    async def cmd_start(message: Message) -> None:
        await message.answer(_help_text(message.chat.id), reply_markup=main_menu_kb())

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
                if parsed in {5, 7, 10, 12, 15}:
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
        await message.answer(game_manager.get_team_lobby_text(message.chat.id), reply_markup=main_menu_kb())

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
            await message.answer(
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
            await message.answer(
                'Неверный профиль. Используй: casual, standard или hardcore.',
                reply_markup=main_menu_kb(),
            )
            return

        await message.answer(
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
        started = time.perf_counter()
        if not await _is_admin(message):
            await message.answer('⚠️ Команда /health доступна только администратору.', reply_markup=main_menu_kb())
            return
        llm_configured = bool(settings.openai_api_key and settings.openai_model and settings.openai_base_url)
        llm_ms = (time.perf_counter() - llm_started) * 1000

        web_started = time.perf_counter()
        web_search_enabled = bool(settings.yandex_search_api_key and settings.yandex_search_folder_id)
        web_ms = (time.perf_counter() - web_started) * 1000

        db_status = 'OK' if db_ok else 'FAIL'
        llm_status = 'OK' if llm_configured else 'DEGRADED'
        web_status = 'OK' if web_search_enabled else 'DEGRADED'
        overall = 'OK'
        if not db_ok:
            overall = 'FAIL'
        elif not llm_configured or not web_search_enabled:
            overall = 'DEGRADED'

        log_operation(
            logger,
            operation='health_check',
            chat_id=message.chat.id,
            result=overall.lower(),
            duration_ms=(time.perf_counter() - started) * 1000,
            extra={
                'db_status': db_status,
                'db_latency_ms': f'{db_ms:.1f}',
                'llm_status': llm_status,
                'llm_latency_ms': f'{llm_ms:.1f}',
                'web_status': web_status,
                'web_latency_ms': f'{web_ms:.1f}',
            },
        )

        snapshot = await health_service.check(
            chat_id=message.chat.id,
            db=db,
            llm_configured=llm_configured,
            web_search_enabled=web_search_enabled,
            logger=logger,
        )
        text = health_service.format_text(snapshot)
        await message.answer(text, reply_markup=main_menu_kb())

    @router.message(F.text == '🎯 Классика 10')
    async def btn_classic(message: Message) -> None:
        await _start_quiz(message, 10, 'classic')

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
        await message.answer(game_manager.get_team_lobby_text(message.chat.id), reply_markup=main_menu_kb())

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
        await message.answer(
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
        await message.answer(f'⏱ Новый таймер: {value} сек.', reply_markup=main_menu_kb())

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

    @router.message(F.text)
    async def answer_listener(message: Message) -> None:
        if not message.from_user or not message.text:
            return

        if (message.text.startswith('/') and not message.text.startswith('/web')) or message.text in BUTTON_TEXTS:
            return

        username = message.from_user.username or message.from_user.full_name.replace(' ', '_')
        addressed = await _is_addressed_to_bot(message)

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
            addressed=addressed,
        )

    return router
