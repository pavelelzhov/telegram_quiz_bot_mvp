from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from app.core.difficulty_service import DifficultyService
from app.core.models import GameState, PlayerSkillSnapshot
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


if __name__ == '__main__':
    unittest.main()
