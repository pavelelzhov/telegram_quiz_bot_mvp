from __future__ import annotations

from aiogram import Bot
from aiogram.types import FSInputFile

from app.core.models import GameState, QuizQuestion


class RoundLifecycleService:
    def source_label(self, question: QuizQuestion) -> str:
        if question.source == 'llm':
            return 'ИИ'
        if question.source == 'image_pool':
            return 'картинка'
        if question.source == 'music_pool':
            return 'музыка'
        return 'резерв'

    def build_question_header(self, state: GameState, question: QuizQuestion) -> str:
        multiplier_line = ''
        if question.point_value > 1:
            multiplier_line = f'\n💠 Цена вопроса: x{question.point_value}'

        return (
            f'❓ Вопрос {state.asked_count}/{state.question_limit}\n'
            f'{question.round_label}\n'
            f'Категория: {question.category}\n'
            f'Тема: {question.topic}\n'
            f'Сложность: {question.difficulty}\n'
            f'Источник: {self.source_label(question)}'
            f'{multiplier_line}\n\n'
            f'{question.question}'
        )

    async def send_question(self, bot: Bot, chat_id: int, question: QuizQuestion, header: str, logger) -> None:
        if question.question_type == 'image' and question.photo_url:
            try:
                await bot.send_photo(chat_id, photo=question.photo_url, caption=header)
                return
            except Exception as exc:
                logger.exception('Failed to send image round: %s', exc)
                await bot.send_message(chat_id, header + '\n\n(Картинку отправить не удалось, но вопрос остаётся активным.)')
                return

        if question.question_type == 'audio' and question.audio_path:
            try:
                audio = FSInputFile(question.audio_path)
                await bot.send_audio(
                    chat_id,
                    audio=audio,
                    caption=header,
                    title=question.audio_title or 'Музыкальный раунд',
                    performer=question.audio_performer or 'Quiz Bot',
                )
                return
            except Exception as exc:
                logger.exception('Failed to send audio round: %s', exc)
                await bot.send_message(chat_id, header + '\n\n(Аудио отправить не удалось, но вопрос остаётся активным.)')
                return

        await bot.send_message(chat_id, header)

    def build_timeout_text(self, question: QuizQuestion) -> str:
        return (
            '⌛ Время вышло.\n'
            f'Правильный ответ: {question.answer}\n'
            f'Факт: {question.explanation}'
        )
