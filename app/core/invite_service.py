from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Deque, Dict

from aiogram import Bot


class InviteService:
    def __init__(self, *, invite_chance: float = 0.30, invite_cooldown_sec: int = 600, invite_timeout_sec: int = 25) -> None:
        self.invite_chance = invite_chance
        self.invite_cooldown_sec = invite_cooldown_sec
        self.invite_timeout_sec = invite_timeout_sec

        self.chat_last_invite_ts: Dict[int, float] = defaultdict(lambda: 0.0)
        self.chat_activity: Dict[int, Deque[dict[str, object]]] = defaultdict(lambda: deque(maxlen=60))
        self.pending_invites: Dict[int, dict] = {}
        self.invite_tasks: Dict[int, asyncio.Task] = {}

    def cancel_invite_task(self, chat_id: int) -> None:
        task = self.invite_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    def clear_pending_invite(self, chat_id: int) -> None:
        self.pending_invites.pop(chat_id, None)
        self.cancel_invite_task(chat_id)

    def remember_activity(self, chat_id: int, user_id: int, username: str, text: str) -> None:
        self.chat_activity[chat_id].append({'ts': time.time(), 'user_id': user_id, 'username': username, 'text': text[:300]})

    def recent_unique_user_count(self, chat_id: int, window_sec: int) -> int:
        cutoff = time.time() - window_sec
        users = {
            int(item['user_id'])
            for item in self.chat_activity[chat_id]
            if float(item['ts']) >= cutoff
        }
        return len(users)

    def recent_message_count(self, chat_id: int, window_sec: int) -> int:
        cutoff = time.time() - window_sec
        return sum(1 for item in self.chat_activity[chat_id] if float(item['ts']) >= cutoff)

    def is_join_intent(self, text: str) -> bool:
        value = text.strip().lower()
        intents = {
            '+', '++', 'го', 'да', 'ага', 'погнали', 'запускай', 'старт',
            'го квиз', 'давай квиз', 'квиз', 'погнали квиз'
        }
        return value in intents

    async def maybe_send_host_invite(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        if chat_id in self.pending_invites:
            return False
        if time.time() - self.chat_last_invite_ts[chat_id] < self.invite_cooldown_sec:
            return False
        if self.recent_unique_user_count(chat_id, 180) < 2:
            return False
        if self.recent_message_count(chat_id, 180) < 6:
            return False
        if random.random() > self.invite_chance:
            return False

        self.pending_invites[chat_id] = {'votes': {user_id}, 'started_by': user_id, 'created_at': time.time()}
        self.chat_last_invite_ts[chat_id] = time.time()

        await bot.send_message(
            chat_id,
            '👀 Вижу, чат ожил. Го мини-квиз на 5? Напишите «+», «го» или «да» в ближайшие 25 секунд.'
        )
        self.invite_tasks[chat_id] = asyncio.create_task(self._invite_timeout(bot, chat_id))
        return True

    async def handle_pending_invite_vote(
        self,
        bot: Bot,
        chat_id: int,
        user_id: int,
        text: str,
        on_threshold_reached: Callable[[int], Awaitable[None]],
    ) -> bool:
        pending = self.pending_invites.get(chat_id)
        if not pending:
            return False
        if not self.is_join_intent(text):
            return False

        pending['votes'].add(user_id)
        if len(pending['votes']) >= 2:
            started_by = int(pending['started_by'])
            self.clear_pending_invite(chat_id)
            await bot.send_message(chat_id, '🎤 Поймал настрой. Запускаю квиз на 5 вопросов.')
            await on_threshold_reached(started_by)
            return True
        return False

    async def _invite_timeout(self, bot: Bot, chat_id: int) -> None:
        try:
            await asyncio.sleep(self.invite_timeout_sec)
        except asyncio.CancelledError:
            return

        if chat_id not in self.pending_invites:
            return

        self.clear_pending_invite(chat_id)
        await bot.send_message(chat_id, 'Ладно, вижу, чат сегодня делает загадочное лицо. Квиз пока отложим 😏')

