from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(slots=True)
class QuizQuestion:
    category: str
    difficulty: str
    question: str
    answer: str
    aliases: List[str]
    hint: str
    explanation: str
    topic: str = ''
    key: str = ''
    source: str = 'llm'
    question_type: str = 'text'
    photo_url: Optional[str] = None
    audio_path: Optional[str] = None
    audio_title: Optional[str] = None
    audio_performer: Optional[str] = None
    point_value: int = 1
    round_label: str = '🎯 Основной раунд'
    question_id: Optional[int] = None
    question_hash: str = ''
    uniqueness_hash: str = ''
    quality_score: float = 0.0


@dataclass(slots=True)
class QuestionCandidate:
    provider_name: str
    model_name: str
    language: str
    topic: str
    subtopic: str
    difficulty: str
    question_type: str
    question_text: str
    options: List[str] = field(default_factory=list)
    correct_option_index: Optional[int] = None
    correct_answer_text: str = ''
    explanation: str = ''
    canonical_facts: List[str] = field(default_factory=list)
    uniqueness_tags: List[str] = field(default_factory=list)
    question_hash: str = ''
    uniqueness_hash: str = ''
    quality_score: float = 0.0
    is_valid: bool = True
    created_for_mode: str = 'classic'
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QuestionEnvelope:
    question_id: int
    candidate: QuestionCandidate
    generated_at: str
    expires_at: Optional[str] = None


@dataclass(slots=True)
class QuestionSelectionContext:
    chat_id: int
    local_game_date: str
    timezone: str = 'Europe/Berlin'
    player_id: Optional[int] = None
    topic_focus: List[str] = field(default_factory=list)
    target_difficulty: str = 'medium'
    repeat_window_days: int = 5
    same_day_repeat_block_enabled: bool = True
    question_ids_used_in_game: Set[int] = field(default_factory=set)
    uniqueness_hashes_used_in_game: Set[str] = field(default_factory=set)


@dataclass(slots=True)
class PlayerSkillSnapshot:
    player_id: int
    global_skill_score: float = 0.0
    current_band: str = 'easy'
    recent_accuracy: float = 0.0
    recent_avg_response_ms: float = 0.0
    current_streak: int = 0
    best_streak: int = 0
    daily_streak: int = 0
    games_played: int = 0
    answers_total: int = 0
    answers_correct: int = 0


@dataclass(slots=True)
class AdaptiveDifficultyDecision:
    target_band: str
    reason: str
    confidence: float = 0.0
    mix: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class QuestionUsageRecord:
    question_id: int
    chat_id: int
    shown_at: str
    player_id: Optional[int] = None
    game_id: Optional[str] = None
    round_id: Optional[str] = None
    answered_at: Optional[str] = None
    was_correct: Optional[bool] = None
    response_ms: Optional[int] = None
    local_game_date: Optional[str] = None


@dataclass(slots=True)
class PlayerScore:
    user_id: int
    username: str
    points: int = 0


@dataclass(slots=True)
class ChatSettings:
    question_timeout_sec: int = 30
    game_profile: str = 'standard'
    image_rounds_enabled: bool = True
    music_rounds_enabled: bool = True
    admin_only_control: bool = False
    chat_mode_enabled: bool = True
    host_mode_enabled: bool = False
    timezone: str = 'Europe/Berlin'
    adaptive_mode_enabled: bool = True
    repeat_window_days: int = 5
    same_day_repeat_block_enabled: bool = True
    preferred_topics: List[str] = field(default_factory=list)
    language: str = 'ru'
    allow_hard_questions: bool = True
    llm_only_mode: bool = True


@dataclass(slots=True)
class GameState:
    chat_id: int
    started_by_user_id: int
    question_limit: int
    preferred_category: str = 'Случайно'
    quiz_mode: str = 'classic'
    asked_count: int = 0
    current_question: Optional[QuizQuestion] = None
    current_question_answered: bool = False
    current_question_started_ts: float = 0.0
    scores: Dict[int, PlayerScore] = field(default_factory=dict)
    team_assignments: Dict[int, str] = field(default_factory=dict)
    used_question_keys: Set[str] = field(default_factory=set)
    hints_used_for_current_question: int = 0
    near_miss_user_ids: Set[int] = field(default_factory=set)
    wrong_reply_user_ids: Set[int] = field(default_factory=set)
    wrong_attempts_count: int = 0
    last_correct_user_id: Optional[int] = None
    correct_streak_count: int = 0
    is_active: bool = True
    mode: str = 'group_blitz'
    local_game_date: str = ''
    difficulty_policy: str = 'adaptive'
    target_difficulty_by_player: Dict[int, str] = field(default_factory=dict)
    question_ids_used_in_game: Set[int] = field(default_factory=set)
    uniqueness_hashes_used_in_game: Set[str] = field(default_factory=set)
    answer_fingerprints_used_in_game: Set[str] = field(default_factory=set)
    round_index: int = 0
    question_buffer: List[QuizQuestion] = field(default_factory=list)
    generation_inflight: bool = False
    topic_focus: List[str] = field(default_factory=list)
    adaptive_enabled: bool = True
    current_question_started_at: float = 0.0
    current_question_deadline_at: float = 0.0
