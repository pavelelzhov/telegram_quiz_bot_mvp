from __future__ import annotations

import unittest

from app.core.leaderboard_service import LeaderboardService


class LeaderboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LeaderboardService()

    def test_format_chat_top_empty(self) -> None:
        self.assertEqual(self.service.format_chat_top([]), 'Пока статистики по этому чату нет.')

    def test_format_chat_top_rows(self) -> None:
        text = self.service.format_chat_top([
            ('alice', 12, 3, 5),
            ('bob', 8, 1, 4),
        ])
        self.assertIn('📈 Топ игроков чата:', text)
        self.assertIn('1. @alice — очки: 12, победы: 3, игр: 5', text)

    def test_format_weekly_top_empty(self) -> None:
        self.assertEqual(self.service.format_weekly_top([]), 'За эту неделю пока нет результатов.')

    def test_format_weekly_top_rows(self) -> None:
        text = self.service.format_weekly_top([
            ('alice', 7, 2, 3),
        ])
        self.assertIn('🗓 Недельный топ игроков:', text)
        self.assertIn('1. @alice — очки: 7, победы: 2, игр: 3', text)


if __name__ == '__main__':
    unittest.main()
