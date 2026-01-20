# Manual Fulfillment Workflow

## Overview
The InSite Signs fulfillment system uses an **Atomic Claim** model.
The central Print Server (cloud) queues file generation jobs.
A lightweight Worker Script (on-premise or local) polls for claimed jobs, downloads them, and marks them as downloaded.

## Architecture

1.  **Cloud App (`routes/printing.py`)**:
    *   `POST /api/print-jobs/claim`: Atomically locks and claims pending jobs.
    *   `GET /api/print-jobs/<id>/pdf`: Authenticated PDF download.
    *   `POST /api/print-jobs/<id>/downloaded`: Acknowledges receipt.

2.  **Worker (`scripts/print_worker.py`)**:
    *   Polls the API.
    *   Downloads files to `/opt/insite_print_worker/inbox`.
    *   Writes a JSON manifest for each job.

## Setup

### 1. Install Worker
On the print server machine (Ubuntu/Debian):

```bash
cd scripts
sudo ./install_print_worker.sh https://app.insitesigns.com <YOUR_PRINT_TOKEN>
```

This will:
- Create `/opt/insite_print_worker`.
- Set up systemd service `insite-worker`.
- Start polling.

Troubleshooting:
```bash
journalctl -u insite-worker -f
```

### 2. Manual Verification
Check the inbox:
```bash
ls -l /opt/insite_print_worker/inbox
```
You should see `.pdf` and `.json` files appearing.

## API Reference

### Claim Jobs
`POST /api/print-jobs/claim?limit=5`
Headers: `Authorization: Bearer <TOKEN>`

Response:
```json
{
  "jobs": [
    {
      "job_id": "uuid...",
      "download_url": "https://...",
      ...
    }
  ]
}
```

### Download PDF
`GET /api/print-jobs/<job_id>/pdf`
Headers: `Authorization: Bearer <TOKEN>`

### Ack Download
`POST /api/print-jobs/<job_id>/downloaded`
Headers: `Authorization: Bearer <TOKEN>`
