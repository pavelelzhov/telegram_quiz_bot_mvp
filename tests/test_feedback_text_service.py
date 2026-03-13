from __future__ import annotations

import unittest

from app.core.feedback_text_service import FeedbackTextService
from app.core.models import QuizQuestion


class FeedbackTextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FeedbackTextService()

    def _q(self, qtype: str) -> QuizQuestion:
        return QuizQuestion(
            category='Общие',
            difficulty='easy',
            question='?',
            answer='a',
            aliases=['a'],
            hint='h',
            explanation='e',
            question_type=qtype,
        )

    def test_wrong_text_prefixes_by_round_type(self) -> None:
        audio_text = self.service.wrong_answer_text('alice', self._q('audio'))
        image_text = self.service.wrong_answer_text('alice', self._q('image'))
        plain_text = self.service.wrong_answer_text('alice', self._q('text'))

        self.assertIn('@alice', audio_text)
        self.assertIn('@alice', image_text)
        self.assertIn('@alice', plain_text)

    def test_near_miss_text_prefixes_by_round_type(self) -> None:
        audio_text = self.service.near_miss_text('bob', self._q('audio'))
        image_text = self.service.near_miss_text('bob', self._q('image'))
        plain_text = self.service.near_miss_text('bob', self._q('text'))

        self.assertIn('@bob', audio_text)
        self.assertIn('@bob', image_text)
        self.assertIn('@bob', plain_text)


if __name__ == '__main__':
    unittest.main()
