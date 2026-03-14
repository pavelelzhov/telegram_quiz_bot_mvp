import asyncio
import logging
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError

from app.bot.handlers import build_router
from app.config import settings
from app.core.game_manager import GameManager
from app.providers.llm_provider import LLMQuestionProvider
from app.storage.db import Database

logger = logging.getLogger(__name__)


def should_retry_polling(exc: BaseException) -> bool:
    return isinstance(exc, (TelegramNetworkError, asyncio.TimeoutError, OSError))


def build_bot_session() -> AiohttpSession:
    proxy = settings.telegram_proxy_url.strip() or None
    timeout = max(5.0, float(settings.telegram_request_timeout_seconds))

    if proxy:
        try:
            session = AiohttpSession(proxy=proxy, timeout=timeout)
        except RuntimeError as exc:
            logger.warning('Proxy is configured but proxy transport is unavailable, fallback to direct Telegram session: %s', exc)
            session = AiohttpSession(timeout=timeout)
    else:
        session = AiohttpSession(timeout=timeout)

    if settings.telegram_force_ipv4:
        session._connector_init['family'] = socket.AF_INET
    return session


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

    bot = Bot(token=settings.bot_token, session=build_bot_session())
    dp = Dispatcher()
    dp.include_router(build_router(game_manager=game_manager, db=db))

    try:
        await run_polling_with_retry(dp, bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
