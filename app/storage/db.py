from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

import aiosqlite

from app.core.models import PlayerSkillSnapshot, QuestionCandidate, QuestionUsageRecord


class Database:
    def __init__(self, path: str = 'data/quiz.db') -> None:
        self.path = path

    async def init(self) -> None:
        db_path = Path(self.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS game_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    finished_at TEXT NOT NULL,
                    quiz_mode TEXT NOT NULL DEFAULT 'classic',
                    winner_user_id INTEGER,
                    winner_username TEXT,
                    winner_points INTEGER NOT NULL DEFAULT 0,
                    total_questions INTEGER NOT NULL DEFAULT 0
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS player_stats (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    total_points INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS weekly_player_stats (
                    chat_id INTEGER NOT NULL,
                    week_start TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    total_points INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_id, week_start, user_id)
                )
                '''
            )

            async with db.execute('PRAGMA table_info(game_results)') as cursor:
                cols = await cursor.fetchall()
            col_names = {row[1] for row in cols}
            if 'quiz_mode' not in col_names:
                await db.execute(
                    "ALTER TABLE game_results ADD COLUMN quiz_mode TEXT NOT NULL DEFAULT 'classic'"
                )
            await db.commit()

        await self.create_llm_quiz_tables()

    async def create_llm_quiz_tables(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS llm_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'ru',
                    topic TEXT NOT NULL,
                    subtopic TEXT NOT NULL DEFAULT '',
                    difficulty TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    options_json TEXT NOT NULL DEFAULT '[]',
                    correct_option_index INTEGER,
                    correct_answer_text TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    canonical_facts_json TEXT NOT NULL DEFAULT '[]',
                    uniqueness_tags_json TEXT NOT NULL DEFAULT '[]',
                    question_hash TEXT NOT NULL,
                    uniqueness_hash TEXT NOT NULL,
                    quality_score REAL NOT NULL DEFAULT 0,
                    is_valid INTEGER NOT NULL DEFAULT 1,
                    generated_at TEXT NOT NULL,
                    expires_at TEXT,
                    created_for_mode TEXT NOT NULL DEFAULT 'classic'
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS question_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    player_id INTEGER,
                    game_id TEXT,
                    round_id TEXT,
                    shown_at TEXT NOT NULL,
                    answered_at TEXT,
                    was_correct INTEGER,
                    response_ms INTEGER,
                    local_game_date TEXT NOT NULL,
                    FOREIGN KEY(question_id) REFERENCES llm_questions(id)
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS player_skill_profile (
                    player_id INTEGER PRIMARY KEY,
                    global_skill_score REAL NOT NULL DEFAULT 0,
                    current_band TEXT NOT NULL DEFAULT 'easy',
                    recent_accuracy REAL NOT NULL DEFAULT 0,
                    recent_avg_response_ms REAL NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    last_played_at TEXT,
                    daily_streak INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    answers_total INTEGER NOT NULL DEFAULT 0,
                    answers_correct INTEGER NOT NULL DEFAULT 0
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS player_topic_skill (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    skill_score REAL NOT NULL DEFAULT 0,
                    recent_accuracy REAL NOT NULL DEFAULT 0,
                    attempts_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(player_id, topic)
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS daily_generation_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_game_date TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    target_topic TEXT NOT NULL DEFAULT '',
                    target_difficulty_mix_json TEXT NOT NULL DEFAULT '{}',
                    needed_count INTEGER NOT NULL,
                    generated_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS question_rejection_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_payload TEXT NOT NULL,
                    reject_reason TEXT NOT NULL,
                    matched_question_id INTEGER,
                    matched_uniqueness_hash TEXT,
                    created_at TEXT NOT NULL
                )
                '''
            )

            await db.execute('CREATE INDEX IF NOT EXISTS idx_llm_questions_question_hash ON llm_questions(question_hash)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_llm_questions_uniqueness_hash ON llm_questions(uniqueness_hash)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_usage_chat_local_date ON question_usage_log(chat_id, local_game_date)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_usage_player_shown ON question_usage_log(player_id, shown_at)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_usage_chat_shown ON question_usage_log(chat_id, shown_at)')
            await db.commit()

    def _week_start(self, iso_value: str) -> str:
        normalized = iso_value.replace('Z', '+00:00')
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        week_start_dt = dt_utc - timedelta(days=dt_utc.weekday())
        week_start_dt = week_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return week_start_dt.date().isoformat()

    async def save_generated_questions(self, batch: List[QuestionCandidate]) -> int:
        if not batch:
            return 0
        generated_at = datetime.now(timezone.utc).isoformat()
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for item in batch:
                await db.execute(
                    '''
                    INSERT INTO llm_questions (
                        provider_name, model_name, language, topic, subtopic,
                        difficulty, question_type, question_text, options_json,
                        correct_option_index, correct_answer_text, explanation,
                        canonical_facts_json, uniqueness_tags_json, question_hash,
                        uniqueness_hash, quality_score, is_valid, generated_at,
                        expires_at, created_for_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        item.provider_name,
                        item.model_name,
                        item.language,
                        item.topic,
                        item.subtopic,
                        item.difficulty,
                        item.question_type,
                        item.question_text,
                        str(item.options),
                        item.correct_option_index,
                        item.correct_answer_text,
                        item.explanation,
                        str(item.canonical_facts),
                        str(item.uniqueness_tags),
                        item.question_hash,
                        item.uniqueness_hash,
                        item.quality_score,
                        1 if item.is_valid else 0,
                        generated_at,
                        None,
                        item.created_for_mode,
                    ),
                )
                inserted += 1
            await db.commit()
        return inserted

    async def get_candidate_questions(
        self,
        difficulty: str,
        limit: int,
        topic: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            query = (
                'SELECT * FROM llm_questions WHERE is_valid = 1 AND difficulty = ? '
                "AND (expires_at IS NULL OR expires_at > datetime('now'))"
            )
            params: list[Any] = [difficulty]
            if topic:
                query += ' AND topic = ?'
                params.append(topic)
            if mode:
                query += ' AND created_for_mode IN (?, ?)'
                params.extend([mode, 'classic'])
            query += ' ORDER BY quality_score DESC, id DESC LIMIT ?'
            params.append(limit)
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def log_question_usage(self, record: QuestionUsageRecord) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO question_usage_log (
                    question_id, chat_id, player_id, game_id, round_id, shown_at,
                    answered_at, was_correct, response_ms, local_game_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.question_id,
                    record.chat_id,
                    record.player_id,
                    record.game_id,
                    record.round_id,
                    record.shown_at,
                    record.answered_at,
                    None if record.was_correct is None else int(record.was_correct),
                    record.response_ms,
                    record.local_game_date or datetime.now(timezone.utc).date().isoformat(),
                ),
            )
            await db.commit()

    async def get_recent_question_usage_for_chat(self, chat_id: int, days: int = 5) -> List[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM question_usage_log WHERE chat_id = ? AND shown_at >= ?',
                (chat_id, cutoff),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_recent_question_usage_for_player(self, player_id: int, days: int = 5) -> List[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM question_usage_log WHERE player_id = ? AND shown_at >= ?',
                (player_id, cutoff),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_player_skill_profile(self, player_id: int) -> PlayerSkillSnapshot:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM player_skill_profile WHERE player_id = ?', (player_id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return PlayerSkillSnapshot(player_id=player_id)
        data = dict(row)
        return PlayerSkillSnapshot(
            player_id=player_id,
            global_skill_score=float(data.get('global_skill_score', 0.0)),
            current_band=str(data.get('current_band', 'easy')),
            recent_accuracy=float(data.get('recent_accuracy', 0.0)),
            recent_avg_response_ms=float(data.get('recent_avg_response_ms', 0.0)),
            current_streak=int(data.get('current_streak', 0)),
            best_streak=int(data.get('best_streak', 0)),
            daily_streak=int(data.get('daily_streak', 0)),
            games_played=int(data.get('games_played', 0)),
            answers_total=int(data.get('answers_total', 0)),
            answers_correct=int(data.get('answers_correct', 0)),
        )

    async def upsert_player_skill_profile(self, snapshot: PlayerSkillSnapshot) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO player_skill_profile (
                    player_id, global_skill_score, current_band, recent_accuracy,
                    recent_avg_response_ms, current_streak, best_streak,
                    last_played_at, daily_streak, games_played, answers_total, answers_correct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    global_skill_score=excluded.global_skill_score,
                    current_band=excluded.current_band,
                    recent_accuracy=excluded.recent_accuracy,
                    recent_avg_response_ms=excluded.recent_avg_response_ms,
                    current_streak=excluded.current_streak,
                    best_streak=excluded.best_streak,
                    last_played_at=excluded.last_played_at,
                    daily_streak=excluded.daily_streak,
                    games_played=excluded.games_played,
                    answers_total=excluded.answers_total,
                    answers_correct=excluded.answers_correct
                ''',
                (
                    snapshot.player_id,
                    snapshot.global_skill_score,
                    snapshot.current_band,
                    snapshot.recent_accuracy,
                    snapshot.recent_avg_response_ms,
                    snapshot.current_streak,
                    snapshot.best_streak,
                    now_iso,
                    snapshot.daily_streak,
                    snapshot.games_played,
                    snapshot.answers_total,
                    snapshot.answers_correct,
                ),
            )
            await db.commit()

    async def get_player_topic_skill(self, player_id: int, topic: str) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM player_topic_skill WHERE player_id = ? AND topic = ?',
                (player_id, topic),
            ) as cursor:
                row = await cursor.fetchone()
        return None if not row else dict(row)

    async def upsert_player_topic_skill(
        self,
        player_id: int,
        topic: str,
        skill_score: float,
        recent_accuracy: float,
        attempts_count: int,
    ) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO player_topic_skill (
                    player_id, topic, skill_score, recent_accuracy, attempts_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, topic) DO UPDATE SET
                    skill_score=excluded.skill_score,
                    recent_accuracy=excluded.recent_accuracy,
                    attempts_count=excluded.attempts_count,
                    updated_at=excluded.updated_at
                ''',
                (player_id, topic, skill_score, recent_accuracy, attempts_count, updated_at),
            )
            await db.commit()

    async def save_question_rejection(
        self,
        raw_payload: str,
        reject_reason: str,
        matched_question_id: Optional[int] = None,
        matched_uniqueness_hash: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO question_rejection_log (
                    raw_payload, reject_reason, matched_question_id,
                    matched_uniqueness_hash, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    raw_payload,
                    reject_reason,
                    matched_question_id,
                    matched_uniqueness_hash,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def save_game_result(
        self,
        chat_id: int,
        finished_at: str,
        quiz_mode: str,
        winner_user_id: Optional[int],
        winner_username: Optional[str],
        winner_points: int,
        total_questions: int,
        all_scores: List[Tuple[int, str, int]],
    ) -> None:
        week_start = self._week_start(finished_at)

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO game_results (
                    chat_id, finished_at, quiz_mode, winner_user_id, winner_username, winner_points, total_questions
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (chat_id, finished_at, quiz_mode, winner_user_id, winner_username, winner_points, total_questions),
            )

            for user_id, username, points in all_scores:
                await db.execute(
                    '''
                    INSERT INTO player_stats (chat_id, user_id, username, total_points, wins, games_played)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(chat_id, user_id) DO UPDATE SET
                        username = excluded.username,
                        total_points = player_stats.total_points + excluded.total_points,
                        wins = player_stats.wins + excluded.wins,
                        games_played = player_stats.games_played + 1
                    ''',
                    (
                        chat_id,
                        user_id,
                        username,
                        points,
                        1 if winner_user_id == user_id else 0,
                    ),
                )
                await db.execute(
                    '''
                    INSERT INTO weekly_player_stats (
                        chat_id, week_start, user_id, username, total_points, wins, games_played
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(chat_id, week_start, user_id) DO UPDATE SET
                        username = excluded.username,
                        total_points = weekly_player_stats.total_points + excluded.total_points,
                        wins = weekly_player_stats.wins + excluded.wins,
                        games_played = weekly_player_stats.games_played + 1
                    ''',
                    (
                        chat_id,
                        week_start,
                        user_id,
                        username,
                        points,
                        1 if winner_user_id == user_id else 0,
                    ),
                )

            await db.commit()

    async def get_top_players(self, chat_id: int, limit: int = 10) -> List[Tuple[str, int, int, int]]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                '''
                SELECT username, total_points, wins, games_played
                FROM player_stats
                WHERE chat_id = ?
                ORDER BY total_points DESC, wins DESC, games_played DESC
                LIMIT ?
                ''',
                (chat_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [(row[0], row[1], row[2], row[3]) for row in rows]

    async def get_weekly_top_players(
        self,
        chat_id: int,
        limit: int = 10,
        now_iso: Optional[str] = None,
    ) -> List[Tuple[str, int, int, int]]:
        week_start = self._week_start(now_iso or datetime.now(timezone.utc).isoformat())

        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                '''
                SELECT username, total_points, wins, games_played
                FROM weekly_player_stats
                WHERE chat_id = ? AND week_start = ?
                ORDER BY total_points DESC, wins DESC, games_played DESC
                LIMIT ?
                ''',
                (chat_id, week_start, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [(row[0], row[1], row[2], row[3]) for row in rows]

    async def get_last_game_result(self, chat_id: int) -> Optional[dict[str, object]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''
                SELECT id, chat_id, finished_at, winner_user_id, winner_username, winner_points, total_questions
                    , quiz_mode
                FROM game_results
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT 1
                ''',
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return dict(row)

    async def healthcheck(self) -> bool:
        try:
            async with aiosqlite.connect(self.path) as db:
                async with db.execute('SELECT 1') as cursor:
                    row = await cursor.fetchone()
                    return bool(row and row[0] == 1)
        except Exception:
            return False
