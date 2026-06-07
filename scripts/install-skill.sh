#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_skill="$repo_root/skills/ankicli"

if [[ ! -f "$source_skill/SKILL.md" ]]; then
  echo "Could not find ankicli skill at $source_skill" >&2
  exit 1
fi

target_root="${1:-${ANKICLI_SKILL_HOME:-}}"
if [[ -z "$target_root" ]]; then
  if [[ -n "${CODEX_HOME:-}" ]]; then
    target_root="$CODEX_HOME/skills"
  elif [[ -d "$HOME/.codex" ]]; then
    target_root="$HOME/.codex/skills"
  elif [[ -d "$HOME/.agents" ]]; then
    target_root="$HOME/.agents/skills"
  else
    target_root="$HOME/.codex/skills"
  fi
fi

mkdir -p "$target_root"
python3 - "$source_skill" "$target_root/ankicli" <<'PY'
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
shutil.copytree(source, target, dirs_exist_ok=True)
print(target)
PY
