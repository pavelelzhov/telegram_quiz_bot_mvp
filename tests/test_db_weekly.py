from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.storage.db import Database


class WeeklyStatsDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.db = Database(path=f'{self.tmp_dir.name}/quiz.db')
        await self.db.init()

    async def asyncTearDown(self) -> None:
        self.tmp_dir.cleanup()

    async def test_weekly_top_isolated_by_week(self) -> None:
        await self.db.save_game_result(
            chat_id=1,
            finished_at='2026-03-17T12:00:00+00:00',
            quiz_mode='classic',
            winner_user_id=10,
            winner_username='alice',
            winner_points=5,
            total_questions=10,
            all_scores=[(10, 'alice', 5), (11, 'bob', 3)],
        )
        await self.db.save_game_result(
            chat_id=1,
            finished_at='2026-03-25T12:00:00+00:00',
            quiz_mode='classic',
            winner_user_id=11,
            winner_username='bob',
            winner_points=7,
            total_questions=10,
            all_scores=[(11, 'bob', 7), (10, 'alice', 2)],
        )

        week1 = await self.db.get_weekly_top_players(1, now_iso='2026-03-17T22:00:00+00:00')
        week2 = await self.db.get_weekly_top_players(1, now_iso='2026-03-25T22:00:00+00:00')

        self.assertEqual(week1[0][0], 'alice')
        self.assertEqual(week1[0][1], 5)
        self.assertEqual(week2[0][0], 'bob')
        self.assertEqual(week2[0][1], 7)

    async def test_weekly_stats_do_not_break_global_top(self) -> None:
        await self.db.save_game_result(
            chat_id=1,
            finished_at='2026-03-17T12:00:00+00:00',
            quiz_mode='classic',
            winner_user_id=10,
            winner_username='alice',
            winner_points=5,
            total_questions=10,
            all_scores=[(10, 'alice', 5)],
        )
        await self.db.save_game_result(
            chat_id=1,
            finished_at='2026-03-24T12:00:00+00:00',
            quiz_mode='classic',
            winner_user_id=10,
            winner_username='alice',
            winner_points=4,
            total_questions=10,
            all_scores=[(10, 'alice', 4)],
        )

        global_top = await self.db.get_top_players(1)
        weekly_top = await self.db.get_weekly_top_players(1, now_iso='2026-03-24T22:00:00+00:00')

        self.assertEqual(global_top[0][0], 'alice')
        self.assertEqual(global_top[0][1], 9)
        self.assertEqual(weekly_top[0][1], 4)


if __name__ == '__main__':
    unittest.main()
