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
    log_level: str = 'INFO'


settings = Settings()
