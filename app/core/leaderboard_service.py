from __future__ import annotations


class LeaderboardService:
    def format_chat_top(
        self,
        rows: list[tuple[str, int, int, int]],
        extended: list[dict] | None = None,
    ) -> str:
        if not rows:
            return 'Пока статистики по этому чату нет.'

        lines = ['📈 Топ игроков чата:']
        for idx, (username, total_points, wins, games_played) in enumerate(rows, start=1):
            lines.append(f'{idx}. @{username} — очки: {total_points}, победы: {wins}, игр: {games_played}')
        if extended:
            lines.append('')
            lines.append('Доп. метрики:')
            for item in extended:
                lines.append(
                    f"@{item.get('username','user')}: accuracy {item.get('accuracy',0):.0%}, "
                    f"avg diff {item.get('avg_difficulty','medium')}, band {item.get('current_band','easy')}, "
                    f"best streak {item.get('best_streak',0)}, 7d {item.get('last_7d_points',0)} pts"
                )
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
