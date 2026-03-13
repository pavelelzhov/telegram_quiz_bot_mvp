from __future__ import annotations


class LeaderboardService:
    def format_chat_top(
        self,
        rows: list[tuple[str, int, int, int]],
    ) -> str:
        if not rows:
            return 'Пока статистики по этому чату нет.'

        lines = ['📈 Топ игроков чата:']
        for idx, (username, total_points, wins, games_played) in enumerate(rows, start=1):
            lines.append(f'{idx}. @{username} — очки: {total_points}, победы: {wins}, игр: {games_played}')
        return '\n'.join(lines)

    def format_weekly_top(
        self,
        rows: list[tuple[str, int, int, int]],
    ) -> str:
        if not rows:
            return 'За эту неделю пока нет результатов.'

        lines = ['🗓 Недельный топ игроков:']
        for idx, (username, total_points, wins, games_played) in enumerate(rows, start=1):
            lines.append(f'{idx}. @{username} — очки: {total_points}, победы: {wins}, игр: {games_played}')
        return '\n'.join(lines)
