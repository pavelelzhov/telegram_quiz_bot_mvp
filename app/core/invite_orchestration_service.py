from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import Bot

from app.core.invite_service import InviteService


class InviteOrchestrationService:
    async def maybe_send_host_invite(
        self,
        *,
        invite_service: InviteService,
        bot: Bot,
        chat_id: int,
        user_id: int,
        on_invited: Callable[[], None],
    ) -> bool:
        invited = await invite_service.maybe_send_host_invite(bot, chat_id, user_id)
        if invited:
            on_invited()
        return invited

    async def handle_pending_invite_vote(
        self,
        *,
        invite_service: InviteService,
        bot: Bot,
        chat_id: int,
        user_id: int,
        text: str,
        on_threshold_reached: Callable[[int], Awaitable[None]],
    ) -> bool:
        return await invite_service.handle_pending_invite_vote(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            on_threshold_reached=on_threshold_reached,
        )
