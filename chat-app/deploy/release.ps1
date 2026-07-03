# Publica una version nueva de la app de escritorio Kurug (Windows).
#
#   .\release.ps1 0.1.2   -> version explicita
#   .\release.ps1         -> auto-incrementa el patch (0.1.1 -> 0.1.2)
#
# Sube la version en package.json y tauri.conf.json (deben coincidir), commitea,
# crea el tag vX.Y.Z y lo empuja. GitHub Actions compila, firma y publica.
#
# Requisito: no debe haber cambios sin commitear (esto solo sube la version).
param([string]$Version)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\web")
$conf = "src-tauri\tauri.conf.json"

$cur = (Get-Content package.json -Raw | ConvertFrom-Json).version
if (-not $Version) {
    $p = $cur.Split('.')
    $Version = "$($p[0]).$($p[1]).$([int]$p[2] + 1)"
}
Write-Host "Version: $cur -> $Version"

if (git status --porcelain) { throw "Hay cambios sin commitear. Commitea o descartalos primero." }

# 1) Subir la version en los dos archivos.
npm version $Version --no-git-tag-version | Out-Null
$rx = [regex]'("version"\s*:\s*")[^"]+'
$s = Get-Content $conf -Raw
$s = $rx.Replace($s, "`${1}$Version", 1)
[System.IO.File]::WriteAllText((Resolve-Path $conf).Path, $s, (New-Object System.Text.UTF8Encoding($false)))

# 2) Commit + tag + push (dispara el build).
git add package.json package-lock.json $conf
git commit -m "release v$Version"
git tag "v$Version"
git push origin HEAD
git push origin "v$Version"

Write-Host ""
Write-Host "Listo. Tag v$Version empujado -> https://github.com/Ruisux/Kurug/actions"
