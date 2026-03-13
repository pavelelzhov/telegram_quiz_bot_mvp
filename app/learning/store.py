from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import aiosqlite


class LearningStore:
    def __init__(self, path: str = 'data/learning.db') -> None:
        self.path = path
        self._initialized = False

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return

        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                addressed_count INTEGER NOT NULL DEFAULT 0,
                quiz_correct INTEGER NOT NULL DEFAULT 0,
                quiz_close INTEGER NOT NULL DEFAULT 0,
                quiz_wrong INTEGER NOT NULL DEFAULT 0,
                search_count INTEGER NOT NULL DEFAULT 0,
                support_count INTEGER NOT NULL DEFAULT 0,
                roast_count INTEGER NOT NULL DEFAULT 0,
                topic_scores_json TEXT NOT NULL DEFAULT '{}',
                last_seen TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (chat_id, user_id)
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_profiles (
                chat_id INTEGER PRIMARY KEY,
                message_count INTEGER NOT NULL DEFAULT 0,
                quiz_count INTEGER NOT NULL DEFAULT 0,
                search_count INTEGER NOT NULL DEFAULT 0,
                bot_reply_count INTEGER NOT NULL DEFAULT 0,
                host_invites INTEGER NOT NULL DEFAULT 0,
                topic_scores_json TEXT NOT NULL DEFAULT '{}',
                category_scores_json TEXT NOT NULL DEFAULT '{}',
                round_type_scores_json TEXT NOT NULL DEFAULT '{}',
                last_updated TEXT NOT NULL DEFAULT ''
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS question_feedback (
                chat_id INTEGER NOT NULL,
                question_key TEXT NOT NULL,
                category TEXT NOT NULL,
                topic TEXT NOT NULL,
                round_type TEXT NOT NULL,
                asked_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                close_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                skip_count INTEGER NOT NULL DEFAULT 0,
                timeout_count INTEGER NOT NULL DEFAULT 0,
                response_count INTEGER NOT NULL DEFAULT 0,
                total_response_time REAL NOT NULL DEFAULT 0,
                engagement_total REAL NOT NULL DEFAULT 0,
                last_asked_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (chat_id, question_key)
            )
            """)
            await db.commit()

        self._initialized = True

    async def log_message(
        self,
        chat_id: int,
        user_id: int,
        username: str,
        text: str,
        addressed: bool = False,
    ) -> None:
        await self.ensure_initialized()

        text = (text or '').strip()
        if not text:
            return

        user = await self._get_user(chat_id, user_id, username)
        chat = await self._get_chat(chat_id)

        user['message_count'] += 1
        if addressed:
            user['addressed_count'] += 1
        user['last_seen'] = self._now()

        chat['message_count'] += 1
        chat['last_updated'] = self._now()

        topics = self._extract_topics(text)
        self._bump_scores(user['topic_scores_json'], topics, 2)
        self._bump_scores(chat['topic_scores_json'], topics, 1)

        lowered = text.lower()
        if self._looks_supportive_context(lowered):
            user['support_count'] += 1
        if self._looks_roast_request(lowered):
            user['roast_count'] += 1

        await self._save_user(user)
        await self._save_chat(chat)

    async def log_search(
        self,
        chat_id: int,
        user_id: int,
        username: str,
        query: str,
    ) -> None:
        await self.ensure_initialized()

        user = await self._get_user(chat_id, user_id, username)
        chat = await self._get_chat(chat_id)

        user['search_count'] += 1
        user['last_seen'] = self._now()
        chat['search_count'] += 1
        chat['last_updated'] = self._now()

        topics = self._extract_topics(query)
        self._bump_scores(user['topic_scores_json'], topics, 2)
        self._bump_scores(chat['topic_scores_json'], topics, 1)

        await self._save_user(user)
        await self._save_chat(chat)

    async def log_bot_reply(self, chat_id: int, kind: str = 'reply') -> None:
        await self.ensure_initialized()

        chat = await self._get_chat(chat_id)
        chat['bot_reply_count'] += 1
        if kind == 'host_invite':
            chat['host_invites'] += 1
        chat['last_updated'] = self._now()
        await self._save_chat(chat)

    async def log_question_presented(
        self,
        chat_id: int,
        question_key: str,
        category: str,
        topic: str,
        round_type: str,
    ) -> None:
        await self.ensure_initialized()

        feedback = await self._get_question(chat_id, question_key, category, topic, round_type)
        feedback['asked_count'] += 1
        feedback['last_asked_at'] = self._now()
        await self._save_question(feedback)

        chat = await self._get_chat(chat_id)
        chat['quiz_count'] += 1
        chat['last_updated'] = self._now()
        await self._save_chat(chat)

    async def log_answer_attempt(
        self,
        chat_id: int,
        user_id: int,
        username: str,
        question_key: str,
        category: str,
        topic: str,
        round_type: str,
        verdict: str,
        elapsed_sec: float | None = None,
    ) -> None:
        await self.ensure_initialized()

        user = await self._get_user(chat_id, user_id, username)
        user['last_seen'] = self._now()

        if verdict == 'correct':
            user['quiz_correct'] += 1
        elif verdict == 'close':
            user['quiz_close'] += 1
        else:
            user['quiz_wrong'] += 1

        if topic:
            self._bump_scores(user['topic_scores_json'], [topic], 2)

        await self._save_user(user)

        feedback = await self._get_question(chat_id, question_key, category, topic, round_type)
        feedback['response_count'] += 1
        if elapsed_sec is not None:
            feedback['total_response_time'] += max(float(elapsed_sec), 0.0)

        if verdict == 'correct':
            feedback['correct_count'] += 1
        elif verdict == 'close':
            feedback['close_count'] += 1
        else:
            feedback['wrong_count'] += 1

        await self._save_question(feedback)

    async def log_question_closed(
        self,
        chat_id: int,
        question_key: str,
        category: str,
        topic: str,
        round_type: str,
        outcome: str,
        engagement_score: float,
    ) -> None:
        await self.ensure_initialized()

        feedback = await self._get_question(chat_id, question_key, category, topic, round_type)

        if outcome == 'skip':
            feedback['skip_count'] += 1
        elif outcome == 'timeout':
            feedback['timeout_count'] += 1

        feedback['engagement_total'] += max(float(engagement_score), 0.0)
        await self._save_question(feedback)

        chat = await self._get_chat(chat_id)

        category_boost = engagement_score
        round_type_boost = engagement_score

        if outcome == 'skip':
            category_boost *= 0.25
            round_type_boost *= 0.25
        elif outcome == 'timeout':
            category_boost *= 0.15
            round_type_boost *= 0.15

        if category:
            self._bump_scores(chat['category_scores_json'], [category], category_boost)
        if round_type:
            self._bump_scores(chat['round_type_scores_json'], [round_type], round_type_boost)

        chat['last_updated'] = self._now()
        await self._save_chat(chat)

    async def get_user_profile_text(self, chat_id: int, user_id: int, username: str) -> str:
        await self.ensure_initialized()
        user = await self._get_user(chat_id, user_id, username)

        parts: list[str] = []

        if user['message_count'] >= 25:
            parts.append('довольно активный участник')
        elif user['message_count'] >= 8:
            parts.append('умеренно активный участник')

        if user['quiz_correct'] >= 6:
            parts.append('хорошо отвечает в квизе')
        elif user['quiz_correct'] >= 2:
            parts.append('иногда попадает в ответы квиза')

        if user['search_count'] >= 3:
            parts.append('любит поисковые запросы и свежую инфу')
        if user['support_count'] >= 2:
            parts.append('иногда приходит за поддержкой или мягким разговором')
        if user['roast_count'] >= 1:
            parts.append('нормально относится к дружеской прожарке')

        top_topics = self._top_keys(user['topic_scores_json'], 4)
        if top_topics:
            parts.append('частые темы: ' + ', '.join(top_topics))

        if not parts:
            return 'Пока мало данных: участник ещё не успел раскрыться.'
        return '; '.join(parts)

    async def get_chat_profile_text(self, chat_id: int) -> str:
        await self.ensure_initialized()
        chat = await self._get_chat(chat_id)

        parts: list[str] = []
        if chat['message_count'] >= 120:
            parts.append('чат очень живой')
        elif chat['message_count'] >= 30:
            parts.append('чат умеренно активный')
        else:
            parts.append('чат пока набирает характер')

        top_topics = self._top_keys(chat['topic_scores_json'], 5)
        if top_topics:
            parts.append('любимые темы: ' + ', '.join(top_topics))

        top_categories = self._top_keys(chat['category_scores_json'], 3)
        if top_categories:
            parts.append('в квизе лучше заходят: ' + ', '.join(top_categories))

        top_round_types = self._top_keys(chat['round_type_scores_json'], 3)
        if top_round_types:
            normalized = [self._human_round_type(x) for x in top_round_types]
            parts.append('по формату чаще цепляет: ' + ', '.join(normalized))

        return '; '.join(parts)

    async def get_category_bias(self, chat_id: int) -> dict[str, float]:
        await self.ensure_initialized()
        chat = await self._get_chat(chat_id)
        scores = self._loads_json(chat['category_scores_json'])
        if not scores:
            return {}

        ordered = sorted(scores.items(), key=lambda x: (-float(x[1]), x[0]))[:3]
        bias: dict[str, float] = {}
        for idx, (category, _) in enumerate(ordered):
            if idx == 0:
                bias[category] = 2.0
            elif idx == 1:
                bias[category] = 1.0
            else:
                bias[category] = 0.5
        return bias

    async def _get_user(self, chat_id: int, user_id: int, username: str) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchone(
                "SELECT * FROM user_profiles WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )

        if row:
            data = dict(row)
            data['username'] = username
            return data

        return {
            'chat_id': chat_id,
            'user_id': user_id,
            'username': username,
            'message_count': 0,
            'addressed_count': 0,
            'quiz_correct': 0,
            'quiz_close': 0,
            'quiz_wrong': 0,
            'search_count': 0,
            'support_count': 0,
            'roast_count': 0,
            'topic_scores_json': '{}',
            'last_seen': self._now(),
        }

    async def _save_user(self, user: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            INSERT INTO user_profiles (
                chat_id, user_id, username, message_count, addressed_count,
                quiz_correct, quiz_close, quiz_wrong,
                search_count, support_count, roast_count,
                topic_scores_json, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = excluded.username,
                message_count = excluded.message_count,
                addressed_count = excluded.addressed_count,
                quiz_correct = excluded.quiz_correct,
                quiz_close = excluded.quiz_close,
                quiz_wrong = excluded.quiz_wrong,
                search_count = excluded.search_count,
                support_count = excluded.support_count,
                roast_count = excluded.roast_count,
                topic_scores_json = excluded.topic_scores_json,
                last_seen = excluded.last_seen
            """, (
                user['chat_id'], user['user_id'], user['username'], user['message_count'], user['addressed_count'],
                user['quiz_correct'], user['quiz_close'], user['quiz_wrong'],
                user['search_count'], user['support_count'], user['roast_count'],
                user['topic_scores_json'], user['last_seen'],
            ))
            await db.commit()

    async def _get_chat(self, chat_id: int) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchone(
                "SELECT * FROM chat_profiles WHERE chat_id = ?",
                (chat_id,),
            )

        if row:
            return dict(row)

        return {
            'chat_id': chat_id,
            'message_count': 0,
            'quiz_count': 0,
            'search_count': 0,
            'bot_reply_count': 0,
            'host_invites': 0,
            'topic_scores_json': '{}',
            'category_scores_json': '{}',
            'round_type_scores_json': '{}',
            'last_updated': self._now(),
        }

    async def _save_chat(self, chat: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            INSERT INTO chat_profiles (
                chat_id, message_count, quiz_count, search_count,
                bot_reply_count, host_invites,
                topic_scores_json, category_scores_json, round_type_scores_json,
                last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                message_count = excluded.message_count,
                quiz_count = excluded.quiz_count,
                search_count = excluded.search_count,
                bot_reply_count = excluded.bot_reply_count,
                host_invites = excluded.host_invites,
                topic_scores_json = excluded.topic_scores_json,
                category_scores_json = excluded.category_scores_json,
                round_type_scores_json = excluded.round_type_scores_json,
                last_updated = excluded.last_updated
            """, (
                chat['chat_id'], chat['message_count'], chat['quiz_count'], chat['search_count'],
                chat['bot_reply_count'], chat['host_invites'],
                chat['topic_scores_json'], chat['category_scores_json'], chat['round_type_scores_json'],
                chat['last_updated'],
            ))
            await db.commit()

    async def _get_question(
        self,
        chat_id: int,
        question_key: str,
        category: str,
        topic: str,
        round_type: str,
    ) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchone(
                "SELECT * FROM question_feedback WHERE chat_id = ? AND question_key = ?",
                (chat_id, question_key),
            )

        if row:
            data = dict(row)
            data['category'] = category or data['category']
            data['topic'] = topic or data['topic']
            data['round_type'] = round_type or data['round_type']
            return data

        return {
            'chat_id': chat_id,
            'question_key': question_key,
            'category': category,
            'topic': topic,
            'round_type': round_type,
            'asked_count': 0,
            'correct_count': 0,
            'close_count': 0,
            'wrong_count': 0,
            'skip_count': 0,
            'timeout_count': 0,
            'response_count': 0,
            'total_response_time': 0.0,
            'engagement_total': 0.0,
            'last_asked_at': self._now(),
        }

    async def _save_question(self, item: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            INSERT INTO question_feedback (
                chat_id, question_key, category, topic, round_type,
                asked_count, correct_count, close_count, wrong_count,
                skip_count, timeout_count, response_count, total_response_time,
                engagement_total, last_asked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, question_key) DO UPDATE SET
                category = excluded.category,
                topic = excluded.topic,
                round_type = excluded.round_type,
                asked_count = excluded.asked_count,
                correct_count = excluded.correct_count,
                close_count = excluded.close_count,
                wrong_count = excluded.wrong_count,
                skip_count = excluded.skip_count,
                timeout_count = excluded.timeout_count,
                response_count = excluded.response_count,
                total_response_time = excluded.total_response_time,
                engagement_total = excluded.engagement_total,
                last_asked_at = excluded.last_asked_at
            """, (
                item['chat_id'], item['question_key'], item['category'], item['topic'], item['round_type'],
                item['asked_count'], item['correct_count'], item['close_count'], item['wrong_count'],
                item['skip_count'], item['timeout_count'], item['response_count'], item['total_response_time'],
                item['engagement_total'], item['last_asked_at'],
            ))
            await db.commit()

    def _loads_json(self, raw: str) -> dict[str, float]:
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return {str(k): float(v) for k, v in value.items()}
        except Exception:
            pass
        return {}

    def _dumps_json(self, value: dict[str, float]) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _bump_scores(self, raw_json: str, keys: list[str], delta: float) -> str:
        scores = self._loads_json(raw_json)
        for key in keys:
            key = (key or '').strip()
            if not key:
                continue
            scores[key] = float(scores.get(key, 0.0)) + float(delta)
        return self._dumps_json(scores)

    def _top_keys(self, raw_json: str, limit: int) -> list[str]:
        scores = self._loads_json(raw_json)
        ordered = sorted(scores.items(), key=lambda x: (-float(x[1]), x[0]))
        return [k for k, _ in ordered[:limit]]

    def _human_round_type(self, value: str) -> str:
        mapping = {
            'text': 'классика',
            'image': 'картинки',
            'audio': 'музыка',
        }
        return mapping.get(value, value)

    def _extract_topics(self, text: str) -> list[str]:
        stopwords = {
            'бот','бота','боту','сегодня','сейчас','вообще','короче','очень','можно','нужно','давай',
            'почему','когда','какой','какая','какие','это','этот','того','тебе','меня','мне','него',
            'есть','как','что','кто','где','или','для','надо','если','еще','ещё','привет','ладно',
            'хочу','будет','сети','интернете','просто','найди','поищи','курс','сегодня'
        }
        words = re.findall(r'[A-Za-zА-Яа-яЁё0-9]{4,}', text.lower())
        filtered = [w for w in words if w not in stopwords]
        counts = Counter(filtered)
        return [word for word, _ in counts.most_common(5)]

    def _looks_supportive_context(self, lowered: str) -> bool:
        tokens = ['тревожно', 'устал', 'не вывожу', 'грустно', 'тяжело', 'накрывает', 'паника', 'плохо']
        return any(token in lowered for token in tokens)

    def _looks_roast_request(self, lowered: str) -> bool:
        tokens = ['обосри', 'прожарь', 'роаст', 'разнеси меня', 'поругай меня']
        return any(token in lowered for token in tokens)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
