from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


class MemoryStore:
    def __init__(self, path: str = 'data/agent_memory.json') -> None:
        self.path = Path(path)
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
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _ensure_chat(self, chat_id: int) -> dict[str, Any]:
        chats = self.data.setdefault('chats', {})
        chat = chats.setdefault(
            str(chat_id),
            {
                'message_count': 0,
                'topic_scores': {},
                'users': {},
                'updated_at': '',
                'chat_vibe_summary': '',
                'activity_level': 0.0,
                'current_tension_level': 0.0,
                'last_alisa_message_at': '',
                'last_alisa_initiative_at': '',
                'last_conflict_at': '',
            },
        )
        return chat

    def _ensure_user(self, chat: dict[str, Any], user_id: int, username: str) -> dict[str, Any]:
        users = chat.setdefault('users', {})
        user = users.setdefault(
            str(user_id),
            {
                'username': username,
                'message_count': 0,
                'recent_message_count': 0,
                'likes_quiz_score': 0,
                'roast_opt_in': False,
                'topic_scores': {},
                'summary': '',
                'first_seen_at': self._now(),
                'last_seen_at': self._now(),
                'rapport_score': 0.0,
                'banter_tolerance': 0.3,
                'hostility_score': 0.0,
                'warmth_affinity': 0.2,
                'tease_affinity': 0.3,
                'direct_address_frequency': 0,
                'recent_sentiment_toward_alisa': 'neutral',
                'last_interaction_mode': 'observed_silence',
                'last_significant_interaction_at': '',
            },
        )
        user['username'] = username
        return user

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

    def note_message(self, chat_id: int, user_id: int, username: str, text: str, addressed_to_alisa: bool = False) -> None:
        text = (text or '').strip()
        if not text:
            return

        chat = self._ensure_chat(chat_id)
        user = self._ensure_user(chat, user_id, username)

        chat['message_count'] = int(chat.get('message_count', 0)) + 1
        chat['updated_at'] = self._now()

        user['message_count'] = int(user.get('message_count', 0)) + 1
        user['recent_message_count'] = min(50, int(user.get('recent_message_count', 0)) + 1)
        user['last_seen_at'] = self._now()
        if addressed_to_alisa:
            user['direct_address_frequency'] = int(user.get('direct_address_frequency', 0)) + 1

        topics = self._extract_topics(text)
        self._bump_scores(chat.setdefault('topic_scores', {}), topics, 1)
        self._bump_scores(user.setdefault('topic_scores', {}), topics, 2)

        lowered = text.lower()
        if any(token in lowered for token in ['квиз', 'викторин', 'вопрос']):
            user['likes_quiz_score'] = int(user.get('likes_quiz_score', 0)) + 1

        if any(token in lowered for token in ['роаст', 'прожарь', 'обосри', 'поругай меня', 'разнеси меня']):
            user['roast_opt_in'] = True
            user['banter_tolerance'] = min(1.0, float(user.get('banter_tolerance', 0.3)) + 0.1)

        if any(token in lowered for token in ['заткнись', 'тупая', 'идиотка', 'дура']):
            user['hostility_score'] = min(1.0, float(user.get('hostility_score', 0.0)) + 0.2)
            user['recent_sentiment_toward_alisa'] = 'negative'
            chat['current_tension_level'] = min(1.0, float(chat.get('current_tension_level', 0.0)) + 0.15)
            chat['last_conflict_at'] = self._now()
        elif addressed_to_alisa:
            user['rapport_score'] = min(1.0, float(user.get('rapport_score', 0.0)) + 0.05)
            user['recent_sentiment_toward_alisa'] = 'positive'

        user['summary'] = self._build_user_summary(user)
        chat['chat_vibe_summary'] = self._build_chat_summary(chat)
        self._save()

    def note_alisa_reply(self, chat_id: int, user_id: int, mode: str) -> None:
        chat = self._ensure_chat(chat_id)
        user = self._ensure_user(chat, user_id, username='unknown')
        now = self._now()
        chat['last_alisa_message_at'] = now
        user['last_interaction_mode'] = mode
        user['last_significant_interaction_at'] = now
        self._save()

    def note_quiz_event(self, chat_id: int, user_id: int, username: str, correct: bool = False, won: bool = False) -> None:
        chat = self._ensure_chat(chat_id)
        user = self._ensure_user(chat, user_id, username)
        if correct:
            user['likes_quiz_score'] = int(user.get('likes_quiz_score', 0)) + 2
        if won:
            user['likes_quiz_score'] = int(user.get('likes_quiz_score', 0)) + 3
        user['summary'] = self._build_user_summary(user)
        self._save()

    def get_user_summary(self, chat_id: int, user_id: int, username: str) -> str:
        chat = self._ensure_chat(chat_id)
        user = self._ensure_user(chat, user_id, username)
        summary = str(user.get('summary') or '').strip()
        if summary:
            return summary[: settings.alisa_memory_summary_max_chars]
        return 'Пока почти ничего не известно. Новый или молчаливый участник.'

    def get_chat_summary(self, chat_id: int) -> str:
        chat = self._ensure_chat(chat_id)
        summary = str(chat.get('chat_vibe_summary') or '').strip()
        if summary:
            return summary[: settings.alisa_memory_summary_max_chars]
        return self._build_chat_summary(chat)

    def get_relationship_hint(self, chat_id: int, user_id: int, username: str) -> str:
        chat = self._ensure_chat(chat_id)
        user = self._ensure_user(chat, user_id, username)
        rapport = float(user.get('rapport_score', 0.0))
        hostility = float(user.get('hostility_score', 0.0))
        banter = float(user.get('banter_tolerance', 0.0))
        if hostility >= 0.6:
            return 'пользователь конфликтный, держи границы и не эскалируй'
        if rapport >= 0.6 and banter >= 0.5:
            return 'контакт тёплый, можно чуть живее и с подколом'
        if rapport >= 0.4:
            return 'контакт нормальный, спокойный дружелюбный тон'
        return 'нейтральный контакт, без лишней резкости'

    def get_chat_tension_level(self, chat_id: int) -> float:
        chat = self._ensure_chat(chat_id)
        try:
            return max(0.0, min(1.0, float(chat.get('current_tension_level', 0.0))))
        except (TypeError, ValueError):
            return 0.0

    def _extract_topics(self, text: str) -> list[str]:
        stopwords = {
            'бот', 'бота', 'боту', 'сегодня', 'сейчас', 'просто', 'вообще', 'короче', 'типа',
            'очень', 'можно', 'нужно', 'давай', 'почему', 'когда', 'какой', 'какая', 'какие',
            'это', 'этот', 'того', 'тебе', 'меня', 'мне', 'него', 'нее', 'него', 'них',
            'есть', 'как', 'что', 'кто', 'где', 'или', 'для', 'надо', 'если', 'еще', 'ещё',
            'привет', 'ладно', 'хочу', 'будет', 'сети', 'интернете'
        }
        words = re.findall(r'[A-Za-zА-Яа-яЁё0-9]{4,}', text.lower())
        filtered = [w for w in words if w not in stopwords]
        counts = Counter(filtered)
        return [word for word, _ in counts.most_common(5)]

    def _bump_scores(self, target: dict[str, Any], topics: list[str], weight: int) -> None:
        for topic in topics:
            target[topic] = int(target.get(topic, 0)) + weight

    def _build_user_summary(self, user: dict[str, Any]) -> str:
        topic_scores = user.get('topic_scores', {}) or {}
        top_topics = [name for name, _ in sorted(topic_scores.items(), key=lambda x: (-x[1], x[0]))[:4]]

        parts: list[str] = []
        if int(user.get('likes_quiz_score', 0)) >= 4:
            parts.append('любит квизы или активно в них участвует')
        if bool(user.get('roast_opt_in')):
            parts.append('нормально относится к дружескому подколу')
        if float(user.get('hostility_score', 0.0)) >= 0.4:
            parts.append('иногда уходит в конфликтный тон')
        if top_topics:
            parts.append('частые темы: ' + ', '.join(top_topics))
        if int(user.get('message_count', 0)) >= 20:
            parts.append('довольно активный участник')
        summary = '; '.join(parts) if parts else 'пока почти ничего не известно'
        return summary[: settings.alisa_memory_summary_max_chars]

    def _build_chat_summary(self, chat: dict[str, Any]) -> str:
        topic_scores = chat.get('topic_scores', {}) or {}
        top_topics = [name for name, _ in sorted(topic_scores.items(), key=lambda x: (-x[1], x[0]))[:5]]
        message_count = int(chat.get('message_count', 0))
        parts: list[str] = []
        if message_count >= 100:
            parts.append('чат разговорчивый')
        elif message_count >= 20:
            parts.append('чат умеренно активный')
        else:
            parts.append('чат пока не очень активный')

        tension = float(chat.get('current_tension_level', 0.0))
        if tension >= 0.6:
            parts.append('напряжение высокое')
        elif tension >= 0.3:
            parts.append('напряжение умеренное')

        if top_topics:
            parts.append('частые темы: ' + ', '.join(top_topics))
        return '; '.join(parts)[: settings.alisa_memory_summary_max_chars]
