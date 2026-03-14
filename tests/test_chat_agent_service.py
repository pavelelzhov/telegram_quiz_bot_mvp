from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.agent.memory_store import MemoryStore
from app.core.chat_agent_service import ChatAgentService


class _FakeReplyProvider:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def generate_reply(self, **kwargs: object) -> str:
        self.last_kwargs = kwargs
        return 'ok-reply'


class ChatAgentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.memory_store = MemoryStore(path=f'{self.tmp_dir.name}/agent_memory.json')
        self.provider = _FakeReplyProvider()
        self.service = ChatAgentService(memory_store=self.memory_store, agent_reply_provider=self.provider)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_detect_mode(self) -> None:
        self.assertEqual(self.service.detect_mode('мне тревожно и плохо'), 'warm_support')
        self.assertEqual(self.service.detect_mode('заткнись уже'), 'pushback')
        self.assertEqual(self.service.detect_mode('привет, как дела?'), 'micro_reaction')

        self.assertEqual(self.service.detect_mode('покажи настройки'), 'addressed_reply')
        self.assertEqual(self.service.detect_mode('депрессивный фильм норм'), 'addressed_reply')
        self.assertEqual(self.service.detect_mode('придурок какой-то'), 'addressed_reply')



    def test_resolve_sharpness_ceiling(self) -> None:
        self.assertEqual(self.service.resolve_sharpness_ceiling('warm_support'), 'low')
        self.assertEqual(self.service.resolve_sharpness_ceiling('quiz_safe_mode'), 'low')
        self.assertEqual(self.service.resolve_sharpness_ceiling('pushback'), 'medium')

    async def test_generate_reply_passes_micro_reaction_mode(self) -> None:
        reply = await self.service.generate_reply(
            chat_id=2,
            chat_title='Micro Chat',
            user_id=11,
            username='v',
            text='спасибо! очень помогла',
            history=[{'role': 'user', 'speaker': 'v', 'text': 'спасибо! очень помогла'}],
            quiz_active=False,
            current_question_text=None,
            addressed=True,
            mode='addressed_reply',
        )

        self.assertEqual(reply, 'ok-reply')
        self.assertIsNotNone(self.provider.last_kwargs)
        assert self.provider.last_kwargs is not None
        self.assertEqual(self.provider.last_kwargs.get('mode'), 'micro_reaction')
        self.assertEqual(self.provider.last_kwargs.get('sharpness_ceiling'), 'medium')

    async def test_generate_reply_passes_mode_and_context(self) -> None:
        self.memory_store.note_message(chat_id=1, user_id=10, username='u', text='старое сообщение')

        reply = await self.service.generate_reply(
            chat_id=1,
            chat_title='Test Chat',
            user_id=10,
            username='u',
            text='заткнись уже',
            history=[{'role': 'user', 'speaker': 'u', 'text': 'заткнись уже'}],
            quiz_active=False,
            current_question_text=None,
            addressed=True,
            mode='addressed_reply',
        )

        self.assertEqual(reply, 'ok-reply')
        self.assertIsNotNone(self.provider.last_kwargs)
        assert self.provider.last_kwargs is not None
        self.assertEqual(self.provider.last_kwargs.get('mode'), 'pushback')
        self.assertEqual(self.provider.last_kwargs.get('chat_title'), 'Test Chat')
        self.assertEqual(self.provider.last_kwargs.get('sharpness_ceiling'), 'medium')


if __name__ == '__main__':
    unittest.main()
