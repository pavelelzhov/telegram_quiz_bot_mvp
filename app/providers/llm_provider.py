from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Iterable

from openai import AsyncOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field

from app.config import settings
from app.core.models import QuestionCandidate, QuizQuestion
from app.core.question_dedup_service import QuestionDedupService
from app.quiz.history_store import QuizHistoryStore
from app.utils.ops_log import log_operation
from app.utils.retry import retry_async
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

CATEGORY_RANDOM = 'Случайно'
SUPPORTED_CATEGORIES = [
    'Общие знания',
    'География',
    'История',
    'Кино',
    'Музыка',
    'Технологии',
    'Наука',
    'Спорт',
    'Литература',
    'Интернет',
]

QUESTION_SYSTEM_PROMPT = """
Ты — генератор сильных вопросов для Telegram-квиза.
Нужен интересный, массово понятный и разнообразный квиз.
Вопросы про компьютерные игры запрещены.

Верни только валидный JSON без markdown и без пояснений:
{
  "questions": [
    {
      "category": "История",
      "difficulty": "medium",
      "topic": "Монгольская империя",
      "question": "Кто основал Монгольскую империю?",
      "answer": "Чингисхан",
      "aliases": ["Тэмуджин"],
      "hint": "Он объединил монгольские племена.",
      "explanation": "Монгольскую империю основал Чингисхан."
    }
  ]
}

Правила:
- верни ровно 4 вопроса
- все 4 вопроса должны быть разными
- вопрос должен быть однозначным
- ответ короткий
- не делай душные или слишком редкие вопросы
- не повторяй недавние темы, ответы и шаблоны
- difficulty только easy, medium или hard
- topic — короткая тема
- aliases — короткий список допустимых вариантов
- hint — подсказка без спойлера
- explanation — одно короткое предложение
""".strip()


class QuestionPayload(BaseModel):
    category: str = Field(min_length=2, max_length=50)
    difficulty: str = Field(min_length=4, max_length=10)
    topic: str = Field(default='Общее', min_length=2, max_length=60)
    question: str = Field(min_length=8, max_length=300)
    answer: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    hint: str = Field(min_length=3, max_length=220)
    explanation: str = Field(min_length=3, max_length=250)


