from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ctm:ctm@localhost:5432/clinical_trials"
    api_key: str = "local-dev-api-key"
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    ctgov_rate_limit: float = 3.0  # requests per second
    ctgov_max_retries: int = 2
    ctgov_retry_backoff_seconds: float = 1.0
    ingest_rate_limit_requests: int = 20
    ingest_rate_limit_window_seconds: int = 60
    search_ingest_rate_limit_requests: int = 10
    search_ingest_rate_limit_window_seconds: int = 60
    reextract_rate_limit_requests: int = 20
    reextract_rate_limit_window_seconds: int = 60
    coding_fuzzy_similarity_threshold: float = 0.55
    pipeline_version: str = "0.2.0"
    spacy_model: str = "en_core_sci_lg"
    abbreviation_dict_path: str = "data/dictionaries/onc_abbreviations.jsonl"
    patterns_dir: str = "data/patterns"

    model_config = {"env_prefix": "CTM_"}


settings = Settings()
