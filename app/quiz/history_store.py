from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class QuizHistoryStore:
    def __init__(self, path: str = 'data/quiz_history.json', max_items: int = 300) -> None:
        self.path = Path(path)
        self.max_items = max_items
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {'chats': {}}
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception:
            return {'chats': {}}

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    def _ensure_chat(self, chat_id: int) -> dict[str, Any]:
        chats = self.data.setdefault('chats', {})
        return chats.setdefault(
            str(chat_id),
            {
                'recent_keys': [],
                'recent_categories': [],
                'recent_topics': [],
                'recent_answers': [],
                'recent_round_types': [],
            },
        )

    def recent_keys(self, chat_id: int, limit: int = 100) -> list[str]:
        return list(self._ensure_chat(chat_id).get('recent_keys', []))[-limit:]

    def recent_categories(self, chat_id: int, limit: int = 20) -> list[str]:
        return list(self._ensure_chat(chat_id).get('recent_categories', []))[-limit:]

    def recent_topics(self, chat_id: int, limit: int = 40) -> list[str]:
        return list(self._ensure_chat(chat_id).get('recent_topics', []))[-limit:]

    def recent_answers(self, chat_id: int, limit: int = 40) -> list[str]:
        return list(self._ensure_chat(chat_id).get('recent_answers', []))[-limit:]

    def recent_round_types(self, chat_id: int, limit: int = 20) -> list[str]:
        return list(self._ensure_chat(chat_id).get('recent_round_types', []))[-limit:]

    def remember(
        self,
        chat_id: int,
        key: str,
        category: str,
        topic: str,
        answer: str,
        round_type: str,
    ) -> None:
        chat = self._ensure_chat(chat_id)
        self._append(chat['recent_keys'], key)
        self._append(chat['recent_categories'], category)
        self._append(chat['recent_topics'], topic)
        self._append(chat['recent_answers'], answer)
        self._append(chat['recent_round_types'], round_type)
        self._save()

    def _append(self, target: list[str], value: str) -> None:
        value = (value or '').strip()
        if not value:
            return
        target.append(value)
        while len(target) > self.max_items:
            target.pop(0)
