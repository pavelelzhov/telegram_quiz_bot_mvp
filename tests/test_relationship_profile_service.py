from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.agent.memory_store import MemoryStore
from app.core.relationship_profile_service import RelationshipProfileService


class RelationshipProfileServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.memory_store = MemoryStore(path=f'{self.tmp_dir.name}/agent_memory.json')
        self.service = RelationshipProfileService(self.memory_store)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_note_and_read_profile_data(self) -> None:
        self.service.note_user_message(
            chat_id=1,
            user_id=10,
            username='user',
            text='Алиса, ты сегодня в ударе',
            addressed_to_alisa=True,
        )

        hint = self.service.get_relationship_hint(chat_id=1, user_id=10, username='user')
        user_summary = self.service.get_user_summary(chat_id=1, user_id=10, username='user')
        chat_summary = self.service.get_chat_summary(chat_id=1)

        self.assertTrue(hint)
        self.assertTrue(user_summary)
        self.assertTrue(chat_summary)


if __name__ == '__main__':
    unittest.main()
