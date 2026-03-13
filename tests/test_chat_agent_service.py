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
        self.assertEqual(self.service.detect_mode('мне тревожно и плохо'), 'support')
        self.assertEqual(self.service.detect_mode('обосри меня как следует'), 'roast')
        self.assertEqual(self.service.detect_mode('привет, как дела?'), 'chat')

    async def test_generate_reply_passes_mode_and_context(self) -> None:
        self.memory_store.note_message(chat_id=1, user_id=10, username='u', text='старое сообщение')

        reply = await self.service.generate_reply(
            chat_id=1,
            chat_title='Test Chat',
            user_id=10,
            username='u',
            text='обосри меня',
            history=[{'role': 'user', 'speaker': 'u', 'text': 'обосри меня'}],
            quiz_active=False,
            current_question_text=None,
            addressed=True,
        )

        self.assertEqual(reply, 'ok-reply')
        self.assertIsNotNone(self.provider.last_kwargs)
        assert self.provider.last_kwargs is not None
        self.assertEqual(self.provider.last_kwargs.get('mode'), 'roast')
        self.assertEqual(self.provider.last_kwargs.get('chat_title'), 'Test Chat')


if __name__ == '__main__':
    unittest.main()
