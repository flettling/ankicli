import contextlib
import io
import os
from pathlib import Path
from typing import Callable, Iterator, List, Optional

import typer

from .backups import BackupError, BackupService
from .bridge import BridgeClient, BridgeError
from .collection import AnkiCollectionService, CollectionError
from .importing import import_options_payload, validate_apkg_path
from .jsonio import dumps
from .notetypes import export_notetype_bundle, load_notetype_bundle, summarize_notetype_changes
from .paths import configured_base, is_default_desktop_base
from .profiles import ProfileResolver, ProfileStore, ResolvedProfile
from .safety import MutatingCommandContext, SafetyError, run_guarded_mutation

app = typer.Typer(help="Command line access to Anki collections.")
profile_app = typer.Typer(help="Inspect and choose Anki profiles.")
default_app = typer.Typer(help="Inspect and set the default profile.")
auth_app = typer.Typer(help="Manage AnkiWeb authentication.")
backup_app = typer.Typer(help="Create, list, and prune Anki backups.")
sync_app = typer.Typer(help="Synchronize with AnkiWeb.")
deck_app = typer.Typer(help="Inspect and mutate decks.")
filtered_app = typer.Typer(help="Inspect and mutate filtered decks.")
note_app = typer.Typer(help="Inspect and mutate notes.")
card_app = typer.Typer(help="Inspect and mutate cards.")
notetype_app = typer.Typer(help="Inspect and mutate notetypes.")
import_app = typer.Typer(help="Import Anki packages.")
app.add_typer(profile_app, name="profile")
profile_app.add_typer(default_app, name="default")
app.add_typer(auth_app, name="auth")
app.add_typer(backup_app, name="backup")
app.add_typer(sync_app, name="sync")
app.add_typer(deck_app, name="deck")
app.add_typer(filtered_app, name="filtered")
app.add_typer(note_app, name="note")
app.add_typer(card_app, name="card")
app.add_typer(notetype_app, name="notetype")
app.add_typer(import_app, name="import")


class CliState:
    def __init__(self) -> None:
        self.base: Optional[Path] = None
        self.json: bool = False
        self.profile: Optional[str] = None


state = CliState()


