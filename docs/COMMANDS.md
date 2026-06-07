# ankicli Command Reference

This page documents the current `ankicli` command surface. Use `--json` for
agent workflows and prefer an isolated `--base`/`ANKI_BASE` workspace for VPS
automation.

## Global Options

All commands accept these options before the command group:

```bash
ankicli [--base PATH] [--profile NAME] [--json] COMMAND ...
```

- `--base PATH`: Anki base directory. Defaults to the platform Anki2 path.
- `--profile NAME`: Explicit Anki profile. Use this when multiple profiles are plausible.
- `--json`: Emit compact JSON for agents.

Default profile resolution:

1. `--profile NAME`
2. `ANKICLI_PROFILE`
3. Anki `_global.last_loaded_profile_name` if sync-authenticated
4. the single sync-authenticated profile
5. otherwise fail and list candidates

## Safety Rules

- Read commands do not create backups.
- Mutating commands create an Anki backup first.
- Desktop Anki mutations require `--write`.
- `--no-backup` is not exposed for desktop operations.
- Delete, full sync, and notetype schema changes require explicit confirmation flags.
- On sandboxed systems, read commands may need permission to open Anki's collection because Anki may create lock/sidecar files.

## Profile Commands

### `profile list`

List Anki profiles in the selected Anki base.

```bash
ankicli --json profile list
```

JSON shape:

```json
{"profiles":[{"name":"Florian","sync_authenticated":true,"sync_user":"user@example.com"}]}
```

### `profile default get`

Show the resolved default profile and why it was selected.

```bash
ankicli --json profile default get
```

JSON shape:

```json
{"name":"Florian","source":"anki-last-loaded-sync"}
```

### `profile default set NAME`

Validate that `NAME` exists. Current behavior does not rewrite Anki's
`last_loaded_profile_name`; use `--profile NAME` or `ANKICLI_PROFILE` for
explicit command selection.

```bash
ankicli --json profile default set Florian
```

## Auth Commands

### `auth status`

Show whether the resolved profile has AnkiWeb sync auth.

```bash
ankicli --json auth status
```

### `auth login`

Prompt for AnkiWeb username and password, call Anki's sync login, and store only
the returned sync key/user in the selected Anki profile.

In an isolated non-desktop Anki base, an explicit missing `--profile` is created
automatically. This is intended for first-time VPS/agent setup; desktop Anki
profiles are not created implicitly.

```bash
ankicli --base /srv/anki --profile agent --json auth login
```

### `auth logout`

Clear sync auth from the selected profile.

```bash
ankicli --profile agent --json auth logout
```

## Backup Commands

### `backup create`

Create a backup using Anki's own `Collection.create_backup()` backend.

```bash
ankicli --json backup create
ankicli --json backup create --force
```

Output includes `backup_dir` and retention.

### `backup list`

List backup files for the selected profile.

```bash
ankicli --json backup list
```

### `backup prune`

Delete old backup files beyond the profile retention count, usually Anki's
`numBackups` profile setting.

```bash
ankicli --json backup prune
```

## Sync Commands

### `sync status`

Ask AnkiWeb whether the collection needs normal sync, upload, download, or no action.

```bash
ankicli --json sync status
```

Requires a sync-authenticated profile.

### `sync run`

Run a normal collection sync through Anki's sync backend.

```bash
ankicli --json sync run
```

### `sync full-upload`

Upload the local collection to AnkiWeb. This is destructive for the remote side
and requires an explicit confirmation flag.

```bash
ankicli --json sync full-upload --confirm-full-sync
```

### `sync full-download`

Replace the local collection from AnkiWeb. This is destructive for the local
side and requires an explicit confirmation flag.

```bash
ankicli --json sync full-download --confirm-full-sync
```

## Deck Commands

### `deck list`

List all decks.

```bash
ankicli --json deck list
```

JSON shape:

```json
{"decks":[{"id":1730937936132,"name":".learn"}]}
```

### `deck list --counts`

Return Anki's deck overview counts as a recursive tree. This mirrors the counts
Anki shows in the deck overview; it is not a generic search-query count. The
command is read-only and does not require `--write` or create a backup.

```bash
ankicli --json deck list --counts
```

JSON shape:

```json
{
  "deck_tree": {
    "id": 1730937936132,
    "name": ".learn",
    "level": 0,
    "collapsed": false,
    "filtered": false,
    "counts": {
      "new": 57,
      "learn": 97,
      "due": 2690,
      "total_in_deck": 0,
      "total_including_children": 12345
    },
    "children": []
  }
}
```

Count fields:

- `new`: new cards available in Anki's scheduler overview
- `learn`: learning cards in Anki's scheduler overview
- `due`: review cards due in Anki's scheduler overview
- `total_in_deck`: cards directly in this deck
- `total_including_children`: cards in this deck plus child decks

### `deck info NAME`

Show the raw Anki deck object for `NAME`.

```bash
ankicli --json deck info "Ankizin"
```

### `deck create NAME`

Create a deck. Mutating command.

```bash
ankicli --json deck create "Agent Scratch" --write
```

### `deck rename OLD NEW`

Rename a deck. Mutating command.

