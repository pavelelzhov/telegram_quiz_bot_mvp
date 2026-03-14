from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from app.core.models import QuestionCandidate


class QuestionDedupService:
    def normalize_text(self, text: str) -> str:
        cleaned = re.sub(r'\s+', ' ', (text or '').strip().lower())
        cleaned = re.sub(r'[^\w\sа-яё-]', '', cleaned)
        return cleaned

    def question_hash(self, candidate: QuestionCandidate) -> str:
        payload = {
            'question': self.normalize_text(candidate.question_text),
            'question_type': candidate.question_type,
            'answer': self.normalize_text(candidate.correct_answer_text),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    def uniqueness_hash(self, candidate: QuestionCandidate) -> str:
        payload = {
            'topic': self.normalize_text(candidate.topic),
            'subtopic': self.normalize_text(candidate.subtopic),
            'facts': [self.normalize_text(item) for item in candidate.canonical_facts],
            'answer': self.normalize_text(candidate.correct_answer_text),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    def has_duplicate(self, candidate: QuestionCandidate, seen_question_hashes: Iterable[str], seen_uniqueness_hashes: Iterable[str]) -> bool:
        return candidate.question_hash in set(seen_question_hashes) or candidate.uniqueness_hash in set(seen_uniqueness_hashes)
