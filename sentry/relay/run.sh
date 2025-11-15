#!/usr/bin/env sh
set -euo pipefail

CONFIG_DIR="/tmp/relay"
mkdir -p "${CONFIG_DIR}"

cat <<EOF >"${CONFIG_DIR}/config.yml"
relay:
  mode: proxy
  upstream: ${SENTRY_RELAY_UPSTREAM_URL:-https://sentry.io/}
  host: 0.0.0.0
  port: ${SENTRY_RELAY_PORT:-3000}

auth:
  credentials: ${CONFIG_DIR}/credentials.json

logging:
  level: info

processing:
  enabled: false
EOF

cp /etc/relay/credentials.json "${CONFIG_DIR}/credentials.json"

exec relay run --config "${CONFIG_DIR}"
