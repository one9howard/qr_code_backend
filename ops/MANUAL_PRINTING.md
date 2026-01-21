# Manual Printing Workflow

We use a "pull" model where a local worker polls the cloud for print jobs.

## Overview
1.  User pays for sign on Cloud App.
2.  Cloud App saves PDF to S3 and queues a `print_jobs` record.
3.  Local Worker (`scripts/print_worker.py`) polls Cloud API.
4.  Worker downloads PDF + Shipping Info to local inbox.
5.  Operator prints PDF and Shipping Label manually.

## Setup Local Worker

1.  **Requirement**: Python 3.9+ installed on the print station.
2.  **Script**: Use the canonical worker script at `scripts/print_worker.py`.

### Installation
You can move `scripts/print_worker.py` to your print station or check out the repo.

### Configuration
Set environment variables (in `.env` or system):

```bash
export INSITE_BASE_URL="https://insitesigns.com"
export PRINT_JOBS_TOKEN="<prod-token-from-railway>"
export PRINT_WORKER_INBOX="./inbox"
```

### Running the Worker
```bash
python3 scripts/print_worker.py --poll-seconds 60
```

The worker will:
- Poll for unclaimed jobs.
- Download PDFs to `inbox/`.
- Write metadata JSON sidecars.
- ACK jobs as downloaded in the cloud.

## Production Deployment
See `scripts/install_print_worker.sh` (if available) or simply run under Systemd/Supervisor using the command above.
