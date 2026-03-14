from __future__ import annotations

from datetime import datetime, timezone

from app.core.difficulty_service import DifficultyService
from app.core.models import GameState, PlayerScore, QuestionUsageRecord, QuizQuestion
from app.utils.text import answer_match_details


class AnswerFlowService:
    def __init__(self, db=None, difficulty_service: DifficultyService | None = None) -> None:
        self.db = db
        self.difficulty_service = difficulty_service or DifficultyService()

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

    async def finalize_answer(
        self,
        state: GameState,
        player_id: int,
        was_correct: bool,
        response_ms: int,
    ) -> None:
        if self.db is None or state.current_question is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        if state.current_question.question_id:
            await self.db.log_question_usage(
                QuestionUsageRecord(
                    question_id=state.current_question.question_id,
                    chat_id=state.chat_id,
                    player_id=player_id,
                    shown_at=datetime.fromtimestamp(state.current_question_started_ts, tz=timezone.utc).isoformat(),
                    answered_at=now,
                    was_correct=was_correct,
                    response_ms=response_ms,
                    local_game_date=state.local_game_date,
                )
            )

        snapshot = await self.db.get_player_skill_profile(player_id)
        updated = self.difficulty_service.update_skill_after_answer(
            snapshot=snapshot,
            was_correct=was_correct,
            response_ms=response_ms,
            question_difficulty=state.current_question.difficulty,
        )
        await self.db.upsert_player_skill_profile(updated)
        topic = state.current_question.topic or state.preferred_category
        topic_row = await self.db.get_player_topic_skill(player_id, topic)
        attempts = int(topic_row['attempts_count']) + 1 if topic_row else 1
        topic_score = float(topic_row['skill_score']) if topic_row else 0.0
        if was_correct:
            topic_score = min(1.0, topic_score + 0.08)
        else:
            topic_score = max(0.0, topic_score - 0.03)
        await self.db.upsert_player_topic_skill(
            player_id=player_id,
            topic=topic,
            skill_score=topic_score,
            recent_accuracy=updated.recent_accuracy,
            attempts_count=attempts,
        )

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
