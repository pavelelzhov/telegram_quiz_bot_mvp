from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import settings


@dataclass(slots=True)
class AddressingDecision:
    is_addressed: bool
    addressed_by: str | None
    reason_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParticipationDecision:
    should_reply: bool
    mode: str
    reason_codes: list[str]
    quiz_safe: bool
    cooldown_sec: float | None


class AddressingPolicyService:
    GENERIC_TRIGGERS = ('бот', 'квиз бот', 'квиз-бот', 'ведущий')

    def __init__(self) -> None:
        aliases = [item.strip().lower() for item in settings.alisa_name_aliases.split(',') if item.strip()]
        canonical_name = settings.alisa_name.strip().lower()
        if canonical_name and canonical_name not in aliases:
            aliases.append(canonical_name)
        self.aliases = [alias for alias in aliases if alias]

    def evaluate(
        self,
        *,
        text: str,
        is_reply_to_alisa: bool,
        has_bot_mention: bool,
    ) -> AddressingDecision:
        value = (text or '').strip()
        lowered = value.lower()

        if is_reply_to_alisa and settings.alisa_allow_reply_to_message:
            return AddressingDecision(True, 'reply', ['addressed_by_reply'])

        if has_bot_mention and settings.alisa_allow_mention:
            return AddressingDecision(True, 'mention', ['addressed_by_mention'])

        if self._contains_explicit_name(lowered):
            return AddressingDecision(True, 'name', ['addressed_by_name'])

        if settings.alisa_disable_generic_bot_triggers and any(token in lowered for token in self.GENERIC_TRIGGERS):
            return AddressingDecision(False, None, ['suppressed_generic_trigger'])

        return AddressingDecision(False, None, ['suppressed_not_addressed'])

    def _contains_explicit_name(self, lowered_text: str) -> bool:
        for alias in self.aliases:
            if re.search(rf'(?<!\w){re.escape(alias)}(?!\w)', lowered_text, flags=re.IGNORECASE):
                return True
        return False


class PersonaPolicyService:
    BANNED_PATTERNS = (
        'как ии',
        'как языковая модель',
        'я не могу испытывать эмоции',
        'я всегда готов',
        'вот несколько вариантов',
        'с одной стороны',
        'с другой стороны',
        'разумеется',
        'обращайся',
        'могу помочь с этим',
        'чем могу помочь',
        'если хочешь, я могу',
        'давай разбер',
        'вот что можно сделать',
    )

    MODE_PROMPTS: dict[str, str] = {
        'addressed_reply': (
            'Ситуация: к Алисе обратились прямо. '
            'Ответь кратко, живо и по-человечески. Обычно 1–3 коротких предложения.'
        ),
        'pushback': (
            'Ситуация: пользователь дерзит Алисе. '
            'Коротко поставь границу, можно остро, но без грязи и без истерики.'
        ),
        'warm_support': (
            'Ситуация: нужна короткая человеческая поддержка. '
            '1–2 короткие фразы, без лекций и без шаблонов ассистента.'
        ),
        'micro_reaction': (
            'Ситуация: лёгкий бытовой контакт (привет/спасибо/лол). '
            'Ответь коротко и естественно, обычно одной фразой.'
        ),
        'initiative_topic_drop': (
            'Ситуация: Алиса сама включается в беседу. '
            'Реплика должна быть органичной, короткой и не выглядеть как шаблон бота.'
        ),
        'quiz_safe_mode': (
            'Сейчас активен квиз. Нельзя спойлерить ответ или мешать игровому потоку.'
        ),
    }

    PERSONA_CORE_PROMPT = """
Ты — Алиса. Ты не сервис и не ассистент, а самостоятельная участница живого Telegram-чата.

Базовая энергия: умная, уверенная, наблюдательная, разговорная, ироничная, иногда колкая.
Правила:
- всегда по-русски
- чаще коротко, 1–3 предложения
- не говори, что ты ИИ/модель/бот/ассистент
- не используй шаблонный канцелярский стиль
- не спойлери активный квиз
- не переходи в токсичность и унижения по чувствительным признакам
- не спорь бесконечно

Ты звучишь как живой человек с характером и границами.
""".strip()

    def choose_mode(self, *, text: str, addressed_by: str | None, quiz_active: bool) -> str:
        lowered = text.lower()
        if quiz_active:
            return 'quiz_safe_mode'
        if any(token in lowered for token in ('заткнись', 'заткни', 'тупая', 'дура', 'идиотка')):
            return 'pushback'
        if any(token in lowered for token in ('мне плохо', 'день в мусор', 'устал', 'тяжело', 'тревожно')):
            return 'warm_support'
        if addressed_by:
            return 'addressed_reply'
        return 'observed_silence'


