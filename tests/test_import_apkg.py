import copy
import json
import time
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ankicli.cli as cli
from ankicli.cli import app
from ankicli.collection import AnkiCollectionService
from ankicli.importing import import_options_payload


def _profile(base: Path, write_profile_db) -> None:
    write_profile_db(
        base,
        {"agent": {"syncKey": "token", "syncUser": "agent@example.com"}},
        {"last_loaded_profile_name": "agent"},
    )
    (base / "agent").mkdir()
    (base / "agent" / "collection.anki2").touch()


def _export_basic_apkg(root: Path, *, front: str = "Question", back: str = "Answer"):
    from anki.collection import Collection
    from anki.generic_pb2 import Empty
    from anki.import_export_pb2 import ExportAnkiPackageOptions, ExportLimit

    source_path = root / "source.anki2"
    package_path = root / "deck.apkg"
    collection = Collection(str(source_path))
    model = collection.models.by_name("Basic")
    note = collection.new_note(model)
    note["Front"] = front
    note["Back"] = back
    collection.add_note(note, collection.decks.id("Imported"))
    collection.export_anki_package(
        out_path=str(package_path),
        options=ExportAnkiPackageOptions(
            with_scheduling=True,
            with_deck_configs=True,
            with_media=False,
            legacy=False,
        ),
        limit=ExportLimit(whole_collection=Empty()),
    )
    note_id = int(note.id)
    collection.close()
    return source_path, package_path, note_id


def _safe_options(**overrides):
    values = {
        "with_scheduling": False,
        "with_deck_configs": False,
        "update_notes": "never",
        "update_notetypes": "never",
        "merge_notetypes": False,
    }
    values.update(overrides)
    return import_options_payload(**values)


def test_service_passes_explicit_native_import_options(tmp_path):
    captured = {}

    class FakeCollection:
        def import_anki_package(self, request):
            captured["request"] = request
            log = types.SimpleNamespace(
                new=[types.SimpleNamespace(id=types.SimpleNamespace(nid=10))],
                updated=[],
                duplicate=[types.SimpleNamespace(id=types.SimpleNamespace(nid=20))],
                conflicting=[],
                first_field_match=[],
                missing_notetype=[],
                missing_deck=[],
                empty_first_field=[],
                found_notes=2,
            )
            return types.SimpleNamespace(
                log=log, changes=types.SimpleNamespace(note=True)
            )

    package = tmp_path / "deck.apkg"
    package.write_bytes(b"PK\x03\x04")
    options = _safe_options(update_notes="always", merge_notetypes=True)
    result = AnkiCollectionService(FakeCollection()).import_apkg(package, options)

    native = captured["request"].options
    assert native.with_scheduling is False
    assert native.with_deck_configs is False
    assert native.update_notes == 1
    assert native.update_notetypes == 2
    assert native.merge_notetypes is True
    assert result["notes"] == {
        "new": 1,
        "updated": 0,
        "unchanged": 1,
        "skipped": 1,
        "found": 2,
    }
    assert result["warnings"] == ["duplicate: 1 note(s)"]


def test_cli_rejects_invalid_apkg_before_backup(
    tmp_path, write_profile_db, monkeypatch
):
    _profile(tmp_path, write_profile_db)
    package = tmp_path / "broken.apkg"
    package.write_text("not a zip")
    monkeypatch.setattr(
        cli, "_backup_service", lambda: pytest.fail("backup must not run")
    )

    result = CliRunner().invoke(
        app,
        [
            "--base",
            str(tmp_path),
            "--profile",
            "agent",
            "--json",
            "import",
            "apkg",
            str(package),
            "--write",
        ],
    )

    assert result.exit_code == 2
    assert "invalid Anki package" in result.output


def test_cli_stops_when_backup_fails(tmp_path, write_profile_db, monkeypatch):
    _profile(tmp_path, write_profile_db)
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"PK\x03\x04minimal")
    imported = []

    class FailingBackup:
        def create(self, *, force=False):
            from ankicli.backups import BackupError

            raise BackupError("backup failed deliberately")

    class FakeService:
        def import_apkg(self, *_args):
            imported.append(True)

        def close(self):
            pass

    monkeypatch.setattr(cli, "_backup_service", lambda: FailingBackup())
    monkeypatch.setattr(cli.AnkiCollectionService, "open", lambda _path: FakeService())
    result = CliRunner().invoke(
        app,
        [
            "--base",
            str(tmp_path),
            "--profile",
            "agent",
            "--json",
            "import",
            "apkg",
            str(package),
            "--write",
        ],
    )

    assert result.exit_code == 2
    assert "backup failed deliberately" in result.output
    assert imported == []


def test_cli_import_requires_write_in_isolated_base(
    tmp_path, write_profile_db, monkeypatch
):
    _profile(tmp_path, write_profile_db)
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"PK\x03\x04minimal")
    monkeypatch.setattr(
        cli, "_backup_service", lambda: pytest.fail("backup must not run")
    )

    result = CliRunner().invoke(
        app,
        [
            "--base",
            str(tmp_path),
            "--profile",
            "agent",
            "--json",
            "import",
            "apkg",
            str(package),
        ],
    )

    assert result.exit_code == 2
    assert "requires --write" in result.output


