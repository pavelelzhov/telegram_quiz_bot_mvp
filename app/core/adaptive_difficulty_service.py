from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict


class AdaptiveDifficultyService:
    def __init__(self, history_size: int = 20) -> None:
        self.signals: Dict[int, Deque[int]] = defaultdict(lambda: deque(maxlen=history_size))

    def note_correct(self, chat_id: int) -> None:
        self.signals[chat_id].append(1)

    def note_close(self, chat_id: int) -> None:
        self.signals[chat_id].append(0)

    def note_wrong(self, chat_id: int) -> None:
        self.signals[chat_id].append(-1)

    def note_timeout(self, chat_id: int) -> None:
        self.signals[chat_id].append(-1)

    def target_difficulty(self, chat_id: int, asked_count: int) -> str:
        # Первые вопросы не усложняем, чтобы чат успел «вкатиться».
        if asked_count < 3:
            return 'easy'

        items = self.signals.get(chat_id)
        if not items:
            return 'medium'

        avg = sum(items) / len(items)
        if avg >= 0.45:
            return 'hard'
        if avg <= -0.30:
            return 'easy'
        return 'medium'

