import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class ProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    data: dict[str, Any]

    @property
    def sync_authenticated(self) -> bool:
        return bool(self.data.get("syncKey"))

    @property
    def sync_user(self) -> Optional[str]:
        user = self.data.get("syncUser")
        return str(user) if user else None


@dataclass(frozen=True)
class ResolvedProfile:
    name: str
    source: str


@dataclass(frozen=True)
class ResolveResult:
    ok: bool
    profile: Optional[ResolvedProfile] = None
    error: str = ""
    candidates: Optional[list[str]] = None


class ProfileStore:
    def __init__(self, base: Path):
        self.base = base
        self.db_path = base / "prefs21.db"

    def exists(self) -> bool:
        return self.db_path.exists()

    def list_profiles(self) -> list[Profile]:
        rows = self._read_all()
        return [
            Profile(name=name, data=data)
            for name, data in sorted(rows.items())
            if name != "_global"
        ]

    def get_profile(self, name: str) -> Profile:
        rows = self._read_all()
        if name not in rows or name == "_global":
            raise ProfileError("profile not found: %s" % name)
        return Profile(name=name, data=rows[name])

    def global_config(self) -> dict[str, Any]:
        return self._read_all().get("_global", {})

    def set_sync_auth(self, name: str, *, sync_key: str, sync_user: str) -> None:
        rows = self._read_all()
        if name not in rows or name == "_global":
            raise ProfileError("profile not found: %s" % name)
        data = dict(rows[name])
        data["syncKey"] = sync_key
        data["syncUser"] = sync_user
        self._write_profile(name, data)

    def clear_sync_auth(self, name: str) -> None:
        rows = self._read_all()
        if name not in rows or name == "_global":
            raise ProfileError("profile not found: %s" % name)
        data = dict(rows[name])
        data["syncKey"] = ""
        data["syncUser"] = ""
        self._write_profile(name, data)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise ProfileError("Anki profile database not found: %s" % self.db_path)
        return sqlite3.connect(str(self.db_path))

    def _read_all(self) -> dict[str, dict[str, Any]]:
        con = self._connect()
        try:
            rows = con.execute("select name, data from profiles").fetchall()
        finally:
            con.close()
        result: dict[str, dict[str, Any]] = {}
        for name, blob in rows:
            result[str(name)] = self._decode(blob)
        return result

    def _write_profile(self, name: str, data: dict[str, Any]) -> None:
        con = self._connect()
        try:
            con.execute(
                "update profiles set data = ? where name = ?",
                (pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL), name),
            )
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _decode(blob: bytes) -> dict[str, Any]:
        try:
            data = pickle.loads(blob)
        except Exception as exc:
            raise ProfileError("could not decode Anki profile data") from exc
        if isinstance(data, dict):
            return data
        raise ProfileError("Anki profile data was not a dictionary")


class ProfileResolver:
    def __init__(self, store: ProfileStore, config_default: Optional[str] = None):
        self.store = store
        self.config_default = config_default

    def resolve(self, explicit: Optional[str] = None) -> ResolvedProfile:
        result = self.resolve_result(explicit=explicit)
        if result.ok and result.profile:
            return result.profile
        raise ProfileError(result.error)

    def resolve_result(self, explicit: Optional[str] = None) -> ResolveResult:
        profiles = {profile.name: profile for profile in self.store.list_profiles()}
        if explicit:
            if explicit in profiles:
                return ResolveResult(True, ResolvedProfile(explicit, "explicit"))
            return ResolveResult(False, error="profile not found: %s" % explicit, candidates=sorted(profiles))

        if self.config_default:
            if self.config_default in profiles:
                return ResolveResult(True, ResolvedProfile(self.config_default, "ankicli-config"))
            return ResolveResult(
                False,
                error="configured default profile not found: %s" % self.config_default,
                candidates=sorted(profiles),
            )

        global_config = self.store.global_config()
        last_loaded = global_config.get("last_loaded_profile_name")
        if isinstance(last_loaded, str) and last_loaded in profiles and profiles[last_loaded].sync_authenticated:
            return ResolveResult(True, ResolvedProfile(last_loaded, "anki-last-loaded-sync"))

        synced = [profile.name for profile in profiles.values() if profile.sync_authenticated]
        if len(synced) == 1:
            return ResolveResult(True, ResolvedProfile(synced[0], "single-sync-profile"))
        if len(synced) > 1:
            return ResolveResult(
                False,
                error="multiple sync-authenticated profiles; pass --profile",
                candidates=sorted(synced),
            )
        return ResolveResult(False, error="no sync-authenticated default profile found", candidates=sorted(profiles))
