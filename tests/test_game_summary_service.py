from __future__ import annotations

import unittest

from app.core.game_summary_service import GameSummaryService
from app.core.models import PlayerScore


class GameSummaryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GameSummaryService()

    def test_build_ranking(self) -> None:
        ranking = self.service.build_ranking(
            [
                PlayerScore(user_id=1, username='bob', points=5),
                PlayerScore(user_id=2, username='alice', points=5),
                PlayerScore(user_id=3, username='zoe', points=3),
            ]
        )
        self.assertEqual([p.username for p in ranking], ['alice', 'bob', 'zoe'])

    def test_build_summary_lines_with_winner_and_team_lines(self) -> None:
        ranking = [
            PlayerScore(user_id=1, username='alice', points=8),
            PlayerScore(user_id=2, username='bob', points=6),
        ]
        lines = self.service.build_summary_lines(
            ranking=ranking,
            mode_label='👥 Командный 2v2',
            team_score_lines=['🟥 Alpha: 8', '🟦 Beta: 6'],
        )
        text = '\n'.join(lines)
        self.assertIn('Режим: 👥 Командный 2v2', text)
        self.assertIn('1. @alice — 8', text)
        self.assertIn('🟥 Alpha: 8', text)
        self.assertIn('👑 Победитель: @alice', text)

    def test_build_summary_lines_no_scores(self) -> None:
        lines = self.service.build_summary_lines(ranking=[], mode_label='🎯 Классика')
        self.assertEqual(lines, ['🏁 Игра завершена!', '', 'Никто не набрал очков.'])


if __name__ == '__main__':
    unittest.main()
