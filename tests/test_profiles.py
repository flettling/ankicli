from ankicli.profiles import ProfileResolver, ProfileStore


def test_default_profile_prefers_last_loaded_sync_profile(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {
            "local": {"syncKey": "", "syncUser": ""},
            "synced": {"syncKey": "token", "syncUser": "user@example.com"},
        },
        {"last_loaded_profile_name": "synced"},
    )

    resolved = ProfileResolver(ProfileStore(tmp_path)).resolve()

    assert resolved.name == "synced"
    assert resolved.source == "anki-last-loaded-sync"


def test_default_profile_falls_back_to_single_sync_profile(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {
            "plain": {},
            "web": {"syncKey": "token", "syncUser": "user@example.com"},
        },
        {"last_loaded_profile_name": "plain"},
    )

    resolved = ProfileResolver(ProfileStore(tmp_path)).resolve()

    assert resolved.name == "web"
    assert resolved.source == "single-sync-profile"


def test_default_profile_fails_when_multiple_sync_profiles_are_plausible(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {
            "a": {"syncKey": "a-token", "syncUser": "a@example.com"},
            "b": {"syncKey": "b-token", "syncUser": "b@example.com"},
        },
        {},
    )

    result = ProfileResolver(ProfileStore(tmp_path)).resolve_result()

    assert not result.ok
    assert "multiple sync-authenticated profiles" in result.error
    assert result.candidates == ["a", "b"]


def test_profile_store_updates_sync_auth_in_selected_profile(tmp_path, write_profile_db):
    write_profile_db(tmp_path, {"agent": {"numBackups": 7}}, {})
    store = ProfileStore(tmp_path)

    store.set_sync_auth("agent", sync_key="new-token", sync_user="user@example.com")

    profile = store.get_profile("agent")
    assert profile.data["syncKey"] == "new-token"
    assert profile.data["syncUser"] == "user@example.com"
    assert profile.data["numBackups"] == 7


def test_profile_store_ensures_profile_in_fresh_agent_base(tmp_path):
    store = ProfileStore(tmp_path)

    profile = store.ensure_profile("agent")

    assert profile.name == "agent"
    assert profile.data["syncKey"] == ""
    assert profile.data["syncUser"] == ""
    assert profile.data["syncMedia"] is True
    assert profile.data["numBackups"] == 50
    assert store.global_config()["last_loaded_profile_name"] == "agent"
