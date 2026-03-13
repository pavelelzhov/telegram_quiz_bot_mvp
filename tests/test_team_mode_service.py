from __future__ import annotations

import unittest

from app.core.models import GameState, PlayerScore
from app.core.team_mode_service import TeamModeService


class TeamModeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TeamModeService()

    def test_build_team_assignments_requires_full_lobby(self) -> None:
        self.service.set_team_choice(1, 10, 'alice', 'alpha')
        self.assertIsNone(self.service.build_team_assignments(1))

        self.service.set_team_choice(1, 11, 'bob', 'alpha')
        self.service.set_team_choice(1, 20, 'neo', 'beta')
        self.service.set_team_choice(1, 21, 'max', 'beta')

        assignments = self.service.build_team_assignments(1)
        self.assertIsNotNone(assignments)
        assert assignments is not None
        self.assertEqual(assignments[10], 'alpha')
        self.assertEqual(assignments[21], 'beta')

    def test_team_score_lines_contains_team_totals(self) -> None:
        state = GameState(chat_id=1, started_by_user_id=1, question_limit=10, quiz_mode='team2v2')
        state.team_assignments = {10: 'alpha', 20: 'beta'}
        state.scores = {
            10: PlayerScore(user_id=10, username='alice', points=4),
            20: PlayerScore(user_id=20, username='neo', points=2),
        }

        lines = self.service.team_score_lines(state)

        text = '\n'.join(lines)
        self.assertIn('🟥 Альфа — 4', text)
        self.assertIn('🟦 Бета — 2', text)


if __name__ == '__main__':
    unittest.main()
