from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.agent.memory_store import MemoryStore

if TYPE_CHECKING:
    from app.agent.agent_reply_provider import AgentReplyProvider


class ChatAgentService:
    def __init__(self, memory_store: MemoryStore, agent_reply_provider: Optional['AgentReplyProvider'] = None) -> None:
        self.memory_store = memory_store
        if agent_reply_provider is None:
            from app.agent.agent_reply_provider import AgentReplyProvider

            self.agent_reply_provider = AgentReplyProvider()
        else:
            self.agent_reply_provider = agent_reply_provider

    def detect_mode(self, text: str) -> str:
        lowered = text.lower()

        support_tokens = [
            'мне плохо', 'тревожно', 'паника', 'паническую', 'устал', 'не вывожу',
            'одиноко', 'грустно', 'тяжело', 'накрывает', 'депресс', 'разбит'
        ]
        if any(token in lowered for token in support_tokens):
            return 'support'

        roast_tokens = ['обосри', 'прожарь', 'роаст', 'разнеси меня', 'поругай меня', 'обругай']
        if any(token in lowered for token in roast_tokens):
            return 'roast'

        return 'chat'

    async def generate_reply(
        self,
        chat_id: int,
        chat_title: str,
        user_id: int,
        username: str,
        text: str,
        history: list[dict[str, str]],
        quiz_active: bool,
        current_question_text: str | None,
        addressed: bool,
    ) -> str:
        mode = self.detect_mode(text)
        user_memory = self.memory_store.get_user_summary(chat_id, user_id, username)
        chat_memory = self.memory_store.get_chat_summary(chat_id)

        return await self.agent_reply_provider.generate_reply(
            chat_title=chat_title,
            username=username,
            user_text=text,
            history=history,
            quiz_active=quiz_active,
            current_question_text=current_question_text,
            addressed=addressed,
            user_memory=user_memory,
            chat_memory=chat_memory,
            mode=mode,
        )
