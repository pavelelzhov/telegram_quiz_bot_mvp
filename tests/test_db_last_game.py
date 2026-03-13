from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.storage.db import Database


class LastGameDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.db = Database(path=f'{self.tmp_dir.name}/quiz.db')
        await self.db.init()

    async def asyncTearDown(self) -> None:
        self.tmp_dir.cleanup()

    async def test_get_last_game_result_returns_latest_row(self) -> None:
        await self.db.save_game_result(
            chat_id=10,
            finished_at='2026-03-25T12:00:00+00:00',
            quiz_mode='classic',
            winner_user_id=1,
            winner_username='alice',
            winner_points=5,
            total_questions=10,
            all_scores=[(1, 'alice', 5)],
        )
        await self.db.save_game_result(
            chat_id=10,
            finished_at='2026-03-26T12:00:00+00:00',
            quiz_mode='team2v2',
            winner_user_id=2,
            winner_username='bob',
            winner_points=6,
            total_questions=10,
            all_scores=[(2, 'bob', 6)],
        )

        result = await self.db.get_last_game_result(10)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result['winner_username'], 'bob')
        self.assertEqual(result['quiz_mode'], 'team2v2')


if __name__ == '__main__':
    unittest.main()
