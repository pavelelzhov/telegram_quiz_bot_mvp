from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Iterable, Optional


NUM_WORDS = {
    'ноль': '0',
    'один': '1',
    'одна': '1',
    'два': '2',
    'три': '3',
    'четыре': '4',
    'пять': '5',
    'шесть': '6',
    'семь': '7',
    'восемь': '8',
    'девять': '9',
    'десять': '10',
    'одиннадцать': '11',
    'двенадцать': '12',
}


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = value.replace('ё', 'е')
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'[^\w\s]', ' ', value, flags=re.UNICODE)
    value = re.sub(r'[_]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()

    tokens = []
    for token in value.split():
        tokens.append(NUM_WORDS.get(token, token))

    return ' '.join(tokens).strip()


def build_answer_variants(correct_answer: str, aliases: Optional[Iterable[str]] = None) -> list[str]:
    variants = [correct_answer]
    if aliases:
        variants.extend(list(aliases))

    normalized: list[str] = []
    for item in variants:
        if not item or not item.strip():
            continue
        norm = normalize_text(item)
        if norm and norm not in normalized:
            normalized.append(norm)
    return normalized


def _token_set(value: str) -> set[str]:
    return {token for token in value.split() if token}


def _looks_numeric(value: str) -> bool:
    return value.replace(' ', '').isdigit()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_exact_answer(user_text: str, correct_answer: str, aliases: Optional[list[str]] = None) -> bool:
    user_norm = normalize_text(user_text)
    if not user_norm:
        return False

    valid = build_answer_variants(correct_answer, aliases)
    user_tokens = _token_set(user_norm)

    for item in valid:
        item_tokens = _token_set(item)

        if user_norm == item:
            return True

        if item_tokens and item_tokens.issubset(user_tokens):
            return True

        if not _looks_numeric(user_norm) and not _looks_numeric(item):
            if len(item) >= 5 and item in user_norm:
                return True
            if len(user_norm) >= 5 and user_norm in item:
                return True

            max_len = max(len(user_norm), len(item))
            ratio = _ratio(user_norm, item)
            if max_len >= 8 and ratio >= 0.88:
                return True
            if 5 <= max_len < 8 and ratio >= 0.93:
                return True

    return False


def is_close_answer(user_text: str, correct_answer: str, aliases: Optional[list[str]] = None) -> bool:
    user_norm = normalize_text(user_text)
    if not user_norm:
        return False

    if is_exact_answer(user_text, correct_answer, aliases):
        return False

    valid = build_answer_variants(correct_answer, aliases)
    user_tokens = _token_set(user_norm)

    for item in valid:
        item_tokens = _token_set(item)
        shared_tokens = user_tokens & item_tokens

        if item_tokens and len(shared_tokens) >= 1:
            overlap = len(shared_tokens) / max(len(item_tokens), 1)
            if overlap >= 0.5:
                return True

        if not _looks_numeric(user_norm) and not _looks_numeric(item):
            ratio = _ratio(user_norm, item)
            if ratio >= 0.72:
                return True

            if len(item) >= 4 and item in user_norm:
                return True
            if len(user_norm) >= 4 and user_norm in item:
                return True

    return False


def answer_match_details(user_text: str, correct_answer: str, aliases: Optional[list[str]] = None) -> str:
    if is_exact_answer(user_text, correct_answer, aliases):
        return 'exact'
    if is_close_answer(user_text, correct_answer, aliases):
        return 'close'
    return 'wrong'
