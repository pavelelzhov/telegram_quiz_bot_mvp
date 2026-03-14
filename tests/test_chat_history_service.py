from __future__ import annotations

import unittest

from app.core.chat_history_service import ChatHistoryService


class ChatHistoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatHistoryService(max_items=2)

    def test_remember_and_limit(self) -> None:
        self.service.remember_message(1, 'user', 'u1', 'first', author_id=10, addressed_to_alisa=True)
        self.service.remember_message(1, 'assistant', 'bot', 'second', author_id=20)
        self.service.remember_message(1, 'user', 'u2', 'third', author_id=30)

        history = self.service.get_history(1)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['text'], 'second')
        self.assertEqual(history[1]['text'], 'third')
        self.assertEqual(history[1]['author_id'], 30)

    def test_empty_text_is_ignored(self) -> None:
        self.service.remember_message(1, 'user', 'u1', '   ', author_id=10)
        self.assertEqual(self.service.get_history(1), [])

    def test_cooldown_tracking(self) -> None:
        self.assertTrue(self.service.can_reply(1, now_ts=100.0, cooldown_sec=8.0))
        self.service.mark_reply(1, now_ts=100.0)
        self.assertFalse(self.service.can_reply(1, now_ts=105.0, cooldown_sec=8.0))
        self.assertTrue(self.service.can_reply(1, now_ts=109.0, cooldown_sec=8.0))


if __name__ == '__main__':
    unittest.main()
