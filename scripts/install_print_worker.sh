#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo ./install_print_worker.sh https://app.insitesigns.com <PRINT_SERVER_TOKEN> [poll_seconds]

BASE_URL="${1:-}"
TOKEN="${2:-}"
POLL_SECONDS="${3:-10}"

if [[ -z "${BASE_URL}" || -z "${TOKEN}" ]]; then
  echo "Usage: sudo $0 <BASE_URL> <PRINT_SERVER_TOKEN> [poll_seconds]" >&2
  exit 2
fi

INSTALL_DIR="/opt/insite_print_worker"
INBOX_DIR="${INSTALL_DIR}/inbox"
ENV_FILE="/etc/insite_print_worker.env"
SERVICE_FILE="/etc/systemd/system/insite-worker.service"

echo "[Installer] Installing InSite Signs print worker..."

# 1) Create service user (no login)
if ! id -u insite-worker >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin insite-worker
  echo "[Installer] Created user: insite-worker"
fi

# 2) Create directories
mkdir -p "${INBOX_DIR}" "${INSTALL_DIR}/logs"
chown -R insite-worker:insite-worker "${INSTALL_DIR}"

# 3) Create virtualenv and install minimal deps
if [[ ! -x "${INSTALL_DIR}/venv/bin/python" ]]; then
  python3 -m venv "${INSTALL_DIR}/venv"
  "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip >/dev/null
  "${INSTALL_DIR}/venv/bin/pip" install requests >/dev/null
  echo "[Installer] Created venv and installed requests"
fi

# 4) Install worker script
cp -f "$(dirname "$0")/print_worker.py" "${INSTALL_DIR}/print_worker.py"
chown insite-worker:insite-worker "${INSTALL_DIR}/print_worker.py"
chmod 755 "${INSTALL_DIR}/print_worker.py"

# 5) Write environment file
cat > "${ENV_FILE}" <<EOF
INSITE_BASE_URL=${BASE_URL}
PRINT_SERVER_TOKEN=${TOKEN}
PRINT_WORKER_INBOX=${INBOX_DIR}
PRINT_WORKER_POLL_SECONDS=${POLL_SECONDS}
PRINT_WORKER_LIMIT=10
PRINT_WORKER_HTTP_TIMEOUT=20
EOF
chmod 600 "${ENV_FILE}"

# 6) Install systemd unit
cp -f "$(dirname "$0")/insite-worker.service" "${SERVICE_FILE}"
chmod 644 "${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable insite-worker.service
systemctl restart insite-worker.service

echo "[Installer] Installed and started insite-worker"
echo "[Installer] Check logs: journalctl -u insite-worker -f"
