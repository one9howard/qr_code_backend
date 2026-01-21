# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by emailing security@example.com (update with your actual security contact).

## Secrets Management

> **⚠️ CRITICAL: Secrets must NEVER be committed to the repository.**

### Files that must remain in `.gitignore`:
- `.env` - Contains all secrets (Stripe keys, database credentials, etc.)

- `*.db-journal`, `*.db-wal`, `*.db-shm` - Database temp files
- `private/` - Private PDFs and preview images
- `print_inbox/` - Print job PDFs

### Required Environment Variables

See `.env.example` for the full list. Key secrets include:
- `SECRET_KEY` - Flask session encryption
- `STRIPE_SECRET_KEY` - Stripe API key
- `STRIPE_WEBHOOK_SECRET` - Webhook signature verification
- `PRINT_JOBS_TOKEN` - Print server authentication

### Before Committing

Always verify you're not committing secrets:
```bash
git diff --cached | grep -i "secret\|password\|key\|token"
```

## Production Security Checklist

- [ ] All secrets loaded from environment variables
- [ ] HTTPS enabled (via nginx/certbot)
- [ ] `TRUST_PROXY_HEADERS=true` set when behind nginx
- [ ] Stripe webhook signature verification enabled
- [ ] Session cookies set to `secure=True` in production
- [ ] Database backups encrypted at rest
