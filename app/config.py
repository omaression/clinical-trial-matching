from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ctm:ctm@localhost:5432/clinical_trials"
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    ctgov_rate_limit: float = 3.0  # requests per second
    pipeline_version: str = "0.1.0"
    spacy_model: str = "en_core_sci_lg"
    abbreviation_dict_path: str = "data/dictionaries/onc_abbreviations.jsonl"
    patterns_dir: str = "data/patterns"

    model_config = {"env_prefix": "CTM_"}


settings = Settings()
