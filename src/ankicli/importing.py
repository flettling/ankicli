from pathlib import Path
from typing import Any, Dict

from .collection import CollectionError

UPDATE_CONDITIONS = ("never", "if-newer", "always")


def validate_apkg_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() != ".apkg":
        raise CollectionError(
            "Anki package must have an .apkg extension: %s" % resolved
        )
    if not resolved.is_file():
        raise CollectionError("Anki package not found: %s" % resolved)
    try:
        with resolved.open("rb") as handle:
            signature = handle.read(4)
    except OSError as exc:
        raise CollectionError("Anki package is not readable: %s" % resolved) from exc
    if signature != b"PK\x03\x04":
        raise CollectionError(
            "invalid Anki package (expected a ZIP-based .apkg): %s" % resolved
        )
    return resolved


def import_options_payload(
    *,
    with_scheduling: bool,
    with_deck_configs: bool,
    update_notes: str,
    update_notetypes: str,
    merge_notetypes: bool,
) -> Dict[str, Any]:
    return {
        "with_scheduling": bool(with_scheduling),
        "with_deck_configs": bool(with_deck_configs),
        "update_notes": normalize_update_condition(update_notes),
        "update_notetypes": normalize_update_condition(update_notetypes),
        "merge_notetypes": bool(merge_notetypes),
    }


def normalize_update_condition(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized not in UPDATE_CONDITIONS:
        raise CollectionError(
            "invalid update condition %r (choose: %s)"
            % (value, ", ".join(UPDATE_CONDITIONS))
        )
    return normalized


def anki_import_options(payload: Dict[str, Any]) -> Any:
    try:
        from anki.import_export_pb2 import (
            IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS,
            IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER,
            IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER,
            ImportAnkiPackageOptions,
        )
    except ModuleNotFoundError as exc:
        raise CollectionError("the anki package is required for APKG import") from exc

    conditions = {
        "if-newer": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER,
        "always": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS,
        "never": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER,
    }
    update_notes = normalize_update_condition(str(payload["update_notes"]))
    update_notetypes = normalize_update_condition(str(payload["update_notetypes"]))
    return ImportAnkiPackageOptions(
        merge_notetypes=bool(payload["merge_notetypes"]),
        update_notes=conditions[update_notes],
        update_notetypes=conditions[update_notetypes],
        with_scheduling=bool(payload["with_scheduling"]),
        with_deck_configs=bool(payload["with_deck_configs"]),
    )


def serialize_import_response(
    response: Any, package_path: Path, options: Dict[str, Any]
) -> Dict[str, Any]:
    log = response.log
    categories = {
        name: _serialize_notes(getattr(log, name, []))
        for name in (
            "new",
            "updated",
            "duplicate",
            "conflicting",
            "first_field_match",
            "missing_notetype",
            "missing_deck",
            "empty_first_field",
        )
    }
    skipped_names = (
        "duplicate",
        "conflicting",
        "first_field_match",
        "missing_notetype",
        "missing_deck",
        "empty_first_field",
    )
    warnings = [
        "%s: %d note(s)" % (name.replace("_", " "), len(categories[name]))
        for name in skipped_names
        if categories[name]
    ]
    return {
        "package_path": str(package_path),
        "options": dict(options),
        "notes": {
            "new": len(categories["new"]),
            "updated": len(categories["updated"]),
            "unchanged": len(categories["duplicate"]),
            "skipped": sum(len(categories[name]) for name in skipped_names),
            "found": int(getattr(log, "found_notes", 0)),
        },
        "categories": categories,
        "warnings": warnings,
        "errors": [],
        "changes": _serialize_changes(getattr(response, "changes", None)),
    }


def _serialize_notes(notes: Any) -> list:
    output = []
    for note in notes:
        note_id = getattr(note, "id", None)
        if hasattr(note_id, "nid"):
            note_id = note_id.nid
        elif hasattr(note_id, "value"):
            note_id = note_id.value
        output.append({"id": int(note_id or 0)})
    return output


def _serialize_changes(changes: Any) -> Dict[str, bool]:
    names = (
        "card",
        "note",
        "deck",
        "tag",
        "notetype",
        "config",
        "deck_config",
        "mtime",
        "browser_table",
        "browser_sidebar",
        "note_text",
        "study_queues",
    )
    return {name: bool(getattr(changes, name, False)) for name in names}
