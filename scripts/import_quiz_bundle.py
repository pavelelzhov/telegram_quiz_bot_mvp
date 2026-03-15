from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import zipfile
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Iterable

from app.core.models import QuestionCandidate
from app.storage.db import Database

ALLOWED_TOPICS = {
    'Случайно',
    'География',
    'История',
    'Кино',
    'Музыка',
    'Технологии',
    'Наука',
    'Спорт',
    'Литература',
    'Интернет',
    'Общие знания',
}


def _norm_topic(raw: str) -> str:
    text = (raw or '').strip()
    if not text:
        return 'Общие знания'
    if text in ALLOWED_TOPICS:
        return text
    lowered = text.lower()
    aliases = {
        'общие': 'Общие знания',
        'общие знания': 'Общие знания',
        'science': 'Наука',
        'sport': 'Спорт',
        'sports': 'Спорт',
        'music': 'Музыка',
        'history': 'История',
        'geography': 'География',
        'movies': 'Кино',
        'cinema': 'Кино',
        'literature': 'Литература',
        'internet': 'Интернет',
        'tech': 'Технологии',
        'technology': 'Технологии',
    }
    mapped = aliases.get(lowered)
    return mapped if mapped in ALLOWED_TOPICS else 'Общие знания'


def _compute_hash(*parts: str) -> str:
    payload = '|'.join(item.strip().lower() for item in parts if item).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _normalize_aliases(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]

    if isinstance(raw_value, str):
        parts = raw_value
        for separator in (';', ','):
            parts = parts.replace(separator, '|')
        return [item.strip() for item in parts.split('|') if item.strip()]

    return []


def _row_to_candidate(row: dict[str, Any]) -> QuestionCandidate | None:
    question = str(row.get('question') or row.get('question_text') or '').strip()
    answer = str(row.get('answer') or row.get('correct_answer') or row.get('correct_answer_text') or '').strip()
    if not question or not answer:
        return None

    topic = _norm_topic(str(row.get('topic') or row.get('category') or ''))
    difficulty = str(row.get('difficulty') or 'medium').strip().lower()
    if difficulty not in {'easy', 'medium', 'hard'}:
        difficulty = 'medium'

    question_hash = _compute_hash(question, answer, topic)
    uniqueness_hash = _compute_hash(question, topic)
    aliases = _normalize_aliases(row.get('aliases') or row.get('alt_answers') or row.get('accepted_answers') or [])
    hint = str(row.get('hint') or row.get('tip') or '').strip()
    explanation = str(row.get('explanation') or row.get('fact') or '').strip()
    if not explanation:
        explanation = 'Факт временно недоступен.'

    return QuestionCandidate(
        provider_name='import_zip',
        model_name='manual_bundle',
        language='ru',
        topic=topic,
        subtopic=str(row.get('subtopic') or ''),
        difficulty=difficulty,
        question_type='text',
        question_text=question,
        correct_answer_text=answer,
        explanation=explanation,
        canonical_facts=[str(row.get('fact') or '').strip()] if row.get('fact') else [],
        uniqueness_tags=[topic],
        question_hash=question_hash,
        uniqueness_hash=uniqueness_hash,
        quality_score=0.8,
        is_valid=True,
        created_for_mode='classic',
        raw_payload={
            'aliases': aliases,
            'hint': hint,
        },
    )


def _load_json_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _load_rows_from_zip(zip_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith('/'):
                continue
            with zf.open(name) as f:
                if name.lower().endswith('.jsonl'):
                    wrapper = TextIOWrapper(f, encoding='utf-8')
                    rows.extend(_load_json_lines(wrapper))
                elif name.lower().endswith('.json'):
                    data = json.load(TextIOWrapper(f, encoding='utf-8'))
                    if isinstance(data, list):
                        rows.extend(item for item in data if isinstance(item, dict))
                    elif isinstance(data, dict):
                        rows.append(data)
                elif name.lower().endswith('.csv'):
                    reader = csv.DictReader(TextIOWrapper(f, encoding='utf-8'))
                    rows.extend(dict(item) for item in reader)
    return rows


async def _run(zip_path: Path, db_path: Path, chunk_size: int) -> None:
    db = Database(str(db_path))
    await db.init()
    rows = _load_rows_from_zip(zip_path)
    candidates = [c for c in (_row_to_candidate(row) for row in rows) if c is not None]

    inserted_total = 0
    for idx in range(0, len(candidates), chunk_size):
        inserted_total += await db.save_generated_questions(candidates[idx : idx + chunk_size])

    print(f'Файл: {zip_path}')
    print(f'Строк в архиве: {len(rows)}')
    print(f'Валидных кандидатов: {len(candidates)}')
    print(f'Сохранено в БД: {inserted_total}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Импорт вопросов из zip-архива в llm_questions')
    parser.add_argument('--zip-path', required=True, help='Путь к zip-архиву с вопросами')
    parser.add_argument('--db-path', default='quiz.db', help='Путь к sqlite базе')
    parser.add_argument('--chunk-size', type=int, default=500, help='Размер батча вставки')
    args = parser.parse_args()

    zip_path = Path(args.zip_path).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()

    if not zip_path.exists():
        raise SystemExit(f'Файл не найден: {zip_path}')

    asyncio.run(_run(zip_path=zip_path, db_path=db_path, chunk_size=max(1, args.chunk_size)))


if __name__ == '__main__':
    main()
