#!/bin/sh
set -eu

# SCRIPT_DIR robusto al path de invocación:
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# (Recomendado) Fijar el cwd al del script para que rutas relativas funcionen
cd "$SCRIPT_DIR"

# Si common.sh está una carpeta arriba del script:
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_SH="${COMMON_SH:-"$ROOT_DIR/common.sh"}"

if [ ! -f "$COMMON_SH" ]; then
  echo "❌ No se encontró common.sh en: $COMMON_SH" >&2
  exit 1
fi
. "$COMMON_SH"

SCRIPT_NAME="$(basename "$0")"

compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi

  echo "❌ No se encontró docker compose ni docker-compose" >&2
  exit 1
}

# Encabezado e identificación del script en ejecución
h "mysql-profiler | $SCRIPT_NAME"
log "[INFO] Ejecutando $SCRIPT_NAME desde $SCRIPT_DIR"

# Stop Docker Compose services
log "[INFO] Stopping Docker Compose MYSQL Profiler services..."
compose down --remove-orphans

# Build Docker Compose services
log "[INFO] Build Docker Compose MYSQL Profiler..."
compose build --no-cache

# Start Docker Compose services
log "[INFO] Starting Docker Compose MYSQL Profiler services..."
compose up -d

log "[INFO] Docker Compose MYSQL Profiler services started."
log "[INFO] UI disponible en http://192.168.50.32:38110"
log "[INFO] Si no defines WEB_AUTH_PASSWORD o WEB_AUTH_PASSWORD_HASH, se generará una contraseña en mysql-profiler/data/admin-password.txt"
