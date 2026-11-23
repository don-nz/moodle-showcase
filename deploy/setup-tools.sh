#!/usr/bin/env bash
# Set up a fresh Ubuntu 24.04 or 26.04 server for the quiz tool, behind a Cloudflare Tunnel.
#
#   sudo TOOL_URL=https://tools.aht-test.site MOODLE_URL=https://aht-test.site bash setup-tools.sh
#
# Optional: TOOL_NAME (default "Quiz Showcase"), TIMEZONE (default Australia/Sydney),
# CF_TUNNEL_TOKEN (otherwise you're asked).
#
# What it does: a service user, a Python environment in /opt/quiz-tool, the settings file
# /etc/quiz-tool.env, the quiz-tool systemd service (listening on 127.0.0.1:8000 only),
# a firewall allowing SSH only, and cloudflared. The code itself arrives with
# deploy/deploy.sh, run from the laptop afterwards.  See docs/server-setup.md.
set -euo pipefail

: "${TOOL_URL:?Set TOOL_URL, e.g. https://tools.aht-test.site}"
: "${MOODLE_URL:?Set MOODLE_URL, e.g. https://aht-test.site}"
TOOL_NAME="${TOOL_NAME:-Quiz Showcase}"
TIMEZONE="${TIMEZONE:-Australia/Sydney}"

[ "$(id -u)" = 0 ] || { echo "Run this with sudo."; exit 1; }
. /etc/os-release
case "$VERSION_CODENAME" in noble|resolute) ;; *) echo "This needs Ubuntu 24.04 or 26.04."; exit 1;; esac
cd /tmp
export DEBIAN_FRONTEND=noninteractive

echo "== System packages"
timedatectl set-timezone "$TIMEZONE"
apt-get update
apt-get -y full-upgrade
apt-get install -y python3 python3-venv rsync ufw unattended-upgrades curl ca-certificates

echo "== Service user and Python environment"
id quiztool >/dev/null 2>&1 || useradd --system --home /opt/quiz-tool --shell /usr/sbin/nologin quiztool
install -d /opt/quiz-tool
[ -x /opt/quiz-tool/.venv/bin/python ] || python3 -m venv /opt/quiz-tool/.venv

echo "== Settings"
cat > /etc/quiz-tool.env <<EOF
TOOL_BASE_URL=${TOOL_URL%/}
TOOL_ALLOWED_ISSUERS=${MOODLE_URL%/}
TOOL_DATA_DIR=/var/lib/quiz-tool
TOOL_NAME=$TOOL_NAME
EOF
chown root:quiztool /etc/quiz-tool.env
chmod 640 /etc/quiz-tool.env

cat > /etc/systemd/system/quiz-tool.service <<'EOF'
[Unit]
Description=Quiz Showcase LTI 1.3 tool
After=network.target

[Service]
User=quiztool
Group=quiztool
WorkingDirectory=/opt/quiz-tool
EnvironmentFile=/etc/quiz-tool.env
ExecStart=/opt/quiz-tool/.venv/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure

# Data (database, keys) lives in /var/lib/quiz-tool; everything else read-only.
StateDirectory=quiz-tool
StateDirectoryMode=0700
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable quiz-tool   # started by the first deploy

echo "== Firewall"
ufw allow OpenSSH >/dev/null
ufw --force enable

echo "== cloudflared"
curl -fsSL -o /usr/share/keyrings/cloudflare-main.gpg https://pkg.cloudflare.com/cloudflare-main.gpg
cat > /etc/apt/sources.list.d/cloudflared.sources <<'EOF'
Types: deb
URIs: https://pkg.cloudflare.com/cloudflared
Suites: any
Components: main
Signed-By: /usr/share/keyrings/cloudflare-main.gpg
EOF
apt-get update
apt-get install -y cloudflared
if [ -z "${CF_TUNNEL_TOKEN:-}" ]; then
  read -rsp "Paste the tools tunnel token (or press Enter to do it later): " CF_TUNNEL_TOKEN; echo
fi
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  cloudflared service install "$CF_TUNNEL_TOKEN"
else
  echo "Later: sudo cloudflared service install <token>"
fi

echo
echo "Done. Now run deploy/deploy.sh <this server> from the laptop to install the tool's code."
