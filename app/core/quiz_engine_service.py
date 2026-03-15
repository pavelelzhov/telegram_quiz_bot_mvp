from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.core.models import (
    ChatSettings,
    GameState,
    QuestionSelectionContext,
    QuizQuestion,
)
from app.core.question_dedup_service import QuestionDedupService
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)


class QuizEngineService:
    TARGET_CACHE_SIZE = 10000
    LOW_WATERMARK_CACHE_SIZE = 8000
    MIN_START_CACHE_SIZE = 7000
    GENERATION_BATCH_SIZE = 50

    def __init__(self, db=None, llm_provider=None, dedup_service: Optional[QuestionDedupService] = None) -> None:
        self.db = db
        self.llm_provider = llm_provider
        self.dedup_service = dedup_service or QuestionDedupService()
        self.background_refill_inflight: set[int] = set()
        self.category_memory_by_chat: dict[int, dict[str, list[str]]] = {}

    def _is_generation_enabled(self) -> bool:
        return bool(settings.quiz_allow_generation and self.llm_provider is not None and self.db is not None)

    def game_profile_label(self, profile: str) -> str:
        mapping = {
            'casual': '😌 casual',
            'standard': '🎯 standard',
            'hardcore': '💀 hardcore',
        }
        return mapping.get(profile, '🎯 standard')

    def mode_label(self, quiz_mode: str) -> str:
        mapping = {
            'classic': '🎯 Классика',
            'blitz': '🔥 Блиц',
            'epic': '👑 Эпик',
            'team2v2': '🤝 Командный 2v2',
            'solo_adaptive': '🧠 Solo Adaptive',
            'daily': '📅 Daily Challenge',
        }
        return mapping.get(quiz_mode, '🎯 Классика')

    def timeout_for_mode(self, state: GameState, cfg: ChatSettings) -> int:
        timeout = cfg.question_timeout_sec
        if cfg.game_profile == 'casual':
            timeout += 5
        elif cfg.game_profile == 'hardcore':
            timeout -= 5

        timeout = max(15, min(60, timeout))

        if state.quiz_mode == 'blitz':
            return max(15, timeout - 8)
        if state.quiz_mode == 'epic':
            return min(60, timeout + 5)
        return timeout

    def determine_stage(self, state: GameState, question_number: int) -> str:
        total = state.question_limit

        if state.quiz_mode == 'blitz':
            if question_number == total:
                return 'finale'
            if question_number <= 2:
                return 'warmup'
            if question_number in {3, 5}:
                return 'special'
            return 'core'

        if state.quiz_mode == 'epic':
            if question_number == total:
                return 'finale'
            if question_number <= 2:
                return 'warmup'
            if question_number in {4, 8, 10}:
                return 'special'
            return 'core'

        if question_number == total:
            return 'finale'
        if question_number <= min(2, total):
            return 'warmup'
        special_slot = max(3, (total // 2) + 1)
        if question_number == special_slot and question_number < total:
            return 'special'
        return 'core'

    def apply_mode_profile(self, question: QuizQuestion, state: GameState, stage: str) -> None:
        if stage == 'warmup':
            question.round_label = '🔥 Разогрев'
            question.point_value = 1
        elif stage == 'special':
            if question.question_type == 'audio':
                question.round_label = '🎧 Спецраунд x2'
            elif question.question_type == 'image':
                question.round_label = '🖼 Спецраунд x2'
            else:
                question.round_label = '⚡ Спецраунд x2'
            question.point_value = 2
        elif stage == 'finale':
            if state.quiz_mode == 'epic':
                question.round_label = '👑 Финальный босс x3'
                question.point_value = 3
            else:
                question.round_label = '👑 Финальный x2'
                question.point_value = 2
        else:
            question.round_label = '🎯 Основной раунд'
            question.point_value = 1

        if state.quiz_mode == 'blitz' and stage == 'core':
            question.round_label = '⚡ Блиц-раунд'
        if state.quiz_mode == 'epic' and stage == 'core':
            question.round_label = '🧩 Эпик-раунд'

    async def prepare_question_buffer(self, game_state: GameState, participants: list[int]) -> None:
        if len(game_state.question_buffer) >= 5:
            return
        target_difficulty = await self._resolve_target_difficulty(game_state, participants)
        await self.ensure_minimum_buffer(game_state, target_difficulty=target_difficulty)

    async def _resolve_target_difficulty(self, game_state: GameState, participants: list[int]) -> str:
        if self.db is None or not game_state.adaptive_enabled:
            return 'medium'

        candidate_ids = [item for item in participants if item > 0]
        if not candidate_ids:
            candidate_ids = [game_state.started_by_user_id]

        band_to_weight = {'easy': 0, 'medium': 1, 'hard': 2}
        weights: list[int] = []
        for player_id in candidate_ids[:5]:
            snapshot = await self.db.get_player_skill_profile(player_id)
            weights.append(band_to_weight.get(snapshot.current_band, 1))
            game_state.target_difficulty_by_player[player_id] = snapshot.current_band

        if not weights:
            return 'medium'

        avg = sum(weights) / len(weights)
        if avg >= 1.5:
            return 'hard'
        if avg <= 0.5:
            return 'easy'
        return 'medium'

    async def ensure_minimum_buffer(self, game_state: GameState, target_difficulty: str = 'medium') -> None:
        if self.db is None:
            return
        needed = max(0, 10 - len(game_state.question_buffer))
        if needed == 0:
            return

        appended = await self._append_candidates_to_buffer(
            game_state,
            target_difficulty=target_difficulty,
            needed=needed,
            relaxed_repeat=False,
        )

        if appended == 0:
            appended = await self._append_candidates_to_buffer(
                game_state,
                target_difficulty=target_difficulty,
                needed=needed,
                relaxed_repeat=True,
            )

        if self._is_generation_enabled():
            await self.request_generation_if_buffer_low(game_state)

        if appended == 0 and len(game_state.question_buffer) < 5:
            post_generation_needed = max(0, 10 - len(game_state.question_buffer))
            if post_generation_needed > 0:
                difficulty_fallbacks = [target_difficulty, 'medium', 'easy', 'hard']
                for difficulty in difficulty_fallbacks:
                    added = await self._append_candidates_to_buffer(
                        game_state,
                        target_difficulty=difficulty,
                        needed=post_generation_needed,
                        relaxed_repeat=False,
                    )
                    if added == 0:
                        added = await self._append_candidates_to_buffer(
                            game_state,
                            target_difficulty=difficulty,
                            needed=post_generation_needed,
                            relaxed_repeat=True,
                        )
                    if added > 0:
                        break

    async def _append_candidates_to_buffer(
        self,
        game_state: GameState,
        target_difficulty: str,
        needed: int,
        relaxed_repeat: bool,
    ) -> int:
        if self.db is None or needed <= 0:
            return 0

        chat_id_for_query = None if relaxed_repeat else game_state.chat_id
        same_day_repeat_block = False if relaxed_repeat else True
        repeat_window_days = 1 if relaxed_repeat else 5

        candidates = await self.db.get_candidate_questions(
            difficulty=target_difficulty,
            limit=max(needed, 5),
            topic=game_state.topic_focus[0] if game_state.topic_focus else None,
            mode=game_state.quiz_mode,
            chat_id=chat_id_for_query,
            local_game_date=game_state.local_game_date or datetime.now(timezone.utc).date().isoformat(),
            repeat_window_days=repeat_window_days,
            same_day_repeat_block_enabled=same_day_repeat_block,
            exclude_question_ids=game_state.question_ids_used_in_game,
            exclude_uniqueness_hashes=game_state.uniqueness_hashes_used_in_game,
        )
        if relaxed_repeat and candidates:
            logger.info(
                'Relaxed repeat policy selected %s candidates for chat_id=%s mode=%s difficulty=%s',
                len(candidates),
                game_state.chat_id,
                game_state.quiz_mode,
                target_difficulty,
            )
        selection_context = QuestionSelectionContext(
            chat_id=game_state.chat_id,
            local_game_date=game_state.local_game_date or datetime.now(timezone.utc).date().isoformat(),
            topic_focus=game_state.topic_focus,
            target_difficulty=target_difficulty,
            question_ids_used_in_game=set(game_state.question_ids_used_in_game),
            uniqueness_hashes_used_in_game=set(game_state.uniqueness_hashes_used_in_game),
        )
        if relaxed_repeat:
            filtered = candidates
        else:
            filtered = await self.filter_repeated_questions(candidates, selection_context)
        filtered = sorted(filtered, key=lambda item: self.score_candidate_fit(item, selection_context), reverse=True)
        filtered = self._mix_candidates_for_variety(filtered)
        appended = 0
        buffer_answer_fingerprints = {
            normalize_text(str(item.answer or ''))
            for item in game_state.question_buffer
            if str(item.answer or '').strip()
        }
        for item in filtered[:needed]:
            answer_fingerprint = normalize_text(str(item.get('correct_answer_text') or ''))
            if answer_fingerprint and answer_fingerprint in game_state.answer_fingerprints_used_in_game:
                continue
            if answer_fingerprint and answer_fingerprint in buffer_answer_fingerprints:
                continue
            game_state.question_buffer.append(
                self._candidate_to_quiz_question(item)
            )
            if answer_fingerprint:
                buffer_answer_fingerprints.add(answer_fingerprint)
            appended += 1

        return appended

    def _mix_candidates_for_variety(self, candidates: list[dict]) -> list[dict]:
        if len(candidates) <= 2:
            return candidates

        buckets: dict[str, list[dict]] = {}
        for item in candidates:
            category = str(item.get('topic') or 'Общие знания').strip() or 'Общие знания'
            bucket = buckets.setdefault(category, [])
            bucket.append(item)

        for bucket in buckets.values():
            random.shuffle(bucket)

        category_order = list(buckets.keys())
        random.shuffle(category_order)

        mixed: list[dict] = []
        while True:
            moved = False
            for category in category_order:
                bucket = buckets.get(category) or []
                if not bucket:
                    continue
                mixed.append(bucket.pop(0))
                moved = True
            if not moved:
                break

        return mixed

    def _candidate_to_quiz_question(self, item: dict) -> QuizQuestion:
        raw_aliases = item.get('aliases')
        aliases: list[str] = []
        if isinstance(raw_aliases, list):
            aliases = [str(alias).strip() for alias in raw_aliases if str(alias).strip()]

        hint_text = str(item.get('hint_text') or '').strip() or 'Подумай о главном факте вопроса.'

        return QuizQuestion(
            category=item.get('topic') or 'Общие знания',
            difficulty=item['difficulty'],
            topic=item.get('topic') or '',
            question=item['question_text'],
            answer=item['correct_answer_text'],
            aliases=aliases,
            hint=hint_text,
            explanation=item['explanation'],
            question_type=item['question_type'],
            source='llm_cache',
            question_id=item['id'],
            question_hash=item.get('question_hash', ''),
            uniqueness_hash=item.get('uniqueness_hash', ''),
            quality_score=float(item.get('quality_score') or 0),
        )

    async def select_next_question(self, game_state: GameState, player_id: int | None = None) -> QuizQuestion | None:
        if not game_state.question_buffer:
            fallback_target = game_state.target_difficulty_by_player.get(game_state.started_by_user_id, 'medium')
            await self.ensure_minimum_buffer(game_state, target_difficulty=fallback_target)
        if not game_state.question_buffer:
            return None
        return game_state.question_buffer.pop(0)

    async def request_generation_if_buffer_low(self, game_state: GameState) -> None:
        if len(game_state.question_buffer) >= 3 or game_state.generation_inflight:
            return
        if not self._is_generation_enabled():
            return
        game_state.generation_inflight = True
        try:
            preferred_difficulty = game_state.target_difficulty_by_player.get(game_state.started_by_user_id, 'medium')
            attempts = [
                {'difficulty': preferred_difficulty, 'category': game_state.preferred_category},
                {'difficulty': preferred_difficulty, 'category': 'Случайно'},
                {'difficulty': 'medium', 'category': 'Случайно'},
            ]
            batch = []
            for idx, attempt in enumerate(attempts, start=1):
                batch = await self.llm_provider.generate_question_batch(
                    {
                        'chat_id': game_state.chat_id,
                        'count': 10,
                        'difficulty': attempt['difficulty'],
                        'category': attempt['category'],
                        'mode': game_state.quiz_mode,
                        'llm_only': True,
                    }
                )
                if batch:
                    if idx > 1:
                        logger.info(
                            'LLM batch refill recovered on attempt=%s chat_id=%s difficulty=%s category=%s size=%s',
                            idx,
                            game_state.chat_id,
                            attempt['difficulty'],
                            attempt['category'],
                            len(batch),
                        )
                    break

                logger.warning(
                    'LLM batch refill attempt returned empty batch: attempt=%s chat_id=%s difficulty=%s category=%s',
                    idx,
                    game_state.chat_id,
                    attempt['difficulty'],
                    attempt['category'],
                )

            validator = getattr(self.llm_provider, 'validate_question_batch', None)
            if callable(validator):
                valid_batch = validator(batch)
            else:
                valid_batch = batch
            accepted_count = await self._persist_unique_candidates(game_state.chat_id, game_state.quiz_mode, valid_batch)
            if accepted_count == 0:
                logger.warning(
                    'Пакет генерации не дал валидных LLM-вопросов: chat_id=%s, mode=%s, valid_batch=%s',
                    game_state.chat_id,
                    game_state.quiz_mode,
                    len(valid_batch),
                )
        except Exception:
            logger.exception('Не удалось догенерировать пакет вопросов для буфера')
        finally:
            game_state.generation_inflight = False

    async def maybe_start_background_cache_refill(self, chat_id: int, quiz_mode: str, preferred_category: str) -> None:
        if not self._is_generation_enabled():
            return
        cache_size = await self.db.get_valid_llm_questions_count()
        if cache_size >= self.LOW_WATERMARK_CACHE_SIZE:
            return
        if chat_id in self.background_refill_inflight:
            return

        self.background_refill_inflight.add(chat_id)
        try:
            await self._run_background_cache_refill(chat_id, quiz_mode, preferred_category)
        finally:
            self.background_refill_inflight.discard(chat_id)

    async def ensure_cache_after_restart(self) -> None:
        if self.db is None:
            return

        if not self._is_generation_enabled():
            cache_size = await self.db.get_valid_llm_questions_count()
            logger.info(
                'Стартовый контроль кэша: автогенерация выключена, работаем только из буфера (cache_size=%s)',
                cache_size,
            )
            return

        cache_size = await self.db.get_valid_llm_questions_count()
        if cache_size >= self.LOW_WATERMARK_CACHE_SIZE:
            logger.info(
                'Стартовый контроль кэша: вопросов достаточно, refill не нужен (cache_size=%s, low_watermark=%s)',
                cache_size,
                self.LOW_WATERMARK_CACHE_SIZE,
            )
            return

        logger.warning(
            'Стартовый контроль кэша: вопросов мало, запускаю refill (cache_size=%s, low_watermark=%s)',
            cache_size,
            self.LOW_WATERMARK_CACHE_SIZE,
        )
        await self.maybe_start_background_cache_refill(
            chat_id=0,
            quiz_mode='classic',
            preferred_category='Случайно',
        )

    async def _run_background_cache_refill(self, chat_id: int, quiz_mode: str, preferred_category: str) -> None:
        if not self._is_generation_enabled():
            return

        while True:
            cache_size = await self.db.get_valid_llm_questions_count()
            if cache_size >= self.TARGET_CACHE_SIZE:
                logger.info('Фоновый прогрев завершён: chat_id=%s cache_size=%s', chat_id, cache_size)
                return

            request_count = min(self.GENERATION_BATCH_SIZE, self.TARGET_CACHE_SIZE - cache_size)
            category = preferred_category if preferred_category and preferred_category != 'Случайно' else 'Случайно'
            difficulty = random.choice(['easy', 'medium', 'hard'])

            batch = await self.llm_provider.generate_question_batch(
                {
                    'chat_id': chat_id,
                    'count': request_count,
                    'difficulty': difficulty,
                    'category': category,
                    'mode': quiz_mode,
                    'llm_only': True,
                }
            )
            validator = getattr(self.llm_provider, 'validate_question_batch', None)
            valid_batch = validator(batch) if callable(validator) else batch
            accepted_count = await self._persist_unique_candidates(chat_id, quiz_mode, valid_batch)

            if accepted_count == 0:
                logger.warning(
                    'Фоновая генерация не пополнила кэш: chat_id=%s cache_size=%s requested=%s valid=%s',
                    chat_id,
                    cache_size,
                    request_count,
                    len(valid_batch),
                )
                return

    async def _persist_unique_candidates(self, chat_id: int, quiz_mode: str, valid_batch: list) -> int:
        if self.db is None:
            return 0
        accepted = []
        seen_question_hashes: set[str] = set()
        seen_uniqueness_hashes: set[str] = set()

        for candidate in valid_batch:
            candidate.quality_score = max(
                0.1,
                min(
                    1.0,
                    0.35 + (0.01 * len(candidate.question_text)) + (0.02 * len(candidate.explanation)),
                ),
            )

            if candidate.question_hash in seen_question_hashes or candidate.uniqueness_hash in seen_uniqueness_hashes:
                await self.db.save_question_rejection(
                    raw_payload=json.dumps(asdict(candidate), ensure_ascii=False),
                    reject_reason='duplicate_in_batch',
                    matched_uniqueness_hash=candidate.uniqueness_hash,
                )
                continue

            existing = await self.db.find_question_by_hashes(candidate.question_hash, candidate.uniqueness_hash)
            if existing is not None:
                await self.db.save_question_rejection(
                    raw_payload=json.dumps(asdict(candidate), ensure_ascii=False),
                    reject_reason='duplicate_in_cache',
                    matched_question_id=int(existing['id']),
                    matched_uniqueness_hash=str(existing.get('uniqueness_hash') or ''),
                )
                continue

            seen_question_hashes.add(candidate.question_hash)
            seen_uniqueness_hashes.add(candidate.uniqueness_hash)
            candidate.created_for_mode = quiz_mode
            accepted.append(candidate)

        if not accepted:
            return 0

        await self.db.save_generated_questions(accepted)
        self._remember_batch_by_category(chat_id, accepted)
        return len(accepted)

    def _remember_batch_by_category(self, chat_id: int, accepted: list) -> None:
        buckets = self.category_memory_by_chat.setdefault(chat_id, {})
        for candidate in accepted:
            category = (candidate.topic or 'Общие знания').strip() or 'Общие знания'
            bucket = buckets.setdefault(category, [])
            marker = candidate.question_hash or candidate.question_text
            if marker in bucket:
                continue
            bucket.append(marker)
            if len(bucket) > 300:
                del bucket[0]

    async def get_refill_status_text(self, chat_id: int) -> str:
        if self.db is None:
            return 'LLM-буфер недоступен: база не подключена.'

        cache_size = await self.db.get_valid_llm_questions_count()
        inflight = chat_id in self.background_refill_inflight
        buckets = self.category_memory_by_chat.get(chat_id, {})
        categories_tracked = len(buckets)
        generation_mode = 'вкл' if settings.quiz_allow_generation else 'выкл'
        breakdown = await self.db.get_llm_question_breakdown(top_categories_limit=6)

        progress = min(100, int((cache_size / max(1, self.TARGET_CACHE_SIZE)) * 100))
        refill_state = 'идёт' if inflight else 'не идёт'
        threshold_hint = (
            f'автопополнение включится при падении ниже {self.LOW_WATERMARK_CACHE_SIZE}'
            if cache_size >= self.LOW_WATERMARK_CACHE_SIZE
            else 'ниже порога, пополнение должно быть активным'
        )

        difficulty = breakdown.get('difficulty', {})
        difficulty_line = ', '.join(
            f"{key}:{difficulty.get(key, 0)}" for key in ('easy', 'medium', 'hard')
        )
        category_rows = breakdown.get('top_categories', [])
        categories_line = ', '.join(f'{name}: {count}' for name, count in category_rows) if category_rows else 'нет данных'

        return (
            '📦 Статус LLM-буфера\n'
            f'Валидных вопросов в кэше: {cache_size}\n'
            f'Автогенерация новых вопросов: {generation_mode}\n'
            f'Целевой объём: {self.TARGET_CACHE_SIZE} ({progress}%)\n'
            f'Фоновое пополнение: {refill_state}\n'
            f'Категорий в памяти чата: {categories_tracked}\n'
            f'Порог low-watermark: {self.LOW_WATERMARK_CACHE_SIZE} ({threshold_hint}).\n'
            f'Разбивка по сложности: {difficulty_line}\n'
            f'Топ категорий: {categories_line}'
        )

    async def filter_repeated_questions(self, candidates: list[dict], context: QuestionSelectionContext) -> list[dict]:
        if self.db is None:
            return candidates
        chat_usage = await self.db.get_recent_question_usage_for_chat(context.chat_id, days=context.repeat_window_days)
        player_usage = []
        if context.player_id is not None:
            player_usage = await self.db.get_recent_question_usage_for_player(context.player_id, days=context.repeat_window_days)

        chat_qids_today = {
            int(item['question_id'])
            for item in chat_usage
            if item.get('local_game_date') == context.local_game_date
        }
        chat_seen_uniqueness = {str(item.get('uniqueness_hash', '')) for item in chat_usage if item.get('uniqueness_hash')}
        player_seen_uniqueness = {str(item.get('uniqueness_hash', '')) for item in player_usage if item.get('uniqueness_hash')}

        filtered = []
        for candidate in candidates:
            candidate_id = int(candidate['id'])
            if context.same_day_repeat_block_enabled and candidate_id in chat_qids_today:
                continue
            if candidate_id in context.question_ids_used_in_game:
                continue
            uq = str(candidate.get('uniqueness_hash', ''))
            if uq and (uq in chat_seen_uniqueness or uq in player_seen_uniqueness):
                continue
            if uq and uq in context.uniqueness_hashes_used_in_game:
                continue
            filtered.append(candidate)
        return filtered

    def score_candidate_fit(self, candidate: dict, context: QuestionSelectionContext) -> float:
        quality = float(candidate.get('quality_score') or 0)
        difficulty = candidate.get('difficulty', 'medium')
        diff_bonus = 1.0 if difficulty == context.target_difficulty else 0.2
        topic_bonus = 0.3 if not context.topic_focus or candidate.get('topic') in context.topic_focus else 0.0
        return quality + diff_bonus + topic_bonus
