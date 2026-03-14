from __future__ import annotations

import unittest

from app.agent.agent_reply_provider import AgentReplyProvider


class AgentReplyProviderTemperatureTests(unittest.TestCase):
    def test_mode_specific_temperatures(self) -> None:
        provider = object.__new__(AgentReplyProvider)

        self.assertEqual(provider.resolve_temperature(mode='warm_support', sharpness_ceiling='medium'), 0.45)
        self.assertEqual(provider.resolve_temperature(mode='quiz_safe_mode', sharpness_ceiling='high'), 0.45)
        self.assertEqual(provider.resolve_temperature(mode='micro_reaction', sharpness_ceiling='low'), 0.75)
        self.assertEqual(provider.resolve_temperature(mode='initiative_topic_drop', sharpness_ceiling='low'), 0.75)
        self.assertEqual(provider.resolve_temperature(mode='pushback', sharpness_ceiling='low'), 0.65)

    def test_fallback_temperatures_by_sharpness(self) -> None:
        provider = object.__new__(AgentReplyProvider)

        self.assertEqual(provider.resolve_temperature(mode='addressed_reply', sharpness_ceiling='low'), 0.5)
        self.assertEqual(provider.resolve_temperature(mode='addressed_reply', sharpness_ceiling='high'), 0.9)
        self.assertEqual(provider.resolve_temperature(mode='addressed_reply', sharpness_ceiling='medium'), 0.8)


if __name__ == '__main__':
    unittest.main()
