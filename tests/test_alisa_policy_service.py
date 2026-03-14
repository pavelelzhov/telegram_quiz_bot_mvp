from __future__ import annotations

import time
import unittest

from app.core.alisa_policy import (
    AddressingPolicyService,
    AddressingDecision,
    ParticipationDecisionService,
    ReplyValidationService,
)


class AddressingPolicyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AddressingPolicyService()

    def test_name_detection(self) -> None:
        decision = self.service.evaluate(text='Алиса, привет', is_reply_to_alisa=False, has_bot_mention=False)
        self.assertTrue(decision.is_addressed)
        self.assertEqual(decision.addressed_by, 'name')
        self.assertIn('addressed_by_name', decision.reason_codes)

    def test_reply_priority(self) -> None:
        decision = self.service.evaluate(text='что скажешь', is_reply_to_alisa=True, has_bot_mention=True)
        self.assertTrue(decision.is_addressed)
        self.assertEqual(decision.addressed_by, 'reply')
        self.assertIn('addressed_by_reply', decision.reason_codes)

    def test_generic_trigger_is_blocked(self) -> None:
        decision = self.service.evaluate(text='бот, ответь', is_reply_to_alisa=False, has_bot_mention=False)
        self.assertFalse(decision.is_addressed)
        self.assertIn('suppressed_generic_trigger', decision.reason_codes)


class ParticipationDecisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ParticipationDecisionService()

    def test_reply_when_addressed(self) -> None:
        decision = self.service.decide(
            chat_id=1,
            addressed=AddressingDecision(True, 'name', ['addressed_by_name']),
            quiz_active=False,
        )
        self.assertTrue(decision.should_reply)

    def test_cooldown(self) -> None:
        self.service.last_reply_ts[1] = time.time()
        decision = self.service.decide(
            chat_id=1,
            addressed=AddressingDecision(True, 'name', ['addressed_by_name']),
            quiz_active=False,
        )
        self.assertFalse(decision.should_reply)
        self.assertIn('suppressed_cooldown', decision.reason_codes)


class ReplyValidationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReplyValidationService()

    def test_banned_phrase_rejected(self) -> None:
        text, reasons, _ = self.service.validate_and_clamp(
            text='Как ИИ, я не могу это сделать.',
            mode='addressed_reply',
            quiz_active=False,
        )
        self.assertEqual(text, '')
        self.assertIn('suppressed_ai_phrase', reasons)

    def test_length_clamp(self) -> None:
        candidate = 'Очень длинный ответ. ' * 30
        text, reasons, rewritten = self.service.validate_and_clamp(
            text=candidate,
            mode='addressed_reply',
            quiz_active=False,
        )
        self.assertTrue(text)
        self.assertTrue(rewritten)
        self.assertTrue(any(reason.startswith('clamped_') for reason in reasons))


if __name__ == '__main__':
    unittest.main()
