# Actualizador de DuckDNS para Windows.
# Mantiene tu dominio apuntando a la IP pública actual de tu casa.
# Programa este script en el Programador de tareas para que corra cada 5 min.
#
# 1) Pon tu subdominio y tu token (de duckdns.org).
# 2) Probarlo a mano:  powershell -ExecutionPolicy Bypass -File deploy\duckdns-update.ps1

$DOMAIN = "kurug"          # solo el nombre, SIN ".duckdns.org"
$TOKEN  = "PEGA_TU_TOKEN_DE_DUCKDNS"

# ip= vacío => DuckDNS detecta tu IP automáticamente.
$resp = Invoke-RestMethod "https://www.duckdns.org/update?domains=$DOMAIN&token=$TOKEN&ip="
if ($resp -eq "OK") { Write-Host "DuckDNS actualizado OK" } else { Write-Host "DuckDNS respondió: $resp" }
