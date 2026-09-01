#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_addon="$repo_root/addons/ankicli_bridge"
anki_base="${1:-${ANKI_BASE:-}}"

if [[ -z "$anki_base" ]]; then
  case "$(uname -s)" in
    Darwin) anki_base="$HOME/Library/Application Support/Anki2" ;;
    Linux) anki_base="${XDG_DATA_HOME:-$HOME/.local/share}/Anki2" ;;
    *) echo "Pass the Anki base directory as the first argument." >&2; exit 2 ;;
  esac
fi

target_root="$anki_base/addons21"
target="$target_root/ankicli_bridge"
mkdir -p "$target_root"

python3 - "$source_addon" "$target" <<'PY'
import datetime
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
if not (source / "__init__.py").is_file():
    raise SystemExit("bridge source is incomplete: %s" % source)
if target.exists():
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(target.name + ".bak-" + stamp)
    shutil.copytree(target, backup)
    print("backup=" + str(backup))
    shutil.rmtree(target)
shutil.copytree(source, target)
print("installed=" + str(target))
PY

echo "Restart Anki to load the ankicli bridge."
