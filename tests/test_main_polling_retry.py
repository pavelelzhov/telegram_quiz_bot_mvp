from __future__ import annotations

import unittest

from aiogram.exceptions import TelegramNetworkError

from app.main import build_bot_session, run_polling_with_retry, should_retry_polling


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


    def test_build_bot_session_respects_timeout_and_ipv4(self) -> None:
        import socket
        from app import config as config_module

        old_timeout = config_module.settings.telegram_request_timeout_seconds
        old_proxy = config_module.settings.telegram_proxy_url
        old_ipv4 = config_module.settings.telegram_force_ipv4
        config_module.settings.telegram_request_timeout_seconds = 12
        config_module.settings.telegram_proxy_url = ''
        config_module.settings.telegram_force_ipv4 = True
        try:
            session = build_bot_session()
            self.assertEqual(session.timeout, 12)
            self.assertEqual(session._connector_init.get('family'), socket.AF_INET)
        finally:
            config_module.settings.telegram_request_timeout_seconds = old_timeout
            config_module.settings.telegram_proxy_url = old_proxy
            config_module.settings.telegram_force_ipv4 = old_ipv4


    def test_build_bot_session_fallback_when_proxy_transport_missing(self) -> None:
        from app import config as config_module

        old_timeout = config_module.settings.telegram_request_timeout_seconds
        old_proxy = config_module.settings.telegram_proxy_url
        old_ipv4 = config_module.settings.telegram_force_ipv4
        config_module.settings.telegram_request_timeout_seconds = 20
        config_module.settings.telegram_proxy_url = 'socks5://127.0.0.1:1080'
        config_module.settings.telegram_force_ipv4 = False
        try:
            session = build_bot_session()
            self.assertEqual(session.timeout, 20)
        finally:
            config_module.settings.telegram_request_timeout_seconds = old_timeout
            config_module.settings.telegram_proxy_url = old_proxy
            config_module.settings.telegram_force_ipv4 = old_ipv4

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
