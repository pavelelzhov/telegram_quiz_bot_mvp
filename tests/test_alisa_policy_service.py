from __future__ import annotations

import time
import unittest

from app.core.alisa_policy import (
    AddressingDecision,
    AddressingPolicyService,
    InitiativeService,
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
            user_id=10,
            addressed=AddressingDecision(True, 'name', ['addressed_by_name']),
            quiz_active=False,
            recent_messages=0,
            recent_unique_users=0,
            tension_level=0.0,
        )
        self.assertTrue(decision.should_reply)

    def test_cooldown(self) -> None:
        self.service.last_reply_ts[1] = time.time()
        decision = self.service.decide(
            chat_id=1,
            user_id=10,
            addressed=AddressingDecision(True, 'name', ['addressed_by_name']),
            quiz_active=False,
            recent_messages=0,
            recent_unique_users=0,
            tension_level=0.0,
        )
        self.assertFalse(decision.should_reply)
        self.assertIn('suppressed_cooldown', decision.reason_codes)

    def test_quiz_mode_suppression_reason(self) -> None:
        decision = self.service.decide(
            chat_id=42,
            user_id=12,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=True,
            recent_messages=0,
            recent_unique_users=0,
            tension_level=0.0,
        )
        self.assertFalse(decision.should_reply)
        self.assertIn('suppressed_quiz_mode', decision.reason_codes)

    def test_followup_window_allows_short_next_message(self) -> None:
        now = time.time()
        self.service.last_addressed_user_ts[(99, 501)] = now
        decision = self.service.decide(
            chat_id=99,
            user_id=501,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=False,
            recent_messages=1,
            recent_unique_users=1,
            tension_level=0.0,
            now_ts=now + 5,
        )
        self.assertTrue(decision.should_reply)
        self.assertIn('addressed_followup_window', decision.reason_codes)

    def test_chat_followup_window_allows_other_user_in_group_dialogue(self) -> None:
        now = time.time()
        self.service.last_addressed_chat_ts[50] = now
        decision = self.service.decide(
            chat_id=50,
            user_id=777,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=False,
            recent_messages=8,
            recent_unique_users=3,
            tension_level=0.1,
            now_ts=now + 6,
        )
        self.assertTrue(decision.should_reply)
        self.assertIn('addressed_followup_chat_window', decision.reason_codes)

    def test_initiative_allowed_on_activity(self) -> None:
        decision = self.service.decide(
            chat_id=7,
            user_id=22,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=False,
            recent_messages=25,
            recent_unique_users=5,
            tension_level=0.1,
            now_ts=time.time() + 20000,
        )
        self.assertTrue(decision.should_reply)
        self.assertEqual(decision.mode, 'initiative_topic_drop')

    def test_light_dialogue_join_triggers_before_full_initiative_threshold(self) -> None:
        decision = self.service.decide(
            chat_id=701,
            user_id=44,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=False,
            recent_messages=7,
            recent_unique_users=2,
            tension_level=0.2,
            now_ts=time.time() + 5000,
        )
        self.assertTrue(decision.should_reply)
        self.assertEqual(decision.mode, 'initiative_topic_drop')
        self.assertIn('passive_dialogue_join', decision.reason_codes)

    def test_initiative_avoids_same_user_streak_when_chat_is_active(self) -> None:
        now = time.time()
        self.service.last_initiative_user_id[7] = 22
        self.service.same_user_initiative_streak[(7, 22)] = 1
        decision = self.service.decide(
            chat_id=7,
            user_id=22,
            addressed=AddressingDecision(False, None, ['suppressed_not_addressed']),
            quiz_active=False,
            recent_messages=30,
            recent_unique_users=4,
            tension_level=0.1,
            now_ts=now + 20000,
        )
        self.assertFalse(decision.should_reply)
        self.assertIn('suppressed_same_user_initiative_streak', decision.reason_codes)

    def test_mark_initiative_tracks_streak_for_user(self) -> None:
        self.service.mark_initiative(chat_id=9, user_id=100)
        self.service.mark_initiative(chat_id=9, user_id=100)
        self.assertEqual(self.service.same_user_initiative_streak[(9, 100)], 1)


class InitiativeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InitiativeService()

    def test_initiative_suppressed_on_low_activity(self) -> None:
        decision = self.service.can_start(
            chat_id=1,
            recent_messages=0,
            recent_unique_users=0,
            tension_level=0.0,
            now_ts=time.time(),
        )
        self.assertFalse(decision.should_reply)
        self.assertIn('suppressed_low_activity', decision.reason_codes)


class ReplyValidationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReplyValidationService()

    def test_banned_phrase_rejected(self) -> None:
        text, reasons, _ = self.service.validate_and_clamp(
            text='Как ИИ, я не могу это сделать.',
            mode='addressed_reply',
            quiz_active=False,
        )
        self.assertNotEqual(text, '')
        self.assertIn('rewritten_ai_phrase', reasons)
        self.assertNotIn('suppressed_ai_phrase', reasons)
        self.assertTrue(text)

    def test_repeated_reply_rewritten(self) -> None:
        text, reasons, rewritten = self.service.validate_and_clamp(
            text='Привет, как дела?',
            mode='addressed_reply',
            quiz_active=False,
            recent_assistant_texts=['Привет, как дела?'],
        )
        self.assertTrue(text)
        self.assertTrue(rewritten)
        self.assertIn('rewritten_repeated_reply', reasons)
        self.assertIn(text, {
            'Скажу короче: Привет, как дела?',
            'Коротко так: Привет, как дела?',
            'Если по-простому: Привет, как дела?',
            'Суть такая: Привет, как дела?',
        })

    def test_repeated_reply_suppressed_when_rewrite_still_duplicate(self) -> None:
        text, reasons, rewritten = self.service.validate_and_clamp(
            text='Привет, как дела?',
            mode='addressed_reply',
            quiz_active=False,
            recent_assistant_texts=['Привет, как дела?', 'Суть такая: Привет, как дела?'],
        )
        self.assertEqual(text, '')
        self.assertFalse(rewritten)
        self.assertIn('suppressed_repeated_reply', reasons)

    def test_repeated_micro_reaction_rewritten_to_human_short_variant(self) -> None:
        text, reasons, rewritten = self.service.validate_and_clamp(
            text='Спасибо! ❤️',
            mode='micro_reaction',
            quiz_active=False,
            recent_assistant_texts=['Спасибо! ❤️'],
        )
        self.assertTrue(rewritten)
        self.assertIn('rewritten_repeated_reply', reasons)
        self.assertIn(text, {'Есть контакт 🙂', 'Окей, приняла.', 'Поймала вайб 😌', 'Норм, едем дальше.'})


    def test_micro_reaction_has_stricter_length_limit(self) -> None:
        text, reasons, rewritten = self.service.validate_and_clamp(
            text='x' * 200,
            mode='micro_reaction',
            quiz_active=False,
        )
        self.assertTrue(rewritten)
        self.assertIn('clamped_max_chars', reasons)
        self.assertLessEqual(len(text), 90)

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


class PersonaPolicyServiceTests(unittest.TestCase):
    def test_choose_mode_prefers_micro_reaction_for_addressed_short_social_phrase(self) -> None:
        from app.core.alisa_policy import PersonaPolicyService

        service = PersonaPolicyService()
        mode = service.choose_mode(text='Алиса, спасибо!', addressed_by='name', quiz_active=False)
        self.assertEqual(mode, 'micro_reaction')

    def test_choose_mode_stays_addressed_reply_without_micro_token(self) -> None:
        from app.core.alisa_policy import PersonaPolicyService

        service = PersonaPolicyService()
        mode = service.choose_mode(text='Алиса, как думаешь?', addressed_by='name', quiz_active=False)
        self.assertEqual(mode, 'addressed_reply')

    def test_choose_mode_prefers_micro_reaction_for_emoji_ping(self) -> None:
        from app.core.alisa_policy import PersonaPolicyService

        service = PersonaPolicyService()
        mode = service.choose_mode(text='❤️❤️', addressed_by='reply', quiz_active=False)
        self.assertEqual(mode, 'micro_reaction')


if __name__ == '__main__':
    unittest.main()
