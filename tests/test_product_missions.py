from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.quiz.product_store import ProductStore


class ProductMissionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.store = ProductStore(path=f'{self.tmp_dir.name}/quiz_product.db')
        await self.store.ensure_initialized()

    async def asyncTearDown(self) -> None:
        self.tmp_dir.cleanup()

    async def test_profile_contains_missions_progress(self) -> None:
        await self.store.note_match_result(
            chat_id=1,
            ranking=[(10, 'alice', 4), (11, 'bob', 2)],
        )
        for streak in [1, 2, 3]:
            await self.store.note_correct(
                chat_id=1,
                user_id=10,
                username='alice',
                points=1,
                streak_count=streak,
            )

        text = await self.store.get_player_text(chat_id=1, user_id=10, username='alice')

        self.assertIn('🎯 Миссии:', text)
        self.assertIn('Сыграть 5 матчей', text)
        self.assertIn('Взять серию x3', text)

    async def test_missions_have_completion_marks(self) -> None:
        for _ in range(5):
            await self.store.note_match_result(
                chat_id=1,
                ranking=[(20, 'max', 3), (21, 'neo', 1)],
            )
        for streak in [1, 2, 3, 4, 5]:
            await self.store.note_correct(
                chat_id=1,
                user_id=20,
                username='max',
                points=1,
                streak_count=streak,
            )

        text = await self.store.get_player_text(chat_id=1, user_id=20, username='max')
        done_count = text.count('✅')

        self.assertGreaterEqual(done_count, 4)

    async def test_mission_rewards_do_not_add_extra_season_points(self) -> None:
        for _ in range(5):
            await self.store.note_match_result(
                chat_id=2,
                ranking=[(30, 'luna', 4), (31, 'sam', 1)],
            )

        player_before = await self.store._get_player(chat_id=2, user_id=30, username='luna')
        self.assertEqual(int(player_before['season_points']), 30)

        text = await self.store.get_player_text(chat_id=2, user_id=30, username='luna')
        self.assertIn('🎁 Награды за миссии: только ачивки и титулы (без SP).', text)
        self.assertIn('🎁 Миссия: сыграть 5 матчей', text)

        player_after = await self.store._get_player(chat_id=2, user_id=30, username='luna')
        self.assertEqual(int(player_after['season_points']), 30)


if __name__ == '__main__':
    unittest.main()
