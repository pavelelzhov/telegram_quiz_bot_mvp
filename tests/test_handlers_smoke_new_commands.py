from __future__ import annotations

import tempfile
import unittest

from app.bot.handlers import build_router
from app.core.game_manager import GameManager
from app.providers.llm_provider import LLMQuestionProvider
from app.storage.db import Database


class HandlersSmokeTests(unittest.TestCase):
    def test_router_builds_with_new_commands(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            db = Database(tmp.name)
            manager = GameManager(db=db, question_provider=LLMQuestionProvider())
            router = build_router(manager, db)
            self.assertIsNotNone(router)


if __name__ == '__main__':
    unittest.main()
