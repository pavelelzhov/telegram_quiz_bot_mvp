from __future__ import annotations

from collections import defaultdict
from typing import Dict

from app.core.models import GameState


class TeamModeService:
    def __init__(self) -> None:
        self.team_lobbies: Dict[int, dict[str, dict[int, str]]] = defaultdict(
            lambda: {'alpha': {}, 'beta': {}}
        )

    def set_team_choice(self, chat_id: int, user_id: int, username: str, team: str) -> str:
        team_name = team.strip().lower()
        if team_name not in {'alpha', 'beta'}:
            return 'Неверная команда. Используй: /team_alpha или /team_beta.'

        lobby = self.team_lobbies[chat_id]
        current_team = self.team_of_user_in_lobby(chat_id, user_id)
        if current_team == team_name:
            return f'Ты уже в команде {self.team_label(team_name)}.'

        if current_team:
            lobby[current_team].pop(user_id, None)

        if len(lobby[team_name]) >= 2:
            return f'Команда {self.team_label(team_name)} уже заполнена (2/2).'

        lobby[team_name][user_id] = username
        return f'@{username}, ты в команде {self.team_label(team_name)}.\n{self.get_team_lobby_text(chat_id)}'

    def get_team_lobby_text(self, chat_id: int) -> str:
        lobby = self.team_lobbies[chat_id]
        alpha = ', '.join(f'@{name}' for name in lobby['alpha'].values()) or '—'
        beta = ', '.join(f'@{name}' for name in lobby['beta'].values()) or '—'
        return (
            '🤝 Лобби 2v2\n'
            f'{self.team_label("alpha")}: {len(lobby["alpha"])}/2 — {alpha}\n'
            f'{self.team_label("beta")}: {len(lobby["beta"])}/2 — {beta}\n'
            'Выбор: /team_alpha или /team_beta\n'
            'Старт: /team_start'
        )

    def team_of_user_in_lobby(self, chat_id: int, user_id: int) -> str | None:
        lobby = self.team_lobbies[chat_id]
        for team_name in ('alpha', 'beta'):
            if user_id in lobby[team_name]:
                return team_name
        return None

    def team_label(self, team_name: str) -> str:
        if team_name == 'alpha':
            return '🟥 Альфа'
        return '🟦 Бета'

    def build_team_assignments(self, chat_id: int) -> dict[int, str] | None:
        lobby = self.team_lobbies[chat_id]
        if len(lobby['alpha']) != 2 or len(lobby['beta']) != 2:
            return None

        team_assignments: dict[int, str] = {}
        for user_id in lobby['alpha']:
            team_assignments[user_id] = 'alpha'
        for user_id in lobby['beta']:
            team_assignments[user_id] = 'beta'
        return team_assignments

    def team_score_lines(self, state: GameState) -> list[str]:
        totals = {'alpha': 0, 'beta': 0}
        for user_id, score in state.scores.items():
            team = state.team_assignments.get(user_id)
            if team in totals:
                totals[team] += score.points

        lines = ['🤝 Командный счёт:']
        for team_name in ('alpha', 'beta'):
            lines.append(f'{self.team_label(team_name)} — {totals[team_name]}')

        lines.append('')
        lines.append('Вклад игроков:')
        for team_name in ('alpha', 'beta'):
            lines.append(f'{self.team_label(team_name)}:')
            members = [
                player
                for player in state.scores.values()
                if state.team_assignments.get(player.user_id) == team_name
            ]
            members.sort(key=lambda item: (-item.points, item.username.lower()))
            if not members:
                lines.append('• пока без очков')
                continue
            for player in members:
                lines.append(f'• @{player.username} — {player.points}')

        return lines
