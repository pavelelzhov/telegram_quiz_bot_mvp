from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from app.core.models import (
    ChatSettings,
    GameState,
    QuestionSelectionContext,
    QuizQuestion,
)
from app.core.question_dedup_service import QuestionDedupService

logger = logging.getLogger(__name__)


class QuizEngineService:
    TARGET_CACHE_SIZE = 500
    LOW_WATERMARK_CACHE_SIZE = 300
    GENERATION_BATCH_SIZE = 50

    def __init__(self, db=None, llm_provider=None, dedup_service: Optional[QuestionDedupService] = None) -> None:
        self.db = db
        self.llm_provider = llm_provider
        self.dedup_service = dedup_service or QuestionDedupService()
        self.background_refill_inflight: set[int] = set()
        self.category_memory_by_chat: dict[int, dict[str, list[str]]] = {}

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

        candidates = await self.db.get_candidate_questions(
            difficulty=target_difficulty,
            limit=max(needed, 5),
            topic=game_state.topic_focus[0] if game_state.topic_focus else None,
            mode=game_state.quiz_mode,
            chat_id=game_state.chat_id,
            local_game_date=game_state.local_game_date or datetime.now(timezone.utc).date().isoformat(),
            repeat_window_days=5,
            same_day_repeat_block_enabled=True,
            exclude_question_ids=game_state.question_ids_used_in_game,
            exclude_uniqueness_hashes=game_state.uniqueness_hashes_used_in_game,
        )
        selection_context = QuestionSelectionContext(
            chat_id=game_state.chat_id,
            local_game_date=game_state.local_game_date or datetime.now(timezone.utc).date().isoformat(),
            topic_focus=game_state.topic_focus,
            target_difficulty=target_difficulty,
            question_ids_used_in_game=set(game_state.question_ids_used_in_game),
            uniqueness_hashes_used_in_game=set(game_state.uniqueness_hashes_used_in_game),
        )
        filtered = await self.filter_repeated_questions(candidates, selection_context)
        filtered = sorted(filtered, key=lambda item: self.score_candidate_fit(item, selection_context), reverse=True)
        for item in filtered[:needed]:
            game_state.question_buffer.append(
                QuizQuestion(
                    category=item.get('topic') or 'Общие знания',
                    difficulty=item['difficulty'],
                    topic=item.get('topic') or '',
                    question=item['question_text'],
                    answer=item['correct_answer_text'],
                    aliases=[],
                    hint='Подумай о главном факте вопроса.',
                    explanation=item['explanation'],
                    question_type=item['question_type'],
                    source='llm_cache',
                    question_id=item['id'],
                    question_hash=item.get('question_hash', ''),
                    uniqueness_hash=item.get('uniqueness_hash', ''),
                    quality_score=float(item.get('quality_score') or 0),
                )
            )

        await self.request_generation_if_buffer_low(game_state)

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
        if self.llm_provider is None or self.db is None:
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
        if self.db is None or self.llm_provider is None:
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

    async def _run_background_cache_refill(self, chat_id: int, quiz_mode: str, preferred_category: str) -> None:
        if self.db is None or self.llm_provider is None:
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