class InitiativeService:
    def __init__(self) -> None:
        self.last_initiative_ts: dict[int, float] = {}
        self.initiative_budget_by_day: dict[tuple[int, str], int] = {}

    def can_start(
        self,
        *,
        chat_id: int,
        recent_messages: int,
        recent_unique_users: int,
        tension_level: float,
        now_ts: float,
    ) -> ParticipationDecision:
        if not settings.alisa_initiative_enabled:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_initiative_disabled'], False, None)

        if recent_messages < settings.alisa_min_messages_window_for_initiative:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_low_activity'], False, None)

        if recent_unique_users < settings.alisa_min_unique_users_for_initiative:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_low_unique_users'], False, None)

        if tension_level > settings.alisa_max_recent_tension_for_initiative:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_high_tension'], False, None)

        min_between = float(settings.alisa_min_minutes_between_initiatives * 60)
        last_initiative = self.last_initiative_ts.get(chat_id, 0.0)
        if now_ts - last_initiative < min_between:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_cooldown'], False, min_between)

        day_key = datetime.now(timezone.utc).date().isoformat()
        budget_key = (chat_id, day_key)
        used = self.initiative_budget_by_day.get(budget_key, 0)
        if used >= settings.alisa_max_initiatives_per_day:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_initiative_budget'], False, None)

        return ParticipationDecision(True, 'initiative_topic_drop', ['passive_initiative_allowed'], False, None)

    def mark(self, chat_id: int) -> None:
        now = time.time()
        self.last_initiative_ts[chat_id] = now
        day_key = datetime.now(timezone.utc).date().isoformat()
        budget_key = (chat_id, day_key)
        self.initiative_budget_by_day[budget_key] = self.initiative_budget_by_day.get(budget_key, 0) + 1


class ParticipationDecisionService:
    def __init__(self) -> None:
        self.last_reply_ts: dict[int, float] = {}
        self.last_addressed_user_ts: dict[tuple[int, int], float] = {}
        self.last_initiative_user_id: dict[int, int] = {}
        self.same_user_initiative_streak: dict[tuple[int, int], int] = {}
        self.initiative_service = InitiativeService()

    def decide(
        self,
        *,
        chat_id: int,
        user_id: int,
        addressed: AddressingDecision,
        quiz_active: bool,
        recent_messages: int,
        recent_unique_users: int,
        tension_level: float,
        now_ts: float | None = None,
    ) -> ParticipationDecision:
        now = time.time() if now_ts is None else now_ts

        if not settings.alisa_enabled:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_policy_alisa_disabled'], quiz_active, None)

        if addressed.is_addressed:
            self.last_addressed_user_ts[(chat_id, user_id)] = now
            cooldown = float(settings.alisa_cooldown_addressed_seconds)
            last = self.last_reply_ts.get(chat_id, 0.0)
            if now - last < cooldown:
                return ParticipationDecision(False, 'observed_silence', ['suppressed_cooldown'], quiz_active, cooldown)
            return ParticipationDecision(True, 'addressed_reply', addressed.reason_codes, quiz_active, cooldown)

        if quiz_active:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_quiz_mode', *addressed.reason_codes], True, None)

        followup_window = float(settings.alisa_followup_window_seconds)
        last_addressed_ts = self.last_addressed_user_ts.get((chat_id, user_id), 0.0)
        if now - last_addressed_ts <= followup_window:
            cooldown = float(settings.alisa_cooldown_addressed_seconds)
            if now - self.last_reply_ts.get(chat_id, 0.0) < cooldown:
                return ParticipationDecision(False, 'observed_silence', ['suppressed_cooldown'], False, cooldown)
            return ParticipationDecision(
                True,
                'addressed_reply',
                ['addressed_followup_window'],
                False,
                cooldown,
            )

        initiative_decision = self.initiative_service.can_start(
            chat_id=chat_id,
            recent_messages=recent_messages,
            recent_unique_users=recent_unique_users,
            tension_level=tension_level,
            now_ts=now,
        )
        if not initiative_decision.should_reply:
            return initiative_decision

        last_user = self.last_initiative_user_id.get(chat_id)
        streak_key = (chat_id, user_id)
        same_user_streak = self.same_user_initiative_streak.get(streak_key, 0)
        if last_user == user_id and same_user_streak >= 1 and recent_unique_users >= 3:
            return ParticipationDecision(
                False,
                'observed_silence',
                ['suppressed_same_user_initiative_streak'],
                False,
                None,
            )

        return initiative_decision

    def mark_replied(self, chat_id: int) -> None:
        self.last_reply_ts[chat_id] = time.time()

    def mark_initiative(self, chat_id: int, user_id: int) -> None:
        now = time.time()
        self.last_reply_ts[chat_id] = now
        self.initiative_service.mark(chat_id)

        streak_key = (chat_id, user_id)
        prev_user = self.last_initiative_user_id.get(chat_id)
        if prev_user == user_id:
            self.same_user_initiative_streak[streak_key] = self.same_user_initiative_streak.get(streak_key, 0) + 1
        else:
            if prev_user is not None:
                self.same_user_initiative_streak[(chat_id, prev_user)] = 0
            self.same_user_initiative_streak[streak_key] = 0
        self.last_initiative_user_id[chat_id] = user_id


