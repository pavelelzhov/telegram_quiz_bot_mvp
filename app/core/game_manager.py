from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from aiogram import Bot
from aiogram.types import FSInputFile

from app.agent.memory_store import MemoryStore
from app.config import settings
from app.core.adaptive_difficulty_service import AdaptiveDifficultyService
from app.core.chat_agent_service import ChatAgentService
from app.core.invite_service import InviteService
from app.core.models import ChatSettings, GameState, PlayerScore, QuizQuestion
from app.core.quiz_engine_service import QuizEngineService
from app.providers.llm_provider import CATEGORY_RANDOM, LLMQuestionProvider
from app.quiz.product_store import ProductStore
from app.storage.db import Database
from app.utils.ops_log import log_operation
from app.utils.text import answer_match_details

logger = logging.getLogger(__name__)


class GameManager:
    def __init__(self, db: Database, question_provider: LLMQuestionProvider) -> None:
        self.db = db
        self.question_provider = question_provider
        self.memory_store = MemoryStore()
        self.chat_agent_service = ChatAgentService(self.memory_store)
        self.invite_service = InviteService()
        self.adaptive_difficulty = AdaptiveDifficultyService()
        self.product_store = ProductStore()
        self.quiz_engine = QuizEngineService()
        self.games: Dict[int, GameState] = {}
        self.question_tasks: Dict[int, asyncio.Task] = {}
        self.preferred_categories: Dict[int, str] = {}
        self.chat_settings: Dict[int, ChatSettings] = {}
        self.recent_question_keys: Dict[int, Deque[str]] = defaultdict(
            lambda: deque(maxlen=settings.recent_questions_limit)
        )
        self.start_locks: Dict[int, asyncio.Lock] = {}
        self.chat_histories: Dict[int, Deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=20))
        self.chat_last_reply_ts: Dict[int, float] = defaultdict(lambda: 0.0)
        self.team_lobbies: Dict[int, dict[str, dict[int, str]]] = defaultdict(
            lambda: {'alpha': {}, 'beta': {}}
        )

    def _get_start_lock(self, chat_id: int) -> asyncio.Lock:
        lock = self.start_locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self.start_locks[chat_id] = lock
        return lock

    def get_game(self, chat_id: int) -> Optional[GameState]:
        return self.games.get(chat_id)

    def get_chat_settings(self, chat_id: int) -> ChatSettings:
        if chat_id not in self.chat_settings:
            self.chat_settings[chat_id] = ChatSettings(question_timeout_sec=settings.question_timeout_sec)
        return self.chat_settings[chat_id]

    def get_settings_text(self, chat_id: int) -> str:
        cfg = self.get_chat_settings(chat_id)
        return (
            '⚙️ Настройки чата\n'
            f'Профиль игры: {self.quiz_engine.game_profile_label(cfg.game_profile)}\n'
            f'Тема по умолчанию: {self.get_preferred_category(chat_id)}\n'
            f'Таймер на вопрос: {cfg.question_timeout_sec} сек.\n'
            f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
            f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
            f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
            f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}\n'
            f'Только админ может старт/стоп: {"вкл" if cfg.admin_only_control else "выкл"}'
        )

    def set_game_profile(self, chat_id: int, profile: str) -> bool:
        if profile not in {'casual', 'standard', 'hardcore'}:
            return False
        cfg = self.get_chat_settings(chat_id)
        cfg.game_profile = profile
        return True

    def get_game_profile(self, chat_id: int) -> str:
        return self.get_chat_settings(chat_id).game_profile

    async def get_player_product_text(self, chat_id: int, user_id: int, username: str) -> str:
        return await self.product_store.get_player_text(chat_id, user_id, username)

    async def get_season_product_text(self, chat_id: int) -> str:
        return await self.product_store.get_season_text(chat_id)

    def cycle_timeout(self, chat_id: int) -> int:
        cfg = self.get_chat_settings(chat_id)
        values = [20, 30, 45]
        try:
            idx = values.index(cfg.question_timeout_sec)
        except ValueError:
            idx = 1
        cfg.question_timeout_sec = values[(idx + 1) % len(values)]
        return cfg.question_timeout_sec

    def toggle_image_rounds(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.image_rounds_enabled = not cfg.image_rounds_enabled
        return cfg.image_rounds_enabled

    def toggle_music_rounds(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.music_rounds_enabled = not cfg.music_rounds_enabled
        return cfg.music_rounds_enabled

    def toggle_admin_only_control(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.admin_only_control = not cfg.admin_only_control
        return cfg.admin_only_control

    def toggle_host_mode(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.host_mode_enabled = not cfg.host_mode_enabled
        return cfg.host_mode_enabled

    def set_preferred_category(self, chat_id: int, category: str) -> None:
        self.preferred_categories[chat_id] = category

    def get_preferred_category(self, chat_id: int) -> str:
        return self.preferred_categories.get(chat_id, CATEGORY_RANDOM)

    def set_team_choice(self, chat_id: int, user_id: int, username: str, team: str) -> str:
        team_name = team.strip().lower()
        if team_name not in {'alpha', 'beta'}:
            return 'Неверная команда. Используй: /team_alpha или /team_beta.'

        lobby = self.team_lobbies[chat_id]
        current_team = self._team_of_user_in_lobby(chat_id, user_id)
        if current_team == team_name:
            return f'Ты уже в команде {self._team_label(team_name)}.'

        if current_team:
            lobby[current_team].pop(user_id, None)

        if len(lobby[team_name]) >= 2:
            return f'Команда {self._team_label(team_name)} уже заполнена (2/2).'

        lobby[team_name][user_id] = username
        return f'@{username}, ты в команде {self._team_label(team_name)}.\n{self.get_team_lobby_text(chat_id)}'

    def get_team_lobby_text(self, chat_id: int) -> str:
        lobby = self.team_lobbies[chat_id]
        alpha = ', '.join(f'@{name}' for name in lobby['alpha'].values()) or '—'
        beta = ', '.join(f'@{name}' for name in lobby['beta'].values()) or '—'
        return (
            '🤝 Лобби 2v2\n'
            f'{self._team_label("alpha")}: {len(lobby["alpha"])}/2 — {alpha}\n'
            f'{self._team_label("beta")}: {len(lobby["beta"])}/2 — {beta}\n'
            'Выбор: /team_alpha или /team_beta\n'
            'Старт: /team_start'
        )

    def _team_of_user_in_lobby(self, chat_id: int, user_id: int) -> str | None:
        lobby = self.team_lobbies[chat_id]
        for team_name in ('alpha', 'beta'):
            if user_id in lobby[team_name]:
                return team_name
        return None

    def _team_label(self, team_name: str) -> str:
        if team_name == 'alpha':
            return '🟥 Альфа'
        return '🟦 Бета'

    def _team_score_lines(self, state: GameState) -> list[str]:
        totals = {'alpha': 0, 'beta': 0}
        for user_id, score in state.scores.items():
            team = state.team_assignments.get(user_id)
            if team in totals:
                totals[team] += score.points

        lines = ['🤝 Командный счёт:']
        for team_name in ('alpha', 'beta'):
            lines.append(f'{self._team_label(team_name)} — {totals[team_name]}')

        lines.append('')
        lines.append('Вклад игроков:')
        for team_name in ('alpha', 'beta'):
            lines.append(f'{self._team_label(team_name)}:')
            members = [
                player
                for player in state.scores.values()
                if state.team_assignments.get(player.user_id) == team_name
            ]
            members.sort(key=lambda item: (-item.points, item.username.lower()))
            if not members:
                lines.append('• пока без очков')
                continue
            for player in members:
                lines.append(f'• @{player.username} — {player.points}')

        return lines

    async def start_game(
        self,
        bot: Bot,
        chat_id: int,
        started_by_user_id: int,
        question_limit: int,
        quiz_mode: str = 'classic',
    ) -> str:
        started = time.perf_counter()
        lock = self._get_start_lock(chat_id)

        async with lock:
            if chat_id in self.games and self.games[chat_id].is_active:
                log_operation(
                    logger,
                    operation='game_start',
                    chat_id=chat_id,
                    result='already_active',
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
                return 'Игра уже идет в этом чате. Сначала закончи текущую — этот квиз не любит бигамию 😏'

            self._clear_pending_invite(chat_id)

            preferred_category = self.get_preferred_category(chat_id)
            cfg = self.get_chat_settings(chat_id)
            team_assignments: dict[int, str] = {}

            if quiz_mode == 'team2v2':
                lobby = self.team_lobbies[chat_id]
                if len(lobby['alpha']) != 2 or len(lobby['beta']) != 2:
                    return f'Для 2v2 нужны команды 2 на 2.\n{self.get_team_lobby_text(chat_id)}'

                for user_id in lobby['alpha']:
                    team_assignments[user_id] = 'alpha'
                for user_id in lobby['beta']:
                    team_assignments[user_id] = 'beta'

            state = GameState(
                chat_id=chat_id,
                started_by_user_id=started_by_user_id,
                question_limit=question_limit,
                preferred_category=preferred_category,
                quiz_mode=quiz_mode,
                team_assignments=team_assignments,
            )
            self.games[chat_id] = state

            mode_label = self._mode_label(quiz_mode)

            await bot.send_message(
                chat_id,
                (
                    f'🎤 {mode_label} стартовал!\n\n'
                    f'Всего вопросов: {question_limit}\n'
                    f'Режим тем: {preferred_category}\n'
                    f'Профиль игры: {self.quiz_engine.game_profile_label(cfg.game_profile)}\n'
                    f'Время на вопрос: {cfg.question_timeout_sec} сек. (база)\n'
                    f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
                    f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n\n'
                    'Есть сезонные очки, титулы и ачивки. Теперь это уже не просто квиз, а маленькая лига 😏\n'
                    'Подсказка: /hint\n'
                    'Пропуск: /skip\n'
                    'Очки: /score\n'
                    'Профиль: /me\n'
                    'Сезон: /season'
                ),
            )

        await self._ask_next_question(bot, chat_id)
        log_operation(
            logger,
            operation='game_start',
            chat_id=chat_id,
            result='ok',
            duration_ms=(time.perf_counter() - started) * 1000,
            extra={'question_limit': question_limit, 'quiz_mode': quiz_mode},
        )
        return 'OK'

    def _mode_label(self, quiz_mode: str) -> str:
        return self.quiz_engine.mode_label(quiz_mode)

    def _timeout_for_mode(self, state: GameState, cfg: ChatSettings) -> int:
        return self.quiz_engine.timeout_for_mode(state, cfg)

    async def stop_game(self, bot: Bot, chat_id: int, reason: str = 'Игра остановлена.') -> str:
        started = time.perf_counter()
        state = self.games.get(chat_id)
        if not state or not state.is_active:
            log_operation(
                logger,
                operation='game_stop',
                chat_id=chat_id,
                result='no_active_game',
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            return 'В этом чате нет активной игры.'

        state.is_active = False
        self._cancel_question_task(chat_id)

        await bot.send_message(chat_id, f'⛔ {reason}')
        await self._finalize_game(bot, chat_id)
        log_operation(
            logger,
            operation='game_stop',
            chat_id=chat_id,
            result='ok',
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        return 'OK'

    async def handle_answer(self, bot: Bot, chat_id: int, user_id: int, username: str, text: str) -> bool:
        state = self.games.get(chat_id)
        if not state or not state.is_active or not state.current_question:
            return False
        if state.quiz_mode == 'team2v2' and user_id not in state.team_assignments:
            await bot.send_message(chat_id, f'@{username}, выбери команду: /team_alpha или /team_beta.')
            return False
        if state.current_question_answered:
            return False

        verdict = answer_match_details(text, state.current_question.answer, state.current_question.aliases)

        if verdict == 'wrong':
            self.adaptive_difficulty.note_wrong(chat_id)
            if user_id not in state.wrong_reply_user_ids and len(state.wrong_reply_user_ids) < 3:
                state.wrong_reply_user_ids.add(user_id)
                await bot.send_message(chat_id, self._wrong_answer_text(username, state.current_question))
            return False

        if verdict == 'close':
            self.adaptive_difficulty.note_close(chat_id)
            if user_id not in state.near_miss_user_ids:
                state.near_miss_user_ids.add(user_id)
                await bot.send_message(chat_id, self._near_miss_text(username, state.current_question))
            return False

        state.current_question_answered = True
        self.adaptive_difficulty.note_correct(chat_id)
        score = state.scores.setdefault(user_id, PlayerScore(user_id=user_id, username=username))
        score.username = username
        score.points += state.current_question.point_value
        self.memory_store.note_quiz_event(chat_id, user_id, username, correct=True)

        if state.last_correct_user_id == user_id:
            state.correct_streak_count += 1
        else:
            state.last_correct_user_id = user_id
            state.correct_streak_count = 1

        await self.product_store.note_correct(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            points=state.current_question.point_value,
            streak_count=state.correct_streak_count,
        )

        leader_line = self._leader_line(state)
        streak_line = ''
        if state.correct_streak_count >= 2:
            streak_line = f'\n🔥 Серия @{username}: {state.correct_streak_count} подряд!'
        points_line = f'\n💠 За этот вопрос: +{state.current_question.point_value} SP'
        if state.current_question.point_value == 1:
            points_line = '\n💠 За этот вопрос: +1 SP'

        self._cancel_question_task(chat_id)

        await bot.send_message(
            chat_id,
            (
                f'✅ Правильно! @{username} забирает ответ.\n'
                f'Ответ: {state.current_question.answer}\n'
                f'Факт: {state.current_question.explanation}'
                f'{points_line}'
                f'{streak_line}'
                f'{leader_line}'
            ),
        )
        await self._ask_next_question(bot, chat_id)
        return True

    async def handle_chat_participation(
        self,
        bot: Bot,
        chat_id: int,
        chat_title: str,
        user_id: int,
        username: str,
        text: str,
        addressed: bool,
    ) -> bool:
        cfg = self.get_chat_settings(chat_id)
        if not cfg.chat_mode_enabled:
            return False

        self._remember_chat_message(chat_id, 'user', username, text)
        self._remember_activity(chat_id, user_id, username, text)
        self.memory_store.note_message(chat_id, user_id, username, text)

        if await self._handle_pending_invite_vote(bot, chat_id, user_id, text):
            return True

        state = self.games.get(chat_id)
        quiz_active = bool(state and state.is_active)
        current_question_text = state.current_question.question if quiz_active and state and state.current_question else None

        if cfg.host_mode_enabled and not quiz_active:
            if await self._maybe_send_host_invite(bot, chat_id, user_id):
                return True

        if quiz_active and not addressed:
            return False

        now = time.time()
        if addressed:
            cooldown = 8.0
        elif cfg.host_mode_enabled:
            cooldown = 35.0
        else:
            return False

        if now - self.chat_last_reply_ts[chat_id] < cooldown:
            return False

        if not addressed:
            if self._recent_unique_user_count(chat_id, 180) < 2:
                return False
            if self._recent_message_count(chat_id, 180) < 5:
                return False
            if len(text.strip()) < 10:
                return False
            if random.random() > 0.18:
                return False

        reply = await self.chat_agent_service.generate_reply(
            chat_id=chat_id,
            chat_title=chat_title,
            user_id=user_id,
            username=username,
            text=text,
            history=list(self.chat_histories[chat_id]),
            quiz_active=quiz_active,
            current_question_text=current_question_text,
            addressed=addressed,
        )
        if not reply:
            return False

        self.chat_last_reply_ts[chat_id] = now
        self._remember_chat_message(chat_id, 'assistant', 'quiz_bot', reply)
        await bot.send_message(chat_id, reply)
        return True

    async def give_hint(self, bot: Bot, chat_id: int) -> str:
        state = self.games.get(chat_id)
        if not state or not state.is_active or not state.current_question:
            return 'Сейчас нет активного вопроса.'

        if state.hints_used_for_current_question >= settings.max_hints_per_question:
            return 'Лимит подсказок для этого вопроса уже исчерпан.'

        state.hints_used_for_current_question += 1
        await bot.send_message(chat_id, f'💡 Подсказка: {state.current_question.hint}')
        return 'OK'

    async def skip_question(self, bot: Bot, chat_id: int) -> str:
        state = self.games.get(chat_id)
        if not state or not state.is_active or not state.current_question:
            return 'Нет активного вопроса для пропуска.'

        self._cancel_question_task(chat_id)
        state.last_correct_user_id = None
        state.correct_streak_count = 0

        await bot.send_message(
            chat_id,
            (
                '⏭ Вопрос пропущен.\n'
                f'Правильный ответ: {state.current_question.answer}\n'
                f'Факт: {state.current_question.explanation}'
            ),
        )
        await self._ask_next_question(bot, chat_id)
        return 'OK'

    def get_score_text(self, chat_id: int) -> str:
        state = self.games.get(chat_id)
        if not state or not state.is_active:
            return 'Сейчас нет активной игры.'

        if not state.scores:
            return 'Пока очков нет.'

        ranking = sorted(state.scores.values(), key=lambda item: (-item.points, item.username.lower()))
        lines = [f'🏆 Текущие очки ({self._mode_label(state.quiz_mode)}):']
        for idx, player in enumerate(ranking, start=1):
            lines.append(f'{idx}. @{player.username} — {player.points}')
        if state.quiz_mode == 'team2v2':
            lines.extend([''] + self._team_score_lines(state))
        return '\n'.join(lines)

    def get_status_text(self, chat_id: int) -> str:
        cfg = self.get_chat_settings(chat_id)
        state = self.games.get(chat_id)
        if not state or not state.is_active:
            return (
                'Сейчас нет активной игры.\n'
                f'Профиль игры: {self.quiz_engine.game_profile_label(cfg.game_profile)}\n'
                f'Тема для следующей игры: {self.get_preferred_category(chat_id)}\n'
                f'Таймер: {cfg.question_timeout_sec} сек.\n'
                f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
                f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
                f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
                f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}\n'
                f'Только админ может старт/стоп: {"вкл" if cfg.admin_only_control else "выкл"}'
            )

        text = (
            '📊 Статус игры\n'
            f'Режим: {self._mode_label(state.quiz_mode)}\n'
            f'Профиль игры: {self.quiz_engine.game_profile_label(cfg.game_profile)}\n'
            f'Вопросов выдано: {state.asked_count}/{state.question_limit}\n'
            f'Тема: {state.preferred_category}\n'
            f'Игроков с очками: {len(state.scores)}\n'
            f'Таймер: {self._timeout_for_mode(state, cfg)} сек.\n'
            f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
            f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
            f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
            f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}'
        )
        if state.quiz_mode == 'team2v2':
            text += '\n\n' + '\n'.join(self._team_score_lines(state))
        return text

    def _leader_line(self, state: GameState) -> str:
        if not state.scores:
            return ''
        ranking = sorted(state.scores.values(), key=lambda item: (-item.points, item.username.lower()))
        leader = ranking[0]
        return f'\n🏁 Лидер сейчас: @{leader.username} — {leader.points}'

    def _determine_stage(self, state: GameState, question_number: int) -> str:
        return self.quiz_engine.determine_stage(state, question_number)

    def _apply_mode_profile(self, question: QuizQuestion, state: GameState, stage: str) -> None:
        self.quiz_engine.apply_mode_profile(question, state, stage)

    async def _ask_next_question(self, bot: Bot, chat_id: int) -> None:
        state = self.games.get(chat_id)
        if not state or not state.is_active:
            return

        if state.asked_count >= state.question_limit:
            await self._finalize_game(bot, chat_id)
            return

        cfg = self.get_chat_settings(chat_id)
        used_keys = set(state.used_question_keys)
        used_keys.update(self.recent_question_keys.get(chat_id, []))

        next_number = state.asked_count + 1
        stage = self._determine_stage(state, next_number)
        target_difficulty = self.adaptive_difficulty.target_difficulty(chat_id, state.asked_count)

        try:
            question = await self.question_provider.generate_question(
                chat_id=chat_id,
                used_keys=used_keys,
                preferred_category=state.preferred_category,
                allow_image_rounds=cfg.image_rounds_enabled,
                allow_music_rounds=cfg.music_rounds_enabled,
                stage=stage,
                preferred_difficulty=target_difficulty,
            )
        except Exception as exc:
            logger.exception('Failed to obtain question: %s', exc)
            await bot.send_message(chat_id, 'Не удалось получить вопрос. Игра завершена.')
            await self._finalize_game(bot, chat_id)
            return

        self._apply_mode_profile(question, state, stage)

        state.current_question = question
        state.current_question_answered = False
        state.current_question_started_ts = time.time()
        state.hints_used_for_current_question = 0
        state.near_miss_user_ids = set()
        state.wrong_reply_user_ids = set()
        state.used_question_keys.add(question.key)
        self.recent_question_keys[chat_id].append(question.key)
        state.asked_count += 1

        if question.source == 'llm':
            source_label = 'ИИ'
        elif question.source == 'image_pool':
            source_label = 'картинка'
        elif question.source == 'music_pool':
            source_label = 'музыка'
        else:
            source_label = 'резерв'

        multiplier_line = ''
        if question.point_value > 1:
            multiplier_line = f'\n💠 Цена вопроса: x{question.point_value}'

        header = (
            f'❓ Вопрос {state.asked_count}/{state.question_limit}\n'
            f'{question.round_label}\n'
            f'Категория: {question.category}\n'
            f'Тема: {question.topic}\n'
            f'Сложность: {question.difficulty}\n'
            f'Источник: {source_label}'
            f'{multiplier_line}\n\n'
            f'{question.question}'
        )

        if question.question_type == 'image' and question.photo_url:
            try:
                await bot.send_photo(chat_id, photo=question.photo_url, caption=header)
            except Exception as exc:
                logger.exception('Failed to send image round: %s', exc)
                await bot.send_message(chat_id, header + '\n\n(Картинку отправить не удалось, но вопрос остаётся активным.)')
        elif question.question_type == 'audio' and question.audio_path:
            try:
                audio = FSInputFile(question.audio_path)
                await bot.send_audio(
                    chat_id,
                    audio=audio,
                    caption=header,
                    title=question.audio_title or 'Музыкальный раунд',
                    performer=question.audio_performer or 'Quiz Bot',
                )
            except Exception as exc:
                logger.exception('Failed to send audio round: %s', exc)
                await bot.send_message(chat_id, header + '\n\n(Аудио отправить не удалось, но вопрос остаётся активным.)')
        else:
            await bot.send_message(chat_id, header)

        task = asyncio.create_task(self._question_timeout(bot, chat_id, state.asked_count))
        self.question_tasks[chat_id] = task

    async def _question_timeout(self, bot: Bot, chat_id: int, question_number: int) -> None:
        state = self.games.get(chat_id)
        cfg = self.get_chat_settings(chat_id)

        try:
            await asyncio.sleep(self._timeout_for_mode(state, cfg) if state else cfg.question_timeout_sec)
        except asyncio.CancelledError:
            return

        state = self.games.get(chat_id)
        if not state or not state.is_active or not state.current_question:
            return
        if state.current_question_answered:
            return
        if state.asked_count != question_number:
            return

        state.last_correct_user_id = None
        state.correct_streak_count = 0

        await bot.send_message(
            chat_id,
            (
                '⌛ Время вышло.\n'
                f'Правильный ответ: {state.current_question.answer}\n'
                f'Факт: {state.current_question.explanation}'
            ),
        )
        self.adaptive_difficulty.note_timeout(chat_id)
        await self._ask_next_question(bot, chat_id)

    async def _finalize_game(self, bot: Bot, chat_id: int) -> None:
        started = time.perf_counter()
        state = self.games.get(chat_id)
        if not state:
            return

        state.is_active = False
        self._cancel_question_task(chat_id)
        ranking = sorted(state.scores.values(), key=lambda item: (-item.points, item.username.lower()))

        if ranking:
            winner = ranking[0]
            await self.product_store.note_match_result(
                chat_id=chat_id,
                ranking=[(player.user_id, player.username, player.points) for player in ranking],
            )
            self.memory_store.note_quiz_event(chat_id, winner.user_id, winner.username, won=True)

            summary = ['🏁 Игра завершена!', '', f'Режим: {self._mode_label(state.quiz_mode)}', '', 'Итоговая таблица:']
            for idx, player in enumerate(ranking, start=1):
                summary.append(f'{idx}. @{player.username} — {player.points}')
            if state.quiz_mode == 'team2v2':
                summary.append('')
                summary.extend(self._team_score_lines(state))
            summary.append('')
            summary.append(f'👑 Победитель: @{winner.username}')
            summary.append('💎 Победитель получил +5 сезонных очков')
        else:
            winner = None
            summary = ['🏁 Игра завершена!', '', 'Никто не набрал очков.']

        await bot.send_message(chat_id, '\n'.join(summary))

        try:
            await self.db.save_game_result(
                chat_id=chat_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                winner_user_id=winner.user_id if winner else None,
                winner_username=winner.username if winner else None,
                winner_points=winner.points if winner else 0,
                total_questions=state.question_limit,
                all_scores=[(player.user_id, player.username, player.points) for player in ranking],
            )
        except Exception as exc:
            logger.exception('Failed to save game result: %s', exc)

        self.games.pop(chat_id, None)
        log_operation(
            logger,
            operation='game_finalize',
            chat_id=chat_id,
            result='ok',
            duration_ms=(time.perf_counter() - started) * 1000,
            extra={'players': len(ranking), 'asked_count': state.asked_count},
        )

    def _cancel_question_task(self, chat_id: int) -> None:
        task = self.question_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    def _cancel_invite_task(self, chat_id: int) -> None:
        self.invite_service.cancel_invite_task(chat_id)

    def _clear_pending_invite(self, chat_id: int) -> None:
        self.invite_service.clear_pending_invite(chat_id)

    def _remember_chat_message(self, chat_id: int, role: str, speaker: str, text: str) -> None:
        value = text.strip()
        if not value:
            return
        self.chat_histories[chat_id].append({'role': role, 'speaker': speaker, 'text': value[:500]})

    def _remember_activity(self, chat_id: int, user_id: int, username: str, text: str) -> None:
        self.invite_service.remember_activity(chat_id, user_id, username, text)

    def _recent_unique_user_count(self, chat_id: int, window_sec: int) -> int:
        return self.invite_service.recent_unique_user_count(chat_id, window_sec)

    def _recent_message_count(self, chat_id: int, window_sec: int) -> int:
        return self.invite_service.recent_message_count(chat_id, window_sec)

    def _is_join_intent(self, text: str) -> bool:
        return self.invite_service.is_join_intent(text)

    async def _maybe_send_host_invite(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        invited = await self.invite_service.maybe_send_host_invite(bot, chat_id, user_id)
        if invited:
            self.chat_last_reply_ts[chat_id] = time.time()
        return invited

    async def _handle_pending_invite_vote(self, bot: Bot, chat_id: int, user_id: int, text: str) -> bool:
        async def _start_quiz(started_by: int) -> None:
            await self.start_game(bot, chat_id, started_by_user_id=started_by, question_limit=5, quiz_mode='classic')

        return await self.invite_service.handle_pending_invite_vote(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            on_threshold_reached=_start_quiz,
        )

    def _wrong_answer_text(self, username: str, question: QuizQuestion) -> str:
        if question.question_type == 'audio':
            variants = [
                f'🎧 @{username}, версия смелая, но оригинал сейчас нервно перематывается.',
                f'🎵 @{username}, ты попал не в трек, а в альтернативную вселенную.',
                f'🎙 @{username}, это был уверенный ответ. Жаль, что не правильный.',
            ]
        elif question.question_type == 'image':
            variants = [
                f'🖼 @{username}, картинка на тебя посмотрела и тихо не согласилась.',
                f'👀 @{username}, глаз-алмаз сегодня с небольшим сколом.',
                f'📸 @{username}, смело. Но фактология попросила тебя выйти на следующей.',
            ]
        else:
            variants = [
                f'😄 @{username}, версия бодрая, но истина сейчас в другом окне.',
                f'🫠 @{username}, ответ красивый, уверенный и мимо кассы.',
                f'😂 @{username}, это было близко примерно как соседний район к другой стране.',
                f'🤡 @{username}, звучит так, будто ты почти знал... лет пять назад.',
                f'🧠 @{username}, мозг завёлся, но навигатор повёл не туда.',
                f'🎯 @{username}, стрела выпущена эффектно, мишень пока жива и улыбается.',
            ]
        return random.choice(variants)

    def _near_miss_text(self, username: str, question: QuizQuestion) -> str:
        if question.question_type == 'audio':
            variants = [
                f'🎧 @{username}, уши у тебя рабочие — но трек пока не сдался.',
                f'🎵 @{username}, почти попал в ноты, но не в ответ.',
                f'🎙 @{username}, горячо. Музыкальный Шазам в тебе проснулся, но не до конца.',
            ]
        elif question.question_type == 'image':
            variants = [
                f'🖼 @{username}, почти. Глаза орлиные, но ответ пока мимо ветки.',
                f'👀 @{username}, очень близко — картинка тебя уважает, но не подтверждает.',
                f'📸 @{username}, тепло. Фото уже дрогнуло, но правильный ответ ещё нет.',
            ]
        else:
            variants = [
                f'😏 @{username}, очень близко. Мозг разогрелся, теперь бы ещё доехать до станции «верно».',
                f'🔥 @{username}, горячо. Ещё полшага — и ты бы забрал этот вопрос как налоговая забирает нервы.',
                f'🤏 @{username}, почти. Ответ уже машет тебе рукой, но ты пока машешь ему из соседнего окна.',
                f'🧠 @{username}, мысль правильная по вайбу, но формально мимо. Квиз любит придираться.',
            ]
        return random.choice(variants)
