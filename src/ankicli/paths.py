import os
import sys
from pathlib import Path
from typing import Optional


def default_anki_base() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Anki2"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "Anki2"
    return Path.home() / ".local" / "share" / "Anki2"


def configured_base(cli_base: Optional[Path]) -> Path:
    if cli_base:
        return cli_base.expanduser()
    env_base = os.environ.get("ANKI_BASE")
    if env_base:
        return Path(env_base).expanduser()
    return default_anki_base()


def is_default_desktop_base(base: Path) -> bool:
    try:
        return base.expanduser().resolve() == default_anki_base().expanduser().resolve()
    except FileNotFoundError:
        return base.expanduser() == default_anki_base().expanduser()
