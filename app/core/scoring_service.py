from __future__ import annotations


class ScoringService:
    def total_score(
        self,
        difficulty: str,
        response_ms: int,
        streak: int,
        base_score: int = 1,
    ) -> int:
        return max(1, int(base_score * self.difficulty_modifier(difficulty) + self.speed_bonus(response_ms) + self.streak_bonus(streak)))

    def speed_bonus(self, response_ms: int) -> float:
        if response_ms <= 4000:
            return 1.0
        if response_ms <= 8000:
            return 0.5
        return 0.0

    def streak_bonus(self, streak: int) -> float:
        if streak >= 5:
            return 1.0
        if streak >= 3:
            return 0.5
        return 0.0

    def difficulty_modifier(self, difficulty: str) -> float:
        return {'easy': 1.0, 'medium': 1.4, 'hard': 1.8}.get(difficulty, 1.0)
