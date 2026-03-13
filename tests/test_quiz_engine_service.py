from __future__ import annotations

import unittest

from app.core.models import ChatSettings, GameState, QuizQuestion
from app.core.quiz_engine_service import QuizEngineService


class QuizEngineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QuizEngineService()

    def _state(self, *, quiz_mode: str = 'classic', question_limit: int = 10) -> GameState:
        return GameState(chat_id=1, started_by_user_id=1, question_limit=question_limit, quiz_mode=quiz_mode)

    def _question(self, *, question_type: str = 'text') -> QuizQuestion:
        return QuizQuestion(
            category='Общие знания',
            difficulty='medium',
            question='Тестовый вопрос?',
            answer='Тест',
            aliases=[],
            hint='Подсказка',
            explanation='Объяснение',
            question_type=question_type,
        )

    def test_mode_label_and_fallback(self) -> None:
        self.assertEqual(self.service.mode_label('classic'), '🎯 Классика')
        self.assertEqual(self.service.mode_label('blitz'), '🔥 Блиц')
        self.assertEqual(self.service.mode_label('epic'), '👑 Эпик')
        self.assertEqual(self.service.mode_label('unknown'), '🎯 Классика')

    def test_timeout_for_mode(self) -> None:
        cfg = ChatSettings(question_timeout_sec=30)

        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='classic'), cfg), 30)
        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='blitz'), cfg), 22)
        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='epic'), cfg), 35)

        cfg_small = ChatSettings(question_timeout_sec=20)
        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='blitz'), cfg_small), 15)

        cfg_big = ChatSettings(question_timeout_sec=58)
        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='epic'), cfg_big), 60)

    def test_determine_stage_for_modes(self) -> None:
        blitz_state = self._state(quiz_mode='blitz', question_limit=7)
        self.assertEqual(self.service.determine_stage(blitz_state, 1), 'warmup')
        self.assertEqual(self.service.determine_stage(blitz_state, 3), 'special')
        self.assertEqual(self.service.determine_stage(blitz_state, 7), 'finale')

        epic_state = self._state(quiz_mode='epic', question_limit=12)
        self.assertEqual(self.service.determine_stage(epic_state, 2), 'warmup')
        self.assertEqual(self.service.determine_stage(epic_state, 4), 'special')
        self.assertEqual(self.service.determine_stage(epic_state, 12), 'finale')

        classic_state = self._state(quiz_mode='classic', question_limit=10)
        self.assertEqual(self.service.determine_stage(classic_state, 1), 'warmup')
        self.assertEqual(self.service.determine_stage(classic_state, 6), 'special')
        self.assertEqual(self.service.determine_stage(classic_state, 10), 'finale')

    def test_apply_mode_profile_updates_points_and_labels(self) -> None:
        state = self._state(quiz_mode='epic')

        warmup = self._question(question_type='text')
        self.service.apply_mode_profile(warmup, state, 'warmup')
        self.assertEqual(warmup.point_value, 1)
        self.assertEqual(warmup.round_label, '🔥 Разогрев')

        special_audio = self._question(question_type='audio')
        self.service.apply_mode_profile(special_audio, state, 'special')
        self.assertEqual(special_audio.point_value, 2)
        self.assertEqual(special_audio.round_label, '🎧 Спецраунд x2')

        finale_epic = self._question(question_type='text')
        self.service.apply_mode_profile(finale_epic, state, 'finale')
        self.assertEqual(finale_epic.point_value, 3)
        self.assertEqual(finale_epic.round_label, '👑 Финальный босс x3')

        core_epic = self._question(question_type='text')
        self.service.apply_mode_profile(core_epic, state, 'core')
        self.assertEqual(core_epic.point_value, 1)
        self.assertEqual(core_epic.round_label, '🧩 Эпик-раунд')


if __name__ == '__main__':
    unittest.main()