def test_cli_uses_running_bridge_instead_of_opening_collection(
    tmp_path, write_profile_db, monkeypatch
):
    _profile(tmp_path, write_profile_db)
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"PK\x03\x04minimal")
    payloads = []

    class FakeBridge:
        def health(self):
            return {"ok": True, "profile": "agent"}

        def import_apkg(self, payload):
            payloads.append(payload)
            return {
                "backup": {"verified": True, "path": "/backups/live.colpkg"},
                "result": {"notes": {"new": 1}, "warnings": [], "errors": []},
            }

    monkeypatch.setattr(cli.BridgeClient, "discover", lambda _base: FakeBridge())
    monkeypatch.setattr(
        cli.AnkiCollectionService,
        "open",
        lambda _path: pytest.fail("live collection must not be opened directly"),
    )
    result = CliRunner().invoke(
        app,
        [
            "--base",
            str(tmp_path),
            "--profile",
            "agent",
            "--json",
            "import",
            "apkg",
            str(package),
            "--write",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["transport"] == "live_bridge"
    assert data["backup"]["path"] == "/backups/live.colpkg"
    assert payloads[0]["options"] == _safe_options()


def test_cli_refuses_direct_open_when_bridge_state_is_unreachable(
    tmp_path, write_profile_db, monkeypatch
):
    from ankicli.bridge import BridgeError

    _profile(tmp_path, write_profile_db)
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"PK\x03\x04minimal")

    class UnreachableBridge:
        def health(self):
            raise BridgeError("Anki bridge is unavailable")

    monkeypatch.setattr(cli.BridgeClient, "discover", lambda _base: UnreachableBridge())
    monkeypatch.setattr(
        cli.AnkiCollectionService,
        "open",
        lambda _path: pytest.fail("collection must remain unopened"),
    )
    result = CliRunner().invoke(
        app,
        [
            "--base",
            str(tmp_path),
            "--profile",
            "agent",
            "--json",
            "import",
            "apkg",
            str(package),
            "--write",
        ],
    )

    assert result.exit_code == 2
    assert "refusing to open the collection directly" in result.output


def test_isolated_import_new_duplicate_update_and_preserves_scheduling(tmp_path):
    from anki.collection import Collection

    source_path, package_path, source_note_id = _export_basic_apkg(tmp_path)
    target_path = tmp_path / "target.anki2"
    target = Collection(str(target_path))
    service = AnkiCollectionService(target)

    first = service.import_apkg(package_path, _safe_options())
    assert first["notes"]["new"] == 1
    duplicate = service.import_apkg(package_path, _safe_options())
    assert duplicate["notes"]["new"] == 0
    assert duplicate["notes"]["unchanged"] == 1

    target_note_id = int(target.find_notes("deck:Imported")[0])
    card_id = int(target.find_cards("nid:%d" % target_note_id)[0])
    card = target.get_card(card_id)
    card.queue = 2
    card.type = 2
    card.due = 54321
    card.ivl = 23
    target.update_card(card)
    schedule_before = (card.queue, card.type, card.due, card.ivl)

    source = Collection(str(source_path))
    source_note = source.get_note(source_note_id)
    # Anki's native package updater uses second-resolution modification times.
    time.sleep(1.05)
    source_note["Back"] = "Updated answer"
    source.update_note(source_note)
    from anki.generic_pb2 import Empty
    from anki.import_export_pb2 import ExportAnkiPackageOptions, ExportLimit

    package_path.unlink()
    source.export_anki_package(
        out_path=str(package_path),
        options=ExportAnkiPackageOptions(
            with_scheduling=True,
            with_deck_configs=True,
            with_media=False,
            legacy=False,
        ),
        limit=ExportLimit(whole_collection=Empty()),
    )
    source.close()

    updated = service.import_apkg(
        package_path,
        _safe_options(update_notes="always"),
    )
    assert updated["notes"]["updated"] == 1
    assert target.get_note(target_note_id)["Back"] == "Updated answer"
    card_after = target.get_card(card_id)
    assert (
        card_after.queue,
        card_after.type,
        card_after.due,
        card_after.ivl,
    ) == schedule_before
    target.close()


def test_import_keeps_native_image_occlusion_metadata_when_notetype_updates_disabled(
    tmp_path,
):
    from anki.collection import Collection
    from anki.generic_pb2 import Empty
    from anki.import_export_pb2 import ExportAnkiPackageOptions, ExportLimit

    source_path = tmp_path / "io-source.anki2"
    package_path = tmp_path / "io.apkg"
    source = Collection(str(source_path))
    model = source.models.by_name("Image Occlusion")
    note = source.new_note(model)
    note["Occlusion"] = "{{c1::mask}}"
    note["Image"] = '<img src="io-test.png">'
    source.add_note(note, source.decks.id("IO"))
    source.export_anki_package(
        out_path=str(package_path),
        options=ExportAnkiPackageOptions(with_media=False, legacy=False),
        limit=ExportLimit(whole_collection=Empty()),
    )
    source.close()

    target = Collection(str(tmp_path / "io-target.anki2"))
    before = copy.deepcopy(target.models.by_name("Image Occlusion"))
    result = AnkiCollectionService(target).import_apkg(package_path, _safe_options())
    after = target.models.by_name("Image Occlusion")

    assert result["notes"]["new"] == 1
    assert after["originalStockKind"] == before["originalStockKind"] == 6
    assert [field["preventDeletion"] for field in after["flds"]] == [
        field["preventDeletion"] for field in before["flds"]
    ]
    assert after == before
    target.close()
