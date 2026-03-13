from __future__ import annotations

from typing import Iterable

from app.core.models import PlayerScore


class GameSummaryService:
    def build_ranking(self, scores: Iterable[PlayerScore]) -> list[PlayerScore]:
        return sorted(scores, key=lambda item: (-item.points, item.username.lower()))

    def build_summary_lines(
        self,
        *,
        ranking: list[PlayerScore],
        mode_label: str,
        team_score_lines: list[str] | None = None,
    ) -> list[str]:
        if not ranking:
            return ['🏁 Игра завершена!', '', 'Никто не набрал очков.']

        winner = ranking[0]
        lines = ['🏁 Игра завершена!', '', f'Режим: {mode_label}', '', 'Итоговая таблица:']
        for idx, player in enumerate(ranking, start=1):
            lines.append(f'{idx}. @{player.username} — {player.points}')

        if team_score_lines:
            lines.append('')
            lines.extend(team_score_lines)

        lines.append('')
        lines.append(f'👑 Победитель: @{winner.username}')
        lines.append('💎 Победитель получил +5 сезонных очков')
        return lines
