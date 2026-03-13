from __future__ import annotations

from app.core.models import GameState, PlayerScore, QuizQuestion
from app.utils.text import answer_match_details


class AnswerFlowService:
    def match_verdict(self, text: str, question: QuizQuestion) -> str:
        return answer_match_details(text, question.answer, question.aliases)

    def register_wrong_attempt(self, state: GameState, user_id: int) -> bool:
        if user_id in state.wrong_reply_user_ids:
            return False
        if len(state.wrong_reply_user_ids) >= 3:
            return False
        state.wrong_reply_user_ids.add(user_id)
        return True

    def register_close_attempt(self, state: GameState, user_id: int) -> bool:
        if user_id in state.near_miss_user_ids:
            return False
        state.near_miss_user_ids.add(user_id)
        return True

    def register_correct_answer(self, state: GameState, user_id: int, username: str) -> tuple[int, int]:
        if state.current_question is None:
            return (0, 0)

        state.current_question_answered = True
        score = state.scores.setdefault(user_id, PlayerScore(user_id=user_id, username=username))
        score.username = username
        score.points += state.current_question.point_value

        if state.last_correct_user_id == user_id:
            state.correct_streak_count += 1
        else:
            state.last_correct_user_id = user_id
            state.correct_streak_count = 1

        return (state.current_question.point_value, state.correct_streak_count)

    def build_correct_answer_text(
        self,
        username: str,
        question: QuizQuestion,
        points_awarded: int,
        streak_count: int,
        leader_line: str,
    ) -> str:
        streak_line = ''
        if streak_count >= 2:
            streak_line = f'\n🔥 Серия @{username}: {streak_count} подряд!'

        points_line = f'\n💠 За этот вопрос: +{points_awarded} SP'
        if points_awarded == 1:
            points_line = '\n💠 За этот вопрос: +1 SP'

        return (
            f'✅ Правильно! @{username} забирает ответ.\n'
            f'Ответ: {question.answer}\n'
            f'Факт: {question.explanation}'
            f'{points_line}'
            f'{streak_line}'
            f'{leader_line}'
        )
