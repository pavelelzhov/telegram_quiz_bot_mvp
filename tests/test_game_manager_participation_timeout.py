from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
import unittest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')

from app.config import settings
from app.core.game_manager import GameManager
from app.storage.db import Database


class _DummyBot:
    def __init__(self) -> None:
        self.id = 777
        self.messages: list[str] = []
        self.message_kwargs: list[dict[str, object]] = []

    async def send_message(self, _chat_id: int, text: str, **kwargs: object) -> None:
        self.messages.append(text)
        self.message_kwargs.append(dict(kwargs))


class _NoopProvider:
    async def generate_question_batch(self, _request):
        return []

    def validate_question_batch(self, batch):
        return batch


class GameManagerParticipationTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_participation_reply_kwargs_for_dialogue_join(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / 'gm_prefix.db')
            db = Database(db_path)
            await db.init()
            manager = GameManager(db=db, question_provider=_NoopProvider())

            kwargs = manager._build_participation_reply_kwargs(
                message_id=321,
                reason_codes=['passive_dialogue_join'],
            )

            self.assertEqual(kwargs.get('reply_to_message_id'), 321)
            self.assertEqual(kwargs.get('allow_sending_without_reply'), True)

    async def test_participation_provider_timeout_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / 'gm_participation_timeout.db')
            db = Database(db_path)
            await db.init()
            manager = GameManager(db=db, question_provider=_NoopProvider())
            bot = _DummyBot()

            async def _slow_generate_reply(**_kwargs: object) -> str:
                await asyncio.sleep(1.2)
                return 'медленный ответ'

            manager.chat_agent_service.generate_reply = _slow_generate_reply  # type: ignore[assignment]

            old_timeout = settings.alisa_generation_timeout_seconds
            settings.alisa_generation_timeout_seconds = 1.0
            try:
                handled = await manager.handle_chat_participation(
                    bot=bot,
                    chat_id=500,
                    chat_title='Test',
                    user_id=10,
                    username='u',
                    text='Алиса, привет',
                    is_reply_to_alisa=True,
                    has_bot_mention=False,
                    message_id=42,
                )
            finally:
                settings.alisa_generation_timeout_seconds = old_timeout

            self.assertFalse(handled)
            self.assertEqual(bot.messages, [])
            stages = [event.stage for event in manager.decision_audit.recent(chat_id=500)]
            self.assertIn('provider_timeout', stages)

    async def test_participation_reply_is_sent_as_reply_to_user_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / 'gm_participation_tag.db')
            db = Database(db_path)
            await db.init()
            manager = GameManager(db=db, question_provider=_NoopProvider())
            bot = _DummyBot()

            async def _reply(**_kwargs: object) -> str:
                return 'рада тебя видеть'

            manager.chat_agent_service.generate_reply = _reply  # type: ignore[assignment]

            handled = await manager.handle_chat_participation(
                bot=bot,
                chat_id=501,
                chat_title='Test',
                user_id=11,
                username='v',
                text='Алиса, привет',
                is_reply_to_alisa=True,
                has_bot_mention=False,
                message_id=43,
            )

            self.assertTrue(handled)
            self.assertTrue(bot.messages)
            self.assertEqual(bot.messages[-1], 'рада тебя видеть')
            self.assertTrue(bot.message_kwargs)
            self.assertEqual(bot.message_kwargs[-1].get('reply_to_message_id'), 43)
            self.assertEqual(bot.message_kwargs[-1].get('allow_sending_without_reply'), True)


if __name__ == '__main__':
    unittest.main()
