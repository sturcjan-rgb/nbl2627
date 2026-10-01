#!/usr/bin/env bash
# Commit + push data/ s ochranou proti souběhu (league build × live).
# Použití: scripts/commit_data.sh "<commit zpráva>" "<příkaz pro přepočet>"
# Když push selže (mezitím pushnul jiný běh), stáhne čerstvou větev, vrátí do ní nově
# archivované raw/*.json.gz (dohrané zápasy jsou neměnné, takže je to bezpečné),
# znovu přepočítá data a zkusí to znovu. Generované JSONy se tak nikdy neslučují ručně.
set -u
MSG="$1"; REBUILD="$2"
BR="${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD)}"
git config user.name "nbl-bot"; git config user.email "bot@nbl2627.local"
SAVE=$(mktemp -d)
for i in 1 2 3 4 5; do
  git add data
  if git diff --cached --quiet; then echo "Beze změn."; exit 0; fi
  git commit -q -m "$MSG"
  if git push -q origin "HEAD:$BR"; then echo "Pushnuto."; exit 0; fi
  echo "Push selhal (pokus $i) — stahuji čerstvý stav a přepočítávám."
  # nové raw archivy z tohoto běhu (v HEAD, ale ne na originu) si odložit
  git fetch -q origin "$BR"
  git diff --name-only --diff-filter=A "origin/$BR" HEAD -- 'data/*/raw/*.json.gz' | while read -r f; do
    mkdir -p "$SAVE/$(dirname "$f")"; cp "$f" "$SAVE/$f"; done
  git reset -q --hard "origin/$BR"
  cp -rn "$SAVE/data" . 2>/dev/null || true
  eval "$REBUILD"
  sleep $((i * 5))
done
exit 1
