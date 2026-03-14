from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo


class DailyChallengeService:
    def is_timezone_supported(self, timezone_name: str) -> bool:
        try:
            ZoneInfo((timezone_name or '').strip())
            return True
        except Exception:
            return False

    def resolve_local_game_date(self, timezone_name: str) -> str:
        tz_name = (timezone_name or '').strip()

        if tz_name:
            try:
                return datetime.now(ZoneInfo(tz_name)).date().isoformat()
            except Exception:
                pass

        # Универсальный fallback без зависимости от tzdata.
        try:
            return datetime.now(dt_timezone.utc).date().isoformat()
        except Exception:
            return datetime.utcnow().date().isoformat()
