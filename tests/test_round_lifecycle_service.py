from __future__ import annotations

import unittest

from app.core.models import GameState, QuizQuestion
from app.core.round_lifecycle_service import RoundLifecycleService


class RoundLifecycleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoundLifecycleService()

    def _question(self, *, source: str = 'llm', point_value: int = 1) -> QuizQuestion:
        return QuizQuestion(
            category='История',
            topic='Рим',
            difficulty='medium',
            question='Кто был первым императором Рима?',
            answer='Октавиан Август',
            aliases=['Август'],
            hint='Принцепс',
            explanation='Октавиан получил титул Август.',
            source=source,
            point_value=point_value,
        )

    def test_source_labels(self) -> None:
        self.assertEqual(self.service.source_label(self._question(source='llm')), 'ИИ')
        self.assertEqual(self.service.source_label(self._question(source='image_pool')), 'картинка')
        self.assertEqual(self.service.source_label(self._question(source='music_pool')), 'музыка')
        self.assertEqual(self.service.source_label(self._question(source='fallback')), 'резерв')

    def test_build_header_with_multiplier(self) -> None:
        state = GameState(chat_id=1, started_by_user_id=1, question_limit=10, asked_count=4)
        question = self._question(point_value=3)

        text = self.service.build_question_header(state, question)

        self.assertIn('❓ Вопрос 4/10', text)
        self.assertIn('Источник: ИИ', text)
        self.assertIn('💠 Цена вопроса: x3', text)

    def test_timeout_text(self) -> None:
        question = self._question()
        text = self.service.build_timeout_text(question)
        self.assertIn('⌛ Время вышло.', text)
        self.assertIn('Правильный ответ: Октавиан Август', text)


if __name__ == '__main__':
    unittest.main()
