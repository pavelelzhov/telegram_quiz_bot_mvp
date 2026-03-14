from __future__ import annotations

from app.core.models import AdaptiveDifficultyDecision, PlayerSkillSnapshot


class DifficultyService:
    bands = ('easy', 'medium', 'hard')

    def choose_target_band(self, snapshot: PlayerSkillSnapshot, topic_accuracy: float | None = None) -> AdaptiveDifficultyDecision:
        acc = snapshot.recent_accuracy
        if topic_accuracy is not None:
            acc = (acc * 0.7) + (topic_accuracy * 0.3)

        if snapshot.current_streak >= 3 and acc >= 0.75:
            target = self._step(snapshot.current_band, 1)
            return AdaptiveDifficultyDecision(target_band=target, reason='win_streak', confidence=0.75)
        if acc <= 0.35:
            target = self._step(snapshot.current_band, -1)
            return AdaptiveDifficultyDecision(target_band=target, reason='low_accuracy', confidence=0.8)
        return AdaptiveDifficultyDecision(target_band=snapshot.current_band or 'medium', reason='stable', confidence=0.6)

    def update_skill_after_answer(self, snapshot: PlayerSkillSnapshot, was_correct: bool, response_ms: int, question_difficulty: str) -> PlayerSkillSnapshot:
        diff_boost = {'easy': 0.05, 'medium': 0.09, 'hard': 0.14}.get(question_difficulty, 0.05)
        speed_bonus = 0.02 if response_ms <= 5000 else 0.0
        delta = (diff_boost + speed_bonus) if was_correct else -0.06

        snapshot.answers_total += 1
        snapshot.answers_correct += int(was_correct)
        snapshot.recent_accuracy = snapshot.answers_correct / max(1, snapshot.answers_total)
        snapshot.global_skill_score = max(0.0, min(1.0, snapshot.global_skill_score + delta))
        snapshot.recent_avg_response_ms = (
            (snapshot.recent_avg_response_ms * max(0, snapshot.answers_total - 1)) + response_ms
        ) / max(1, snapshot.answers_total)

        if was_correct:
            snapshot.current_streak += 1
            snapshot.best_streak = max(snapshot.best_streak, snapshot.current_streak)
        else:
            snapshot.current_streak = 0

        if snapshot.global_skill_score >= 0.72:
            snapshot.current_band = 'hard'
        elif snapshot.global_skill_score >= 0.38:
            snapshot.current_band = 'medium'
        else:
            snapshot.current_band = 'easy'
        return snapshot

    def _step(self, band: str, direction: int) -> str:
        idx = self.bands.index(band) if band in self.bands else 1
        next_idx = max(0, min(len(self.bands) - 1, idx + direction))
        return self.bands[next_idx]
