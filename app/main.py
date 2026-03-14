import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers import build_router
from app.config import settings
from app.core.game_manager import GameManager
from app.providers.llm_provider import LLMQuestionProvider
from app.storage.db import Database


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )

    db = Database()
    await db.init()

    question_provider = LLMQuestionProvider()
    game_manager = GameManager(db=db, question_provider=question_provider)
    asyncio.create_task(game_manager.quiz_engine.ensure_cache_after_restart())

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(game_manager=game_manager, db=db))

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
