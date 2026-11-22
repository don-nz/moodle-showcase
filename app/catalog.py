"""The quizzes and simulators this tool serves, from content/manifest.json."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    topic: str
    graded: bool  # False for simulators: no gradebook column, no score script


def load_catalog(content_dir: Path) -> dict[str, Item]:
    """Items in manifest order, keeping only those whose built page exists."""
    manifest = json.loads((content_dir.parent / "manifest.json").read_text(encoding="utf-8"))
    items = {}
    for q in manifest["quizzes"]:
        if (content_dir / f"{q['id']}.html").exists():
            items[q["id"]] = Item(q["id"], q["title"], q.get("topic", ""), q.get("graded", True))
    return items
