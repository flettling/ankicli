import ankicli.cli as cli
from ankicli.profiles import ProfileStore
from typer.testing import CliRunner

from ankicli.cli import app


def test_profile_list_json_reports_sync_status(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {"agent": {"syncKey": "token", "syncUser": "agent@example.com"}},
        {"last_loaded_profile_name": "agent"},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["--base", str(tmp_path), "--json", "profile", "list"])

    assert result.exit_code == 0
    assert '"name":"agent"' in result.stdout
    assert '"sync_authenticated":true' in result.stdout


def test_default_profile_json_explains_source(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {"agent": {"syncKey": "token", "syncUser": "agent@example.com"}},
        {"last_loaded_profile_name": "agent"},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["--base", str(tmp_path), "--json", "profile", "default", "get"])

    assert result.exit_code == 0
    assert '"name":"agent"' in result.stdout
    assert '"source":"anki-last-loaded-sync"' in result.stdout


def test_profile_env_var_selects_profile(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {
            "agent": {"syncKey": "token", "syncUser": "agent@example.com"},
            "other": {"syncKey": "token2", "syncUser": "other@example.com"},
        },
        {},
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["--base", str(tmp_path), "--json", "profile", "default", "get"],
        env={"ANKICLI_PROFILE": "other"},
    )

    assert result.exit_code == 0
    assert '"name":"other"' in result.stdout
    assert '"source":"explicit"' in result.stdout


def test_auth_status_json_uses_implicit_profile_token(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {"agent": {"syncKey": "token", "syncUser": "agent@example.com"}},
        {"last_loaded_profile_name": "agent"},
    )
    runner = CliRunner()

    result = runner.invoke(app, ["--base", str(tmp_path), "--json", "auth", "status"])

    assert result.exit_code == 0
    assert '"profile":"agent"' in result.stdout
    assert '"sync_authenticated":true' in result.stdout
    assert '"sync_user":"agent@example.com"' in result.stdout


def test_auth_login_bootstraps_explicit_profile_in_fresh_base(tmp_path, monkeypatch):
    def fake_sync_login(profile: str, username: str, password: str) -> str:
        assert profile == "agent"
        assert username == "user@example.com"
        assert password == "secret"
        assert (tmp_path / "agent").is_dir()
        return "sync-token"

    monkeypatch.setattr(cli, "_sync_login_with_anki", fake_sync_login)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["--base", str(tmp_path), "--profile", "agent", "--json", "auth", "login"],
        input="user@example.com\nsecret\n",
    )

    assert result.exit_code == 0
    profile = ProfileStore(tmp_path).get_profile("agent")
    assert profile.data["syncKey"] == "sync-token"
    assert profile.data["syncUser"] == "user@example.com"


def test_backup_list_json_uses_profile_retention(tmp_path, write_profile_db):
    write_profile_db(
        tmp_path,
        {"agent": {"syncKey": "token", "syncUser": "agent@example.com", "numBackups": 3}},
        {"last_loaded_profile_name": "agent"},
    )
    backup_dir = tmp_path / "agent" / "backups"
    backup_dir.mkdir(parents=True)
    (backup_dir / "backup.colpkg").write_text("backup")
    runner = CliRunner()

    result = runner.invoke(app, ["--base", str(tmp_path), "--json", "backup", "list"])

    assert result.exit_code == 0
    assert '"retention":3' in result.stdout
    assert '"backup.colpkg"' in result.stdout


def test_cli_exposes_planned_command_groups():
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ["auth", "backup", "sync", "deck", "filtered", "note", "card", "notetype"]:
        assert command in result.stdout


def test_filtered_command_group_exposes_selection_deck_operations():
    runner = CliRunner()

    result = runner.invoke(app, ["filtered", "--help"])

    assert result.exit_code == 0
    for command in ["list", "get", "orders", "create", "update", "rebuild", "empty", "delete"]:
        assert command in result.stdout
