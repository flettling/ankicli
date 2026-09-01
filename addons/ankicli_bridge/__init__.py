"""Authenticated localhost bridge for operating on Anki's open collection."""

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aqt import gui_hooks, mw

_server = None
_server_thread = None
_state_path = None
_token = None


def _profile_name():
    name = getattr(mw.pm, "name", "")
    return name() if callable(name) else str(name or "")


def _base_path():
    base = getattr(mw.pm, "base", "")
    base = base() if callable(base) else base
    return Path(str(base))


def _backup_dir():
    method = getattr(mw.pm, "backupFolder", None)
    if callable(method):
        return Path(method())
    profile_folder = getattr(mw.pm, "profileFolder", None)
    if callable(profile_folder):
        return Path(profile_folder()) / "backups"
    raise RuntimeError("Anki profile backup folder is unavailable")


def _backup_files(folder):
    if not folder.is_dir():
        return []
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".colpkg"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _verified_backup():
    folder = _backup_dir()
    before = {
        path.resolve(): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in _backup_files(folder)
    }
    created = bool(
        mw.col.create_backup(
            backup_folder=str(folder),
            force=True,
            wait_for_completion=True,
        )
    )
    backups = _backup_files(folder)
    latest = backups[0] if backups else None
    if latest is None or latest.stat().st_size <= 0:
        raise RuntimeError("Anki backup could not be verified in %s" % folder)
    latest_signature = (latest.stat().st_mtime_ns, latest.stat().st_size)
    if created and before.get(latest.resolve()) == latest_signature:
        raise RuntimeError("Anki reported a backup but no new backup file was found")
    return {
        "created": created,
        "verified": True,
        "path": str(latest),
        "backup_dir": str(folder),
        "retention": int((mw.pm.profile or {}).get("numBackups") or 50),
    }


def _validate_package(path_text):
    path = Path(path_text).expanduser().resolve()
    if path.suffix.lower() != ".apkg" or not path.is_file():
        raise RuntimeError("Anki package not found: %s" % path)
    try:
        with path.open("rb") as handle:
            signature = handle.read(4)
    except OSError as exc:
        raise RuntimeError("Anki package is not readable: %s" % path) from exc
    if signature != b"PK\x03\x04":
        raise RuntimeError(
            "invalid Anki package (expected a ZIP-based .apkg): %s" % path
        )
    return path


def _anki_options(payload):
    from anki.import_export_pb2 import (
        IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS,
        IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER,
        IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER,
        ImportAnkiPackageOptions,
    )

    conditions = {
        "if-newer": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER,
        "always": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS,
        "never": IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER,
    }
    try:
        update_notes = conditions[payload["update_notes"]]
        update_notetypes = conditions[payload["update_notetypes"]]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("invalid APKG update condition") from exc
    return ImportAnkiPackageOptions(
        merge_notetypes=bool(payload.get("merge_notetypes", False)),
        update_notes=update_notes,
        update_notetypes=update_notetypes,
        with_scheduling=bool(payload.get("with_scheduling", False)),
        with_deck_configs=bool(payload.get("with_deck_configs", False)),
    )


def _note_id(note):
    value = getattr(note, "id", None)
    if hasattr(value, "nid"):
        value = value.nid
    elif hasattr(value, "value"):
        value = value.value
    return int(value or 0)


def _serialize_import(response, package_path, options):
    log = response.log
    names = (
        "new",
        "updated",
        "duplicate",
        "conflicting",
        "first_field_match",
        "missing_notetype",
        "missing_deck",
        "empty_first_field",
    )
    categories = {
        name: [{"id": _note_id(note)} for note in getattr(log, name, [])]
        for name in names
    }
    skipped_names = names[2:]
    change_names = (
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
        "warnings": [
            "%s: %d note(s)" % (name.replace("_", " "), len(categories[name]))
            for name in skipped_names
            if categories[name]
        ],
        "errors": [],
        "changes": {
            name: bool(getattr(response.changes, name, False)) for name in change_names
        },
    }


def _import_on_main(payload):
    if not payload.get("write"):
        raise RuntimeError("APKG import requires write confirmation")
    requested_profile = str(payload.get("profile", ""))
    if requested_profile != _profile_name():
        raise RuntimeError(
            "open Anki profile is %r, requested profile is %r"
            % (_profile_name(), requested_profile)
        )
    package_path = _validate_package(payload.get("package_path", ""))
    options_payload = payload.get("options") or {}
    options = _anki_options(options_payload)
    backup = _verified_backup()
    from anki.import_export_pb2 import ImportAnkiPackageRequest

    try:
        response = mw.col.import_anki_package(
            ImportAnkiPackageRequest(
                package_path=str(package_path),
                options=options,
            )
        )
    except Exception as exc:
        raise RuntimeError("APKG import failed: %s" % exc) from exc
    mw.reset()
    return {
        "backup": backup,
        "result": _serialize_import(response, package_path, options_payload),
    }


def _run_on_main(operation, timeout=900):
    done = threading.Event()
    output = {}

    def invoke():
        try:
            output["result"] = operation()
        except Exception as exc:
            output["error"] = str(exc)
        finally:
            done.set()

    mw.taskman.run_on_main(invoke)
    if not done.wait(timeout):
        raise RuntimeError("timed out waiting for Anki main thread")
    if "error" in output:
        raise RuntimeError(output["error"])
    return output["result"]


class _Handler(BaseHTTPRequestHandler):
    server_version = "ankicli-bridge/1"

    def do_GET(self):
        if not self._authorized():
            return
        if self.path != "/v1/health":
            self._send(404, {"error": "not found"})
            return
        self._send(200, {"ok": True, "protocol": 1, "profile": _profile_name()})

    def do_POST(self):
        if not self._authorized():
            return
        if self.path != "/v1/import-apkg":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1024 * 1024:
                raise RuntimeError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = _run_on_main(lambda: _import_on_main(payload))
            self._send(200, result)
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def _authorized(self):
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer %s" % _token
        ):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _send(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _write_state(port):
    global _state_path
    _state_path = _base_path() / "ankicli-bridge.json"
    temporary = _state_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "protocol": 1,
                "port": port,
                "token": _token,
                "pid": os.getpid(),
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(str(temporary), 0o600)
    except OSError:
        pass
    temporary.replace(_state_path)


def _start_bridge():
    global _server, _server_thread, _token
    _stop_bridge()
    if mw.col is None:
        return
    _token = secrets.token_urlsafe(32)
    _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _server.daemon_threads = True
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    _write_state(_server.server_address[1])


def _stop_bridge():
    global _server, _server_thread, _state_path
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
    if _server_thread is not None:
        _server_thread.join(timeout=2)
        _server_thread = None
    if _state_path is not None:
        try:
            _state_path.unlink()
        except OSError:
            pass
        _state_path = None


gui_hooks.profile_did_open.append(_start_bridge)
gui_hooks.profile_will_close.append(_stop_bridge)
