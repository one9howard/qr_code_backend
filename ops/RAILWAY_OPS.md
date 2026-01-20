# Railway Operations Guide

## Environment Variables

### Required for Production
| Variable | Description | Example |
|----------|-------------|---------|
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `your-email@gmail.com` |
| `SMTP_PASS` | SMTP password (App Password for Gmail) | `xxxx xxxx xxxx xxxx` |
| `NOTIFY_EMAIL_FROM` | Sender email address | `noreply@insitesigns.com` |
| `SMTP_USE_TLS` | Enable TLS (default: true) | `true` |

### Optional
| Variable | Description | Default |
|----------|-------------|---------|
| `FREE_TIER_RETENTION_DAYS` | Days before unpaid listings expire | `7` |

## Background Jobs (Cron)

### Cleanup Expired Properties
Run the cleanup command to delete expired unpaid properties:

```bash
flask cleanup-expired
```

### Recommended Schedule
Run once per hour:
```text
0 * * * *
```

## Migrations

Migrations run automatically on deploy via entrypoint. To run manually:
```bash
flask db upgrade
```

Or via Alembic directly:
```bash
alembic upgrade head
```

