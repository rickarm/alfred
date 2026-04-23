"""Knowledge base writer — appends entries to ~/kb/journal/YYYY-MM-DD.md."""

from datetime import date
from pathlib import Path

_DEFAULT_DIR = Path.home() / "kb" / "journal"


def append_entry(text: str, tag: str = "note", kb_dir: Path = _DEFAULT_DIR) -> Path:
    """Append a tagged markdown entry to today's journal file. Returns the path."""
    kb_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = kb_dir / f"{today}.md"
    sep = "\n\n" if path.exists() and path.stat().st_size > 0 else ""
    with path.open("a") as f:
        f.write(f"{sep}## [{tag}] {today}\n\n{text.strip()}\n")
    return path
