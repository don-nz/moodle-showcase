#!/usr/bin/env bash
# Set up a fresh Ubuntu 24.04 server as the showcase Moodle, behind a Cloudflare Tunnel.
#
#   sudo MOODLE_URL=https://moodle.aht-test.site ADMIN_EMAIL=you@example.com bash setup-moodle.sh
#
# Optional: SITE_NAME (default "Quiz Showcase"), TIMEZONE (default Australia/Sydney),
# MOODLE_BRANCH (default MOODLE_503_STABLE), CF_TUNNEL_TOKEN (otherwise you're asked).
#
# What it does: Moodle 5.3 on nginx + PHP 8.3 + PostgreSQL 17, nginx listening on
# 127.0.0.1 only (Cloudflare's tunnel is the only way in), firewall allowing SSH only,
# Moodle's cron job, and cloudflared. Passwords are generated and saved to
# /root/moodle-credentials.  See docs/server-setup.md.
set -euo pipefail

: "${MOODLE_URL:?Set MOODLE_URL, e.g. https://moodle.aht-test.site}"
: "${ADMIN_EMAIL:?Set ADMIN_EMAIL (email for the Moodle admin account)}"
SITE_NAME="${SITE_NAME:-Quiz Showcase}"
TIMEZONE="${TIMEZONE:-Australia/Sydney}"
MOODLE_BRANCH="${MOODLE_BRANCH:-MOODLE_503_STABLE}"
PHP=8.3
PG=17
PGDG_FINGERPRINT=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
MOODLE_URL="${MOODLE_URL%/}"

[ "$(id -u)" = 0 ] || { echo "Run this with sudo."; exit 1; }
. /etc/os-release
[ "$VERSION_CODENAME" = noble ] || {
  echo "This needs Ubuntu 24.04. Moodle 5.3 doesn't support the PHP 8.5 in Ubuntu 26.04."; exit 1; }
[ -e /var/www/moodle/config.php ] && { echo "Moodle is already installed here."; exit 1; }
cd /tmp
export DEBIAN_FRONTEND=noninteractive

echo "== System packages"
timedatectl set-timezone "$TIMEZONE"
apt-get update
apt-get -y full-upgrade
apt-get install -y curl ca-certificates gnupg git ufw unattended-upgrades nginx \
  php$PHP-fpm php$PHP-cli php$PHP-pgsql php$PHP-curl php$PHP-gd php$PHP-intl php$PHP-mbstring \
  php$PHP-xml php$PHP-zip php$PHP-soap php$PHP-opcache php$PHP-readline

echo "== PostgreSQL $PG from the PostgreSQL project's own repository (Ubuntu 24.04 ships 16; Moodle 5.3 needs 17)"
install -d /usr/share/postgresql-common/pgdg
key=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
curl -fsSL -o "$key" https://www.postgresql.org/media/keys/ACCC4CF8.asc
fpr=$(gpg --show-keys --with-colons "$key" 2>/dev/null | awk -F: '/^fpr/{print $10; exit}')
[ "$fpr" = "$PGDG_FINGERPRINT" ] || { echo "PostgreSQL signing key fingerprint is $fpr, expected $PGDG_FINGERPRINT. Stopping."; exit 1; }
cat > /etc/apt/sources.list.d/pgdg.sources <<EOF
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: $VERSION_CODENAME-pgdg
Components: main
Signed-By: $key
EOF
apt-get update
apt-get install -y postgresql-$PG

echo "== Database"
DB_PASS=$(openssl rand -hex 24)
ADMIN_PASS="$(openssl rand -hex 8)Aa1!"
sudo -u postgres psql -q -c "CREATE USER moodleuser WITH PASSWORD '$DB_PASS';"
sudo -u postgres createdb -E UTF8 -T template0 -O moodleuser moodle
umask 077
cat > /root/moodle-credentials <<EOF
Moodle:   $MOODLE_URL
Admin:    admin / $ADMIN_PASS
Database: moodle / moodleuser / $DB_PASS
EOF
umask 022

echo "== PHP settings"
printf 'max_input_vars = 5000\nmemory_limit = 256M\nupload_max_filesize = 100M\npost_max_size = 100M\n' \
  | tee /etc/php/$PHP/fpm/conf.d/99-moodle.ini /etc/php/$PHP/cli/conf.d/99-moodle.ini >/dev/null
systemctl restart php$PHP-fpm

echo "== Moodle code ($MOODLE_BRANCH)"
git clone -q -b "$MOODLE_BRANCH" --depth 1 https://github.com/moodle/moodle.git /var/www/moodle
install -d -o www-data -g www-data -m 0750 /var/moodledata

echo "== nginx (local only; the tunnel connects to it)"
cat > /etc/nginx/sites-available/moodle <<'EOF'
server {
    listen 127.0.0.1:80 default_server;
    server_name _;

    root /var/www/moodle/public;
    index index.php;
    client_max_body_size 100M;

    location / {
        try_files $uri $uri/ /r.php;
    }

    location ~ [^/]\.php(/|$) {
        fastcgi_split_path_info ^(.+\.php)(/.*)$;
        fastcgi_index index.php;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
        include fastcgi_params;
        fastcgi_param PATH_INFO $fastcgi_path_info;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    }

    location ~ /\.(?!well-known) { deny all; }
}
EOF
ln -sf /etc/nginx/sites-available/moodle /etc/nginx/sites-enabled/moodle
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "== Installing Moodle (takes a few minutes)"
chown www-data /var/www/moodle   # the installer writes config.php here
sudo -u www-data php /var/www/moodle/admin/cli/install.php \
  --non-interactive --agree-license --lang=en \
  --wwwroot="$MOODLE_URL" --dataroot=/var/moodledata \
  --dbtype=pgsql --dbhost=localhost --dbname=moodle --dbuser=moodleuser --dbpass="$DB_PASS" \
  --fullname="$SITE_NAME" --shortname="Showcase" \
  --adminuser=admin --adminpass="$ADMIN_PASS" --adminemail="$ADMIN_EMAIL"
chown root /var/www/moodle
# Cloudflare ends HTTPS before the request reaches nginx.
sed -i '/lib\/setup\.php/i $CFG->sslproxy = true;' /var/www/moodle/config.php
chown root:www-data /var/www/moodle/config.php
chmod 640 /var/www/moodle/config.php

echo "== Cron and firewall"
echo '* * * * * /usr/bin/php /var/www/moodle/admin/cli/cron.php >/dev/null 2>&1' | crontab -u www-data -
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
  read -rsp "Paste the Moodle tunnel token (or press Enter to do it later): " CF_TUNNEL_TOKEN; echo
fi
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  cloudflared service install "$CF_TUNNEL_TOKEN"
else
  echo "Later: sudo cloudflared service install <token>"
fi

echo
echo "Done. Moodle will be at $MOODLE_URL once the tunnel is connected."
echo "Admin login and passwords are in /root/moodle-credentials (sudo cat /root/moodle-credentials)."
