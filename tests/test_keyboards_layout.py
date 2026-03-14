from __future__ import annotations

import unittest

from app.bot.keyboards import compact_main_menu_kb, control_menu_kb, game_menu_kb, topics_menu_kb


class KeyboardsLayoutTests(unittest.TestCase):
    def test_compact_main_menu_has_3_rows(self) -> None:
        kb = compact_main_menu_kb()
        self.assertEqual(len(kb.keyboard), 3)

    def test_section_menus_have_back_button(self) -> None:
        for kb in (game_menu_kb(), topics_menu_kb(), control_menu_kb()):
            flat = [button.text for row in kb.keyboard for button in row]
            self.assertIn('🏠 Главное меню', flat)

    def test_game_menu_uses_25_questions_and_hides_team_pick_buttons(self) -> None:
        flat = [button.text for row in game_menu_kb().keyboard for button in row]
        self.assertIn('🎯 Классика 25', flat)
        self.assertNotIn('🟥 Team Alpha', flat)
        self.assertNotIn('🟦 Team Beta', flat)


if __name__ == '__main__':
    unittest.main()
