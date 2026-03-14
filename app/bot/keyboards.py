from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BUTTON_TO_CATEGORY = {
    '🎲 Случайно': 'Случайно',
    '🌍 География': 'География',
    '📚 История': 'История',
    '🎬 Кино': 'Кино',
    '🎵 Музыка': 'Музыка',
    '🤖 Технологии': 'Технологии',
    '🔬 Наука': 'Наука',
    '⚽ Спорт': 'Спорт',
    '📖 Литература': 'Литература',
    '🌐 Интернет': 'Интернет',
    '🧠 Общие': 'Общие знания',
}

BUTTON_TEXTS = set(BUTTON_TO_CATEGORY.keys()) | {
    '🏠 Главное меню',
    '🎮 Игровое меню',
    '🧩 Темы',
    '👤 Профиль и рейтинг',
    '⚙️ Управление',
    '🎯 Классика 25',
    '🔥 Блиц 7',
    '👑 Эпик 12',
    '💡 Подсказка',
    '⏭ Пропустить',
    '🏆 Очки',
    '📊 Статус',
    '👥 Топ',
    '🏅 Сезон',
    '🗓 Неделя',
    '🕘 Последняя игра',
    '🙋 Профиль',
    '⛔ Стоп',
    '⚙️ Настройки',
    '⏱ Таймер',
    '👮 Админ-режим',
    '🤖 Host-режим',
    '🤝 Лобби 2v2',
    '🚀 Старт 2v2',
    '🛑 Стоп 2v2',
    '🩺 Health',
    '📦 Буфер LLM',
    '🧠 Solo Start',
    '📅 Daily',
    '📈 My Level',
    '👤 Profile',
}


def compact_main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🎮 Игровое меню'), KeyboardButton(text='🧩 Темы')],
            [KeyboardButton(text='👤 Профиль и рейтинг'), KeyboardButton(text='⚙️ Управление')],
            [KeyboardButton(text='🏆 Очки'), KeyboardButton(text='📊 Статус'), KeyboardButton(text='⛔ Стоп')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Выбери раздел…',
    )


def game_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🎯 Классика 25'), KeyboardButton(text='🔥 Блиц 7'), KeyboardButton(text='👑 Эпик 12')],
            [KeyboardButton(text='🧠 Solo Start'), KeyboardButton(text='📅 Daily')],
            [KeyboardButton(text='🤝 Лобби 2v2'), KeyboardButton(text='🚀 Старт 2v2'), KeyboardButton(text='🛑 Стоп 2v2')],
            [KeyboardButton(text='💡 Подсказка'), KeyboardButton(text='⏭ Пропустить')],
            [KeyboardButton(text='🏠 Главное меню')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Игровые действия…',
    )


def topics_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🎲 Случайно'), KeyboardButton(text='🧠 Общие')],
            [KeyboardButton(text='🌍 География'), KeyboardButton(text='📚 История'), KeyboardButton(text='🎬 Кино')],
            [KeyboardButton(text='🎵 Музыка'), KeyboardButton(text='🤖 Технологии'), KeyboardButton(text='🔬 Наука')],
            [KeyboardButton(text='⚽ Спорт'), KeyboardButton(text='📖 Литература'), KeyboardButton(text='🌐 Интернет')],
            [KeyboardButton(text='🏠 Главное меню')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Выбери тему…',
    )


def profile_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🙋 Профиль'), KeyboardButton(text='👤 Profile'), KeyboardButton(text='📈 My Level')],
            [KeyboardButton(text='👥 Топ'), KeyboardButton(text='🏅 Сезон'), KeyboardButton(text='🗓 Неделя')],
            [KeyboardButton(text='🕘 Последняя игра'), KeyboardButton(text='📦 Буфер LLM')],
            [KeyboardButton(text='🏠 Главное меню')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Профиль и рейтинг…',
    )


def control_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='⚙️ Настройки'), KeyboardButton(text='⏱ Таймер')],
            [KeyboardButton(text='👮 Админ-режим'), KeyboardButton(text='🤖 Host-режим')],
            [KeyboardButton(text='🩺 Health'), KeyboardButton(text='📦 Буфер LLM')],
            [KeyboardButton(text='⛔ Стоп')],
            [KeyboardButton(text='🏠 Главное меню')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Управление и диагностика…',
    )


def main_menu_kb() -> ReplyKeyboardMarkup:
    return compact_main_menu_kb()
