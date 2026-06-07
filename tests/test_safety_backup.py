import pytest

from ankicli.safety import MutatingCommandContext, SafetyError, run_guarded_mutation


class FakeBackupService:
    def __init__(self):
        self.calls = 0

    def create(self, *, force: bool = False):
        self.calls += 1
        return {"path": "/tmp/backups/backup.colpkg", "forced": force}


def test_mutation_requires_write_flag_on_desktop_anki():
    ctx = MutatingCommandContext(profile="User 1", is_desktop_base=True, write=False)

    with pytest.raises(SafetyError, match="requires --write"):
        ctx.validate()


def test_no_backup_is_forbidden_on_desktop_anki_even_with_write():
    ctx = MutatingCommandContext(
        profile="User 1",
        is_desktop_base=True,
        write=True,
        no_backup=True,
    )

    with pytest.raises(SafetyError, match="--no-backup is forbidden"):
        ctx.validate()


def test_guarded_mutation_creates_backup_before_change():
    backup = FakeBackupService()
    events: list[str] = []
    ctx = MutatingCommandContext(profile="agent", is_desktop_base=False, write=True)

    result = run_guarded_mutation(
        ctx,
        backup.create,
        lambda: events.append("mutated") or {"changed_ids": [1, 2]},
    )

    assert backup.calls == 1
    assert events == ["mutated"]
    assert result["backup"]["path"] == "/tmp/backups/backup.colpkg"
    assert result["result"]["changed_ids"] == [1, 2]
