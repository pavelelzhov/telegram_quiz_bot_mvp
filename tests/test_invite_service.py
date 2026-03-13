from __future__ import annotations

import asyncio
import unittest

from app.core.invite_service import InviteService


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class InviteServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_maybe_send_host_invite_requires_activity(self) -> None:
        service = InviteService(invite_chance=1.0, invite_timeout_sec=1)
        bot = _FakeBot()

        invited = await service.maybe_send_host_invite(bot, chat_id=1, user_id=10)

        self.assertFalse(invited)
        self.assertEqual(bot.messages, [])

    async def test_vote_threshold_starts_callback(self) -> None:
        service = InviteService(invite_chance=1.0, invite_timeout_sec=1)
        bot = _FakeBot()

        for i in range(6):
            service.remember_activity(chat_id=1, user_id=10 + i % 2, username=f'u{i}', text='оживлённый чат')

        invited = await service.maybe_send_host_invite(bot, chat_id=1, user_id=10)
        self.assertTrue(invited)

        started_by: list[int] = []

        async def on_threshold(user_id: int) -> None:
            started_by.append(user_id)

        handled = await service.handle_pending_invite_vote(
            bot=bot,
            chat_id=1,
            user_id=11,
            text='го',
            on_threshold_reached=on_threshold,
        )

        self.assertTrue(handled)
        self.assertEqual(started_by, [10])

    async def test_timeout_clears_pending_invite(self) -> None:
        service = InviteService(invite_chance=1.0, invite_timeout_sec=0)
        bot = _FakeBot()

        for i in range(6):
            service.remember_activity(chat_id=2, user_id=20 + i % 2, username=f'u{i}', text='оживлённый чат')

        invited = await service.maybe_send_host_invite(bot, chat_id=2, user_id=20)
        self.assertTrue(invited)

        await asyncio.sleep(0.01)

        self.assertNotIn(2, service.pending_invites)
        self.assertTrue(any('Квиз пока отложим' in text for _, text in bot.messages))


if __name__ == '__main__':
    unittest.main()

