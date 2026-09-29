from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _static_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parents[2] / "static",
        here.parents[3] / "web" / "build",
    ]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    database_url: str = "sqlite:////data/dwellings.db"
    public_url: str = "https://dwellings.rtech.cloud"
    webauthn_rp_id: str = "dwellings.rtech.cloud"
    webauthn_rp_name: str = "Dwellings"
    secret_key: str = "dev-only-change-me"
    token_pepper: str = "dev-only-change-me"
    admin_email: str | None = None
    admin_bootstrap_token: str | None = None
    port: int = 8080
    static_dir: Path | None = None
    photo_max_per_listing: int = 40
    photo_fetch_timeout: int = 20
    trusted_proxies: str = "127.0.0.1"
    cookie_name: str = "__Host-dwl"
    csrf_cookie_name: str = "__Host-dwl-csrf"

    resolved_static_dir: Path | None = Field(default=None, exclude=True)

    def model_post_init(self, __context: object) -> None:
        chosen = self.static_dir
        if chosen is None:
            for candidate in _static_candidates():
                if candidate.is_dir():
                    chosen = candidate
                    break
        elif not chosen.is_dir():
            chosen = None
        object.__setattr__(self, "resolved_static_dir", chosen)

    @property
    def cookie_secure(self) -> bool:
        return self.public_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
