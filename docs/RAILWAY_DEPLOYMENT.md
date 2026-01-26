# Railway / Production Deployment Guide

## Services
The InSite Signs platform requires TWO services to run in production:

1.  **Web Service**
    *   **Command**: `bash scripts/railway_start.sh`
    *   **Variables**: `SERVICE_ROLE=web` (Default)
    *   **Port**: 5000 (HTTP)
    *   **Purpose**: Handle user traffic, API requests, and Webhooks.

2.  **Worker Service**
    *   **Command**: `bash scripts/railway_start.sh`
    *   **Variables**: `SERVICE_ROLE=worker`
    *   **Port**: N/A (Background Process)
    *   **Purpose**: Process order fulfillment, generate listing kits, and handle async tasks.
    *   **CRITICAL**: Without this worker, paid orders accept payment but remain in 'submitted_to_printer' without ever being sent to the provider.

## Environment Variables
Both services must share the same environment variables, especially:
*   `DATABASE_URL`
*   `STRIPE_SECRET_KEY`
*   `APP_STAGE` (prod)
*   `AWS_REGION`, `S3_BUCKET`, etc.

## Deployment Steps
1.  Connect GitHub repo to Railway.
2.  Deploy the main **Web** service.
3.  Add a second service (or duplicate the first).
4.  Override the **Start Command** for the second service to: `python scripts/async_worker.py`.
5.  Ensure both are connected to the same shared PostgreSQL database.