```bash
ankicli --json deck rename "Old" "New" --write
```

### `deck delete NAME`

Delete a deck. Mutating command with extra confirmation.

```bash
ankicli --json deck delete "Agent Scratch" --write --confirm-delete
```

## Filtered Deck Commands

Filtered decks are Anki's Auswahlstapel. They are listed among decks, but they
use a separate Scheduler API and have their own search/order/reschedule config.

### `filtered list`

List all filtered decks.

```bash
ankicli --json filtered list
```

### `filtered get NAME`

Read one filtered deck's search terms and reschedule setting.

```bash
ankicli --json filtered get "Due Today"
```

### `filtered orders`

List supported order names for `filtered create` and `filtered update`.

```bash
ankicli --json filtered orders
```

Known order names:

- `OLDEST_REVIEWED_FIRST`
- `RANDOM`
- `INTERVALS_ASCENDING`
- `INTERVALS_DESCENDING`
- `LAPSES`
- `ADDED`
- `DUE`
- `REVERSE_ADDED`
- `RETRIEVABILITY_ASCENDING`
- `RETRIEVABILITY_DESCENDING`

### `filtered create NAME`

Create or configure a filtered deck. Mutating command.

```bash
ankicli --json filtered create "Due Today" \
  --search "is:due" \
  --limit 100 \
  --order DUE \
  --reschedule \
  --write
```

Use `--no-reschedule` for preview-style cram decks that should not reschedule
cards after review. Use `--allow-empty` if the deck should be created even when
the search currently matches no cards.

### `filtered update NAME`

Update an existing filtered deck's search/order/reschedule config. Mutating command.

```bash
ankicli --json filtered update "Due Today" \
  --search "is:due deck:Ankizin" \
  --limit 50 \
  --order RANDOM \
  --write
```

### `filtered rebuild NAME`

Rebuild a filtered deck from its configured search. Mutating command because it
moves cards into the filtered deck.

```bash
ankicli --json filtered rebuild "Due Today" --write
```

### `filtered empty NAME`

Empty a filtered deck and return cards to their original decks. Mutating command.

```bash
ankicli --json filtered empty "Due Today" --write
```

### `filtered delete NAME`

Delete a filtered deck. Mutating command with extra confirmation.

```bash
ankicli --json filtered delete "Due Today" --write --confirm-delete
```

## Note Commands

### `note search QUERY`

Search note IDs using Anki's search syntax.

```bash
ankicli --json note search "deck:Ankizin tag:todo"
```

Use `--count` when an agent only needs the size of the result set. This is
read-only and returns no note IDs.

```bash
ankicli --json note search "tag:High-Yield" --count
```

JSON shape:

```json
{"count":123}
```

### `note get NOTE_ID`

Read one note's fields and tags.

```bash
ankicli --json note get 1234567890
```

### `note create`

Create a note. Mutating command.

```bash
ankicli --json note create \
  --notetype Basic \
  --deck "Agent Scratch" \
  --field "Front=Question" \
  --field "Back=Answer" \
  --tag agent-created \
  --write
```

### `note update NOTE_ID`

Update fields and optionally tags. Mutating command.

```bash
ankicli --json note update 1234567890 \
  --field "Back=Updated answer" \
  --tag reviewed \
  --write
```

### `note delete NOTE_ID`

Delete a note. Mutating command with extra confirmation.

```bash
ankicli --json note delete 1234567890 --write --confirm-delete
```

## Card Commands

### `card search QUERY`

Search card IDs using Anki's search syntax.

```bash
ankicli --json card search "is:new deck:Ankizin"
```

Use `--count` before bulk actions or filtered-deck planning to avoid returning
large ID arrays. This is read-only and returns no card IDs.

```bash
ankicli --json card search 'deck:".learn" is:due' --count
```

JSON shape:

```json
{"count":123}
```

### `card get CARD_ID`

Read one card's metadata.

```bash
ankicli --json card get 1234567890
```

### `card suspend QUERY`

Suspend cards matching `QUERY`. Mutating command.

```bash
ankicli --json card suspend "cid:1234567890" --write
```

### `card unsuspend QUERY`

Unsuspend cards matching `QUERY`. Mutating command.

```bash
ankicli --json card unsuspend "tag:resume-now" --write
```

## Notetype Commands

### `notetype list`

List notetype IDs, names, fields, and templates.

```bash
ankicli --json notetype list
```

### `notetype get NAME`

Read the full Anki notetype object.

```bash
ankicli --json notetype get Basic
```

### `notetype export NAME --out DIR`

Export a notetype as a directory bundle.

```bash
ankicli --json notetype export Basic --out /tmp/basic-notetype
```

Bundle layout:

```text
notetype.json
fields.json
style.css
templates/<NN>-<name>/template.json
templates/<NN>-<name>/front.html
templates/<NN>-<name>/back.html
```

### `notetype update NAME --from DIR`

Update a notetype from an exported directory bundle. Mutating command.

```bash
ankicli --json notetype update Basic --from /tmp/basic-notetype --write
```

If fields or card templates changed, add:

```bash
--confirm-schema-change
```

Schema changes can require a full sync in Anki.
