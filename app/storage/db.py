from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import aiosqlite


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

    async def save_game_result(
        self,
        chat_id: int,
        finished_at: str,
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
                    chat_id, finished_at, winner_user_id, winner_username, winner_points, total_questions
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (chat_id, finished_at, winner_user_id, winner_username, winner_points, total_questions),
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

    async def healthcheck(self) -> bool:
        try:
            async with aiosqlite.connect(self.path) as db:
                async with db.execute('SELECT 1') as cursor:
                    row = await cursor.fetchone()
                    return bool(row and row[0] == 1)
        except Exception:
            return False
