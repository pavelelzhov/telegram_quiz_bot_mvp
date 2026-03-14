from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.models import QuizQuestion
from app.providers.llm_provider import LLMQuestionProvider


class LlmProviderBatchTests(unittest.TestCase):
    def test_generate_batch_respects_llm_only_flag(self) -> None:
        async def _run() -> None:
            with patch.object(LLMQuestionProvider, '__init__', lambda self: None):
                provider = LLMQuestionProvider()
                provider.model = 'test-model'
                provider.validate_question_batch = lambda candidates: candidates
                provider.history = type('HistoryStub', (), {'recent_keys': lambda self, chat_id, limit: []})()
                provider._choose_category = lambda chat_id, preferred_category, category_bias: 'Общие знания'
                provider._generate_text_question = AsyncMock(
                    return_value=QuizQuestion(
                        category='Общие знания',
                        difficulty='medium',
                        question='Тестовый вопрос?',
                        answer='Ответ',
                        aliases=[],
                        hint='Подсказка',
                        explanation='Объяснение',
                        source='fallback',
                    )
                )

                with patch('app.providers.llm_provider.logger.warning') as warning_mock:
                    batch = await LLMQuestionProvider.generate_question_batch(
                        provider,
                        {
                            'chat_id': 1,
                            'count': 3,
                            'difficulty': 'medium',
                            'llm_only': True,
                        },
                    )
                self.assertEqual(batch, [])
                warning_mock.assert_called_once()

        asyncio.run(_run())


if __name__ == '__main__':
    unittest.main()
