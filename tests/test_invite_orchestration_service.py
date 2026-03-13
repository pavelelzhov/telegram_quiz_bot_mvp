from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from app.core.invite_orchestration_service import InviteOrchestrationService


class InviteOrchestrationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_maybe_send_host_invite_calls_callback_on_success(self) -> None:
        service = InviteOrchestrationService()
        invite_service = Mock()
        invite_service.maybe_send_host_invite = AsyncMock(return_value=True)
        on_invited = Mock()

        result = await service.maybe_send_host_invite(
            invite_service=invite_service,
            bot=Mock(),
            chat_id=1,
            user_id=10,
            on_invited=on_invited,
        )

        self.assertTrue(result)
        on_invited.assert_called_once()

    async def test_maybe_send_host_invite_does_not_call_callback_on_failure(self) -> None:
        service = InviteOrchestrationService()
        invite_service = Mock()
        invite_service.maybe_send_host_invite = AsyncMock(return_value=False)
        on_invited = Mock()

        result = await service.maybe_send_host_invite(
            invite_service=invite_service,
            bot=Mock(),
            chat_id=1,
            user_id=10,
            on_invited=on_invited,
        )

        self.assertFalse(result)
        on_invited.assert_not_called()

    async def test_handle_pending_invite_vote_delegates(self) -> None:
        service = InviteOrchestrationService()
        invite_service = Mock()
        invite_service.handle_pending_invite_vote = AsyncMock(return_value=True)

        async def on_threshold_reached(_started_by: int) -> None:
            return None

        result = await service.handle_pending_invite_vote(
            invite_service=invite_service,
            bot=Mock(),
            chat_id=1,
            user_id=10,
            text='го',
            on_threshold_reached=on_threshold_reached,
        )

        self.assertTrue(result)
        invite_service.handle_pending_invite_vote.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
