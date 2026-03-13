from __future__ import annotations

import random

from app.core.models import QuizQuestion


class FeedbackTextService:
    def wrong_answer_text(self, username: str, question: QuizQuestion) -> str:
        if question.question_type == 'audio':
            variants = [
                f'🎧 @{username}, версия смелая, но оригинал сейчас нервно перематывается.',
                f'🎵 @{username}, ты попал не в трек, а в альтернативную вселенную.',
                f'🎙 @{username}, это был уверенный ответ. Жаль, что не правильный.',
            ]
        elif question.question_type == 'image':
            variants = [
                f'🖼 @{username}, картинка на тебя посмотрела и тихо не согласилась.',
                f'👀 @{username}, глаз-алмаз сегодня с небольшим сколом.',
                f'📸 @{username}, смело. Но фактология попросила тебя выйти на следующей.',
            ]
        else:
            variants = [
                f'😄 @{username}, версия бодрая, но истина сейчас в другом окне.',
                f'🫠 @{username}, ответ красивый, уверенный и мимо кассы.',
                f'😂 @{username}, это было близко примерно как соседний район к другой стране.',
                f'🤡 @{username}, звучит так, будто ты почти знал... лет пять назад.',
                f'🧠 @{username}, мозг завёлся, но навигатор повёл не туда.',
                f'🎯 @{username}, стрела выпущена эффектно, мишень пока жива и улыбается.',
            ]
        return random.choice(variants)

    def near_miss_text(self, username: str, question: QuizQuestion) -> str:
        if question.question_type == 'audio':
            variants = [
                f'🎧 @{username}, уши у тебя рабочие — но трек пока не сдался.',
                f'🎵 @{username}, почти попал в ноты, но не в ответ.',
                f'🎙 @{username}, горячо. Музыкальный Шазам в тебе проснулся, но не до конца.',
            ]
        elif question.question_type == 'image':
            variants = [
                f'🖼 @{username}, почти. Глаза орлиные, но ответ пока мимо ветки.',
                f'👀 @{username}, очень близко — картинка тебя уважает, но не подтверждает.',
                f'📸 @{username}, тепло. Фото уже дрогнуло, но правильный ответ ещё нет.',
            ]
        else:
            variants = [
                f'😏 @{username}, очень близко. Мозг разогрелся, теперь бы ещё доехать до станции «верно».',
                f'🔥 @{username}, горячо. Ещё полшага — и ты бы забрал этот вопрос как налоговая забирает нервы.',
                f'🤏 @{username}, почти. Ответ уже машет тебе рукой, но ты пока машешь ему из соседнего окна.',
                f'🧠 @{username}, мысль правильная по вайбу, но формально мимо. Квиз любит придираться.',
            ]
        return random.choice(variants)
