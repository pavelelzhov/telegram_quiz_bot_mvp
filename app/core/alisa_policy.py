from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

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


class ParticipationDecisionService:
    def __init__(self) -> None:
        self.last_reply_ts: dict[int, float] = {}

    def decide(
        self,
        *,
        chat_id: int,
        addressed: AddressingDecision,
        quiz_active: bool,
    ) -> ParticipationDecision:
        if not settings.alisa_enabled:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_policy_alisa_disabled'], quiz_active, None)

        if not addressed.is_addressed:
            if quiz_active:
                return ParticipationDecision(False, 'observed_silence', ['suppressed_quiz_mode', *addressed.reason_codes], quiz_active, None)
            return ParticipationDecision(False, 'observed_silence', addressed.reason_codes, quiz_active, None)

        now = time.time()
        cooldown = float(settings.alisa_cooldown_addressed_seconds)
        last = self.last_reply_ts.get(chat_id, 0.0)
        if now - last < cooldown:
            return ParticipationDecision(False, 'observed_silence', ['suppressed_cooldown'], quiz_active, cooldown)

        return ParticipationDecision(True, 'addressed_reply', addressed.reason_codes, quiz_active, cooldown)

    def mark_replied(self, chat_id: int) -> None:
        self.last_reply_ts[chat_id] = time.time()


class ReplyValidationService:
    def validate_and_clamp(self, *, text: str, mode: str, quiz_active: bool) -> tuple[str, list[str], bool]:
        value = (text or '').strip()
        if not value:
            return '', ['suppressed_empty_reply'], False

        lowered = value.lower()
        reasons: list[str] = []
        rewritten = False

        if settings.alisa_ai_phrase_filter:
            for pattern in PersonaPolicyService.BANNED_PATTERNS:
                if pattern in lowered:
                    reasons.append('suppressed_ai_phrase')
                    return '', reasons, False

        max_chars = settings.alisa_support_max_chars if mode == 'warm_support' else settings.alisa_reply_max_chars
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

        if quiz_active and any(token in lowered for token in ('правильный ответ', 'ответ:', 'это точно')):
            return 'Я тебе сейчас не помощница. Играй честно.', ['suppressed_quiz_spoiler_risk', 'safe_rewrite'], True

        return value, reasons, rewritten
