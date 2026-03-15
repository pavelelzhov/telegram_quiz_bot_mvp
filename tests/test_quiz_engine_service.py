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

    def test_timeout_respects_game_profile(self) -> None:
        casual_cfg = ChatSettings(question_timeout_sec=30, game_profile='casual')
        hardcore_cfg = ChatSettings(question_timeout_sec=30, game_profile='hardcore')

        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='classic'), casual_cfg), 35)
        self.assertEqual(self.service.timeout_for_mode(self._state(quiz_mode='classic'), hardcore_cfg), 25)

    def test_game_profile_label(self) -> None:
        self.assertEqual(self.service.game_profile_label('casual'), '😌 casual')
        self.assertEqual(self.service.game_profile_label('standard'), '🎯 standard')
        self.assertEqual(self.service.game_profile_label('hardcore'), '💀 hardcore')
        self.assertEqual(self.service.game_profile_label('unknown'), '🎯 standard')

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

    def test_mix_candidates_for_variety_interleaves_categories(self) -> None:
        candidates = [
            {'id': 1, 'topic': 'История'},
            {'id': 2, 'topic': 'История'},
            {'id': 3, 'topic': 'Наука'},
            {'id': 4, 'topic': 'Наука'},
            {'id': 5, 'topic': 'Кино'},
        ]

        mixed = self.service._mix_candidates_for_variety(candidates)

        self.assertEqual(len(mixed), len(candidates))
        self.assertEqual(sorted(item['id'] for item in mixed), [1, 2, 3, 4, 5])
        self.assertGreater(len({item.get('topic') for item in mixed[:3]}), 1)


    def test_candidate_to_quiz_question_uses_aliases_and_hint(self) -> None:
        candidate = {
            'id': 7,
            'topic': 'История',
            'difficulty': 'medium',
            'question_text': 'Кто основал Санкт-Петербург?',
            'correct_answer_text': 'Пётр I',
            'aliases': ['Петр 1', 'Пётр Первый'],
            'hint_text': 'Подумай про первого императора.',
            'explanation': 'Город был основан Петром I в 1703 году.',
            'question_type': 'text',
            'question_hash': 'qh-1',
            'uniqueness_hash': 'uh-1',
            'quality_score': 0.8,
        }

        question = self.service._candidate_to_quiz_question(candidate)

        self.assertEqual(question.answer, 'Пётр I')
        self.assertEqual(question.aliases, ['Петр 1', 'Пётр Первый'])
        self.assertEqual(question.hint, 'Подумай про первого императора.')

    def test_candidate_to_quiz_question_uses_default_hint(self) -> None:
        candidate = {
            'id': 1,
            'topic': 'Общие знания',
            'difficulty': 'easy',
            'question_text': 'Q',
            'correct_answer_text': 'A',
            'explanation': 'E',
            'question_type': 'text',
        }

        question = self.service._candidate_to_quiz_question(candidate)

        self.assertEqual(question.aliases, [])
        self.assertEqual(question.hint, 'Подумай о главном факте вопроса.')


if __name__ == '__main__':
    unittest.main()
