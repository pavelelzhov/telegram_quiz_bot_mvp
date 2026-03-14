from __future__ import annotations

import re
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

    def detect_mode(self, text: str, fallback_mode: str = 'addressed_reply') -> str:
        lowered = text.lower()

        support_tokens = [
            'мне плохо', 'тревожно', 'паника', 'паническую', 'устал', 'не вывожу',
            'одиноко', 'грустно', 'тяжело', 'накрывает', 'депресс', 'разбит', 'день в мусор'
        ]
        if any(token in lowered for token in support_tokens):
            return 'warm_support'

        pushback_tokens = ['заткнись', 'тупая', 'идиотка', 'дура']
        if self._contains_any_token(lowered, pushback_tokens):
            return 'pushback'

        micro_tokens = [
            'спасибо', 'пасиб', 'благодарю', 'привет', 'здорово', 'доброе утро', 'добрый вечер',
            'лол', 'ахах', 'хаха', 'ок', 'оке', 'понял', 'поняла'
        ]
        if self._contains_any_token(lowered, micro_tokens):
            return 'micro_reaction'

        return fallback_mode

    def _contains_any_token(self, text: str, tokens: list[str]) -> bool:
        for token in tokens:
            if ' ' in token:
                if token in text:
                    return True
                continue
            if re.search(rf'(?<!\w){re.escape(token)}(?!\w)', text, flags=re.IGNORECASE):
                return True
        return False

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
        mode: str,
    ) -> str:
        final_mode = self.detect_mode(text, fallback_mode=mode)
        user_memory = self.memory_store.get_user_summary(chat_id, user_id, username)
        chat_memory = self.memory_store.get_chat_summary(chat_id)
        relationship_hint = self.memory_store.get_relationship_hint(chat_id, user_id, username)

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
            mode=final_mode,
            relationship_hint=relationship_hint,
        )
