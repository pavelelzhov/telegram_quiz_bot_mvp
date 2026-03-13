from __future__ import annotations

import unittest

from app.core.chat_participation_service import ChatParticipationService


class ChatParticipationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatParticipationService()

    def test_resolve_cooldown(self) -> None:
        self.assertEqual(self.service.resolve_cooldown(addressed=True, host_mode_enabled=False), 8.0)
        self.assertEqual(self.service.resolve_cooldown(addressed=False, host_mode_enabled=True), 35.0)
        self.assertIsNone(self.service.resolve_cooldown(addressed=False, host_mode_enabled=False))

    def test_passive_filters_happy_path(self) -> None:
        ok = self.service.passes_passive_reply_filters(
            recent_unique_users=3,
            recent_messages=7,
            text='достаточно длинный текст для ответа',
            random_value=0.10,
        )
        self.assertTrue(ok)

    def test_passive_filters_reject_cases(self) -> None:
        self.assertFalse(
            self.service.passes_passive_reply_filters(
                recent_unique_users=1,
                recent_messages=7,
                text='достаточно длинный текст для ответа',
                random_value=0.10,
            )
        )
        self.assertFalse(
            self.service.passes_passive_reply_filters(
                recent_unique_users=3,
                recent_messages=4,
                text='достаточно длинный текст для ответа',
                random_value=0.10,
            )
        )
        self.assertFalse(
            self.service.passes_passive_reply_filters(
                recent_unique_users=3,
                recent_messages=7,
                text='коротко',
                random_value=0.10,
            )
        )
        self.assertFalse(
            self.service.passes_passive_reply_filters(
                recent_unique_users=3,
                recent_messages=7,
                text='достаточно длинный текст для ответа',
                random_value=0.50,
            )
        )


if __name__ == '__main__':
    unittest.main()
