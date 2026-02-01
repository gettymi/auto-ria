from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database settings
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # Scraper settings
    RUN_TIME: str = "12:00"
    DUMP_TIME: str = "12:00"
    DUMP_INTERVAL_HOURS: int = 24
    MAX_CONCURRENT_REQUESTS: int = 3
    REQUEST_DELAY: float = 1.5
    MAX_PAGES: int = 10

    # AutoRia settings
    BASE_URL: str = "https://auto.ria.com"
    SEARCH_URL: str = "https://auto.ria.com/uk/car/used/"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
