from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class DailyChallengeService:
    def resolve_local_game_date(self, timezone_name: str) -> str:
        try:
            return datetime.now(ZoneInfo(timezone_name)).date().isoformat()
        except Exception:
            return datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
