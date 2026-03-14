from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import settings
from app.core.alisa_policy import PersonaPolicyService

logger = logging.getLogger(__name__)


class AgentReplyProvider:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.openai_model

    async def generate_reply(
        self,
        chat_title: str,
        username: str,
        user_text: str,
        history: list[dict[str, str]],
        quiz_active: bool,
        current_question_text: str | None,
        addressed: bool,
        user_memory: str,
        chat_memory: str,
        mode: str = 'addressed_reply',
        relationship_hint: str = '',
        sharpness_ceiling: str = 'medium',
    ) -> str:
        history_lines: list[str] = []
        for item in history[-12:]:
            history_lines.append(
                f"{item.get('role', 'user')}:{item.get('speaker', 'someone')}: {item.get('text', '')}"
            )

        history_text = '\n'.join(history_lines) if history_lines else 'контекст пуст'
        quiz_block = 'Квиз сейчас не активен.'
        if quiz_active:
            quiz_block = f'Квиз активен. Текущий вопрос: {current_question_text or "вопрос скрыт"}'

        mode_prompt = PersonaPolicyService.MODE_PROMPTS.get(mode, PersonaPolicyService.MODE_PROMPTS['addressed_reply'])

        prompt = f"""
[MODE]
{mode}

[MODE_INSTRUCTIONS]
{mode_prompt}

[RELATIONSHIP_CONTEXT]
{relationship_hint or 'Пока нейтральный контакт.'}

[CONVERSATION_CONTEXT]
Чат: {chat_title}
Пользователь: @{username}
Обращение к Алисе: {'да' if addressed else 'нет'}
Память о пользователе: {user_memory}
Память о чате: {chat_memory}
Недавний контекст:
{history_text}

[QUIZ_SAFETY]
{quiz_block}

[STYLE_TARGET]
Макс длина: коротко. Резкость: {sharpness_ceiling}.

[INPUT_MESSAGE]
{user_text}
""".strip()

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.8,
                messages=[
                    {'role': 'system', 'content': PersonaPolicyService.PERSONA_CORE_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
            )
            content = (response.choices[0].message.content or '').strip()
            return self._cleanup(content)
        except Exception as exc:
            logger.exception('Agent reply failed: %s', exc)
            return ''

    def _cleanup(self, text: str) -> str:
        value = text.strip()
        if value.startswith('```'):
            value = value.strip('`').strip()
        if len(value) > 700:
            value = value[:700].rstrip() + '...'
        return value
