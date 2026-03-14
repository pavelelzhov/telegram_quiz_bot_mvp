from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.daily_challenge_service import DailyChallengeService


class DailyChallengeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DailyChallengeService()

    def test_resolve_local_game_date_with_invalid_timezone_falls_back(self) -> None:
        date_value = self.service.resolve_local_game_date('Invalid/Timezone')
        self.assertRegex(date_value, r'^\d{4}-\d{2}-\d{2}$')

    def test_is_timezone_supported(self) -> None:
        self.assertTrue(self.service.is_timezone_supported('UTC'))
        self.assertFalse(self.service.is_timezone_supported('Invalid/Timezone'))

    def test_fallback_works_when_zoneinfo_unavailable(self) -> None:
        with patch('app.core.daily_challenge_service.ZoneInfo', side_effect=Exception('no tzdata')):
            date_value = self.service.resolve_local_game_date('Europe/Berlin')
        self.assertRegex(date_value, r'^\d{4}-\d{2}-\d{2}$')


if __name__ == '__main__':
    unittest.main()
