# Agent Instructions For ankicli

`ankicli` is an agent-first command line interface for Anki collections and
AnkiWeb sync. Treat this file as the working contract for Codex, Hermes,
OpenClaw, and other coding agents modifying this repository.

## Project Principles

- Build on Anki's official behavior. `ankicli` uses the official `anki` Python
  package from `ankitects/anki`; prefer that API over direct SQLite edits,
  copied implementation details, or guessed collection semantics.
- Before changing collection, scheduler, sync, filtered deck, notetype, backup,
  or profile behavior, inspect how current Anki does it in `ankitects/anki` or
  the installed `anki` package.
- Keep the CLI agent-friendly: stable JSON, compact machine-readable output,
  useful exit failures, and no diagnostic noise on stdout when `--json` is
  used.
- Keep changes small and compatible with macOS and Linux.

## Live Anki Safety

- The user's desktop Anki can be a live collection. Do not mutate desktop Anki
  accidentally.
- Mutating commands must require explicit `--write` and must go through the
  backup guard.
- Do not bypass Anki's backup APIs for collection mutations. Use Anki's own
  backup mechanism and existing retention behavior.
- Never perform a full upload to AnkiWeb without explicit user approval. For a
  fresh VPS/agent workspace, prefer full download from AnkiWeb into an isolated
  `--base`.
- Prefer isolated agent workspaces such as `--base /srv/anki` or
  `--base /home/hermes/anki-agent` for automation.
- Before bulk mutations, inspect the blast radius with read-only commands such
  as `deck list --counts`, `card search QUERY --count`, or
  `note search QUERY --count`.

## Documentation Rules

Every user-facing behavior change must update all relevant documentation in the
same change:

- `README.md` for installation, quick examples, and agent workflows.
- `docs/COMMANDS.md` for the complete command reference, flags, JSON shapes,
  confirmation requirements, and examples.
- `skills/ankicli/SKILL.md` for agent operating guidance.
- `skills/ankicli/agents/openai.yaml` if skill metadata or agent-facing entry
  points change.

Documentation is part of the feature. Do not ship a new command, flag, JSON
field, safety rule, or workflow without documenting it for both humans and
agents.

## Testing Rules

- Add service-level tests for behavior in `AnkiCollectionService` or related
  helpers.
- Add CLI tests for every new command, option, confirmation guard, or JSON
  contract.
- Preserve existing JSON shapes unless the change explicitly migrates them.
- Run `python3 -m pytest -q` before considering a code change complete.
- Run `python3 -m build --wheel` before release-style pushes or when packaging
  behavior may be affected.
- For sync, auth, or VPS-agent workflow changes, perform a read-only smoke test
  on an isolated workspace when feasible.

## Release And Install Checks

- Keep the public GitHub repository installable with:
  `python3 -m pip install "git+https://github.com/flettling/ankicli.git"`.
- Keep the skill installable with `bash scripts/install-skill.sh`.
- Do not commit local Anki collections, backups, profile databases, media,
  credentials, tokens, generated virtualenvs, or build artifacts.
- After pushing changes intended for agents, confirm GitHub Actions passes.
- If the VPS workflow is affected, update the Hermes install with
  `uv tool install --force git+https://github.com/flettling/ankicli.git` and
  run a read-only smoke test.

## Implementation Defaults

- Use Anki's search syntax as-is; do not invent a parallel query language.
- Keep read commands backup-free and mutation-free.
- Keep mutating command output focused on changed IDs, backup information, and
  enough context for an agent to report what happened.
- Prefer explicit confirmation flags for destructive operations, full sync
  directions, and notetype schema changes.
- When in doubt, choose the safer behavior and document the decision.
