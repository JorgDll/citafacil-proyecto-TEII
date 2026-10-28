#!/usr/bin/env bash
# Ejecuta qa_exploratorias.py contra un backend con BD temporal y guarda la evidencia.
# Uso: run_exploratorias.sh <carpeta backend> <archivo de salida> [puerto]
#   PYTHON=/ruta/a/python3.12 si el python del sistema no sirve (ver README).
set -u
BACKEND=$(cd "$1" && pwd)
OUT=$(realpath "$2")
PORT=${3:-8799}
PY=${PYTHON:-python}
HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)

export DATABASE_URL="sqlite:///$TMP/qa.db" ADMIN_TOKEN="qa-clave-instalacion-123" \
  DEFAULT_COUNTRY=PA BUSINESS_TIMEZONE=America/Panama \
  TWILIO_ACCOUNT_SID= TWILIO_AUTH_TOKEN= TWILIO_WHATSAPP_FROM=

cd "$BACKEND"
"$PY" seed.py > /dev/null
"$PY" -m uvicorn app.main:app --port "$PORT" > "$TMP/server.log" 2>&1 &
SERVER=$!
for _ in $(seq 30); do curl -s "localhost:$PORT/api/services" > /dev/null && break; sleep 0.5; done

{
  echo "# Pruebas exploratorias de QA"
  echo "# Código: $(git -C "$BACKEND" log -1 --format='%h %s')"
  echo "# Fecha: $(date '+%Y-%m-%d %H:%M %Z') · Python: $("$PY" --version)"
  echo
  BASE_URL="http://localhost:$PORT" "$PY" "$HERE/qa_exploratorias.py"
  echo
  echo "# Recordatorios enviados (log del servidor, modo demo WhatsApp)"
  grep -A7 "te recordamos" "$TMP/server.log"
} > "$OUT" 2>&1

kill "$SERVER"
rm -rf "$TMP"
