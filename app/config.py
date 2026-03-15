from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str

    openai_api_key: str
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_model: str = 'gpt-4o-mini'

    yandex_search_api_key: str = ''
    yandex_search_folder_id: str = ''

    question_timeout_sec: int = 30
    max_hints_per_question: int = 1
    default_question_count: int = 25
    recent_questions_limit: int = 100
    quiz_allow_generation: bool = False
    log_level: str = 'INFO'

    alisa_enabled: bool = True
    alisa_name: str = 'Алиса'
    alisa_name_aliases: str = 'алиса'
    alisa_only_reply_on_name: bool = True
    alisa_allow_reply_to_message: bool = True
    alisa_allow_mention: bool = True
    alisa_disable_generic_bot_triggers: bool = True

    alisa_initiative_enabled: bool = True
    alisa_max_initiatives_per_day: int = 3
    alisa_min_minutes_between_initiatives: int = 90
    alisa_min_messages_window_for_initiative: int = 12
    alisa_min_unique_users_for_initiative: int = 3
    alisa_max_recent_tension_for_initiative: float = 0.45

    alisa_reply_max_sentences: int = 3
    alisa_reply_max_chars: int = 220
    alisa_support_max_chars: int = 260

    alisa_default_sharpness: str = 'medium'
    alisa_default_humor: str = 'medium'
    alisa_roast_policy: str = 'guarded'
    alisa_ai_phrase_filter: bool = True
    alisa_self_check_enabled: bool = True

    alisa_cooldown_addressed_seconds: int = 8
    alisa_cooldown_initiative_seconds: int = 2100
    alisa_cooldown_pushback_seconds: int = 12
    alisa_followup_window_seconds: int = 45

    alisa_memory_summary_max_chars: int = 300
    alisa_history_window_size: int = 30


    polling_retry_delay_seconds: float = 3.0
    polling_max_retries: int = 0

    alisa_enabled: bool = True
    alisa_name: str = 'Алиса'
    alisa_name_aliases: str = 'алиса'
    alisa_only_reply_on_name: bool = True
    alisa_allow_reply_to_message: bool = True
    alisa_allow_mention: bool = True
    alisa_disable_generic_bot_triggers: bool = True

    alisa_initiative_enabled: bool = True
    alisa_max_initiatives_per_day: int = 3
    alisa_min_minutes_between_initiatives: int = 90
    alisa_min_messages_window_for_initiative: int = 12
    alisa_min_unique_users_for_initiative: int = 3
    alisa_max_recent_tension_for_initiative: float = 0.45

    alisa_reply_max_sentences: int = 3
    alisa_reply_max_chars: int = 220
    alisa_support_max_chars: int = 260

    alisa_default_sharpness: str = 'medium'
    alisa_default_humor: str = 'medium'
    alisa_roast_policy: str = 'guarded'
    alisa_ai_phrase_filter: bool = True
    alisa_self_check_enabled: bool = True

    alisa_cooldown_addressed_seconds: int = 8
    alisa_cooldown_initiative_seconds: int = 2100
    alisa_cooldown_pushback_seconds: int = 12
    alisa_followup_window_seconds: int = 45

    alisa_memory_summary_max_chars: int = 300
    alisa_history_window_size: int = 30


    polling_retry_delay_seconds: float = 3.0
    polling_max_retries: int = 0

    alisa_enabled: bool = True
    alisa_name: str = 'Алиса'
    alisa_name_aliases: str = 'алиса'
    alisa_only_reply_on_name: bool = True
    alisa_allow_reply_to_message: bool = True
    alisa_allow_mention: bool = True
    alisa_disable_generic_bot_triggers: bool = True

    alisa_initiative_enabled: bool = True
    alisa_max_initiatives_per_day: int = 3
    alisa_min_minutes_between_initiatives: int = 90
    alisa_min_messages_window_for_initiative: int = 12
    alisa_min_unique_users_for_initiative: int = 3
    alisa_max_recent_tension_for_initiative: float = 0.45

    alisa_reply_max_sentences: int = 3
    alisa_reply_max_chars: int = 220
    alisa_support_max_chars: int = 260

    alisa_default_sharpness: str = 'medium'
    alisa_default_humor: str = 'medium'
    alisa_roast_policy: str = 'guarded'
    alisa_ai_phrase_filter: bool = True
    alisa_self_check_enabled: bool = True

    alisa_cooldown_addressed_seconds: int = 8
    alisa_cooldown_initiative_seconds: int = 2100
    alisa_cooldown_pushback_seconds: int = 12
    alisa_followup_window_seconds: int = 45

    alisa_memory_summary_max_chars: int = 300
    alisa_history_window_size: int = 30


    polling_retry_delay_seconds: float = 3.0
    polling_max_retries: int = 0


    telegram_request_timeout_seconds: float = 60.0
    telegram_proxy_url: str = ''
    telegram_force_ipv4: bool = False

    alisa_enabled: bool = True
    alisa_name: str = 'Алиса'
    alisa_name_aliases: str = 'алиса'
    alisa_only_reply_on_name: bool = True
    alisa_allow_reply_to_message: bool = True
    alisa_allow_mention: bool = True
    alisa_disable_generic_bot_triggers: bool = True

    alisa_initiative_enabled: bool = True
    alisa_max_initiatives_per_day: int = 3
    alisa_min_minutes_between_initiatives: int = 90
    alisa_min_messages_window_for_initiative: int = 12
    alisa_min_unique_users_for_initiative: int = 3
    alisa_max_recent_tension_for_initiative: float = 0.45

    alisa_reply_max_sentences: int = 3
    alisa_reply_max_chars: int = 220
    alisa_support_max_chars: int = 260

    alisa_default_sharpness: str = 'medium'
    alisa_default_humor: str = 'medium'
    alisa_roast_policy: str = 'guarded'
    alisa_ai_phrase_filter: bool = True
    alisa_self_check_enabled: bool = True

    alisa_cooldown_addressed_seconds: int = 8
    alisa_cooldown_initiative_seconds: int = 2100
    alisa_cooldown_pushback_seconds: int = 12
    alisa_followup_window_seconds: int = 45

    alisa_memory_summary_max_chars: int = 300
    alisa_history_window_size: int = 30
    alisa_generation_timeout_seconds: float = 18.0


settings = Settings()
