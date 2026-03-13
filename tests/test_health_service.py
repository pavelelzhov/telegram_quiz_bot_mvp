from __future__ import annotations

import unittest
from logging import getLogger

from app.core.health_service import HealthService


class _DbOk:
    async def healthcheck(self) -> bool:
        return True


class _DbFail:
    async def healthcheck(self) -> bool:
        return False


class HealthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_snapshot_degraded_when_provider_missing(self) -> None:
        service = HealthService()
        snapshot = await service.check(
            chat_id=1,
            db=_DbOk(),
            llm_configured=False,
            web_search_enabled=True,
            logger=getLogger('test_health'),
        )

        self.assertEqual(snapshot.overall, 'DEGRADED')
        self.assertEqual(snapshot.db_status, 'OK')
        self.assertEqual(snapshot.llm_status, 'DEGRADED')

    async def test_health_snapshot_fail_when_db_down(self) -> None:
        service = HealthService()
        snapshot = await service.check(
            chat_id=1,
            db=_DbFail(),
            llm_configured=True,
            web_search_enabled=True,
            logger=getLogger('test_health'),
        )

        self.assertEqual(snapshot.overall, 'FAIL')
        text = service.format_text(snapshot)
        self.assertIn('Overall: FAIL', text)


if __name__ == '__main__':
    unittest.main()
