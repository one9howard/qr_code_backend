#!/usr/bin/env python3
"""InSite Signs Print Worker.

Polls the cloud app for queued print jobs, downloads PDFs, and ACKs receipt.

Workflow:
  1) POST {BASE_URL}/api/print-jobs/claim?limit=N
  2) For each job: GET {BASE_URL}/api/print-jobs/<job_id>/pdf
  3) Write PDF to inbox + write JSON manifest
  4) POST {BASE_URL}/api/print-jobs/<job_id>/downloaded

Auth:
  Authorization: Bearer <PRINT_JOBS_TOKEN>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    return base_url


def auth_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "insite-print-worker/1.0",
    }


def safe_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def claim_jobs(base_url: str, token: str, limit: int, timeout: int) -> List[Dict[str, Any]]:
    url = f"{base_url}/api/print-jobs/claim"
    resp = requests.post(url, headers=auth_headers(token), params={"limit": limit}, timeout=timeout)
    if resp.status_code == 401:
        raise RuntimeError("Unauthorized: PRINT_JOBS_TOKEN is incorrect")
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    return payload.get("jobs", [])


def download_pdf(download_url: str, token: str, timeout: int) -> bytes:
    resp = requests.get(download_url, headers=auth_headers(token), timeout=timeout)
    if resp.status_code == 401:
        raise RuntimeError("Unauthorized when downloading PDF (token mismatch)")
    resp.raise_for_status()
    return resp.content


def ack_downloaded(base_url: str, job_id: str, token: str, timeout: int) -> None:
    url = f"{base_url}/api/print-jobs/{job_id}/downloaded"
    resp = requests.post(url, headers=auth_headers(token), timeout=timeout)
    if resp.status_code == 401:
        raise RuntimeError("Unauthorized when ACKing downloaded")
    resp.raise_for_status()


def process_job(
    *,
    job: Dict[str, Any],
    base_url: str,
    token: str,
    inbox_dir: Path,
    timeout: int,
    dry_run: bool,
) -> bool:
    job_id = job.get("job_id")
    order_id = job.get("order_id")
    download_url = job.get("download_url")
    if not job_id or not download_url:
        print(f"[worker] Skipping malformed job payload: {job}")
        return False

    pdf_name = f"{job_id}.pdf"
    json_name = f"{job_id}.json"
    pdf_path = inbox_dir / pdf_name
    json_path = inbox_dir / json_name

    manifest = {
        "job_id": job_id,
        "order_id": order_id,
        "claimed_payload": job,
        "downloaded_at": utc_now_iso(),
    }

    # If the PDF already exists, we assume prior download succeeded.
    # We still ACK to unblock the pipeline.
    if pdf_path.exists() and json_path.exists():
        print(f"[worker] Already present: {pdf_path.name} (ACKing)")
        if not dry_run:
            ack_downloaded(base_url, job_id, token, timeout)
        return True

    print(f"[worker] Downloading job_id={job_id} order_id={order_id}")

    if dry_run:
        safe_write_json(json_path, manifest)
        return True

    pdf_bytes = download_pdf(download_url, token, timeout)
    safe_write_bytes(pdf_path, pdf_bytes)
    safe_write_json(json_path, manifest)
    ack_downloaded(base_url, job_id, token, timeout)
    return True


def run_loop(
    *,
    base_url: str,
    token: str,
    inbox_dir: Path,
    poll_seconds: float,
    limit: int,
    timeout: int,
    once: bool,
    dry_run: bool,
) -> int:
    base_url = normalize_base_url(base_url)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    print(f"[worker] base_url={base_url}")
    print(f"[worker] inbox_dir={inbox_dir}")
    print(f"[worker] poll_seconds={poll_seconds} limit={limit} timeout={timeout} once={once} dry_run={dry_run}")

    while True:
        try:
            jobs = claim_jobs(base_url, token, limit=limit, timeout=timeout)
        except Exception as e:
            print(f"[worker] Claim error: {e}")
            jobs = []

        if jobs:
            print(f"[worker] Claimed {len(jobs)} job(s)")
            for job in jobs:
                try:
                    process_job(
                        job=job,
                        base_url=base_url,
                        token=token,
                        inbox_dir=inbox_dir,
                        timeout=timeout,
                        dry_run=dry_run,
                    )
                except Exception as e:
                    job_id = job.get("job_id")
                    print(f"[worker] Job failed job_id={job_id}: {e}")
        else:
            print("[worker] No jobs")

        if once:
            return 0

        time.sleep(poll_seconds)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InSite Signs print worker")
    p.add_argument("--base-url", default=os.environ.get("INSITE_BASE_URL", ""), help="Cloud app base URL")
    p.add_argument("--token", default=os.environ.get("PRINT_JOBS_TOKEN", ""), help="Bearer token")
    p.add_argument("--inbox-dir", default=os.environ.get("PRINT_WORKER_INBOX", "/opt/insite_print_worker/inbox"))
    p.add_argument("--poll-seconds", type=float, default=float(os.environ.get("PRINT_WORKER_POLL_SECONDS", "10")))
    p.add_argument("--limit", type=int, default=int(os.environ.get("PRINT_WORKER_LIMIT", "10")))
    p.add_argument("--timeout", type=int, default=int(os.environ.get("PRINT_WORKER_HTTP_TIMEOUT", "20")))
    p.add_argument("--once", action="store_true", help="Run a single polling iteration and exit")
    p.add_argument("--dry-run", action="store_true", help="Do not download/ack; just write manifests")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if not args.base_url:
        print("[worker] ERROR: --base-url (or INSITE_BASE_URL) is required")
        return 2
    if not args.token:
        print("[worker] ERROR: --token (or PRINT_JOBS_TOKEN) is required")
        return 2

    inbox_dir = Path(args.inbox_dir)
    return run_loop(
        base_url=args.base_url,
        token=args.token,
        inbox_dir=inbox_dir,
        poll_seconds=args.poll_seconds,
        limit=max(1, min(args.limit, 50)),
        timeout=max(5, args.timeout),
        once=args.once,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
