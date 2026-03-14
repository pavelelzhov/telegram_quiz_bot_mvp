from __future__ import annotations

import unittest

from app.core.models import QuestionCandidate
from app.core.question_dedup_service import QuestionDedupService


class QuestionDedupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QuestionDedupService()

    def _candidate(self, question: str, answer: str, facts: list[str]) -> QuestionCandidate:
        item = QuestionCandidate(
            provider_name='x',
            model_name='x',
            language='ru',
            topic='История',
            subtopic='Космос',
            difficulty='medium',
            question_type='text',
            question_text=question,
            correct_answer_text=answer,
            explanation='ok',
            canonical_facts=facts,
        )
        item.question_hash = self.service.question_hash(item)
        item.uniqueness_hash = self.service.uniqueness_hash(item)
        return item

    def test_exact_duplicate_detected(self) -> None:
        one = self._candidate('Кто был первым в космосе?', 'Юрий Гагарин', ['Первый человек в космосе'])
        two = self._candidate('Кто был первым в космосе?', 'Юрий Гагарин', ['Первый человек в космосе'])
        self.assertTrue(self.service.has_duplicate(two, {one.question_hash}, {one.uniqueness_hash}))

    def test_paraphrase_duplicate_detected_by_uniqueness(self) -> None:
        one = self._candidate('Назовите первого человека в космосе', 'Юрий Гагарин', ['Первый человек в космосе'])
        two = self._candidate('Кто первым полетел в космос?', 'Юрий Гагарин', ['Первый человек в космосе'])
        self.assertEqual(one.uniqueness_hash, two.uniqueness_hash)


if __name__ == '__main__':
    unittest.main()