@app.callback()
def main(
    base: Optional[Path] = typer.Option(None, "--base", help="Anki base directory."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Anki profile name."),
    json_output: bool = typer.Option(False, "--json", help="Emit compact JSON output."),
) -> None:
    state.base = configured_base(base)
    state.profile = profile or os.environ.get("ANKICLI_PROFILE")
    state.json = json_output


@profile_app.command("list")
def profile_list() -> None:
    store = _store()
    profiles = [
        {
            "name": profile.name,
            "sync_authenticated": profile.sync_authenticated,
            "sync_user": profile.sync_user,
        }
        for profile in store.list_profiles()
    ]
    _emit({"profiles": profiles})


@default_app.command("get")
def profile_default_get() -> None:
    resolver = ProfileResolver(_store())
    result = resolver.resolve_result(explicit=state.profile)
    if not result.ok or not result.profile:
        _fail(result.error, result.candidates or [])
    _emit({"name": result.profile.name, "source": result.profile.source})


@default_app.command("set")
def profile_default_set(name: str) -> None:
    # ankicli keeps profile selection explicit for now; Anki's own last-loaded
    # setting is not rewritten by this metadata command.
    store = _store()
    store.get_profile(name)
    _emit({"name": name, "source": "explicit", "note": "use --profile or ANKICLI_PROFILE for commands"})


@auth_app.command("status")
def auth_status() -> None:
    resolved = _resolve_profile()
    profile = _store().get_profile(resolved.name)
    _emit(
        {
            "profile": profile.name,
            "sync_authenticated": profile.sync_authenticated,
            "sync_user": profile.sync_user,
        }
    )


@auth_app.command("logout")
def auth_logout() -> None:
    resolved = _resolve_profile()
    _store().clear_sync_auth(resolved.name)
    _emit({"profile": resolved.name, "sync_authenticated": False})


@auth_app.command("login")
def auth_login(
    username: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    resolved = _resolve_auth_login_profile()
    sync_key = _sync_login_with_anki(resolved.name, username, password)
    _store().set_sync_auth(resolved.name, sync_key=sync_key, sync_user=username)
    _emit({"profile": resolved.name, "sync_authenticated": True, "sync_user": username})


@backup_app.command("create")
def backup_create(force: bool = typer.Option(False, "--force")) -> None:
    service = _backup_service()
    try:
        with _silence_anki_backend_stdout():
            result = service.create(force=force)
        _emit(result)
    except BackupError as exc:
        _fail(str(exc), [])


@backup_app.command("list")
def backup_list() -> None:
    _emit(_backup_service().list())


@backup_app.command("prune")
def backup_prune() -> None:
    try:
        _emit(_backup_service().prune())
    except BackupError as exc:
        _fail(str(exc), [])


@sync_app.command("status")
def sync_status() -> None:
    _emit(_sync_status())


@sync_app.command("run")
def sync_run() -> None:
    _emit(_sync_run())


@sync_app.command("full-upload")
def sync_full_upload(confirm_full_sync: bool = typer.Option(False, "--confirm-full-sync")) -> None:
    if not confirm_full_sync:
        _fail("full upload requires --confirm-full-sync", [])
    _emit(_sync_full(upload=True))


@sync_app.command("full-download")
def sync_full_download(confirm_full_sync: bool = typer.Option(False, "--confirm-full-sync")) -> None:
    if not confirm_full_sync:
        _fail("full download requires --confirm-full-sync", [])
    _emit(_sync_full(upload=False))


@deck_app.command("list")
def deck_list(counts: bool = typer.Option(False, "--counts", help="Emit Anki overview counts as a deck tree.")) -> None:
    if counts:
        _read_collection(lambda service: service.deck_due_tree())
    else:
        _read_collection(lambda service: service.list_decks())


@deck_app.command("info")
def deck_info(name: str) -> None:
    _read_collection(lambda service: service.deck_info(name))


@deck_app.command("create")
def deck_create(name: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.create_deck(name))


@deck_app.command("rename")
def deck_rename(old: str, new: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.rename_deck(old, new))


@deck_app.command("delete")
def deck_delete(name: str, write: bool = typer.Option(False, "--write"), confirm_delete: bool = typer.Option(False, "--confirm-delete")) -> None:
    if not confirm_delete:
        _fail("deck delete requires --confirm-delete", [])
    _mutate(write, lambda service: service.delete_deck(name))


@filtered_app.command("list")
def filtered_list() -> None:
    _read_collection(lambda service: service.list_filtered_decks())


@filtered_app.command("get")
def filtered_get(name: str) -> None:
    _read_collection(lambda service: service.get_filtered_deck(name))


@filtered_app.command("orders")
def filtered_orders() -> None:
    _read_collection(lambda service: service.filtered_deck_order_labels())


@filtered_app.command("create")
def filtered_create(
    name: str,
    search: str = typer.Option(..., "--search", help="Anki search query for the filtered deck."),
    limit: int = typer.Option(100, "--limit", min=0),
    order: str = typer.Option("OLDEST_REVIEWED_FIRST", "--order"),
    reschedule: bool = typer.Option(True, "--reschedule/--no-reschedule"),
    allow_empty: bool = typer.Option(False, "--allow-empty"),
    write: bool = typer.Option(False, "--write"),
) -> None:
    _mutate(
        write,
        lambda service: service.create_or_update_filtered_deck(
            name,
            search=search,
            limit=limit,
            order=order,
            reschedule=reschedule,
            allow_empty=allow_empty,
            create=True,
        ),
    )


@filtered_app.command("update")
def filtered_update(
    name: str,
    search: str = typer.Option(..., "--search", help="Anki search query for the filtered deck."),
    limit: int = typer.Option(100, "--limit", min=0),
    order: str = typer.Option("OLDEST_REVIEWED_FIRST", "--order"),
    reschedule: bool = typer.Option(True, "--reschedule/--no-reschedule"),
    allow_empty: bool = typer.Option(False, "--allow-empty"),
    write: bool = typer.Option(False, "--write"),
) -> None:
    _mutate(
        write,
        lambda service: service.create_or_update_filtered_deck(
            name,
            search=search,
            limit=limit,
            order=order,
            reschedule=reschedule,
            allow_empty=allow_empty,
            create=False,
        ),
    )


@filtered_app.command("rebuild")
def filtered_rebuild(name: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.rebuild_filtered_deck(name))


@filtered_app.command("empty")
def filtered_empty(name: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.empty_filtered_deck(name))


@filtered_app.command("delete")
def filtered_delete(name: str, write: bool = typer.Option(False, "--write"), confirm_delete: bool = typer.Option(False, "--confirm-delete")) -> None:
    if not confirm_delete:
        _fail("filtered delete requires --confirm-delete", [])
    _mutate(write, lambda service: service.delete_filtered_deck(name))


@note_app.command("search")
def note_search(query: str, count: bool = typer.Option(False, "--count", help="Emit only the number of matching notes.")) -> None:
    if count:
        _read_collection(lambda service: service.count_notes(query))
    else:
        _read_collection(lambda service: service.search_notes(query))


@note_app.command("get")
def note_get(note_id: int) -> None:
    _read_collection(lambda service: service.get_note(note_id))


@note_app.command("create")
def note_create(
    notetype: str = typer.Option(..., "--notetype"),
    deck: str = typer.Option(..., "--deck"),
    fields: Optional[List[str]] = typer.Option(None, "--field", help="Field assignment as Name=Value."),
    tags: Optional[List[str]] = typer.Option(None, "--tag"),
    write: bool = typer.Option(False, "--write"),
) -> None:
    _mutate(
        write,
        lambda service: service.create_note(
            notetype=notetype,
            deck=deck,
            fields=_parse_fields(fields or []),
            tags=tags or [],
        ),
    )


@note_app.command("update")
def note_update(
    note_id: int,
    fields: Optional[List[str]] = typer.Option(None, "--field", help="Field assignment as Name=Value."),
    tags: Optional[List[str]] = typer.Option(None, "--tag"),
    write: bool = typer.Option(False, "--write"),
) -> None:
    _mutate(
        write,
        lambda service: service.update_note(
            note_id,
            fields=_parse_fields(fields or []),
            tags=tags,
        ),
    )


@note_app.command("delete")
def note_delete(note_id: int, write: bool = typer.Option(False, "--write"), confirm_delete: bool = typer.Option(False, "--confirm-delete")) -> None:
    if not confirm_delete:
        _fail("note delete requires --confirm-delete", [])
    _mutate(write, lambda service: service.delete_note(note_id))


@card_app.command("search")
def card_search(query: str, count: bool = typer.Option(False, "--count", help="Emit only the number of matching cards.")) -> None:
    if count:
        _read_collection(lambda service: service.count_cards(query))
    else:
        _read_collection(lambda service: service.search_cards(query))


@card_app.command("get")
def card_get(card_id: int) -> None:
    _read_collection(lambda service: service.get_card(card_id))


@card_app.command("suspend")
def card_suspend(query: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.suspend_cards(query))


@card_app.command("unsuspend")
def card_unsuspend(query: str, write: bool = typer.Option(False, "--write")) -> None:
    _mutate(write, lambda service: service.unsuspend_cards(query))


@notetype_app.command("list")
def notetype_list() -> None:
    _read_collection(lambda service: service.list_notetypes())


@notetype_app.command("get")
def notetype_get(name: str) -> None:
    _read_collection(lambda service: service.get_notetype(name))


@notetype_app.command("export")
def notetype_export(name: str, out: Path = typer.Option(..., "--out")) -> None:
    def export(service: AnkiCollectionService):
        model = service.get_notetype(name)
        export_notetype_bundle(model, out)
        return {"notetype": name, "out": str(out)}

    _read_collection(export)


@notetype_app.command("update")
def notetype_update(
    name: str,
    source: Path = typer.Option(..., "--from"),
    write: bool = typer.Option(False, "--write"),
    confirm_schema_change: bool = typer.Option(False, "--confirm-schema-change"),
) -> None:
    new_model = load_notetype_bundle(source)

    def update(service: AnkiCollectionService):
        old_model = service.get_notetype(name)
        summary = summarize_notetype_changes(old_model, new_model)
        if summary.schema_change and not confirm_schema_change:
            raise CollectionError("notetype schema change requires --confirm-schema-change")
        result = service.update_notetype(name, new_model)
        result["summary"] = summary.messages
        result["schema_change"] = summary.schema_change
        return result

    _mutate(write, update)


@import_app.command("apkg")
def import_apkg(
    path: Path,
    with_scheduling: bool = typer.Option(
        False,
        "--with-scheduling/--without-scheduling",
        help="Import card scheduling/learning progress (default: off).",
    ),
    with_deck_configs: bool = typer.Option(
        False,
        "--with-deck-configs/--without-deck-configs",
        help="Import deck presets/configuration (default: off).",
    ),
    update_notes: str = typer.Option(
        "never",
        "--update-notes",
        help="Existing note update mode: never, if-newer, or always.",
    ),
    update_notetypes: str = typer.Option(
        "never",
        "--update-notetypes",
        help="Existing notetype update mode: never, if-newer, or always.",
    ),
    merge_notetypes: bool = typer.Option(
        False,
        "--merge-notetypes/--no-merge-notetypes",
        help="Merge compatible notetypes instead of keeping them separate (default: off).",
    ),
    write: bool = typer.Option(False, "--write", help="Confirm the collection mutation."),
) -> None:
    try:
        package_path = validate_apkg_path(path)
        options = import_options_payload(
            with_scheduling=with_scheduling,
            with_deck_configs=with_deck_configs,
            update_notes=update_notes,
            update_notetypes=update_notetypes,
            merge_notetypes=merge_notetypes,
        )
    except CollectionError as exc:
        _fail(str(exc), [])
        return

    if not write:
        _fail("APKG import requires --write", [])

    resolved = _resolve_profile()
    bridge = BridgeClient.discover(state.base) if state.base is not None else None
    bridge_health = None
    if bridge:
        try:
            bridge_health = bridge.health()
        except BridgeError as exc:
            _fail(
                "%s; refusing to open the collection directly while a live-bridge state file exists"
                % exc,
                [],
            )
    if bridge_health and bridge_health.get("profile") == resolved.name:
        try:
            result = bridge.import_apkg(
                {
                    "profile": resolved.name,
                    "package_path": str(package_path),
                    "options": options,
                    "write": True,
                }
            )
            result["transport"] = "live_bridge"
            _emit(result)
        except BridgeError as exc:
            _fail(str(exc), [])
        return

    _mutate(
        write,
        lambda service: service.import_apkg(package_path, options),
        transport="direct",
    )


def _store() -> ProfileStore:
    assert state.base is not None
    return ProfileStore(state.base)


def _resolve_profile():
    return ProfileResolver(_store()).resolve(explicit=state.profile)


def _resolve_auth_login_profile() -> ResolvedProfile:
    assert state.base is not None
    if state.profile and not is_default_desktop_base(state.base):
        profile = _store().ensure_profile(state.profile)
        return ResolvedProfile(profile.name, "explicit")
    return _resolve_profile()


def _backup_service() -> BackupService:
    assert state.base is not None
    resolved = _resolve_profile()
    profile = _store().get_profile(resolved.name)
    retention = int(profile.data.get("numBackups") or 50)
    return BackupService(state.base, resolved.name, retention=retention)


def _collection_path(profile: str) -> Path:
    assert state.base is not None
    return state.base / profile / "collection.anki2"


def _read_collection(operation: Callable[[AnkiCollectionService], object]) -> None:
    resolved = _resolve_profile()
    try:
        with _silence_anki_backend_stdout():
            service = AnkiCollectionService.open(_collection_path(resolved.name))
            try:
                result = operation(service)
            finally:
                service.close()
        _emit(result)
    except CollectionError as exc:
        _fail(str(exc), [])


def _mutate(
    write: bool,
    operation: Callable[[AnkiCollectionService], dict],
    *,
    transport: Optional[str] = None,
) -> None:
    assert state.base is not None
    resolved = _resolve_profile()
    context = MutatingCommandContext(
        profile=resolved.name,
        is_desktop_base=is_default_desktop_base(state.base),
        write=write,
    )

    def mutate() -> dict:
        with _silence_anki_backend_stdout():
            service = AnkiCollectionService.open(_collection_path(resolved.name))
            try:
                return operation(service)
            finally:
                service.close()

    def backup(*, force: bool = False) -> dict:
        with _silence_anki_backend_stdout():
            return _backup_service().create(force=force)

    try:
        output = run_guarded_mutation(context, backup, mutate)
        if transport:
            output["transport"] = transport
        _emit(output)
    except (CollectionError, BackupError, SafetyError) as exc:
        _fail(str(exc), [])


def _sync_login_with_anki(profile: str, username: str, password: str) -> str:
    assert state.base is not None
    collection_path = state.base / profile / "collection.anki2"
    try:
        from anki.collection import Collection
    except ModuleNotFoundError as exc:
        raise typer.BadParameter("the anki package is required for auth login") from exc
    with _silence_anki_backend_stdout():
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        collection = Collection(str(collection_path))
        try:
            auth = collection.sync_login(username=username, password=password, endpoint=None)
        finally:
            collection.close()
    sync_key = getattr(auth, "hkey", "")
    if not sync_key:
        raise typer.BadParameter("AnkiWeb login did not return a sync key")
    return sync_key


def _sync_auth(profile_name: str):
    profile = _store().get_profile(profile_name)
    sync_key = profile.data.get("syncKey")
    if not sync_key:
        raise CollectionError("profile is not AnkiWeb authenticated: %s" % profile_name)
    try:
        from anki.sync_pb2 import SyncAuth
    except ModuleNotFoundError as exc:
        raise CollectionError("the anki package is required for sync") from exc
    endpoint = profile.data.get("currentSyncUrl") or profile.data.get("customSyncUrl") or None
    return SyncAuth(hkey=sync_key, endpoint=endpoint)


def _sync_status() -> dict:
    resolved = _resolve_profile()
    with _silence_anki_backend_stdout():
        service = AnkiCollectionService.open(_collection_path(resolved.name))
        try:
            status = service.collection.sync_status(_sync_auth(resolved.name))
            return {"profile": resolved.name, "required": int(status.required), "new_endpoint": getattr(status, "new_endpoint", "")}
        finally:
            service.close()


def _sync_run() -> dict:
    resolved = _resolve_profile()
    with _silence_anki_backend_stdout():
        service = AnkiCollectionService.open(_collection_path(resolved.name))
        try:
            profile = _store().get_profile(resolved.name)
            output = service.collection.sync_collection(_sync_auth(resolved.name), bool(profile.data.get("syncMedia", True)))
            return {
                "profile": resolved.name,
                "required": int(output.required),
                "new_endpoint": getattr(output, "new_endpoint", ""),
                "server_message": getattr(output, "server_message", ""),
                "host_number": int(getattr(output, "host_number", 0)),
                "server_media_usn": int(getattr(output, "server_media_usn", 0)),
            }
        finally:
            service.close()


def _sync_full(upload: bool) -> dict:
    resolved = _resolve_profile()
    with _silence_anki_backend_stdout():
        service = AnkiCollectionService.open(_collection_path(resolved.name))
        try:
            profile = _store().get_profile(resolved.name)
            auth = _sync_auth(resolved.name)
            status = service.collection.sync_collection(auth, bool(profile.data.get("syncMedia", True)))
            if getattr(status, "new_endpoint", ""):
                auth.endpoint = status.new_endpoint
            server_usn = int(getattr(status, "server_media_usn", 0))
            service.collection.full_upload_or_download(auth=auth, server_usn=server_usn, upload=upload)
            return {
                "profile": resolved.name,
                "upload": upload,
                "required": int(getattr(status, "required", 0)),
                "new_endpoint": getattr(status, "new_endpoint", ""),
                "host_number": int(getattr(status, "host_number", 0)),
                "server_media_usn": server_usn,
            }
        finally:
            service.close()


@contextlib.contextmanager
def _silence_anki_backend_stdout() -> Iterator[None]:
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _parse_fields(assignments: List[str]) -> dict[str, str]:
    fields = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise typer.BadParameter("field assignments must use Name=Value")
        key, value = assignment.split("=", 1)
        fields[key] = value
    return fields


def _emit(data: object) -> None:
    if state.json:
        typer.echo(dumps(data))
    else:
        typer.echo(data)


def _fail(message: str, candidates: list[str]) -> None:
    payload = {"error": message, "candidates": candidates}
    if state.json:
        typer.echo(dumps(payload), err=True)
    else:
        typer.echo(message, err=True)
    raise typer.Exit(code=2)
