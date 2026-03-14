from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from app.core.models import PlayerSkillSnapshot, QuestionCandidate, QuestionUsageRecord
from app.storage.db import Database


class LlmQuizDbTests(unittest.TestCase):
    def test_tables_and_basic_ops(self) -> None:
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
                        topic='Наука',
                        subtopic='Физика',
                        difficulty='medium',
                        question_type='text',
                        question_text='Сколько планет в Солнечной системе?',
                        correct_answer_text='8',
                        explanation='Сейчас принято 8.',
                        canonical_facts=['8 планет'],
                        question_hash='qh1',
                        uniqueness_hash='uh1',
                    )
                ]
                inserted = await db.save_generated_questions(batch)
                self.assertEqual(inserted, 1)


                import aiosqlite
                async with aiosqlite.connect(path) as conn:
                    async with conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='llm_questions'") as cur:
                        idx_rows = await cur.fetchall()
                idx_names = {row[0] for row in idx_rows}
                self.assertIn('idx_llm_questions_question_hash', idx_names)
                self.assertIn('idx_llm_questions_uniqueness_hash', idx_names)

                candidates = await db.get_candidate_questions('medium', limit=5)
                self.assertGreaterEqual(len(candidates), 1)


                found = await db.find_question_by_hashes('qh1', 'uh1')
                self.assertIsNotNone(found)
                self.assertEqual(found['question_hash'], 'qh1')

                await db.log_question_usage(
                    QuestionUsageRecord(
                        question_id=candidates[0]['id'],
                        chat_id=1,
                        player_id=42,
                        shown_at='2026-01-01T00:00:00+00:00',
                        answered_at='2026-01-01T00:00:05+00:00',
                        was_correct=True,
                        response_ms=5000,
                        local_game_date='2026-01-01',
                    )
                )
                usage = await db.get_recent_question_usage_for_player(42, days=3650)
                self.assertEqual(len(usage), 1)

                snapshot = PlayerSkillSnapshot(player_id=42, global_skill_score=0.5, current_band='medium')
                await db.upsert_player_skill_profile(snapshot)
                loaded = await db.get_player_skill_profile(42)
                self.assertEqual(loaded.current_band, 'medium')
            finally:
                os.remove(path)

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
