from __future__ import annotations

import os
import tempfile
from pathlib import Path
import unittest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')

from app.core.game_manager import GameManager
from app.core.models import QuestionCandidate
from app.storage.db import Database


class _DummyBot:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, _chat_id: int, text: str) -> None:
        self.messages.append(text)


class _BatchProvider:
    def __init__(self) -> None:
        self.counter = 0

    async def generate_question_batch(self, request):
        items = []
        for _ in range(5):
            self.counter += 1
            idx = self.counter
            items.append(
                QuestionCandidate(
                    provider_name='openai',
                    model_name='gpt-test',
                    language='ru',
                    topic='География',
                    subtopic='',
                    difficulty='medium',
                    question_type='text',
                    question_text=f'Столица страны #{idx}?',
                    correct_answer_text=f'Ответ{idx}',
                    explanation=f'Объяснение {idx}',
                    canonical_facts=[f'fact-{idx}'],
                    uniqueness_tags=['geo'],
                    question_hash=f'gm-qh-{idx}',
                    uniqueness_hash=f'gm-uh-{idx}',
                )
            )
        return items

    def validate_question_batch(self, batch):
        return batch


class GameManagerInteractionFlowTests(unittest.IsolatedAsyncioTestCase):
    def _build_db_path(self, tmp_dir: str) -> str:
        return str(Path(tmp_dir) / 'interaction_flow.db')

    def _build_manager(self, db: Database) -> GameManager:
        manager = GameManager(db=db, question_provider=_BatchProvider())

        async def _noop_refill(*_args, **_kwargs):
            return None

        manager.quiz_engine.maybe_start_background_cache_refill = _noop_refill  # type: ignore[assignment]
        return manager

    async def test_correct_answer_moves_to_next_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(self._build_db_path(tmp_dir))
            await db.init()
            manager = self._build_manager(db)
            bot = _DummyBot()
            try:
                start_result = await manager.start_game(
                    bot=bot,
                    chat_id=123,
                    started_by_user_id=555,
                    question_limit=3,
                    quiz_mode='classic',
                )
                self.assertEqual(start_result, 'OK')

                state = manager.get_game(123)
                self.assertIsNotNone(state)
                assert state is not None
                self.assertIsNotNone(state.current_question)
                first_question_text = state.current_question.question
                first_answer = state.current_question.answer

                handled = await manager.handle_answer(
                    bot=bot,
                    chat_id=123,
                    user_id=555,
                    username='alice',
                    text=first_answer,
                )

                self.assertTrue(handled)
                self.assertEqual(state.asked_count, 2)
                self.assertIsNotNone(state.current_question)
                self.assertNotEqual(state.current_question.question, first_question_text)
                self.assertGreaterEqual(len(state.scores), 1)
            finally:
                await manager.stop_game(bot=bot, chat_id=123, reason='test cleanup')

    async def test_three_unique_wrong_answers_force_next_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(self._build_db_path(tmp_dir))
            await db.init()
            manager = self._build_manager(db)
            bot = _DummyBot()
            try:
                start_result = await manager.start_game(
                    bot=bot,
                    chat_id=124,
                    started_by_user_id=777,
                    question_limit=3,
                    quiz_mode='classic',
                )
                self.assertEqual(start_result, 'OK')

                state = manager.get_game(124)
                assert state is not None
                first_question_text = state.current_question.question if state.current_question else ''

                await manager.handle_answer(bot=bot, chat_id=124, user_id=1, username='u1', text='неверно')
                await manager.handle_answer(bot=bot, chat_id=124, user_id=2, username='u2', text='неверно')
                await manager.handle_answer(bot=bot, chat_id=124, user_id=3, username='u3', text='неверно')

                self.assertEqual(state.asked_count, 2)
                self.assertIsNotNone(state.current_question)
                self.assertNotEqual(state.current_question.question, first_question_text)
            finally:
                await manager.stop_game(bot=bot, chat_id=124, reason='test cleanup')

    async def test_three_wrong_attempts_from_same_user_force_next_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(self._build_db_path(tmp_dir))
            await db.init()
            manager = self._build_manager(db)
            bot = _DummyBot()
            try:
                start_result = await manager.start_game(
                    bot=bot,
                    chat_id=125,
                    started_by_user_id=888,
                    question_limit=3,
                    quiz_mode='classic',
                )
                self.assertEqual(start_result, 'OK')

                state = manager.get_game(125)
                assert state is not None
                first_question_text = state.current_question.question if state.current_question else ''

                await manager.handle_answer(bot=bot, chat_id=125, user_id=9, username='solo', text='мимо 1')
                await manager.handle_answer(bot=bot, chat_id=125, user_id=9, username='solo', text='мимо 2')
                await manager.handle_answer(bot=bot, chat_id=125, user_id=9, username='solo', text='мимо 3')

                self.assertEqual(state.asked_count, 2)
                self.assertIsNotNone(state.current_question)
                self.assertNotEqual(state.current_question.question, first_question_text)
            finally:
                await manager.stop_game(bot=bot, chat_id=125, reason='test cleanup')


if __name__ == '__main__':
    unittest.main()
