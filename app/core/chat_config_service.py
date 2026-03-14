from __future__ import annotations

from typing import Dict

from app.config import settings
from app.core.models import ChatSettings
from app.providers.llm_provider import CATEGORY_RANDOM


class ChatConfigService:
    def __init__(self) -> None:
        self.chat_settings: Dict[int, ChatSettings] = {}
        self.preferred_categories: Dict[int, str] = {}

    def get_chat_settings(self, chat_id: int) -> ChatSettings:
        if chat_id not in self.chat_settings:
            self.chat_settings[chat_id] = ChatSettings(question_timeout_sec=settings.question_timeout_sec)
        return self.chat_settings[chat_id]

    def set_preferred_category(self, chat_id: int, category: str) -> None:
        self.preferred_categories[chat_id] = category

    def get_preferred_category(self, chat_id: int) -> str:
        return self.preferred_categories.get(chat_id, CATEGORY_RANDOM)

    def set_game_profile(self, chat_id: int, profile: str) -> bool:
        if profile not in {'casual', 'standard', 'hardcore'}:
            return False
        cfg = self.get_chat_settings(chat_id)
        cfg.game_profile = profile
        return True

    def get_game_profile(self, chat_id: int) -> str:
        return self.get_chat_settings(chat_id).game_profile

    def cycle_timeout(self, chat_id: int) -> int:
        cfg = self.get_chat_settings(chat_id)
        values = [20, 30, 45]
        try:
            idx = values.index(cfg.question_timeout_sec)
        except ValueError:
            idx = 1
        cfg.question_timeout_sec = values[(idx + 1) % len(values)]
        return cfg.question_timeout_sec

    def toggle_image_rounds(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.image_rounds_enabled = not cfg.image_rounds_enabled
        return cfg.image_rounds_enabled

    def toggle_music_rounds(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.music_rounds_enabled = not cfg.music_rounds_enabled
        return cfg.music_rounds_enabled

    def toggle_admin_only_control(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.admin_only_control = not cfg.admin_only_control
        return cfg.admin_only_control

    def toggle_host_mode(self, chat_id: int) -> bool:
        cfg = self.get_chat_settings(chat_id)
        cfg.host_mode_enabled = not cfg.host_mode_enabled
        return cfg.host_mode_enabled


    def set_timezone(self, chat_id: int, timezone_name: str) -> None:
        cfg = self.get_chat_settings(chat_id)
        cfg.timezone = timezone_name

    def set_repeat_rules(self, chat_id: int, repeat_window_days: int, same_day_block: bool) -> None:
        cfg = self.get_chat_settings(chat_id)
        cfg.repeat_window_days = max(1, min(30, repeat_window_days))
        cfg.same_day_repeat_block_enabled = same_day_block

    def set_preferred_topics(self, chat_id: int, topics: list[str]) -> None:
        cfg = self.get_chat_settings(chat_id)
        cfg.preferred_topics = [item.strip() for item in topics if item.strip()]

    def build_settings_text(self, chat_id: int, profile_label: str) -> str:
        cfg = self.get_chat_settings(chat_id)
        return (
            '⚙️ Настройки чата\n'
            f'Профиль игры: {profile_label}\n'
            f'Тема по умолчанию: {self.get_preferred_category(chat_id)}\n'
            f'Таймер на вопрос: {cfg.question_timeout_sec} сек.\n'
            f'Картинки: {"вкл" if cfg.image_rounds_enabled else "выкл"}\n'
            f'Музыка: {"вкл" if cfg.music_rounds_enabled else "выкл"}\n'
            f'Чат-режим: {"вкл" if cfg.chat_mode_enabled else "выкл"}\n'
            f'Host-режим: {"вкл" if cfg.host_mode_enabled else "выкл"}\n'
            f'Только админ может старт/стоп: {"вкл" if cfg.admin_only_control else "выкл"}\n'
            f'Таймзона: {cfg.timezone}\n'
            f'Адаптивность: {"вкл" if cfg.adaptive_mode_enabled else "выкл"}\n'
            f'Окно анти-повторов: {cfg.repeat_window_days} дн.\n'
            f'Запрет повторов в тот же день: {"вкл" if cfg.same_day_repeat_block_enabled else "выкл"}\n'
            f'LLM-only режим: {"вкл" if cfg.llm_only_mode else "выкл"}'
        )
