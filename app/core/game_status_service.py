from __future__ import annotations

from app.core.models import ChatSettings, GameState


class GameStatusService:
    def build_score_text(
        self,
        *,
        state: GameState | None,
        mode_label: str,
        team_score_lines: list[str] | None = None,
    ) -> str:
        if not state or not state.is_active:
            return 'Сейчас нет активной игры.'

        if not state.scores:
            return 'Пока очков нет.'

        ranking = sorted(state.scores.values(), key=lambda item: (-item.points, item.username.lower()))
        lines = [f'🏆 Текущие очки ({mode_label}):']
        for idx, player in enumerate(ranking, start=1):
            lines.append(f'{idx}. @{player.username} — {player.points}')

        if team_score_lines:
            lines.extend([''] + team_score_lines)
        return '\n'.join(lines)

    def build_status_text(
        self,
        *,
        cfg: ChatSettings,
        state: GameState | None,
        game_profile_label: str,
        preferred_category: str,
        timer_seconds: int,
        mode_label: str | None = None,
        team_score_lines: list[str] | None = None,
    ) -> str:
        if not state or not state.is_active:
            return (
                'Сейчас нет активной игры.\n'
                f'Профиль игры: {game_profile_label}\n'
                f'Тема для следующей игры: {preferred_category}\n'
                f'Таймер: {cfg.question_timeout_sec} сек.\n'
                f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
                f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
                f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
                f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}\n'
                f'Только админ может старт/стоп: {"вкл" if cfg.admin_only_control else "выкл"}'
            )

        text = (
            '📊 Статус игры\n'
            f'Режим: {mode_label}\n'
            f'Профиль игры: {game_profile_label}\n'
            f'Вопросов выдано: {state.asked_count}/{state.question_limit}\n'
            f'Тема: {state.preferred_category}\n'
            f'Игроков с очками: {len(state.scores)}\n'
            f'Таймер: {timer_seconds} сек.\n'
            f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
            f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
            f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
            f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}'
        )
        if team_score_lines:
            text += '\n\n' + '\n'.join(team_score_lines)
        return text
