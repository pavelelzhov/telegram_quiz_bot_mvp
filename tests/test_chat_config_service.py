from __future__ import annotations

import os
import unittest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')

from app.core.chat_config_service import ChatConfigService


class ChatConfigServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChatConfigService()

    def test_profile_and_timeout_controls(self) -> None:
        self.assertEqual(self.service.get_game_profile(1), 'standard')
        self.assertTrue(self.service.set_game_profile(1, 'casual'))
        self.assertEqual(self.service.get_game_profile(1), 'casual')
        self.assertFalse(self.service.set_game_profile(1, 'bad'))

        current = self.service.get_chat_settings(1).question_timeout_sec
        next_value = self.service.cycle_timeout(1)
        self.assertNotEqual(current, next_value)

    def test_preferred_category_and_text(self) -> None:
        self.service.set_preferred_category(7, 'Наука')
        text = self.service.build_settings_text(7, '🎯 standard')
        self.assertIn('Тема по умолчанию: Наука', text)
        self.assertIn('Профиль игры: 🎯 standard', text)


if __name__ == '__main__':
    unittest.main()
