from __future__ import annotations

import os
import unittest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')

from app.core.game_manager import GameManager
from app.core.models import GameState, PlayerScore


class _DummyDb:
    pass


class _DummyProvider:
    pass


class TeamModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = GameManager(db=_DummyDb(), question_provider=_DummyProvider())

    def test_team_lobby_allows_2v2_selection(self) -> None:
        msg1 = self.manager.set_team_choice(1, 101, 'alice', 'alpha')
        msg2 = self.manager.set_team_choice(1, 102, 'bob', 'alpha')
        msg3 = self.manager.set_team_choice(1, 103, 'carl', 'alpha')

        self.assertIn('🟥 Альфа: 1/2', msg1)
        self.assertIn('🟥 Альфа: 2/2', msg2)
        self.assertIn('уже заполнена', msg3)

    def test_score_text_contains_team_table_and_contributions(self) -> None:
        state = GameState(chat_id=7, started_by_user_id=1, question_limit=10, quiz_mode='team2v2')
        state.is_active = True
        state.team_assignments = {10: 'alpha', 11: 'alpha', 20: 'beta', 21: 'beta'}
        state.scores = {
            10: PlayerScore(user_id=10, username='alice', points=4),
            11: PlayerScore(user_id=11, username='bob', points=1),
            20: PlayerScore(user_id=20, username='neo', points=3),
            21: PlayerScore(user_id=21, username='max', points=2),
        }
        self.manager.games[7] = state

        text = self.manager.get_score_text(7)

        self.assertIn('🤝 Командный счёт', text)
        self.assertIn('🟥 Альфа — 5', text)
        self.assertIn('🟦 Бета — 5', text)
        self.assertIn('Вклад игроков', text)


if __name__ == '__main__':
    unittest.main()
