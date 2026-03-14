from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from app.core.models import QuestionCandidate, QuestionSelectionContext, QuestionUsageRecord
from app.core.quiz_engine_service import QuizEngineService
from app.storage.db import Database


class RepeatWindowPolicyTests(unittest.TestCase):
    def test_repeat_policy_for_chat_and_player_windows(self) -> None:
        async def _run() -> None:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            try:
                db = Database(path)
                await db.init()

                batch = [
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
                        question_hash='qh-repeat',
                        uniqueness_hash='uh-repeat',
                    )
                ]
                await db.save_generated_questions(batch)
                rows = await db.get_candidate_questions('medium', 5)
                candidate = rows[0]


                await db.log_question_usage(
                    record=QuestionUsageRecord(
                        question_id=candidate['id'],
                        chat_id=100,
                        player_id=500,
                        shown_at='2026-02-10T12:00:00+00:00',
                        answered_at='2026-02-10T12:00:04+00:00',
                        was_correct=True,
                        response_ms=4000,
                        local_game_date='2026-02-10',
                    )
                )

                sql_filtered = await db.get_candidate_questions(
                    'medium',
                    5,
                    chat_id=100,
                    player_id=500,
                    local_game_date='2026-02-10',
                    repeat_window_days=3650,
                    same_day_repeat_block_enabled=True,
                )
                self.assertEqual(sql_filtered, [])

                engine = QuizEngineService(db=db, llm_provider=None)
                ctx_today = QuestionSelectionContext(
                    chat_id=100,
                    player_id=500,
                    local_game_date='2026-02-10',
                    repeat_window_days=3650,
                    same_day_repeat_block_enabled=True,
                )
                filtered_today = await engine.filter_repeated_questions(rows, ctx_today)
                self.assertEqual(filtered_today, [])

                ctx_other_day = QuestionSelectionContext(
                    chat_id=100,
                    player_id=500,
                    local_game_date='2026-02-11',
                    repeat_window_days=3650,
                    same_day_repeat_block_enabled=True,
                )
                filtered_window = await engine.filter_repeated_questions(rows, ctx_other_day)
                self.assertEqual(filtered_window, [])
            finally:
                os.remove(path)

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
