#!/usr/bin/env bash
# Publica una version nueva de la app de escritorio Kurug (Mac/Linux).
#
#   ./release.sh 0.1.2   -> version explicita
#   ./release.sh         -> auto-incrementa el patch (0.1.1 -> 0.1.2)
#
# Sube la version en package.json y tauri.conf.json (deben coincidir), commitea,
# crea el tag vX.Y.Z y lo empuja. GitHub Actions compila, firma y publica el
# release; a los amigos les sale "Actualizar y reiniciar".
#
# Requisito: no debe haber cambios sin commitear (esto solo sube la version).
set -euo pipefail

cd "$(cd "$(dirname "$0")/../web" && pwd)"
conf="src-tauri/tauri.conf.json"

cur="$(node -p "require('./package.json').version")"
if [ "${1:-}" ]; then
  new="$1"
else
  IFS='.' read -r a b c <<< "$cur"
  new="$a.$b.$((c + 1))"
fi
echo "Version: $cur -> $new"

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: hay cambios sin commitear. Commitea o descartalos primero." >&2
  exit 1
fi

# 1) Subir la version en los dos archivos.
npm version "$new" --no-git-tag-version >/dev/null
CONF="$conf" NEW="$new" node -e 'const fs=require("fs"),f=process.env.CONF,v=process.env.NEW;let s=fs.readFileSync(f,"utf8");s=s.replace(/("version"\s*:\s*")[^"]+/,"$1"+v);fs.writeFileSync(f,s)'

# 2) Commit + tag + push (dispara el build).
git add package.json package-lock.json "$conf"
git commit -m "release v$new"
git tag "v$new"
git push origin HEAD
git push origin "v$new"

echo
echo "Listo. Tag v$new empujado -> compilando en:"
echo "  https://github.com/Ruisux/Kurug/actions"