TEXT_FALLBACK_QUESTIONS = [
    {'category':'География','difficulty':'easy','topic':'Столицы','question':'Столица Франции?','answer':'Париж','aliases':['Paris'],'hint':'Город Эйфелевой башни.','explanation':'Париж — столица Франции.'},
    {'category':'География','difficulty':'easy','topic':'Столицы','question':'Столица Японии?','answer':'Токио','aliases':['Tokyo'],'hint':'Это крупнейший мегаполис Японии.','explanation':'Токио — столица Японии.'},
    {'category':'История','difficulty':'easy','topic':'Космос','question':'Кто был первым человеком в космосе?','answer':'Юрий Гагарин','aliases':['Гагарин'],'hint':'Советский космонавт, 1961 год.','explanation':'Первым человеком в космосе стал Юрий Гагарин.'},
    {'category':'История','difficulty':'medium','topic':'Монгольская империя','question':'Кто основал Монгольскую империю?','answer':'Чингисхан','aliases':['Тэмуджин'],'hint':'Он объединил монгольские племена.','explanation':'Монгольскую империю основал Чингисхан.'},
    {'category':'Кино','difficulty':'easy','topic':'Фэнтези','question':'Как зовут мальчика-волшебника со шрамом на лбу?','answer':'Гарри Поттер','aliases':['Поттер','Harry Potter'],'hint':'Учился в Хогвартсе.','explanation':'Главный герой серии книг и фильмов — Гарри Поттер.'},
    {'category':'Кино','difficulty':'easy','topic':'Классика кино','question':'Как называется фильм о лайнере и любви Джека и Розы?','answer':'Титаник','aliases':['Titanic'],'hint':'Фильм Джеймса Кэмерона 1997 года.','explanation':'Это фильм «Титаник».'},
    {'category':'Музыка','difficulty':'medium','topic':'Рок','question':'Какая группа исполнила песню «Bohemian Rhapsody»?','answer':'Queen','aliases':['Квин'],'hint':'Группа Фредди Меркьюри.','explanation':'«Bohemian Rhapsody» исполнила группа Queen.'},
    {'category':'Музыка','difficulty':'easy','topic':'Инструменты','question':'Какой инструмент имеет 88 клавиш в классическом варианте?','answer':'Фортепиано','aliases':['Пианино','Рояль'],'hint':'На нём играют двумя руками.','explanation':'У классического фортепиано 88 клавиш.'},
    {'category':'Технологии','difficulty':'easy','topic':'Веб','question':'Какой язык разметки используется для структуры веб-страниц?','answer':'HTML','aliases':[],'hint':'Это не язык программирования.','explanation':'Для структуры веб-страниц используется HTML.'},
    {'category':'Технологии','difficulty':'medium','topic':'Языки программирования','question':'Какой язык программирования назван в честь британской комедийной группы?','answer':'Python','aliases':['Питон'],'hint':'Monty ...','explanation':'Python назван в честь Monty Python.'},
    {'category':'Наука','difficulty':'easy','topic':'Планеты','question':'Какая планета Солнечной системы самая большая?','answer':'Юпитер','aliases':[],'hint':'Это газовый гигант.','explanation':'Юпитер — крупнейшая планета Солнечной системы.'},
    {'category':'Наука','difficulty':'medium','topic':'Химия','question':'Какой химический символ у золота?','answer':'Au','aliases':['ау'],'hint':'От латинского названия aurum.','explanation':'Химический символ золота — Au.'},
    {'category':'Спорт','difficulty':'easy','topic':'Футбол','question':'Сколько игроков одной команды находится на поле в футболе?','answer':'11','aliases':['одиннадцать'],'hint':'Больше десяти, но меньше двенадцати.','explanation':'На поле играют 11 футболистов от каждой команды.'},
    {'category':'Спорт','difficulty':'medium','topic':'Баскетбол','question':'Сколько очков обычно дают за бросок из-за дуги в баскетболе?','answer':'3','aliases':['три'],'hint':'Больше, чем за обычный бросок.','explanation':'За дальний бросок обычно дают 3 очка.'},
    {'category':'Литература','difficulty':'easy','topic':'Русская литература','question':'Кто написал роман «Война и мир»?','answer':'Лев Толстой','aliases':['Толстой'],'hint':'Русский писатель XIX века.','explanation':'Автор романа — Лев Николаевич Толстой.'},
    {'category':'Литература','difficulty':'medium','topic':'Детективы','question':'Как зовут знаменитого сыщика, жившего на Бейкер-стрит?','answer':'Шерлок Холмс','aliases':['Холмс','Sherlock Holmes'],'hint':'Его друг — доктор Ватсон.','explanation':'Это Шерлок Холмс.'},
    {'category':'Интернет','difficulty':'medium','topic':'Мессенджеры','question':'Как называется мессенджер, который создал Павел Дуров?','answer':'Telegram','aliases':['Телеграм'],'hint':'Мы сейчас примерно рядом с ним и находимся.','explanation':'Павел Дуров создал Telegram.'},
    {'category':'Общие знания','difficulty':'easy','topic':'Животные','question':'Какое самое быстрое наземное животное?','answer':'Гепард','aliases':[],'hint':'Большая пятнистая кошка.','explanation':'Самое быстрое наземное животное — гепард.'},
]

IMAGE_FALLBACK_QUESTIONS = [
    {'category':'География','difficulty':'easy','topic':'Флаги','question':'Что это за страна по флагу?','answer':'Франция','aliases':['France'],'hint':'Столица — Париж.','explanation':'Это флаг Франции.','question_type':'image','photo_url':'https://flagcdn.com/w1280/fr.png'},
    {'category':'География','difficulty':'easy','topic':'Флаги','question':'Что это за страна по флагу?','answer':'Япония','aliases':['Japan'],'hint':'Страна восходящего солнца.','explanation':'Это флаг Японии.','question_type':'image','photo_url':'https://flagcdn.com/w1280/jp.png'},
    {'category':'География','difficulty':'easy','topic':'Флаги','question':'Что это за страна по флагу?','answer':'Италия','aliases':['Italy'],'hint':'Столица — Рим.','explanation':'Это флаг Италии.','question_type':'image','photo_url':'https://flagcdn.com/w1280/it.png'},
    {'category':'География','difficulty':'easy','topic':'Флаги','question':'Что это за страна по флагу?','answer':'Германия','aliases':['Germany'],'hint':'Столица — Берлин.','explanation':'Это флаг Германии.','question_type':'image','photo_url':'https://flagcdn.com/w1280/de.png'},
    {'category':'География','difficulty':'easy','topic':'Флаги','question':'Что это за страна по флагу?','answer':'Бразилия','aliases':['Brazil'],'hint':'Крупнейшая страна Южной Америки.','explanation':'Это флаг Бразилии.','question_type':'image','photo_url':'https://flagcdn.com/w1280/br.png'},
]


