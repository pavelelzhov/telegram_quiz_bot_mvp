from __future__ import annotations

import unittest

from aiogram.exceptions import TelegramNetworkError

from app.main import run_polling_with_retry, should_retry_polling


class _FakeDp:
    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def start_polling(self, _bot: object) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TelegramNetworkError(method='getMe', message='Request timeout error')


class MainPollingRetryTests(unittest.IsolatedAsyncioTestCase):
    def test_should_retry_polling(self) -> None:
        self.assertTrue(should_retry_polling(TelegramNetworkError(method='m', message='x')))
        self.assertTrue(should_retry_polling(TimeoutError()))
        self.assertTrue(should_retry_polling(OSError('net')))
        self.assertFalse(should_retry_polling(ValueError('bad')))

    async def test_run_polling_retries_and_succeeds(self) -> None:
        from app import config as config_module

        old_retries = config_module.settings.polling_max_retries
        old_delay = config_module.settings.polling_retry_delay_seconds
        config_module.settings.polling_max_retries = 2
        config_module.settings.polling_retry_delay_seconds = 0.01
        try:
            dp = _FakeDp(fail_times=1)
            await run_polling_with_retry(dp, object())
            self.assertEqual(dp.calls, 2)
        finally:
            config_module.settings.polling_max_retries = old_retries
            config_module.settings.polling_retry_delay_seconds = old_delay


if __name__ == '__main__':
    unittest.main()