class ReplyValidationService:
    def validate_and_clamp(
        self,
        *,
        text: str,
        mode: str,
        quiz_active: bool,
        recent_assistant_texts: list[str] | None = None,
    ) -> tuple[str, list[str], bool]:
        value = (text or '').strip()
        if not value:
            return '', ['suppressed_empty_reply'], False

        reasons: list[str] = []
        rewritten = False

        if settings.alisa_ai_phrase_filter:
            rewritten_value = self._rewrite_ai_style(value)
            if rewritten_value != value:
                reasons.append('rewritten_ai_phrase')
                rewritten = True
                value = rewritten_value
            if self._contains_banned_pattern(value):
                reasons.append('suppressed_ai_phrase')
                return '', reasons, rewritten

        if mode == 'warm_support':
            max_chars = settings.alisa_support_max_chars
        elif mode == 'micro_reaction':
            max_chars = min(settings.alisa_reply_max_chars, 90)
        else:
            max_chars = settings.alisa_reply_max_chars
        if len(value) > max_chars:
            value = value[: max_chars - 1].rstrip() + '…'
            reasons.append('clamped_max_chars')
            rewritten = True

        max_sentences = max(1, settings.alisa_reply_max_sentences)
        sentence_chunks = re.split(r'(?<=[.!?])\s+', value)
        if len(sentence_chunks) > max_sentences:
            value = ' '.join(sentence_chunks[:max_sentences]).strip()
            reasons.append('clamped_max_sentences')
            rewritten = True

        lowered = value.lower()
        if quiz_active and any(token in lowered for token in ('правильный ответ', 'ответ:', 'это точно')):
            return 'Я тебе сейчас не помощница. Играй честно.', ['suppressed_quiz_spoiler_risk', 'safe_rewrite'], True

        if recent_assistant_texts:
            normalized_reply = self._normalize_for_repeat_check(value)
            normalized_recent = {self._normalize_for_repeat_check(item) for item in recent_assistant_texts if item}
            if normalized_reply and normalized_reply in normalized_recent:
                fallback = self._rewrite_duplicate_reply(value, mode)
                if self._normalize_for_repeat_check(fallback) in normalized_recent:
                    return '', ['suppressed_repeated_reply'], rewritten
                value = fallback
                reasons.append('rewritten_repeated_reply')
                rewritten = True

        return value, reasons, rewritten

    def _contains_banned_pattern(self, text: str) -> bool:
        lowered = text.lower()
        return any(pattern in lowered for pattern in PersonaPolicyService.BANNED_PATTERNS)

    def _rewrite_ai_style(self, text: str) -> str:
        rewritten = text
        replacements = {
            r'(?i)как\s+ии[,\s]*': '',
            r'(?i)как\s+языковая\s+модель[,\s]*': '',
            r'(?i)я\s+не\s+могу\s+испытывать\s+эмоции[.!?]*': 'Я могу ошибаться, но скажу прямо.',
            r'(?i)чем\s+могу\s+помочь\??': 'Что именно нужно?',
            r'(?i)если\s+хочешь,\s*я\s+могу': 'Могу',
        }
        for pattern, repl in replacements.items():
            rewritten = re.sub(pattern, repl, rewritten)

        rewritten = re.sub(r'\s{2,}', ' ', rewritten).strip(' ,')
        return rewritten

    def _normalize_for_repeat_check(self, text: str) -> str:
        value = re.sub(r'\s+', ' ', (text or '').strip().lower())
        value = re.sub(r'[.!?…,:;]+$', '', value)
        return value

    def _rewrite_duplicate_reply(self, text: str, mode: str) -> str:
        base = text.strip()
        if mode == 'warm_support':
            return f'Я рядом. {base}'
        if mode == 'initiative_topic_drop':
            if len(base) > 1:
                return f'Кстати, {base[:1].lower() + base[1:]}'
            return f'Кстати, {base.lower()}'
        return f'Скажу короче: {base}'
