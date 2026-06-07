from pathlib import Path
from typing import Any, Callable, Optional


class BackupError(RuntimeError):
    pass


class BackupService:
    def __init__(
        self,
        base: Path,
        profile: str,
        *,
        retention: int,
        collection_factory: Optional[Callable[[Path], Any]] = None,
    ):
        self.base = base
        self.profile = profile
        self.retention = retention
        self.collection_factory = collection_factory or _open_anki_collection

    @property
    def profile_dir(self) -> Path:
        return self.base / self.profile

    @property
    def collection_path(self) -> Path:
        return self.profile_dir / "collection.anki2"

    @property
    def backup_dir(self) -> Path:
        return self.profile_dir / "backups"

    def create(self, *, force: bool = False) -> dict[str, Any]:
        collection = self.collection_factory(self.collection_path)
        try:
            created = bool(
                collection.create_backup(
                    backup_folder=str(self.backup_dir),
                    force=force,
                    wait_for_completion=True,
                )
            )
        finally:
            close = getattr(collection, "close", None)
            if callable(close):
                close()
        return {"created": created, "backup_dir": str(self.backup_dir), "retention": self.retention}

    def list(self) -> dict[str, Any]:
        backups = [
            {
                "name": path.name,
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "size": path.stat().st_size,
            }
            for path in sorted(self.backup_dir.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
            if path.is_file()
        ]
        return {"backup_dir": str(self.backup_dir), "retention": self.retention, "backups": backups}

    def prune(self) -> dict[str, Any]:
        if self.retention < 0:
            raise BackupError("backup retention must be non-negative")
        backups = [
            path
            for path in sorted(self.backup_dir.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
            if path.is_file()
        ]
        removed = []
        for path in backups[self.retention :]:
            path.unlink()
            removed.append(str(path))
        return {"backup_dir": str(self.backup_dir), "retention": self.retention, "removed": removed}


def _open_anki_collection(collection_path: Path) -> Any:
    try:
        from anki.collection import Collection
    except ModuleNotFoundError as exc:
        raise BackupError("the anki package is required for collection backups") from exc
    if not collection_path.exists():
        raise BackupError("collection not found: %s" % collection_path)
    return Collection(str(collection_path))
