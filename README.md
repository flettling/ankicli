# ankicli

`ankicli` is a command line interface for Anki collections and AnkiWeb sync.
It is built on Anki's official Python package and is intended for agent-first
workflows on isolated Anki workspaces, while keeping desktop Anki mutations
guarded.

## Quick Install For Agents

Give an agent this README link and ask it to install both the CLI and the skill.
After the repository is published, the recommended path is:

```bash
git clone https://github.com/flettling/ankicli.git
cd ankicli
python3 -m pip install --upgrade pip
python3 -m pip install .
bash scripts/install-skill.sh
bash scripts/install-bridge.sh
ankicli --help
```

From an existing local checkout:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install .
bash scripts/install-skill.sh
bash scripts/install-bridge.sh
ankicli --help
```

For an isolated install, use `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install .
bash scripts/install-skill.sh
ankicli --help
```

To install the skill into a specific agent skill directory:

```bash
bash scripts/install-skill.sh ~/.codex/skills
bash scripts/install-skill.sh ~/.agents/skills
ANKICLI_SKILL_HOME=~/.openclaw/skills bash scripts/install-skill.sh
```

The CLI alone can also be installed directly from GitHub, but this does not
install the skill because `pip` does not copy repository skill folders into an
agent's skill directory:

```bash
python3 -m pip install "git+https://github.com/flettling/ankicli.git"
```

## Manual Development Install

Use a virtual environment when developing locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
pytest -q
```

If editable install is not supported by the local `pip`, install non-editable:

```bash
python -m pip install .
```

## First Smoke Test

Read-only profile and deck inspection:

```bash
ankicli --json profile list
ankicli --json profile default get
ankicli --profile "Florian" --json deck list
```

On macOS/Linux desktop Anki, opening a collection may need permission to create
Anki lock/sidecar files in the profile directory. Do not use mutating commands
against desktop Anki unless explicitly authorized.

## Core Rules

- Use `--json` for automation.
- Pass `--base` or set `ANKI_BASE` for agent/VPS workspaces.
- Let `ankicli` resolve the default profile from Anki's `prefs21.db`, but pass
  `--profile` when multiple sync-authenticated profiles exist.
- On a fresh agent/VPS workspace, bootstrap the first profile with
  `ankicli --base "$ANKI_BASE" --profile agent --json auth login`.
- Use count-only reads before bulk actions: `deck list --counts`,
  `card search QUERY --count`, or `note search QUERY --count`.
- Every mutating command creates a backup first.
- Desktop Anki mutations require `--write` and cannot use `--no-backup`.
- APKG imports use the authenticated native bridge when the selected profile is
  open in Desktop Anki; the CLI never opens that live `collection.anki2` itself.

## Examples

```bash
ankicli --base /srv/anki --json profile list
ankicli --base /srv/anki --json auth status
ankicli --base /srv/anki --json backup create --force
ankicli --base /srv/anki --json sync status
ankicli --base /srv/anki --json deck list --counts
ankicli --base /srv/anki --json card search 'deck:".learn" is:due' --count
ankicli --base /srv/anki --json note search "tag:High-Yield" --count
ankicli --base /srv/anki --json note search "deck:Current"
ankicli --base /srv/anki --json card suspend "tag:pause-me" --write
ankicli --base /srv/anki --json filtered create "Due Today" --search "is:due" --limit 100 --order DUE --write
ankicli --base /srv/anki --json notetype export Basic --out /tmp/basic-notetype
ankicli --json import apkg /path/to/deck.apkg --write
```

## APKG Import And Live Desktop Anki

Install the bundled bridge once, then restart Anki:

```bash
bash scripts/install-bridge.sh
```

The installer copies `ankicli_bridge` into the desktop Anki `addons21`
directory. If it replaces an existing installation, it first creates a
timestamped sibling backup. While Anki is open, the bridge exposes only an
authenticated loopback endpoint and runs the import against Anki's already-open
`mw.col`. With Anki closed or in an isolated `--base`, ankicli uses Anki's
official `Collection` API directly.

Safe import defaults are deliberately conservative:

- scheduling/learning progress: off
- deck presets/configuration: off
- existing notes: never update
- existing notetypes: never update
- notetype merging: off

All APKG imports require `--write`, create and verify an Anki backup first, and
do not trigger synchronization. A repeated import is handled by Anki's native
GUID matching and is reported under `unchanged`, `skipped`, and the detailed
categories instead of being silently treated as new content.

Safe AMBOSSIO update (update only notes whose package version is newer, while
preserving local scheduling, deck presets, and notetype metadata):

```bash
ankicli --json import apkg /Users/florian/repos/AMBOSSIO/dist/AMBOSSIO.apkg \
  --update-notes if-newer \
  --update-notetypes never \
  --without-scheduling \
  --without-deck-configs \
  --no-merge-notetypes \
  --write
```

See the command reference for the full result shape and the more aggressive
`always` update mode.

For the full command reference, see [docs/COMMANDS.md](docs/COMMANDS.md).

## Agent/VPS Workflow

Use a dedicated Anki base on servers:

```bash
export ANKI_BASE=/srv/anki
ankicli --base "$ANKI_BASE" --profile agent --json auth login
ankicli --base "$ANKI_BASE" --profile agent --json sync status
ankicli --base "$ANKI_BASE" --profile agent --json sync run
ankicli --base "$ANKI_BASE" --profile agent --json deck list --counts
```

Before any mutation, inspect the blast radius with counts and then create a backup:

```bash
ankicli --base "$ANKI_BASE" --json card search "tag:pause-me" --count
ankicli --base "$ANKI_BASE" --json backup create --force
ankicli --base "$ANKI_BASE" --json card suspend "tag:pause-me" --write
ankicli --base "$ANKI_BASE" --json filtered rebuild "Due Today" --write
ankicli --base "$ANKI_BASE" --json sync run
```

## Notetype Bundles

`notetype export` writes a directory bundle instead of a flat file:

- `notetype.json`
- `fields.json`
- `style.css`
- `templates/<NN>-<name>/front.html`
- `templates/<NN>-<name>/back.html`
- `templates/<NN>-<name>/template.json`

`notetype update` validates the bundle, creates a backup, summarizes changes,
and requires `--confirm-schema-change` when fields or templates change.

## License

AGPL-3.0-or-later, matching Anki's licensing constraints.
