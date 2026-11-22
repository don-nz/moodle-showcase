"""Settings, read from environment variables (see deploy/quiz-tool.env.example)."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    base_url: str                     # public https URL of this tool, no trailing slash
    data_dir: Path                    # database, private key, session secret (never in git)
    content_dir: Path                 # built quiz pages, one <quiz id>.html each
    allowed_issuers: tuple[str, ...]  # platforms allowed to register, e.g. https://moodle.test
    tool_name: str


def load_settings() -> Settings:
    issuers = os.environ.get("TOOL_ALLOWED_ISSUERS", "")
    return Settings(
        base_url=os.environ.get("TOOL_BASE_URL", "https://tools.test").rstrip("/"),
        data_dir=Path(os.environ.get("TOOL_DATA_DIR", ROOT / "instance")),
        content_dir=Path(os.environ.get("TOOL_CONTENT_DIR", ROOT / "content" / "built")),
        allowed_issuers=tuple(i.strip().rstrip("/") for i in issuers.split(",") if i.strip()),
        tool_name=os.environ.get("TOOL_NAME", "Quiz Showcase"),
    )
