from __future__ import annotations

import unittest

from app.core.adaptive_difficulty_service import AdaptiveDifficultyService


class AdaptiveDifficultyServiceTests(unittest.TestCase):
    def test_warmup_prefers_easy(self) -> None:
        service = AdaptiveDifficultyService()
        self.assertEqual(service.target_difficulty(chat_id=1, asked_count=0), 'easy')
        self.assertEqual(service.target_difficulty(chat_id=1, asked_count=2), 'easy')

    def test_hard_when_many_correct(self) -> None:
        service = AdaptiveDifficultyService()
        for _ in range(8):
            service.note_correct(1)
        self.assertEqual(service.target_difficulty(chat_id=1, asked_count=6), 'hard')

    def test_easy_when_many_wrong(self) -> None:
        service = AdaptiveDifficultyService()
        for _ in range(7):
            service.note_wrong(1)
        self.assertEqual(service.target_difficulty(chat_id=1, asked_count=6), 'easy')

    def test_medium_when_balanced(self) -> None:
        service = AdaptiveDifficultyService()
        for _ in range(4):
            service.note_correct(1)
            service.note_wrong(1)
        self.assertEqual(service.target_difficulty(chat_id=1, asked_count=6), 'medium')


if __name__ == '__main__':
    unittest.main()

