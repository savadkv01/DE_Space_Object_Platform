import os
from dataclasses import dataclass


@dataclass
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    db: str


@dataclass
class NasaConfig:
    api_key: str
    base_url: str = "https://api.nasa.gov"


@dataclass
class CelesTrakConfig:
    base_url: str = "https://celestrak.org"


class Config:
    """
    Central config facade for services.
    Reads from environment variables.
    """

    @property
    def postgres(self) -> PostgresConfig:
        return PostgresConfig(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "space_user"),
            password=os.getenv("POSTGRES_PASSWORD", "space_password"),
            db=os.getenv("POSTGRES_DB", "space_warehouse"),
        )

    @property
    def nasa(self) -> NasaConfig:
        api_key = os.getenv("NASA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "NASA_API_KEY is not set. Please configure it in your .env file."
            )
        return NasaConfig(api_key=api_key)

    @property
    def celestrak(self) -> CelesTrakConfig:
        base_url = os.getenv("CELESTRAK_BASE_URL", "https://celestrak.org")
        return CelesTrakConfig(base_url=base_url)


config = Config()