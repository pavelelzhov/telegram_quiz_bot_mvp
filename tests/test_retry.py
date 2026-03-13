from __future__ import annotations

import unittest

from app.utils.retry import retry_async


class RetryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_async_retries_until_success(self) -> None:
        attempts = {'value': 0}

        async def flaky() -> str:
            attempts['value'] += 1
            if attempts['value'] < 3:
                raise TimeoutError('temporary')
            return 'ok'

        result = await retry_async(flaky, retries=3, base_delay_sec=0.001, should_retry=lambda exc: True)

        self.assertEqual(result, 'ok')
        self.assertEqual(attempts['value'], 3)

    async def test_retry_async_does_not_retry_when_predicate_blocks(self) -> None:
        attempts = {'value': 0}

        async def always_fail() -> str:
            attempts['value'] += 1
            raise ValueError('bad request')

        with self.assertRaises(ValueError):
            await retry_async(always_fail, retries=3, base_delay_sec=0.001, should_retry=lambda exc: False)

        self.assertEqual(attempts['value'], 1)


if __name__ == '__main__':
    unittest.main()
