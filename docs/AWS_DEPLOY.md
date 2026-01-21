# AWS ECS Deployment Runbook

This guide covers deploying the Flask application to AWS ECS Fargate, using Postgres (RDS) and S3.

## 1. Prerequisites
- AWS CLI configured
- AWS Copilot CLI installed (recommended for ECS) OR Terraform
- Docker running

## 2. Infrastructure Setup (AWS Copilot)
Initialize the application:
```bash
copilot init --app qr-app --name web --type "Load Balanced Web Service" --dockerfile Dockerfile
```

### Secrets (SSM)
Set the production secrets:
```bash
copilot secret init --name SECRET_KEY --values production=...
copilot secret init --name STRIPE_SECRET_KEY --values production=...
copilot secret init --name STRIPE_WEBHOOK_SECRET --values production=...
copilot secret init --name STRIPE_PRICE_MONTHLY --values production=...
copilot secret init --name STRIPE_PRICE_ANNUAL --values production=...
# Print pricing uses Stripe Price lookup keys; no print price env vars are required.
# Print products use Stripe Price lookup_keys (no STRIPE_PRICE_* env vars for prints).
# Database URL for RDS
copilot secret init --name DATABASE_URL --values production="postgresql://user:pass@endpoint:5432/dbname"
```

### Environment Variables
Edit `copilot/web/manifest.yml`:
```yaml
variables:
  FLASK_ENV: "production"
  BASE_URL: "https://your-alb-url.com"
  STORAGE_BACKEND: "s3"
  S3_BUCKET: "your-s3-bucket"
  AWS_REGION: "us-east-1"
```

## 3. Storage (S3)
Create an S3 bucket for assets:
```bash
aws s3 mb s3://qrapp-assets-prod
# Configure CORS if serving directly to browser (optional)
```
Ensure the ECS task role has permission to read/write this bucket. Add to `manifest.yml`:
```yaml
storage:
  volumes:
    # Ephemeral or EFS if needed, but we use S3 now
```
(Better: Add an IAM addon for S3 access).

## 4. Run Migrations (One-Off Task)
Before full traffic, run the migration:
```bash
copilot task run --command "python3 migrate.py" --env production
```
*Note: Our `migrate.py` uses `init_db` which is safe to run repeatedly.*

## 5. Deploy
```bash
copilot deploy --env production
```

## 6. Verification
1.  **Health Check**: `curl https://your-domain/healthz`
2.  **Upload Test**: Upload a property photo. Verify it appears in S3.
3.  **Print Job**: Submit a paid order.
    - Check DB: `SELECT * FROM print_jobs;`
    - Check S3: `s3://qrapp-assets-prod/print-jobs/`
