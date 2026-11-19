#!/usr/bin/env bash
# Domácí naplánovaná úloha: FIBA ID z nbl.basketball -> fiba_overrides.json -> push na GitHub.
# Spuštění: scripts/home_sync.sh   (z libovolné složky; potřebuje git, python3 a requests+bs4+lxml)
# Po pushi se na GitHubu sám spustí workflow league (paths: data/*/fiba_overrides.json).
set -euo pipefail
cd "$(dirname "$0")/.."
BR="claude/league-stats-metrics-0it2cf"
git fetch -q origin "$BR"
git checkout -q "$BR"
git reset -q --hard "origin/$BR"     # pracovní kopie jen pro tuhle úlohu, lokální změny se neřeší
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" scripts/home_fiba_ids.py
git add data/*/fiba_overrides.json
if git diff --cached --quiet; then exit 0; fi
git -c user.name="nbl-home" -c user.email="home@nbl2627.local" commit -q -m "chore: FIBA ID z nbl.basketball (domácí úloha)"
git push -q origin "HEAD:$BR"
echo "pushnuto"
