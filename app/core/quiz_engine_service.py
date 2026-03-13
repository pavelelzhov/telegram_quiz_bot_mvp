from __future__ import annotations

from app.core.models import ChatSettings, GameState, QuizQuestion


class QuizEngineService:
    def game_profile_label(self, profile: str) -> str:
        mapping = {
            'casual': '😌 casual',
            'standard': '🎯 standard',
            'hardcore': '💀 hardcore',
        }
        return mapping.get(profile, '🎯 standard')

    def mode_label(self, quiz_mode: str) -> str:
        mapping = {
            'classic': '🎯 Классика',
            'blitz': '🔥 Блиц',
            'epic': '👑 Эпик',
            'team2v2': '🤝 Командный 2v2',
        }
        return mapping.get(quiz_mode, '🎯 Классика')

    def timeout_for_mode(self, state: GameState, cfg: ChatSettings) -> int:
        timeout = cfg.question_timeout_sec
        if cfg.game_profile == 'casual':
            timeout += 5
        elif cfg.game_profile == 'hardcore':
            timeout -= 5

        timeout = max(15, min(60, timeout))

        if state.quiz_mode == 'blitz':
            return max(15, timeout - 8)
        if state.quiz_mode == 'epic':
            return min(60, timeout + 5)
        return timeout

    def determine_stage(self, state: GameState, question_number: int) -> str:
        total = state.question_limit

        if state.quiz_mode == 'blitz':
            if question_number == total:
                return 'finale'
            if question_number <= 2:
                return 'warmup'
            if question_number in {3, 5}:
                return 'special'
            return 'core'

        if state.quiz_mode == 'epic':
            if question_number == total:
                return 'finale'
            if question_number <= 2:
                return 'warmup'
            if question_number in {4, 8, 10}:
                return 'special'
            return 'core'

        if question_number == total:
            return 'finale'
        if question_number <= min(2, total):
            return 'warmup'
        special_slot = max(3, (total // 2) + 1)
        if question_number == special_slot and question_number < total:
            return 'special'
        return 'core'

    def apply_mode_profile(self, question: QuizQuestion, state: GameState, stage: str) -> None:
        if stage == 'warmup':
            question.round_label = '🔥 Разогрев'
            question.point_value = 1
        elif stage == 'special':
            if question.question_type == 'audio':
                question.round_label = '🎧 Спецраунд x2'
            elif question.question_type == 'image':
                question.round_label = '🖼 Спецраунд x2'
            else:
                question.round_label = '⚡ Спецраунд x2'
            question.point_value = 2
        elif stage == 'finale':
            if state.quiz_mode == 'epic':
                question.round_label = '👑 Финальный босс x3'
                question.point_value = 3
            else:
                question.round_label = '👑 Финальный x2'
                question.point_value = 2
        else:
            question.round_label = '🎯 Основной раунд'
            question.point_value = 1

        if state.quiz_mode == 'blitz' and stage == 'core':
            question.round_label = '⚡ Блиц-раунд'
        if state.quiz_mode == 'epic' and stage == 'core':
            question.round_label = '🧩 Эпик-раунд'
