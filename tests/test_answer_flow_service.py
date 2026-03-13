from __future__ import annotations

import unittest

from app.core.answer_flow_service import AnswerFlowService
from app.core.models import GameState, QuizQuestion


class AnswerFlowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AnswerFlowService()
        self.state = GameState(chat_id=1, started_by_user_id=1, question_limit=10)
        self.state.current_question = QuizQuestion(
            category='Общие',
            difficulty='easy',
            question='Столица Франции?',
            answer='Париж',
            aliases=['Paris'],
            hint='Город любви',
            explanation='Париж — столица Франции.',
            point_value=2,
        )

    def test_register_wrong_attempt_with_limit(self) -> None:
        self.assertTrue(self.service.register_wrong_attempt(self.state, 1))
        self.assertFalse(self.service.register_wrong_attempt(self.state, 1))
        self.assertTrue(self.service.register_wrong_attempt(self.state, 2))
        self.assertTrue(self.service.register_wrong_attempt(self.state, 3))
        self.assertFalse(self.service.register_wrong_attempt(self.state, 4))

    def test_register_close_attempt_once_per_user(self) -> None:
        self.assertTrue(self.service.register_close_attempt(self.state, 11))
        self.assertFalse(self.service.register_close_attempt(self.state, 11))

    def test_register_correct_updates_score_and_streak(self) -> None:
        points, streak = self.service.register_correct_answer(self.state, 7, 'alice')
        self.assertEqual(points, 2)
        self.assertEqual(streak, 1)
        self.assertEqual(self.state.scores[7].points, 2)

        points2, streak2 = self.service.register_correct_answer(self.state, 7, 'alice')
        self.assertEqual(points2, 2)
        self.assertEqual(streak2, 2)
        self.assertEqual(self.state.scores[7].points, 4)

    def test_build_correct_answer_text(self) -> None:
        text = self.service.build_correct_answer_text(
            username='alice',
            question=self.state.current_question,
            points_awarded=2,
            streak_count=2,
            leader_line='\n🏁 Лидер сейчас: @alice — 2',
        )
        self.assertIn('✅ Правильно! @alice', text)
        self.assertIn('💠 За этот вопрос: +2 SP', text)
        self.assertIn('🔥 Серия @alice: 2 подряд!', text)


if __name__ == '__main__':
    unittest.main()
