from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite


class ProductStore:
    def __init__(self, path: str = 'data/quiz_product.db') -> None:
        self.path = path
        self._initialized = False

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return

        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS player_progress (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                season_points INTEGER NOT NULL DEFAULT 0,
                total_games INTEGER NOT NULL DEFAULT 0,
                total_wins INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                best_streak INTEGER NOT NULL DEFAULT 0,
                titles_json TEXT NOT NULL DEFAULT '[]',
                achievements_json TEXT NOT NULL DEFAULT '[]',
                last_played_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (chat_id, user_id)
            )
            """)
            await db.commit()

        self._initialized = True

    async def note_correct(
        self,
        chat_id: int,
        user_id: int,
        username: str,
        points: int,
        streak_count: int,
    ) -> None:
        await self.ensure_initialized()
        player = await self._get_player(chat_id, user_id, username)

        player['season_points'] += int(points)
        player['total_correct'] += 1
        player['best_streak'] = max(int(player['best_streak']), int(streak_count))
        player['last_played_at'] = self._now()

        achievements = self._loads_list(player['achievements_json'])
        titles = self._loads_list(player['titles_json'])

        self._grant_achievement(achievements, 'first_blood', 'Первый точный ответ')
        if player['best_streak'] >= 3:
            self._grant_achievement(achievements, 'streak_3', 'Серия x3')
        if player['best_streak'] >= 5:
            self._grant_achievement(achievements, 'streak_5', 'Серия x5')
        if player['total_correct'] >= 25:
            self._grant_achievement(achievements, 'correct_25', '25 точных ответов')
        if player['total_correct'] >= 100:
            self._grant_achievement(achievements, 'correct_100', '100 точных ответов')

        self._grant_title(titles, player)
        self._grant_mission_rewards(achievements, player)

        player['achievements_json'] = json.dumps(achievements, ensure_ascii=False)
        player['titles_json'] = json.dumps(titles, ensure_ascii=False)

        await self._save_player(player)

    async def note_match_result(
        self,
        chat_id: int,
        ranking: list[tuple[int, str, int]],
    ) -> None:
        await self.ensure_initialized()

        if not ranking:
            return

        winner_user_id = ranking[0][0]

        for user_id, username, _points in ranking:
            player = await self._get_player(chat_id, user_id, username)
            player['total_games'] += 1
            player['season_points'] += 1
            player['last_played_at'] = self._now()

            achievements = self._loads_list(player['achievements_json'])
            titles = self._loads_list(player['titles_json'])

            if user_id == winner_user_id:
                player['total_wins'] += 1
                player['season_points'] += 5
                self._grant_achievement(achievements, 'first_win', 'Первая победа')
                if player['total_wins'] >= 10:
                    self._grant_achievement(achievements, 'wins_10', '10 побед')
                if player['total_wins'] >= 25:
                    self._grant_achievement(achievements, 'wins_25', '25 побед')

            self._grant_title(titles, player)
            self._grant_mission_rewards(achievements, player)

            player['achievements_json'] = json.dumps(achievements, ensure_ascii=False)
            player['titles_json'] = json.dumps(titles, ensure_ascii=False)
            await self._save_player(player)

    async def get_player_text(self, chat_id: int, user_id: int, username: str) -> str:
        await self.ensure_initialized()
        player = await self._get_player(chat_id, user_id, username)

        titles = self._loads_list(player['titles_json'])
        achievements = self._loads_list(player['achievements_json'])

        title = titles[-1] if titles else 'Новичок'
        achv = ', '.join([item['label'] for item in achievements[-4:]]) if achievements else 'пока нет'
        missions = self._build_missions(player)

        mission_lines = ['🎯 Миссии:']
        for mission in missions:
            mark = '✅' if mission['done'] else '⬜'
            mission_lines.append(
                f'{mark} {mission["title"]}: {mission["progress"]}/{mission["target"]}'
            )
        mission_lines.append('🎁 Награды за миссии: только ачивки и титулы (без SP).')

        return (
            '🙋 Профиль игрока\n'
            f'Игрок: @{player["username"]}\n'
            f'Титул: {title}\n'
            f'Сезонные очки: {player["season_points"]}\n'
            f'Игр сыграно: {player["total_games"]}\n'
            f'Побед: {player["total_wins"]}\n'
            f'Точных ответов: {player["total_correct"]}\n'
            f'Лучшая серия: {player["best_streak"]}\n'
            f'Ачивки: {achv}\n\n'
            + '\n'.join(mission_lines)
        )

    def _build_missions(self, player: dict[str, Any]) -> list[dict[str, Any]]:
        total_games = int(player.get('total_games', 0))
        total_wins = int(player.get('total_wins', 0))
        total_correct = int(player.get('total_correct', 0))
        best_streak = int(player.get('best_streak', 0))

        missions = [
            {'title': 'Сыграть 5 матчей', 'progress': total_games, 'target': 5},
            {'title': 'Выиграть 3 матча', 'progress': total_wins, 'target': 3},
            {'title': 'Дать 25 точных ответов', 'progress': total_correct, 'target': 25},
            {'title': 'Взять серию x3', 'progress': best_streak, 'target': 3},
            {'title': 'Взять серию x5', 'progress': best_streak, 'target': 5},
        ]

        for mission in missions:
            mission['progress'] = min(int(mission['progress']), int(mission['target']))
            mission['done'] = mission['progress'] >= int(mission['target'])

        return missions

    async def get_season_text(self, chat_id: int, limit: int = 10) -> str:
        await self.ensure_initialized()

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("""
            SELECT username, season_points, total_wins, total_correct
            FROM player_progress
            WHERE chat_id = ?
            ORDER BY season_points DESC, total_wins DESC, total_correct DESC, username ASC
            LIMIT ?
            """, (chat_id, limit))

        if not rows:
            return '🏅 Сезонный рейтинг пока пуст.'

        lines = ['🏅 Сезонный топ:']
        for idx, row in enumerate(rows, start=1):
            lines.append(
                f'{idx}. @{row["username"]} — {row["season_points"]} SP | '
                f'победы: {row["total_wins"]} | точных: {row["total_correct"]}'
            )
        return '\n'.join(lines)

    async def _get_player(self, chat_id: int, user_id: int, username: str) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM player_progress WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            row = await cursor.fetchone()

        if row:
            data = dict(row)
            data['username'] = username
            return data

        return {
            'chat_id': chat_id,
            'user_id': user_id,
            'username': username,
            'season_points': 0,
            'total_games': 0,
            'total_wins': 0,
            'total_correct': 0,
            'best_streak': 0,
            'titles_json': '[]',
            'achievements_json': '[]',
            'last_played_at': self._now(),
        }

    async def _save_player(self, player: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            INSERT INTO player_progress (
                chat_id, user_id, username,
                season_points, total_games, total_wins,
                total_correct, best_streak,
                titles_json, achievements_json, last_played_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = excluded.username,
                season_points = excluded.season_points,
                total_games = excluded.total_games,
                total_wins = excluded.total_wins,
                total_correct = excluded.total_correct,
                best_streak = excluded.best_streak,
                titles_json = excluded.titles_json,
                achievements_json = excluded.achievements_json,
                last_played_at = excluded.last_played_at
            """, (
                player['chat_id'], player['user_id'], player['username'],
                player['season_points'], player['total_games'], player['total_wins'],
                player['total_correct'], player['best_streak'],
                player['titles_json'], player['achievements_json'], player['last_played_at'],
            ))
            await db.commit()

    def _grant_title(self, titles: list[str], player: dict[str, Any]) -> None:
        title = 'Новичок'
        if player['total_correct'] >= 20:
            title = 'Охотник за фактами'
        if player['total_correct'] >= 50:
            title = 'Машина ответов'
        if player['total_wins'] >= 10:
            title = 'Король квиза'
        if player['total_wins'] >= 25:
            title = 'Император викторин'

        if title not in titles:
            titles.append(title)

    def _grant_achievement(self, achievements: list[dict[str, str]], code: str, label: str) -> None:
        if any(item.get('code') == code for item in achievements):
            return
        achievements.append({'code': code, 'label': label})

    def _grant_mission_rewards(self, achievements: list[dict[str, str]], player: dict[str, Any]) -> None:
        missions = self._build_missions(player)
        rewards = {
            'Сыграть 5 матчей': ('mission_games_5', '🎁 Миссия: сыграть 5 матчей'),
            'Выиграть 3 матча': ('mission_wins_3', '🎁 Миссия: выиграть 3 матча'),
            'Дать 25 точных ответов': ('mission_correct_25', '🎁 Миссия: 25 точных ответов'),
            'Взять серию x3': ('mission_streak_3', '🎁 Миссия: серия x3'),
            'Взять серию x5': ('mission_streak_5', '🎁 Миссия: серия x5'),
        }
        for mission in missions:
            if not mission['done']:
                continue
            reward = rewards.get(mission['title'])
            if not reward:
                continue
            code, label = reward
            self._grant_achievement(achievements, code, label)

    def _loads_list(self, raw: str) -> list[Any]:
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return value
        except Exception:
            pass
        return []

    def _now(self) -> str:
        return datetime.utcnow().isoformat(timespec='seconds') + 'Z'
