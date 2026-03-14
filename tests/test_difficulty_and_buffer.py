from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone

from app.core.difficulty_service import DifficultyService
from app.core.models import GameState, PlayerSkillSnapshot, QuestionCandidate, QuestionUsageRecord
from app.core.quiz_engine_service import QuizEngineService
from app.storage.db import Database


class DifficultyAndBufferTests(unittest.TestCase):
    def test_adaptive_progression(self) -> None:
        service = DifficultyService()
        snapshot = PlayerSkillSnapshot(player_id=1, current_band='easy', global_skill_score=0.35, recent_accuracy=0.8, current_streak=4)
        decision = service.choose_target_band(snapshot)
        self.assertIn(decision.target_band, {'easy', 'medium'})

        snapshot = service.update_skill_after_answer(snapshot, was_correct=False, response_ms=9000, question_difficulty='medium')
        self.assertIn(snapshot.current_band, {'easy', 'medium'})

    def test_buffer_low_calls_generation_without_crash(self) -> None:
        class DummyProvider:
            async def generate_question_batch(self, request):
                return []

        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=DummyProvider())
                state = GameState(chat_id=1, started_by_user_id=1, question_limit=5)
                await engine.request_generation_if_buffer_low(state)
                self.assertFalse(state.generation_inflight)
            finally:
                os.remove(path)

        asyncio.run(_run())

    def test_background_cache_refill_populates_db_and_category_memory(self) -> None:
        class DummyProvider:
            def __init__(self) -> None:
                self._idx = 0

            async def generate_question_batch(self, request):
                batch = []
                for _ in range(5):
                    self._idx += 1
                    num = self._idx
                    batch.append(
                        QuestionCandidate(
                            provider_name='openai',
                            model_name='gpt-test',
                            language='ru',
                            topic='Наука' if num % 2 else 'История',
                            subtopic='',
                            difficulty='medium',
                            question_type='text',
                            question_text=f'Вопрос #{num}?',
                            correct_answer_text=f'Ответ #{num}',
                            explanation=f'Объяснение #{num}',
                            canonical_facts=[f'fact-{num}'],
                            uniqueness_tags=['tag'],
                            question_hash=f'qh-{num}',
                            uniqueness_hash=f'uh-{num}',
                        )
                    )
                return batch

            def validate_question_batch(self, batch):
                return batch

        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=DummyProvider())
                engine.TARGET_CACHE_SIZE = 12
                engine.LOW_WATERMARK_CACHE_SIZE = 3
                engine.GENERATION_BATCH_SIZE = 6

                await engine.maybe_start_background_cache_refill(chat_id=777, quiz_mode='classic', preferred_category='Случайно')

                count = await db.get_valid_llm_questions_count()
                self.assertGreaterEqual(count, 12)
                memory = engine.category_memory_by_chat.get(777, {})
                self.assertTrue(memory)
                self.assertIn('Наука', memory)
                status_text = await engine.get_refill_status_text(chat_id=777)
                self.assertIn('Статус LLM-буфера', status_text)
                self.assertIn('Целевой объём', status_text)
            finally:
                os.remove(path)

        asyncio.run(_run())

    def test_restart_refill_triggers_when_cache_below_low_watermark(self) -> None:
        class CountingProvider:
            def __init__(self) -> None:
                self.calls = 0
                self._idx = 0

            async def generate_question_batch(self, request):
                self.calls += 1
                batch = []
                for _ in range(3):
                    self._idx += 1
                    num = self._idx
                    batch.append(
                        QuestionCandidate(
                            provider_name='openai',
                            model_name='gpt-test',
                            language='ru',
                            topic='Общие знания',
                            subtopic='',
                            difficulty='medium',
                            question_type='text',
                            question_text=f'R-вопрос #{num}?',
                            correct_answer_text=f'R-ответ #{num}',
                            explanation=f'R-объяснение #{num}',
                            canonical_facts=[f'r-fact-{num}'],
                            uniqueness_tags=['restart'],
                            question_hash=f'r-qh-{num}',
                            uniqueness_hash=f'r-uh-{num}',
                        )
                    )
                return batch

            def validate_question_batch(self, batch):
                return batch

        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                provider = CountingProvider()
                engine = QuizEngineService(db=db, llm_provider=provider)
                engine.TARGET_CACHE_SIZE = 10
                engine.LOW_WATERMARK_CACHE_SIZE = 4
                engine.GENERATION_BATCH_SIZE = 3

                await engine.ensure_cache_after_restart()

                self.assertGreater(provider.calls, 0)
                self.assertGreaterEqual(await db.get_valid_llm_questions_count(), 4)
            finally:
                os.remove(path)

        asyncio.run(_run())

    def test_ensure_minimum_buffer_refetches_after_generation_on_empty_cache(self) -> None:
        class Provider:
            async def generate_question_batch(self, request):
                return [
                    QuestionCandidate(
                        provider_name='openai',
                        model_name='gpt-test',
                        language='ru',
                        topic='География',
                        subtopic='',
                        difficulty='medium',
                        question_type='text',
                        question_text='Столица Германии?',
                        correct_answer_text='Берлин',
                        explanation='Столица Германии — Берлин.',
                        canonical_facts=['Германия', 'Берлин'],
                        uniqueness_tags=['география'],
                        question_hash='cold-qh-1',
                        uniqueness_hash='cold-uh-1',
                    )
                ]

            def validate_question_batch(self, batch):
                return batch

        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=Provider())
                state = GameState(chat_id=12, started_by_user_id=1, question_limit=5)

                await engine.ensure_minimum_buffer(state, target_difficulty='medium')

                self.assertGreaterEqual(len(state.question_buffer), 1)
                self.assertEqual(state.question_buffer[0].source, 'llm_cache')
            finally:
                os.remove(path)

        asyncio.run(_run())

    def test_buffer_avoids_same_answer_duplicates_inside_game(self) -> None:
        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=None)
                state = GameState(chat_id=33, started_by_user_id=1, question_limit=5)

                await db.save_generated_questions(
                    [
                        QuestionCandidate(
                            provider_name='openai',
                            model_name='gpt-test',
                            language='ru',
                            topic='География',
                            subtopic='',
                            difficulty='medium',
                            question_type='text',
                            question_text='Столица Германии?',
                            correct_answer_text='Берлин',
                            explanation='Берлин — столица Германии.',
                            canonical_facts=['Германия', 'Берлин'],
                            uniqueness_tags=['geo'],
                            question_hash='ans-qh-1',
                            uniqueness_hash='ans-uh-1',
                        ),
                        QuestionCandidate(
                            provider_name='openai',
                            model_name='gpt-test',
                            language='ru',
                            topic='География',
                            subtopic='',
                            difficulty='medium',
                            question_type='text',
                            question_text='Какой город столица ФРГ?',
                            correct_answer_text='Берлин',
                            explanation='Ответ тот же: Берлин.',
                            canonical_facts=['ФРГ', 'Берлин'],
                            uniqueness_tags=['geo'],
                            question_hash='ans-qh-2',
                            uniqueness_hash='ans-uh-2',
                        ),
                    ]
                )

                await engine.ensure_minimum_buffer(state, target_difficulty='medium')
                answers = [item.answer for item in state.question_buffer]
                self.assertEqual(answers.count('Берлин'), 1)
            finally:
                os.remove(path)

        asyncio.run(_run())

    def test_buffer_relaxes_repeat_policy_when_cache_exists_but_strict_filters_exhausted(self) -> None:
        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=None)
                state = GameState(chat_id=44, started_by_user_id=1, question_limit=5)

                await db.save_generated_questions(
                    [
                        QuestionCandidate(
                            provider_name='openai',
                            model_name='gpt-test',
                            language='ru',
                            topic='География',
                            subtopic='',
                            difficulty='medium',
                            question_type='text',
                            question_text='Столица Испании?',
                            correct_answer_text='Мадрид',
                            explanation='Столица Испании — Мадрид.',
                            canonical_facts=['Испания', 'Мадрид'],
                            uniqueness_tags=['geo'],
                            question_hash='relax-qh-1',
                            uniqueness_hash='relax-uh-1',
                        )
                    ]
                )

                candidates = await db.get_candidate_questions(
                    difficulty='medium',
                    limit=5,
                    mode='classic',
                    chat_id=44,
                    local_game_date=datetime.now(timezone.utc).date().isoformat(),
                    repeat_window_days=5,
                    same_day_repeat_block_enabled=True,
                )
                self.assertEqual(len(candidates), 1)
                await db.log_question_usage(
                    QuestionUsageRecord(
                        question_id=int(candidates[0]['id']),
                        chat_id=44,
                        shown_at=datetime.now(timezone.utc).isoformat(),
                        local_game_date=datetime.now(timezone.utc).date().isoformat(),
                    )
                )

                await engine.ensure_minimum_buffer(state, target_difficulty='medium')

                self.assertGreaterEqual(len(state.question_buffer), 1)
                self.assertEqual(state.question_buffer[0].answer, 'Мадрид')
            finally:
                os.remove(path)

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
