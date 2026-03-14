from __future__ import annotations

import unittest

from aiogram.exceptions import TelegramNetworkError

from app.core.game_manager import _should_retry_telegram_send, safe_bot_send_message


class _FlakyBot:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def send_message(self, _chat_id: int, _text: str, **_kwargs: object) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TelegramNetworkError(method='sendMessage', message='Request timeout error')


class GameManagerSafeSendTests(unittest.IsolatedAsyncioTestCase):
    def test_should_retry_predicate(self) -> None:
        self.assertTrue(_should_retry_telegram_send(TelegramNetworkError(method='m', message='x')))
        self.assertTrue(_should_retry_telegram_send(TimeoutError()))
        self.assertTrue(_should_retry_telegram_send(OSError('net')))
        self.assertFalse(_should_retry_telegram_send(ValueError('bad')))

    async def test_safe_send_retries_and_succeeds(self) -> None:
        bot = _FlakyBot(fail_times=1)
        await safe_bot_send_message(bot, 1, 'hello')
        self.assertEqual(bot.calls, 2)


if __name__ == '__main__':
    unittest.main()
