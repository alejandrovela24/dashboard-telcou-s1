#!/bin/sh
set -e

mkdir -p .streamlit
cat > .streamlit/secrets.toml <<EOF
API_BASE_URL = "${API_BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN = "${ADMIN_TOKEN:-}"
EOF

exec streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0 --server.headless true
