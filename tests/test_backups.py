from pathlib import Path

import pytest

from ankicli.backups import BackupError, BackupService


class FakeCollection:
    def __init__(self):
        self.calls = []

    def create_backup(self, *, backup_folder: str, force: bool, wait_for_completion: bool) -> bool:
        self.calls.append(
            {
                "backup_folder": backup_folder,
                "force": force,
                "wait_for_completion": wait_for_completion,
            }
        )
        Path(backup_folder).mkdir(parents=True, exist_ok=True)
        (Path(backup_folder) / "backup-1.colpkg").write_text("backup")
        return True


def test_backup_service_uses_anki_collection_backup_api(tmp_path):
    collection = FakeCollection()
    service = BackupService(tmp_path, "agent", retention=50, collection_factory=lambda _: collection)

    result = service.create(force=True)

    assert collection.calls == [
        {
            "backup_folder": str(tmp_path / "agent" / "backups"),
            "force": True,
            "wait_for_completion": True,
        }
    ]
    assert result["created"] is True
    assert result["verified"] is True
    assert result["path"] == str(tmp_path / "agent" / "backups" / "backup-1.colpkg")
    assert result["backup_dir"] == str(tmp_path / "agent" / "backups")


def test_backup_prune_keeps_newest_files_within_retention(tmp_path):
    backup_dir = tmp_path / "agent" / "backups"
    backup_dir.mkdir(parents=True)
    for index in range(4):
        path = backup_dir / ("backup-%s.colpkg" % index)
        path.write_text(str(index))
        path.touch()
    service = BackupService(tmp_path, "agent", retention=2, collection_factory=lambda _: FakeCollection())

    result = service.prune()

    assert len(result["removed"]) == 2
    assert len(service.list()["backups"]) == 2


def test_backup_service_rejects_unverifiable_backup(tmp_path):
    class NoBackupCollection:
        def create_backup(self, **_kwargs):
            return False

    service = BackupService(
        tmp_path,
        "agent",
        retention=50,
        collection_factory=lambda _: NoBackupCollection(),
    )

    with pytest.raises(BackupError, match="could not be verified"):
        service.create(force=True)


def test_backup_service_wraps_native_backup_failure(tmp_path):
    class FailingCollection:
        def create_backup(self, **_kwargs):
            raise OSError("native failure")

    service = BackupService(
        tmp_path,
        "agent",
        retention=50,
        collection_factory=lambda _: FailingCollection(),
    )

    with pytest.raises(BackupError, match="Anki backup failed: native failure"):
        service.create(force=True)
