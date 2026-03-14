import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError

from app.bot.handlers import build_router
from app.config import settings
from app.core.game_manager import GameManager
from app.providers.llm_provider import LLMQuestionProvider
from app.storage.db import Database

logger = logging.getLogger(__name__)


def should_retry_polling(exc: BaseException) -> bool:
    return isinstance(exc, (TelegramNetworkError, asyncio.TimeoutError, OSError))


async def run_polling_with_retry(dp: Dispatcher, bot: Bot) -> None:
    attempts = 0
    max_retries = max(0, int(settings.polling_max_retries))
    delay = max(0.5, float(settings.polling_retry_delay_seconds))

    while True:
        try:
            await dp.start_polling(bot)
            return
        except Exception as exc:  # noqa: BLE001
            if not should_retry_polling(exc):
                raise

            attempts += 1
            if max_retries and attempts > max_retries:
                logger.error('Polling retries exceeded: attempts=%s max_retries=%s', attempts, max_retries)
                raise

            logger.warning(
                'Polling interrupted by network error, retrying in %.1fs (attempt=%s): %s',
                delay,
                attempts,
                exc,
            )
            await asyncio.sleep(delay)


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

    try:
        await run_polling_with_retry(dp, bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
