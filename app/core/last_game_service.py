from __future__ import annotations

from app.core.quiz_engine_service import QuizEngineService


class LastGameService:
    def __init__(self, quiz_engine: QuizEngineService) -> None:
        self.quiz_engine = quiz_engine

    def format_last_game_text(self, data: dict[str, object] | None) -> str:
        if not data:
            return 'В этом чате пока нет завершённых игр.'

        winner = f'@{data["winner_username"]}' if data.get('winner_username') else 'нет победителя'
        mode = self.quiz_engine.mode_label(str(data.get('quiz_mode') or 'classic'))
        return (
            '🕘 Последняя игра\n'
            f'ID: {data["id"]}\n'
            f'Режим: {mode}\n'
            f'Время: {data["finished_at"]}\n'
            f'Победитель: {winner}\n'
            f'Очки победителя: {data["winner_points"]}\n'
            f'Вопросов: {data["total_questions"]}'
        )
