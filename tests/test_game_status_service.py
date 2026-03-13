from __future__ import annotations

import unittest

from app.core.game_status_service import GameStatusService
from app.core.models import ChatSettings, GameState, PlayerScore


class GameStatusServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GameStatusService()

    def test_build_score_text_for_inactive_game(self) -> None:
        text = self.service.build_score_text(state=None, mode_label='🎯 Классика')
        self.assertEqual(text, 'Сейчас нет активной игры.')

    def test_build_score_text_with_team_lines(self) -> None:
        state = GameState(chat_id=1, started_by_user_id=1, question_limit=10, quiz_mode='team2v2')
        state.scores = {
            2: PlayerScore(user_id=2, username='bob', points=4),
            1: PlayerScore(user_id=1, username='alice', points=5),
        }
        text = self.service.build_score_text(
            state=state,
            mode_label='👥 Командный 2v2',
            team_score_lines=['🟥 Alpha: 5', '🟦 Beta: 4'],
        )
        self.assertIn('1. @alice — 5', text)
        self.assertIn('🟥 Alpha: 5', text)

    def test_build_status_text_for_inactive_game(self) -> None:
        cfg = ChatSettings()
        text = self.service.build_status_text(
            cfg=cfg,
            state=None,
            game_profile_label='🧭 Standard',
            preferred_category='mix',
            timer_seconds=30,
        )
        self.assertIn('Сейчас нет активной игры.', text)
        self.assertIn('Тема для следующей игры: mix', text)

    def test_build_status_text_for_active_game(self) -> None:
        cfg = ChatSettings()
        state = GameState(
            chat_id=1,
            started_by_user_id=1,
            question_limit=10,
            asked_count=3,
            preferred_category='history',
            quiz_mode='team2v2',
        )
        state.scores = {1: PlayerScore(user_id=1, username='alice', points=4)}

        text = self.service.build_status_text(
            cfg=cfg,
            state=state,
            game_profile_label='🧭 Standard',
            preferred_category='mix',
            timer_seconds=25,
            mode_label='👥 Командный 2v2',
            team_score_lines=['🟥 Alpha: 4', '🟦 Beta: 0'],
        )
        self.assertIn('Режим: 👥 Командный 2v2', text)
        self.assertIn('Вопросов выдано: 3/10', text)
        self.assertIn('🟥 Alpha: 4', text)


if __name__ == '__main__':
    unittest.main()
