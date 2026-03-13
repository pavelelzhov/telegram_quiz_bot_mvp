from __future__ import annotations

import unittest

from app.core.last_game_service import LastGameService
from app.core.quiz_engine_service import QuizEngineService


class LastGameServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LastGameService(QuizEngineService())

    def test_fallback_without_data(self) -> None:
        text = self.service.format_last_game_text(None)
        self.assertIn('пока нет завершённых игр', text)

    def test_formats_mode_and_winner(self) -> None:
        text = self.service.format_last_game_text(
            {
                'id': 1,
                'quiz_mode': 'team2v2',
                'finished_at': '2026-01-01T00:00:00Z',
                'winner_username': 'alice',
                'winner_points': 7,
                'total_questions': 10,
            }
        )
        self.assertIn('🤝 Командный 2v2', text)
        self.assertIn('@alice', text)


if __name__ == '__main__':
    unittest.main()
