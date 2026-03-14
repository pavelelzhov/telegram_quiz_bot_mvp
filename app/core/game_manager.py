from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from aiogram import Bot
from app.agent.memory_store import MemoryStore
from app.config import settings
from app.core.adaptive_difficulty_service import AdaptiveDifficultyService
from app.core.difficulty_service import DifficultyService
from app.core.answer_flow_service import AnswerFlowService
from app.core.chat_config_service import ChatConfigService
from app.core.chat_history_service import ChatHistoryService
from app.core.daily_challenge_service import DailyChallengeService
from app.core.chat_participation_service import ChatParticipationService
from app.core.chat_agent_service import ChatAgentService
from app.core.feedback_text_service import FeedbackTextService
from app.core.game_status_service import GameStatusService
from app.core.game_summary_service import GameSummaryService
from app.core.invite_service import InviteService
from app.core.invite_orchestration_service import InviteOrchestrationService
from app.core.models import ChatSettings, GameState, QuestionUsageRecord, QuizQuestion
from app.core.quiz_engine_service import QuizEngineService
from app.core.round_lifecycle_service import RoundLifecycleService
from app.core.team_mode_service import TeamModeService
from app.providers.llm_provider import LLMQuestionProvider
from app.quiz.product_store import ProductStore
from app.storage.db import Database
from app.utils.ops_log import log_operation

logger = logging.getLogger(__name__)


