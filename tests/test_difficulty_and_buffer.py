from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from app.core.difficulty_service import DifficultyService
from app.core.models import GameState, PlayerSkillSnapshot, QuestionCandidate
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
            finally:
                os.remove(path)

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
