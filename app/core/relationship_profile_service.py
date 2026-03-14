from __future__ import annotations

from app.agent.memory_store import MemoryStore


class RelationshipProfileService:
    """Тонкая обёртка над MemoryStore для работы с профилями отношений."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self.memory_store = memory_store

    def note_user_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        username: str,
        text: str,
        addressed_to_alisa: bool,
    ) -> None:
        self.memory_store.note_message(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            text=text,
            addressed_to_alisa=addressed_to_alisa,
        )

    def note_alisa_reply(self, *, chat_id: int, user_id: int, mode: str) -> None:
        self.memory_store.note_alisa_reply(chat_id=chat_id, user_id=user_id, mode=mode)

    def get_relationship_hint(self, *, chat_id: int, user_id: int, username: str) -> str:
        return self.memory_store.get_relationship_hint(chat_id=chat_id, user_id=user_id, username=username)

    def get_user_summary(self, *, chat_id: int, user_id: int, username: str) -> str:
        return self.memory_store.get_user_summary(chat_id=chat_id, user_id=user_id, username=username)

    def get_chat_summary(self, *, chat_id: int) -> str:
        return self.memory_store.get_chat_summary(chat_id=chat_id)

    def get_chat_tension_level(self, *, chat_id: int) -> float:
        return self.memory_store.get_chat_tension_level(chat_id=chat_id)
