from __future__ import annotations

import unittest
import os

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')

from app.core.game_manager import GameManager


class _DummyDb:
    pass


class _DummyProvider:
    pass


class GameProfileSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = GameManager(db=_DummyDb(), question_provider=_DummyProvider())

    def test_default_profile_is_standard(self) -> None:
        self.assertEqual(self.manager.get_game_profile(1), 'standard')
        self.assertIn('🎯 standard', self.manager.get_status_text(1))

    def test_set_game_profile_accepts_only_known_values(self) -> None:
        self.assertTrue(self.manager.set_game_profile(1, 'casual'))
        self.assertEqual(self.manager.get_game_profile(1), 'casual')

        self.assertFalse(self.manager.set_game_profile(1, 'unknown'))
        self.assertEqual(self.manager.get_game_profile(1), 'casual')


if __name__ == '__main__':
    unittest.main()
