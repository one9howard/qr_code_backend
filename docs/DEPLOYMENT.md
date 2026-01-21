# Production Deployment Guide (Ubuntu)

This guide establishes a "correct forever" deployment using `systemd`, `gunicorn`, `nginx`, and `postgres` with **strict security, state isolation, and observable migrations**.

## 0. Prerequisites
- Ubuntu Server (20.04+)
- Python 3.8+ (`sudo apt install python3-venv python3-pip`)
- Nginx (`sudo apt install nginx`)
- **PostgreSQL 14+** (`sudo apt install postgresql postgresql-contrib`)
- **Systemd v235+** (Standard on Ubuntu 20.04+)

## 1. Initial Setup

### A. Dedicated Service User
```bash
# Create system user 'qrapp' with no login access
sudo useradd -r -s /bin/false qrapp
# Add to www-data group (for nginx socket access)
sudo usermod -aG www-data qrapp
```

### B. Code Placement
```bash
sudo mkdir -p /opt/qr_code_backend
sudo chown -R $USER:www-data /opt/qr_code_backend
git clone https://github.com/StartYourSystems/qr_code_backend.git /opt/qr_code_backend
cd /opt/qr_code_backend
```

### C. Database Setup
```bash
sudo -u postgres psql
# In psql:
CREATE DATABASE qrapp;
CREATE USER qrapp WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE qrapp TO qrapp;
\q
```

### D. Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Secrets & Configuration

Create `/etc/qr-secrets.env` with **root:root 600** permissions.

```bash
sudo touch /etc/qr-secrets.env
sudo chmod 600 /etc/qr-secrets.env
sudo nano /etc/qr-secrets.env
```

> [!IMPORTANT]
> The app will **crash at startup** if any required variable is missing or whitespace-only.

**Required Content:**
```ini
FLASK_ENV=production
BASE_URL=https://yourdomain.com
DATABASE_URL=postgresql://qrapp:secure_password@localhost/qrapp

# Secrets (random, high-entropy strings)
SECRET_KEY=<random-string>
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
PRINT_SERVER_TOKEN=<random-string>

# Stripe Price IDs (REQUIRED - from Stripe Dashboard)
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SIGN=price_...
```

> [!NOTE]
> `INSTANCE_DIR` and `PRINT_INBOX_DIR` are injected by systemd (see unit files).
> Do NOT set them in `/etc/qr-secrets.env`.

## 3. Nginx Configuration

### A. Proxy to Application Socket
```bash
sudo nano /etc/nginx/sites-available/qrapp
```

```nginx
server {
    listen 80;
    server_name _;

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/qrapp/qrapp.sock;
    }

    # Serve user-generated content from StateDirectory
    location /uploads/ {
        alias /var/lib/qrapp/uploads/;
    }
    location /qr/ {
        alias /var/lib/qrapp/qr/;
    }
    location /signs/ {
        alias /var/lib/qrapp/signs/;
    }
}
```

### B. Enable and Restart
```bash
sudo ln -sf /etc/nginx/sites-available/qrapp /etc/nginx/sites-enabled/qrapp
sudo rm -f /etc/nginx/sites-enabled/default  # Optional: disable default
sudo nginx -t
sudo systemctl restart nginx
```

## 4. Systemd Service Installation

```bash
sudo cp systemd/qrapp.service /etc/systemd/system/
sudo cp systemd/qrprint.service /etc/systemd/system/

# Verify syntax (should produce no errors)
sudo systemd-analyze verify /etc/systemd/system/qrapp.service /etc/systemd/system/qrprint.service

# Reload and start
sudo systemctl daemon-reload
sudo systemctl enable qrapp qrprint
sudo systemctl restart qrapp qrprint
```

## 5. Verification Checklist

### A. Service Status
```bash
sudo systemctl status qrapp qrprint
# Both should be: active (running)
```

### B. State Directory
```bash
ls -la /var/lib/qrapp
# Should exist and be owned by qrapp:www-data (or qrapp:qrapp)
```

### C. Health Endpoints
```bash
# Main app (via Nginx)
curl -I http://localhost/healthz
# Expected: HTTP/1.1 200 OK

# Print server (localhost only)
curl http://127.0.0.1:8080/health
# Expected: {"status": "ok"}
```

### D. Migration Verification
```bash
# Check postgres connection and tables
sudo -u qrapp psql $DATABASE_URL -c "SELECT * FROM alembic_version;"
# Should show applied migration IDs
```

### E. Logs
```bash
journalctl -u qrapp -f
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "PRODUCTION STARTUP FAILED" | Missing env vars | Check `/etc/qr-secrets.env` |
| "permission denied" | Wrong ownership | `sudo chown -R qrapp:www-data /var/lib/qrapp` |
| 502 Bad Gateway | Socket path mismatch | Verify Nginx `proxy_pass` matches `/run/qrapp/qrapp.sock` |
| Migration lock error | `/run/qrapp` missing | Ensure `RuntimeDirectory=qrapp` in unit file |
