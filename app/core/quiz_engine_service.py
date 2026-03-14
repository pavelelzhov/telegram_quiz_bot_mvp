from __future__ import annotations

import json
import logging
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
    def __init__(self, db=None, llm_provider=None, dedup_service: Optional[QuestionDedupService] = None) -> None:
        self.db = db
        self.llm_provider = llm_provider
        self.dedup_service = dedup_service or QuestionDedupService()

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
        await self.ensure_minimum_buffer(game_state)

    async def ensure_minimum_buffer(self, game_state: GameState) -> None:
        if self.db is None:
            return
        needed = max(0, 10 - len(game_state.question_buffer))
        if needed == 0:
            return

        target_difficulty = 'medium'
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
            await self.ensure_minimum_buffer(game_state)
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
            batch = await self.llm_provider.generate_question_batch(
                {
                    'chat_id': game_state.chat_id,
                    'count': 10,
                    'difficulty': 'medium',
                    'mode': game_state.quiz_mode,
                }
            )
            valid_batch = self.llm_provider.validate_question_batch(batch)
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
                accepted.append(candidate)

            if accepted:
                await self.db.save_generated_questions(accepted)
        except Exception:
            logger.exception('Не удалось догенерировать пакет вопросов для буфера')
        finally:
            game_state.generation_inflight = False

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
