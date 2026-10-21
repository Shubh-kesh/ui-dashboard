#!/usr/bin/env bash
# Idempotent local MSSQL (Azure SQL Edge) starter.
#
# Fixes the two common "docker run" failures:
#   * "container name /aikyc-mssql is already in use"  -> reuse/start it
#   * "Bind for 0.0.0.0:1433 failed: port is already allocated" -> reuse it
#
# Usage: scripts/start-db.sh
set -euo pipefail

NAME="${MSSQL_CONTAINER_NAME:-aikyc-mssql}"
IMAGE="${MSSQL_IMAGE:-mcr.microsoft.com/azure-sql-edge}"
PASSWORD="${MSSQL_SA_PASSWORD:-LocalDev123!}"
PORT="${MSSQL_PORT:-1433}"
VOLUME="${MSSQL_VOLUME:-aikyc-mssql-data}"

if docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "Reusing existing container '$NAME'..."
  if ! docker inspect "$NAME" --format '{{range .Mounts}}{{if eq .Destination "/var/opt/mssql"}}{{.Type}}{{end}}{{end}}' | grep -q volume; then
    echo "WARNING: '$NAME' has no persistent volume on /var/opt/mssql." >&2
    echo "         A container recreate will lose the databases." >&2
    echo "         Recreate it once with: docker rm -f $NAME && $0" >&2
  fi
  docker start "$NAME" >/dev/null 2>&1 || true
else
  echo "Creating container '$NAME'..."
  docker run -d --name "$NAME" \
    -e ACCEPT_EULA=Y \
    -e MSSQL_SA_PASSWORD="$PASSWORD" \
    -p "${PORT}:1433" \
    -v "${VOLUME}:/var/opt/mssql" \
    --restart unless-stopped \
    "$IMAGE" >/dev/null
fi

echo -n "Waiting for MSSQL on localhost:${PORT}"
for _ in $(seq 1 60); do
  if docker exec "$NAME" /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/1433' >/dev/null 2>&1; then
    echo " — ready"
    exit 0
  fi
  echo -n "."
  sleep 2
done

echo
echo "MSSQL did not become ready in time; check 'docker logs $NAME'" >&2
exit 1
