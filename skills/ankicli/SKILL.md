---
name: ankicli
description: Use when an agent needs to inspect, sync, back up, or safely mutate an Anki collection through the ankicli command line tool, especially in VPS or isolated ANKI_BASE workspaces.
---

# ankicli

Use `ankicli` for Anki collection work. Prefer isolated agent workspaces over
desktop Anki paths.

## Required Defaults

- Use `--json` for all machine-read operations.
- Pass `--base PATH` or set `ANKI_BASE` before operating in agent/VPS contexts.
- Run `ankicli profile default get --json` or `ankicli profile list --json`
  before choosing a profile.
- If multiple sync-authenticated profiles exist, pass `--profile NAME`.
- In a fresh isolated agent workspace, run
  `ankicli --base "$ANKI_BASE" --profile agent --json auth login` once to
  bootstrap the profile and store the AnkiWeb sync key.
- Use read-only counts before planning bulk changes: `deck list --counts`,
  `card search QUERY --count`, or `note search QUERY --count`.
- Never mutate detected desktop Anki unless the user explicitly authorized it.
- Never use `--no-backup` against desktop Anki.

## Mutation Workflow

Before any mutation:

1. Inspect the target with `search`, `get`, `list`, or count commands.
2. Run `ankicli backup create --force --json`, unless the mutating command
   itself reports a fresh backup.
3. Apply the smallest mutation possible.
4. Report changed IDs and the backup directory/path.
5. In remote agent workspaces, run sync before and after batches of edits.

## Common Commands

```bash
ankicli --base "$ANKI_BASE" --json profile list
ankicli --base "$ANKI_BASE" --profile agent --json auth login
ankicli --base "$ANKI_BASE" --json auth status
ankicli --base "$ANKI_BASE" --json sync status
ankicli --base "$ANKI_BASE" --json backup create --force
ankicli --base "$ANKI_BASE" --json deck list --counts
ankicli --base "$ANKI_BASE" --json card search 'deck:"Target" is:due' --count
ankicli --base "$ANKI_BASE" --json note search "tag:High-Yield" --count
ankicli --base "$ANKI_BASE" --json note search "deck:Target"
ankicli --base "$ANKI_BASE" --json note get 123
ankicli --base "$ANKI_BASE" --json card suspend "cid:123" --write
ankicli --base "$ANKI_BASE" --json filtered create "Due Today" --search "is:due" --limit 100 --order DUE --write
ankicli --base "$ANKI_BASE" --json notetype export Basic --out /tmp/basic-notetype
```

## Counts And Planning

Counts are read-only. They do not require `--write`, do not create backups, and
are safe to run before deciding whether a mutation is appropriate.

- Deck overview: `ankicli --json deck list --counts`
- Card query size: `ankicli --json card search QUERY --count`
- Note query size: `ankicli --json note search QUERY --count`

Use `deck list --counts` when the user asks for Anki overview numbers such as
New, Learn, and Due per deck. Use `card search --count` before suspend,
unsuspend, filtered deck creation, rebuild planning, or any bulk card operation.
Use `note search --count` before note-level edits or deletes.

For filtered deck planning, count the same search query before creating or
rebuilding the filtered deck:

```bash
ankicli --base "$ANKI_BASE" --json card search 'deck:"Target" tag:High-Yield' --count
ankicli --base "$ANKI_BASE" --json filtered create "Target High-Yield" --search 'deck:"Target" tag:High-Yield' --limit 9999 --order DUE --write
```

## Filtered Decks

Use `filtered` commands for Anki Auswahlstapel. Do not create them with normal
`deck create`.

- Create/configure: `ankicli --json filtered create NAME --search QUERY --limit N --order ORDER --write`
- Rebuild after config/search changes: `ankicli --json filtered rebuild NAME --write`
- Empty and return cards: `ankicli --json filtered empty NAME --write`
- Inspect supported orders: `ankicli --json filtered orders`

## Notetype Editing

Notetypes are directory bundles, not flat files. Edit fields, templates, and CSS
separately:

- `fields.json`
- `style.css`
- `templates/<NN>-<name>/front.html`
- `templates/<NN>-<name>/back.html`
- `templates/<NN>-<name>/template.json`

When fields or card templates change, use `--confirm-schema-change` and mention
that a full sync may be required.
