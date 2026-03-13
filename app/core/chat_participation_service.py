from __future__ import annotations


class ChatParticipationService:
    def resolve_cooldown(self, *, addressed: bool, host_mode_enabled: bool) -> float | None:
        if addressed:
            return 8.0
        if host_mode_enabled:
            return 35.0
        return None

    def passes_passive_reply_filters(
        self,
        *,
        recent_unique_users: int,
        recent_messages: int,
        text: str,
        random_value: float,
    ) -> bool:
        if recent_unique_users < 2:
            return False
        if recent_messages < 5:
            return False
        if len(text.strip()) < 10:
            return False
        if random_value > 0.18:
            return False
        return True
