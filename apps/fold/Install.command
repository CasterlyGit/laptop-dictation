#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/build-app.sh
mkdir -p "$HOME/Applications"
ditto dist/Fold.app "$HOME/Applications/Fold.app"
open "$HOME/Applications/Fold.app"
echo 'Fold is installed in your Applications folder.'
