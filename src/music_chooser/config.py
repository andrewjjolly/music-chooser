from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    db_path: Path
    timezone_name: str = "Australia/Sydney"
    refresh_hours: int = 24
    request_delay_seconds: float = 2.0
    user_agent: str = "MusicChooser/0.1 (private local music discovery app)"
    auto_sync: bool = False

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def load_settings() -> Settings:
    db_path = Path(os.getenv("MUSIC_CHOOSER_DB", ".music-chooser/music-chooser.db"))
    return Settings(
        db_path=db_path,
        timezone_name=os.getenv("MUSIC_CHOOSER_TIMEZONE", "Australia/Sydney"),
        refresh_hours=max(1, int(os.getenv("MUSIC_CHOOSER_REFRESH_HOURS", "24"))),
        request_delay_seconds=max(0.0, float(os.getenv("MUSIC_CHOOSER_REQUEST_DELAY", "2"))),
        user_agent=os.getenv("MUSIC_CHOOSER_USER_AGENT", "MusicChooser/0.1 (private local music discovery app)"),
        auto_sync=os.getenv("MUSIC_CHOOSER_AUTO_SYNC", "0").lower() not in {"0", "false", "no"},
    )
