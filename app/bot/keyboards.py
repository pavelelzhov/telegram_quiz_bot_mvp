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
    '🎯 Классика 10',
    '🔥 Блиц 7',
    '👑 Эпик 12',
    '💡 Подсказка',
    '⏭ Пропустить',
    '🏆 Очки',
    '📊 Статус',
    '👥 Топ',
    '🏅 Сезон',
    '🙋 Профиль',
    '⛔ Стоп',
    '⚙️ Настройки',
    '⏱ Таймер',
    '🖼 Картинки',
    '🎧 Музыка-раунды',
    '👮 Админ-режим',
    '🤖 Host-режим',
}


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🎯 Классика 10'), KeyboardButton(text='🔥 Блиц 7'), KeyboardButton(text='👑 Эпик 12')],
            [KeyboardButton(text='🎲 Случайно'), KeyboardButton(text='🌍 География'), KeyboardButton(text='📚 История')],
            [KeyboardButton(text='🎬 Кино'), KeyboardButton(text='🎵 Музыка'), KeyboardButton(text='🤖 Технологии')],
            [KeyboardButton(text='🔬 Наука'), KeyboardButton(text='⚽ Спорт'), KeyboardButton(text='📖 Литература')],
            [KeyboardButton(text='🌐 Интернет'), KeyboardButton(text='🧠 Общие')],
            [KeyboardButton(text='🏅 Сезон'), KeyboardButton(text='🙋 Профиль')],
            [KeyboardButton(text='⚙️ Настройки'), KeyboardButton(text='⏱ Таймер')],
            [KeyboardButton(text='🖼 Картинки'), KeyboardButton(text='🎧 Музыка-раунды')],
            [KeyboardButton(text='👮 Админ-режим'), KeyboardButton(text='🤖 Host-режим')],
            [KeyboardButton(text='💡 Подсказка'), KeyboardButton(text='⏭ Пропустить')],
            [KeyboardButton(text='🏆 Очки'), KeyboardButton(text='📊 Статус')],
            [KeyboardButton(text='👥 Топ'), KeyboardButton(text='⛔ Стоп')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Выбери действие…',
    )