class LLMQuestionProvider:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        self.model = settings.openai_model
        self.history = QuizHistoryStore()
        self.music_rounds = self._load_music_rounds()
        self.semantic_repeat_stats: dict[int, dict[str, float]] = {}
        self.dedup_service = QuestionDedupService()

    async def generate_question(
        self,
        chat_id: int,
        used_keys: set[str],
        preferred_category: str = CATEGORY_RANDOM,
        allow_image_rounds: bool = True,
        allow_music_rounds: bool = True,
        stage: str = 'core',
        category_bias: dict[str, float] | None = None,
        preferred_difficulty: str | None = None,
    ) -> QuizQuestion:
        started = time.perf_counter()
        category = self._choose_category(chat_id, preferred_category, category_bias or {})
        round_type = self._choose_round_type(chat_id, category, stage, allow_image_rounds, allow_music_rounds)

        recent_keys = set(self.history.recent_keys(chat_id, settings.recent_questions_limit))
        recent_keys.update(used_keys)

        if round_type == 'audio':
            music = self._pick_music_round(chat_id, recent_keys, category)
            if music:
                question = QuizQuestion(
                    **music,
                    key=self._question_key(music['question'], music['answer'], music.get('audio_path')),
                    source='music_pool',
                )
                self._apply_stage_profile(question, stage)
                self._remember_question(chat_id, question)
                log_operation(
                    logger,
                    operation='question_generate',
                    chat_id=chat_id,
                    result='ok',
                    duration_ms=(time.perf_counter() - started) * 1000,
                    extra={'source': question.source, 'round_type': question.question_type, 'stage': stage},
                )
                return question

        if round_type == 'image':
            image = self._pick_image_question(chat_id, recent_keys, category)
            if image:
                question = QuizQuestion(
                    **image,
                    key=self._question_key(image['question'], image['answer'], image.get('photo_url')),
                    source='image_pool',
                )
                self._apply_stage_profile(question, stage)
                self._remember_question(chat_id, question)
                log_operation(
                    logger,
                    operation='question_generate',
                    chat_id=chat_id,
                    result='ok',
                    duration_ms=(time.perf_counter() - started) * 1000,
                    extra={'source': question.source, 'round_type': question.question_type, 'stage': stage},
                )
                return question

        try:
            question = await self._generate_text_question(
                chat_id=chat_id,
                recent_keys=recent_keys,
                category=category,
                stage=stage,
                preferred_difficulty=preferred_difficulty,
            )
            self._apply_stage_profile(question, stage)
            self._remember_question(chat_id, question)
            log_operation(
                logger,
                operation='question_generate',
                chat_id=chat_id,
                result='ok',
                duration_ms=(time.perf_counter() - started) * 1000,
                extra={'source': question.source, 'round_type': question.question_type, 'stage': stage},
            )
            return question
        except Exception as exc:
            logger.exception('LLM question generation failed: %s', exc)
            log_operation(
                logger,
                operation='question_generate',
                chat_id=chat_id,
                result='llm_failed',
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
                extra={'round_type': round_type, 'stage': stage},
                level=logging.ERROR,
            )
            raise

    def _apply_stage_profile(self, question: QuizQuestion, stage: str) -> None:
        if stage == 'warmup':
            question.round_label = '🔥 Разогрев'
            question.point_value = 1
            if question.difficulty == 'hard':
                question.difficulty = 'medium'
        elif stage == 'special':
            if question.question_type == 'audio':
                question.round_label = '🎧 Спецраунд x2'
            elif question.question_type == 'image':
                question.round_label = '🖼 Спецраунд x2'
            else:
                question.round_label = '⚡ Спецраунд x2'
            question.point_value = 2
        elif stage == 'finale':
            question.round_label = '👑 Финальный x2'
            question.point_value = 2
        else:
            question.round_label = '🎯 Основной раунд'
            question.point_value = 1

    def _remember_question(self, chat_id: int, question: QuizQuestion) -> None:
        self.history.remember(
            chat_id=chat_id,
            key=question.key,
            category=question.category,
            topic=question.topic or question.answer,
            answer=normalize_text(question.answer),
            round_type=question.question_type,
        )

    def _choose_category(
        self,
        chat_id: int,
        preferred_category: str,
        category_bias: dict[str, float],
    ) -> str:
        if preferred_category != CATEGORY_RANDOM:
            return preferred_category

        recent = self.history.recent_categories(chat_id, 6)
        weights = {
            'Общие знания': 8,
            'География': 10,
            'История': 10,
            'Кино': 10,
            'Музыка': 10,
            'Технологии': 9,
            'Наука': 9,
            'Спорт': 9,
            'Литература': 8,
            'Интернет': 8,
        }

        pool = []
        pool_weights = []
        for category in SUPPORTED_CATEGORIES:
            weight = float(weights.get(category, 8))
            if recent:
                if category == recent[-1]:
                    weight -= 7
                if len(recent) >= 2 and category == recent[-2]:
                    weight -= 4
                if recent.count(category) >= 2:
                    weight -= 2
            weight += float(category_bias.get(category, 0.0))
            weight = max(weight, 1.0)
            pool.append(category)
            pool_weights.append(weight)

        return random.choices(pool, weights=pool_weights, k=1)[0]

    def _choose_round_type(
        self,
        chat_id: int,
        category: str,
        stage: str,
        allow_image_rounds: bool,
        allow_music_rounds: bool,
    ) -> str:
        return 'text'

    async def _generate_text_question(
        self,
        chat_id: int,
        recent_keys: set[str],
        category: str,
        stage: str,
        preferred_difficulty: str | None,
    ) -> QuizQuestion:
        recent_categories = self.history.recent_categories(chat_id, 6)
        recent_topics = self.history.recent_topics(chat_id, 12)
        recent_answers = self.history.recent_answers(chat_id, 12)

        best_question: QuizQuestion | None = None
        best_score = -10_000.0
        semantic_hits = 0
        max_similarity_seen = 0.0

        for _ in range(3):
            candidates = await self._generate_candidates_via_llm(
                category=category,
                stage=stage,
                recent_categories=recent_categories,
                recent_topics=recent_topics,
                recent_answers=recent_answers,
                preferred_difficulty=preferred_difficulty,
            )

            for payload in candidates:
                key = self._question_key(payload.question, payload.answer)
                score, similarity_hit, similarity_value = self._score_candidate(
                    payload=payload,
                    key=key,
                    recent_keys=recent_keys,
                    recent_categories=recent_categories,
                    recent_topics=recent_topics,
                    recent_answers=recent_answers,
                    stage=stage,
                    preferred_difficulty=preferred_difficulty,
                )
                if similarity_hit:
                    semantic_hits += 1
                if similarity_value > max_similarity_seen:
                    max_similarity_seen = similarity_value
                if score > best_score:
                    best_score = score
                    best_question = QuizQuestion(**payload.model_dump(), key=key, source='llm')

            if best_question and best_score >= 1:
                break

        if not best_question:
            raise ValueError('No valid candidate question.')

        self.semantic_repeat_stats[chat_id] = {
            'semantic_hits': float(semantic_hits),
            'max_similarity': round(max_similarity_seen, 3),
        }

        return best_question

    async def _generate_candidates_via_llm(
        self,
        category: str,
        stage: str,
        recent_categories: list[str],
        recent_topics: list[str],
        recent_answers: list[str],
        preferred_difficulty: str | None,
    ) -> list[QuestionPayload]:
        recent_categories_block = ', '.join(recent_categories[-4:]) if recent_categories else 'нет'
        recent_topics_block = ', '.join(recent_topics[-8:]) if recent_topics else 'нет'
        recent_answers_block = ', '.join(recent_answers[-8:]) if recent_answers else 'нет'

        stage_instruction = 'обычный раунд'
        if stage == 'warmup':
            stage_instruction = 'разогрев: вопросы лучше делать лёгкими и быстро считываемыми'
        elif stage == 'special':
            stage_instruction = 'спецраунд: вопрос должен ощущаться более ярким и неожиданным'
        elif stage == 'finale':
            stage_instruction = 'финал: вопрос должен быть ярким, напряжённым и запоминающимся'

        user_prompt = f"""
Сгенерируй 4 разных вопроса для Telegram-квиза.

Требования:
- целевая категория: {category}
- целевая сложность: {preferred_difficulty or 'medium'}
- стадия игры: {stage_instruction}
- не использовать недавно встречавшиеся категории: {recent_categories_block}
- не использовать недавно встречавшиеся темы: {recent_topics_block}
- не использовать недавно встречавшиеся ответы или ключевые сущности: {recent_answers_block}
- избегай однотипных формулировок
- не используй компьютерные игры, игровые франшизы и игровых персонажей
- делай вопросы массово понятными и интересными

Верни только валидный JSON.
""".strip()

        response = await retry_async(
            lambda: self.client.chat.completions.create(
                model=self.model,
                temperature=0.9,
                messages=[
                    {'role': 'system', 'content': QUESTION_SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_prompt},
                ],
            ),
            retries=2,
            base_delay_sec=0.8,
            should_retry=self._should_retry_llm_error,
        )

        content = response.choices[0].message.content or ''

        try:
            return self._parse_candidates(content, forced_category=category)
        except Exception:
            return await self._repair_candidates(content, forced_category=category)

    async def _repair_candidates(self, broken_content: str, forced_category: str) -> list[QuestionPayload]:
        repair_prompt = f"""
Ниже сломанный ответ модели. Исправь его и верни только валидный JSON вида:
{{
  "questions": [{{...}}, {{...}}, {{...}}, {{...}}]
}}

Если полей не хватает — дополни их.
Целевая категория: {forced_category}
Компьютерные игры запрещены.

Сломанный ответ:
{broken_content}
""".strip()

        response = await retry_async(
            lambda: self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=[
                    {'role': 'system', 'content': QUESTION_SYSTEM_PROMPT},
                    {'role': 'user', 'content': repair_prompt},
                ],
            ),
            retries=2,
            base_delay_sec=0.8,
            should_retry=self._should_retry_llm_error,
        )

        repaired = response.choices[0].message.content or ''
        return self._parse_candidates(repaired, forced_category=forced_category)

    def _parse_candidates(self, content: str, forced_category: str) -> list[QuestionPayload]:
        raw = self._extract_json_value(content)
        data: Any = json.loads(raw)

        if isinstance(data, dict) and isinstance(data.get('questions'), list):
            items = data['questions']
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            raise ValueError('Unexpected candidate payload.')

        candidates: list[QuestionPayload] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            aliases = item.get('aliases', [])
            if not isinstance(aliases, list):
                aliases = [str(aliases)]

            normalized = {
                'category': forced_category if forced_category != CATEGORY_RANDOM else self._normalize_category(str(item.get('category', 'Общие знания'))),
                'difficulty': self._normalize_difficulty(str(item.get('difficulty', 'medium'))),
                'topic': str(item.get('topic', 'Общее')).strip() or 'Общее',
                'question': str(item.get('question', '')).strip(),
                'answer': str(item.get('answer', '')).strip(),
                'aliases': [str(x).strip() for x in aliases if str(x).strip()],
                'hint': str(item.get('hint', '')).strip(),
                'explanation': str(item.get('explanation', '')).strip(),
            }

            question_norm = normalize_text(normalized['question'])
            topic_norm = normalize_text(normalized['topic'])
            if any(token in question_norm for token in ['minecraft','mario','ведьмак','playstation','xbox','steam','dota','cs','counter strike']):
                continue
            if any(token in topic_norm for token in ['игр', 'game', 'гейм']):
                continue

            try:
                candidates.append(QuestionPayload.model_validate(normalized))
            except Exception:
                continue

        if not candidates:
            raise ValueError('No valid parsed candidates.')

        return candidates[:4]

    def _extract_json_value(self, content: str) -> str:
        raw = content.strip()

        if raw.startswith('```'):
            raw = raw.strip('`').strip()
            if raw.lower().startswith('json'):
                raw = raw[4:].strip()

        first_obj = raw.find('{')
        first_arr = raw.find('[')

        if first_obj == -1 and first_arr == -1:
            raise ValueError('No JSON found in model output.')

        if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
            start = first_arr
            end = raw.rfind(']')
        else:
            start = first_obj
            end = raw.rfind('}')

        if start == -1 or end == -1 or end <= start:
            raise ValueError('Broken JSON boundaries.')

        return raw[start:end + 1]

    def _normalize_category(self, value: str) -> str:
        value_norm = normalize_text(value)
        for item in SUPPORTED_CATEGORIES:
            if normalize_text(item) == value_norm:
                return item
        return 'Общие знания'

    def _normalize_difficulty(self, value: str) -> str:
        value_norm = normalize_text(value)
        if value_norm in {'easy', 'изи', 'легкий', 'лёгкий'}:
            return 'easy'
        if value_norm in {'hard', 'хард', 'сложный'}:
            return 'hard'
        return 'medium'

    def _score_candidate(
        self,
        payload: QuestionPayload,
        key: str,
        recent_keys: set[str],
        recent_categories: list[str],
        recent_topics: list[str],
        recent_answers: list[str],
        stage: str,
        preferred_difficulty: str | None,
    ) -> tuple[float, bool, float]:
        if key in recent_keys:
            return -10_000.0, False, 0.0

        score = 10.0
        answer_norm = normalize_text(payload.answer)
        topic_norm = normalize_text(payload.topic)
        recent_topic_norms = [normalize_text(x) for x in recent_topics[-6:]]
        recent_answer_norms = [normalize_text(x) for x in recent_answers[-8:]]

        if payload.category in recent_categories[-2:]:
            score -= 3.0
        if topic_norm in recent_topic_norms:
            score -= 4.0
        if answer_norm in recent_answer_norms:
            score -= 4.0

        semantic_penalty, max_similarity = self._semantic_repeat_penalty(payload, recent_topics, recent_answers)
        score -= semantic_penalty

        if len(payload.aliases) >= 1:
            score += 0.4
        if payload.topic and payload.topic != 'Общее':
            score += 0.4

        if stage == 'warmup':
            if payload.difficulty == 'easy':
                score += 1.2
            if payload.difficulty == 'hard':
                score -= 1.5
        elif stage == 'finale':
            if payload.difficulty == 'medium':
                score += 0.8
            if payload.difficulty == 'hard':
                score += 1.0
        else:
            if payload.difficulty == 'medium':
                score += 0.8

        if preferred_difficulty and payload.difficulty == preferred_difficulty:
            score += 0.35

        return score, max_similarity >= 0.60, max_similarity

    def _semantic_repeat_penalty(
        self,
        payload: QuestionPayload,
        recent_topics: list[str],
        recent_answers: list[str],
    ) -> tuple[float, float]:
        candidate_tokens = self._token_set(f'{payload.topic} {payload.answer}')
        if not candidate_tokens:
            return 0.0, 0.0

        max_similarity = 0.0
        for item in [*recent_topics[-8:], *recent_answers[-8:]]:
            recent_tokens = self._token_set(item)
            if not recent_tokens:
                continue
            inter = len(candidate_tokens & recent_tokens)
            union = len(candidate_tokens | recent_tokens)
            if union == 0:
                continue
            similarity = inter / union
            if similarity > max_similarity:
                max_similarity = similarity

        if max_similarity >= 0.80:
            return 3.0, max_similarity
        if max_similarity >= 0.60:
            return 1.5, max_similarity
        return 0.0, max_similarity

    def _token_set(self, value: str) -> set[str]:
        cleaned = normalize_text(value)
        return {token for token in cleaned.split() if len(token) >= 3}

    def _pick_text_fallback_question(self, chat_id: int, recent_keys: Iterable[str], category: str) -> dict[str, Any]:
        recent_set = set(recent_keys)

        pool = [item for item in TEXT_FALLBACK_QUESTIONS if item['category'] == category]
        if not pool:
            pool = TEXT_FALLBACK_QUESTIONS[:]

        candidates = [
            item for item in pool
            if self._question_key(item['question'], item['answer']) not in recent_set
        ]
        if not candidates:
            candidates = pool[:]

        return random.choice(candidates).copy()

    def _pick_image_question(self, chat_id: int, recent_keys: Iterable[str], category: str) -> dict[str, Any] | None:
        if category != 'География':
            return None

        recent_set = set(recent_keys)
        pool = IMAGE_FALLBACK_QUESTIONS[:]

        candidates = [
            item for item in pool
            if self._question_key(item['question'], item['answer'], item.get('photo_url')) not in recent_set
        ]
        if not candidates:
            candidates = pool[:]

        return random.choice(candidates).copy()

    def _load_music_rounds(self) -> list[dict[str, Any]]:
        path = Path('data/music_rounds.json')
        if not path.exists():
            logger.info('music_rounds.json not found, music rounds disabled until file is filled.')
            return []

        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            logger.exception('Failed to parse music rounds file: %s', exc)
            return []

        if not isinstance(raw, list):
            return []

        items: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue

            audio_path_raw = str(item.get('audio_path', '')).strip()
            if not audio_path_raw:
                continue

            audio_path = Path(audio_path_raw)
            if not audio_path.is_absolute():
                audio_path = Path.cwd() / audio_path

            if not audio_path.exists():
                continue

            normalized = {
                'category': 'Музыка',
                'difficulty': self._normalize_difficulty(str(item.get('difficulty', 'medium'))),
                'topic': str(item.get('topic', 'Музыкальный раунд')).strip() or 'Музыкальный раунд',
                'question': str(item.get('question', 'Угадай трек или исполнителя по фрагменту.')).strip(),
                'answer': str(item.get('answer', '')).strip(),
                'aliases': [str(x).strip() for x in item.get('aliases', []) if str(x).strip()],
                'hint': str(item.get('hint', 'Слушай внимательно.')).strip(),
                'explanation': str(item.get('explanation', 'Это правильный музыкальный ответ.')).strip(),
                'question_type': 'audio',
                'audio_path': str(audio_path),
                'audio_title': str(item.get('audio_title', 'Музыкальный раунд')).strip() or 'Музыкальный раунд',
                'audio_performer': str(item.get('audio_performer', 'Quiz Bot')).strip() or 'Quiz Bot',
            }

            if not normalized['answer']:
                continue

            items.append(normalized)

        logger.info('Loaded music rounds: %s', len(items))
        return items

    def _pick_music_round(self, chat_id: int, recent_keys: Iterable[str], category: str) -> dict[str, Any] | None:
        if category != 'Музыка':
            return None

        recent_set = set(recent_keys)
        pool = self.music_rounds[:]
        if not pool:
            return None

        candidates = [
            item for item in pool
            if self._question_key(item['question'], item['answer'], item.get('audio_path')) not in recent_set
        ]
        if not candidates:
            candidates = pool[:]

        return random.choice(candidates).copy()

    def _question_key(self, question: str, answer: str, extra: str | None = None) -> str:
        base = f'{normalize_text(question)}|{normalize_text(answer)}'
        if extra:
            base += f'|{normalize_text(extra)}'
        return base

    def _should_retry_llm_error(self, exc: Exception) -> bool:
        if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
            return True
        if isinstance(exc, APIStatusError):
            status = getattr(exc, 'status_code', None)
            return bool(status in {429} or (isinstance(status, int) and status >= 500))
        return False


    async def generate_question_batch(self, request: dict[str, Any]) -> list[QuestionCandidate]:
        count = int(request.get('count', 10))
        category = str(request.get('category', CATEGORY_RANDOM))
        difficulty = str(request.get('difficulty', 'medium'))
        mode = str(request.get('mode', 'classic'))
        llm_only = bool(request.get('llm_only', False))
        chat_id = int(request.get('chat_id', 0))

        batch: list[QuestionCandidate] = []
        skipped_non_llm = 0
        skipped_sources: dict[str, int] = {}
        recent_keys = set(self.history.recent_keys(chat_id, settings.recent_questions_limit))

        for _ in range(max(1, min(count, 20))):
            if llm_only:
                selected_category = self._choose_category(chat_id, category, {})
                try:
                    question = await self._generate_text_question(
                        chat_id=chat_id,
                        recent_keys=recent_keys,
                        category=selected_category,
                        stage='core',
                        preferred_difficulty=difficulty,
                    )
                except Exception as exc:
                    logger.warning('LLM-only batch item generation failed: %s', type(exc).__name__)
                    continue
            else:
                try:
                    question = await self.generate_question(
                        chat_id=chat_id,
                        used_keys=recent_keys,
                        preferred_category=category,
                        stage='core',
                        preferred_difficulty=difficulty,
                    )
                except Exception as exc:
                    logger.warning('Batch item generation failed: %s', type(exc).__name__)
                    continue

            if llm_only and question.source != 'llm':
                skipped_non_llm += 1
                source = str(question.source or 'unknown')
                skipped_sources[source] = skipped_sources.get(source, 0) + 1
                continue

            if question.key:
                recent_keys.add(question.key)

            candidate = QuestionCandidate(
                provider_name='openai',
                model_name=self.model,
                language=str(request.get('language', 'ru')),
                topic=question.topic or category,
                subtopic='',
                difficulty=question.difficulty,
                question_type=question.question_type,
                question_text=question.question,
                options=[],
                correct_option_index=None,
                correct_answer_text=question.answer,
                explanation=question.explanation,
                canonical_facts=[question.explanation, question.answer],
                uniqueness_tags=[question.topic or category],
                created_for_mode=mode,
                raw_payload={'hint': question.hint, 'aliases': question.aliases, 'source': question.source},
            )
            batch.append(candidate)

        if llm_only and skipped_non_llm > 0:
            logger.warning(
                'Skip non-llm questions in llm_only batch generation: skipped=%s, sources=%s',
                skipped_non_llm,
                skipped_sources,
            )

        return self.validate_question_batch(batch)

    def validate_question_batch(self, candidates: list[QuestionCandidate]) -> list[QuestionCandidate]:
        valid: list[QuestionCandidate] = []
        for candidate in candidates:
            candidate.question_text = ' '.join(candidate.question_text.split())
            candidate.correct_answer_text = ' '.join(candidate.correct_answer_text.split())
            candidate.topic = (candidate.topic or 'Общее').strip()
            candidate.subtopic = (candidate.subtopic or '').strip()
            candidate.explanation = ' '.join((candidate.explanation or '').split())
            candidate.canonical_facts = [str(item).strip() for item in candidate.canonical_facts if str(item).strip()]

            if not candidate.question_text or len(candidate.question_text) < 8:
                continue
            if candidate.difficulty not in {'easy', 'medium', 'hard'}:
                candidate = self.repair_invalid_question(candidate) or candidate
            if not candidate.correct_answer_text.strip() or not candidate.explanation.strip():
                repaired = self.repair_invalid_question(candidate)
                if repaired is None:
                    continue
                candidate = repaired

            candidate.question_hash = self.dedup_service.question_hash(candidate)
            candidate.uniqueness_hash = self.dedup_service.uniqueness_hash(candidate)
            valid.append(candidate)
        return valid

    def repair_invalid_question(self, candidate: QuestionCandidate) -> QuestionCandidate | None:
        if not candidate.question_text.strip() or not candidate.correct_answer_text.strip():
            return None
        if candidate.difficulty not in {'easy', 'medium', 'hard'}:
            candidate.difficulty = 'medium'
        if not candidate.explanation.strip():
            candidate.explanation = 'Короткое объяснение недоступно.'
        return candidate

    def derive_uniqueness_fingerprint(self, candidate: QuestionCandidate) -> dict[str, Any]:
        canonical_facts = [str(item).strip().lower() for item in candidate.canonical_facts if str(item).strip()]
        return {
            'topic': (candidate.topic or '').strip().lower(),
            'subtopic': (candidate.subtopic or '').strip().lower(),
            'canonical_facts': canonical_facts,
            'answer_normalized': (candidate.correct_answer_text or '').strip().lower(),
        }