class GameManager:
    def __init__(self, db: Database, question_provider: LLMQuestionProvider) -> None:
        self.db = db
        self.question_provider = question_provider
        self.memory_store = MemoryStore()
        self.chat_agent_service = ChatAgentService(self.memory_store)
        self.feedback_text = FeedbackTextService()
        self.invite_service = InviteService()
        self.invite_orchestration = InviteOrchestrationService()
        self.adaptive_difficulty = AdaptiveDifficultyService()
        self.difficulty_service = DifficultyService()
        self.answer_flow = AnswerFlowService(db=db, difficulty_service=self.difficulty_service)
        self.chat_participation = ChatParticipationService()
        self.game_status = GameStatusService()
        self.game_summary = GameSummaryService()
        self.product_store = ProductStore()
        self.quiz_engine = QuizEngineService(db=db, llm_provider=question_provider)
        self.chat_config = ChatConfigService()
        self.round_lifecycle = RoundLifecycleService()
        self.chat_history = ChatHistoryService(max_items=20)
        self.daily_challenge = DailyChallengeService()
        self.games: Dict[int, GameState] = {}
        self.question_tasks: Dict[int, asyncio.Task] = {}
        self.recent_question_keys: Dict[int, Deque[str]] = defaultdict(
            lambda: deque(maxlen=settings.recent_questions_limit)
        )
        self.start_locks: Dict[int, asyncio.Lock] = {}
        self.team_mode = TeamModeService()

    def _get_start_lock(self, chat_id: int) -> asyncio.Lock:
        lock = self.start_locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self.start_locks[chat_id] = lock
        return lock

    def get_game(self, chat_id: int) -> Optional[GameState]:
        return self.games.get(chat_id)

    def get_chat_settings(self, chat_id: int) -> ChatSettings:
        return self.chat_config.get_chat_settings(chat_id)

    def get_settings_text(self, chat_id: int) -> str:
        cfg = self.get_chat_settings(chat_id)
        return self.chat_config.build_settings_text(chat_id, self.quiz_engine.game_profile_label(cfg.game_profile))

    def set_game_profile(self, chat_id: int, profile: str) -> bool:
        return self.chat_config.set_game_profile(chat_id, profile)

    def get_game_profile(self, chat_id: int) -> str:
        return self.chat_config.get_game_profile(chat_id)

    async def get_player_product_text(self, chat_id: int, user_id: int, username: str) -> str:
        return await self.product_store.get_player_text(chat_id, user_id, username)

    async def get_season_product_text(self, chat_id: int) -> str:
        return await self.product_store.get_season_text(chat_id)

    def cycle_timeout(self, chat_id: int) -> int:
        return self.chat_config.cycle_timeout(chat_id)

    def toggle_image_rounds(self, chat_id: int) -> bool:
        return self.chat_config.toggle_image_rounds(chat_id)

    def toggle_music_rounds(self, chat_id: int) -> bool:
        return self.chat_config.toggle_music_rounds(chat_id)

    def toggle_admin_only_control(self, chat_id: int) -> bool:
        return self.chat_config.toggle_admin_only_control(chat_id)

    def toggle_host_mode(self, chat_id: int) -> bool:
        return self.chat_config.toggle_host_mode(chat_id)

    def set_preferred_category(self, chat_id: int, category: str) -> None:
        self.chat_config.set_preferred_category(chat_id, category)

    def get_preferred_category(self, chat_id: int) -> str:
        return self.chat_config.get_preferred_category(chat_id)

    def set_team_choice(self, chat_id: int, user_id: int, username: str, team: str) -> str:
        return self.team_mode.set_team_choice(chat_id, user_id, username, team)

    def get_team_lobby_text(self, chat_id: int) -> str:
        return self.team_mode.get_team_lobby_text(chat_id)

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

            self.invite_service.clear_pending_invite(chat_id)

            preferred_category = self.get_preferred_category(chat_id)
            cfg = self.get_chat_settings(chat_id)
            team_assignments: dict[int, str] = {}

            if quiz_mode == 'team2v2':
                built = self.team_mode.build_team_assignments(chat_id)
                if built is None:
                    return f'Для 2v2 нужны команды 2 на 2.\n{self.get_team_lobby_text(chat_id)}'
                team_assignments = built

            state = GameState(
                chat_id=chat_id,
                started_by_user_id=started_by_user_id,
                question_limit=question_limit,
                preferred_category=preferred_category,
                quiz_mode=quiz_mode,
                team_assignments=team_assignments,
                mode='team_battle' if quiz_mode == 'team2v2' else 'group_blitz',
                local_game_date=self.daily_challenge.resolve_local_game_date(cfg.timezone),
                adaptive_enabled=cfg.adaptive_mode_enabled,
            )

            try:
                await asyncio.wait_for(
                    self.quiz_engine.prepare_question_buffer(state, [started_by_user_id]),
                    timeout=4.0,
                )
            except asyncio.TimeoutError:
                logger.warning('Прогрев буфера превысил таймаут: chat_id=%s', chat_id)
            except Exception:
                logger.exception('Ошибка прогрева буфера перед стартом: chat_id=%s', chat_id)

            if not state.question_buffer:
                await bot.send_message(
                    chat_id,
                    'Пока не удалось получить LLM-вопросы. '
                    'Проверь /health и попробуй ещё раз через 1-2 минуты.',
                )
                log_operation(
                    logger,
                    operation='game_start',
                    chat_id=chat_id,
                    result='no_llm_questions',
                    duration_ms=(time.perf_counter() - started) * 1000,
                    extra={'question_limit': question_limit, 'quiz_mode': quiz_mode},
                    level=logging.WARNING,
                )
                return 'Сейчас нет готовых LLM-вопросов для старта. Попробуй позже.'

            self.games[chat_id] = state
            asyncio.create_task(
                self.quiz_engine.maybe_start_background_cache_refill(
                    chat_id=chat_id,
                    quiz_mode=quiz_mode,
                    preferred_category=preferred_category,
                )
            )

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

        verdict = self.answer_flow.match_verdict(text, state.current_question)

        if verdict == 'wrong':
            self.adaptive_difficulty.note_wrong(chat_id)
            state.wrong_attempts_count += 1
            if self.answer_flow.register_wrong_attempt(state, user_id):
                response_ms = int(max(0.0, (time.time() - state.current_question_started_ts) * 1000))
                await self.answer_flow.finalize_answer(state, user_id, was_correct=False, response_ms=response_ms)
                await bot.send_message(chat_id, self.feedback_text.wrong_answer_text(username, state.current_question))
            if state.wrong_attempts_count >= 3:
                self._cancel_question_task(chat_id)
                state.last_correct_user_id = None
                state.correct_streak_count = 0
                await bot.send_message(chat_id, self.round_lifecycle.build_timeout_text(state.current_question))
                await self._ask_next_question(bot, chat_id)
            return False

        if verdict == 'close':
            self.adaptive_difficulty.note_close(chat_id)
            if self.answer_flow.register_close_attempt(state, user_id):
                await bot.send_message(chat_id, self.feedback_text.near_miss_text(username, state.current_question))
            return False

        question = state.current_question
        self.adaptive_difficulty.note_correct(chat_id)
        points_awarded, streak_count = self.answer_flow.register_correct_answer(state, user_id, username)
        response_ms = int(max(0.0, (time.time() - state.current_question_started_ts) * 1000))
        await self.answer_flow.finalize_answer(state, user_id, was_correct=True, response_ms=response_ms)
        self.memory_store.note_quiz_event(chat_id, user_id, username, correct=True)

        await self.product_store.note_correct(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            points=points_awarded,
            streak_count=streak_count,
        )

        leader_line = self._leader_line(state)

        self._cancel_question_task(chat_id)

        await bot.send_message(
            chat_id,
            self.answer_flow.build_correct_answer_text(
                username=username,
                question=question,
                points_awarded=points_awarded,
                streak_count=streak_count,
                leader_line=leader_line,
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

        self.chat_history.remember_message(chat_id, 'user', username, text)
        self.invite_service.remember_activity(chat_id, user_id, username, text)
        self.memory_store.note_message(chat_id, user_id, username, text)

        async def _start_quiz(started_by: int) -> None:
            await self.start_game(bot, chat_id, started_by_user_id=started_by, question_limit=5, quiz_mode='classic')

        if await self.invite_orchestration.handle_pending_invite_vote(
            invite_service=self.invite_service,
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            on_threshold_reached=_start_quiz,
        ):
            return True

        state = self.games.get(chat_id)
        quiz_active = bool(state and state.is_active)
        current_question_text = state.current_question.question if quiz_active and state and state.current_question else None

        if cfg.host_mode_enabled and not quiz_active:
            if await self.invite_orchestration.maybe_send_host_invite(
                invite_service=self.invite_service,
                bot=bot,
                chat_id=chat_id,
                user_id=user_id,
                on_invited=lambda: self.chat_history.mark_reply(chat_id, time.time()),
            ):
                return True

        if quiz_active and not addressed:
            return False

        now = time.time()
        cooldown = self.chat_participation.resolve_cooldown(
            addressed=addressed,
            host_mode_enabled=cfg.host_mode_enabled,
        )
        if cooldown is None:
            return False

        if not self.chat_history.can_reply(chat_id, now, cooldown):
            return False

        if not addressed:
            if not self.chat_participation.passes_passive_reply_filters(
                recent_unique_users=self.invite_service.recent_unique_user_count(chat_id, 180),
                recent_messages=self.invite_service.recent_message_count(chat_id, 180),
                text=text,
                random_value=random.random(),
            ):
                return False

        reply = await self.chat_agent_service.generate_reply(
            chat_id=chat_id,
            chat_title=chat_title,
            user_id=user_id,
            username=username,
            text=text,
            history=self.chat_history.get_history(chat_id),
            quiz_active=quiz_active,
            current_question_text=current_question_text,
            addressed=addressed,
        )
        if not reply:
            return False

        self.chat_history.mark_reply(chat_id, now)
        self.chat_history.remember_message(chat_id, 'assistant', 'quiz_bot', reply)
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
        team_lines = self.team_mode.team_score_lines(state) if state and state.quiz_mode == 'team2v2' else None
        return self.game_status.build_score_text(
            state=state,
            mode_label=self._mode_label(state.quiz_mode) if state else self._mode_label('classic'),
            team_score_lines=team_lines,
        )

    def get_status_text(self, chat_id: int) -> str:
        cfg = self.get_chat_settings(chat_id)
        state = self.games.get(chat_id)
        team_lines = self.team_mode.team_score_lines(state) if state and state.quiz_mode == 'team2v2' else None
        return self.game_status.build_status_text(
            cfg=cfg,
            state=state,
            game_profile_label=self.quiz_engine.game_profile_label(cfg.game_profile),
            preferred_category=self.get_preferred_category(chat_id),
            timer_seconds=self._timeout_for_mode(state, cfg) if state else cfg.question_timeout_sec,
            mode_label=self._mode_label(state.quiz_mode) if state else None,
            team_score_lines=team_lines,
        )
        if state.quiz_mode == 'team2v2':
            text += '\n\n' + '\n'.join(self.team_mode.team_score_lines(state))
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

        next_number = state.asked_count + 1
        stage = self._determine_stage(state, next_number)

        try:
            await self.quiz_engine.prepare_question_buffer(state, list(state.scores.keys()))
            question = await self.quiz_engine.select_next_question(state)
            if question is None:
                await self.quiz_engine.request_generation_if_buffer_low(state)
                question = await self.quiz_engine.select_next_question(state)
        except Exception as exc:
            logger.exception('Failed to obtain question: %s', exc)
            await bot.send_message(chat_id, 'Не удалось получить вопрос из LLM-кэша. Попробуйте ещё раз через минуту.')
            await self._finalize_game(bot, chat_id)
            return

        if question is None:
            await bot.send_message(
                chat_id,
                'Сейчас нет готовых LLM-вопросов в кэше. '                'Скорее всего, LLM временно недоступен или вернул невалидный пакет. '                'Проверь /health и попробуй запустить игру чуть позже.',
            )
            await self._finalize_game(bot, chat_id)
            return

        self._apply_mode_profile(question, state, stage)

        state.current_question = question
        state.current_question_answered = False
        state.current_question_started_ts = time.time()
        state.hints_used_for_current_question = 0
        state.near_miss_user_ids = set()
        state.wrong_reply_user_ids = set()
        state.wrong_attempts_count = 0
        state.used_question_keys.add(question.key)
        if question.question_id is not None:
            state.question_ids_used_in_game.add(question.question_id)
        if question.uniqueness_hash:
            state.uniqueness_hashes_used_in_game.add(question.uniqueness_hash)
        self.recent_question_keys[chat_id].append(question.key)
        state.asked_count += 1

        header = self.round_lifecycle.build_question_header(state, question)
        await self.round_lifecycle.send_question(bot, chat_id, question, header, logger)

        task = asyncio.create_task(self._question_timeout(bot, chat_id, state.asked_count))
        self.question_tasks[chat_id] = task
        asyncio.create_task(
            self.quiz_engine.maybe_start_background_cache_refill(
                chat_id=chat_id,
                quiz_mode=state.quiz_mode,
                preferred_category=state.preferred_category,
            )
        )

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

        await bot.send_message(chat_id, self.round_lifecycle.build_timeout_text(state.current_question))
        self.adaptive_difficulty.note_timeout(chat_id)
        if state.current_question.question_id is not None:
            await self.db.log_question_usage(
                QuestionUsageRecord(
                    question_id=state.current_question.question_id,
                    chat_id=chat_id,
                    shown_at=datetime.fromtimestamp(state.current_question_started_ts, tz=timezone.utc).isoformat(),
                    answered_at=datetime.now(timezone.utc).isoformat(),
                    was_correct=False,
                    response_ms=None,
                    local_game_date=state.local_game_date,
                )
            )
        await self._ask_next_question(bot, chat_id)

    async def _finalize_game(self, bot: Bot, chat_id: int) -> None:
        started = time.perf_counter()
        state = self.games.get(chat_id)
        if not state:
            return

        state.is_active = False
        self._cancel_question_task(chat_id)
        ranking = self.game_summary.build_ranking(state.scores.values())

        if ranking:
            winner = ranking[0]
            await self.product_store.note_match_result(
                chat_id=chat_id,
                ranking=[(player.user_id, player.username, player.points) for player in ranking],
            )
            self.memory_store.note_quiz_event(chat_id, winner.user_id, winner.username, won=True)

            team_lines = None
            if state.quiz_mode == 'team2v2':
                team_lines = self.team_mode.team_score_lines(state)
            summary = self.game_summary.build_summary_lines(
                ranking=ranking,
                mode_label=self._mode_label(state.quiz_mode),
                team_score_lines=team_lines,
            )
        else:
            winner = None
            summary = self.game_summary.build_summary_lines(ranking=[], mode_label=self._mode_label(state.quiz_mode))

        await bot.send_message(chat_id, '\n'.join(summary))

        try:
            await self.db.save_game_result(
                chat_id=chat_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                quiz_mode=state.quiz_mode,
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
