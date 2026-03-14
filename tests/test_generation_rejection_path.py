from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

import aiosqlite

from app.core.models import GameState, QuestionCandidate
from app.core.quiz_engine_service import QuizEngineService
from app.storage.db import Database


class GenerationRejectionPathTests(unittest.TestCase):
    def test_duplicates_in_batch_go_to_rejection_log(self) -> None:
        class DummyProvider:
            def validate_question_batch(self, candidates):
                return candidates

            async def generate_question_batch(self, request):
                return [
                    QuestionCandidate(
                        provider_name='openai',
                        model_name='gpt',
                        language='ru',
                        topic='История',
                        subtopic='Космос',
                        difficulty='medium',
                        question_type='text',
                        question_text='Кто первым полетел в космос?',
                        correct_answer_text='Юрий Гагарин',
                        explanation='Первый космонавт.',
                        canonical_facts=['Первый человек в космосе'],
                        question_hash='qh-dup',
                        uniqueness_hash='uh-dup',
                    ),
                    QuestionCandidate(
                        provider_name='openai',
                        model_name='gpt',
                        language='ru',
                        topic='История',
                        subtopic='Космос',
                        difficulty='medium',
                        question_type='text',
                        question_text='Назовите первого человека в космосе',
                        correct_answer_text='Юрий Гагарин',
                        explanation='Первый космонавт.',
                        canonical_facts=['Первый человек в космосе'],
                        question_hash='qh-dup',
                        uniqueness_hash='uh-dup',
                    ),
                ]

        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()
                engine = QuizEngineService(db=db, llm_provider=DummyProvider())
                state = GameState(chat_id=1, started_by_user_id=1, question_limit=5)

                await engine.request_generation_if_buffer_low(state)

                async with aiosqlite.connect(path) as conn:
                    async with conn.execute('SELECT COUNT(*) FROM llm_questions') as cur:
                        saved_count = (await cur.fetchone())[0]
                    async with conn.execute('SELECT COUNT(*) FROM question_rejection_log') as cur:
                        rejection_count = (await cur.fetchone())[0]

                self.assertEqual(saved_count, 1)
                self.assertGreaterEqual(rejection_count, 1)
            finally:
                os.remove(path)

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
