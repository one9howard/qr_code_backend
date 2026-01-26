#!/usr/bin/env python3
"""
Async Worker for InSite Signs.
Polls `async_jobs` table and executes tasks.

Job Types:
- 'fulfill_order': Generates Stripe/Pdf/Shipping data and submits to print provider.
- 'generate_listing_kit': Generates ZIP assets for download.
"""
import sys
import time
import logging
import traceback
import signal
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from app import create_app
from services.async_jobs import claim_batch, mark_done, mark_failed
from services.fulfillment import fulfill_order
from services.listing_kits import create_or_get_kit, generate_kit
from models import Order

# Configure Logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] [Worker] %(levelname)s: %(message)s'
)
logger = logging.getLogger("worker")

# Graceful Shutdown
SHUTDOWN = False
def handle_sigterm(signum, frame):
    global SHUTDOWN
    logger.info("Received SIGTERM. Finishing current batch...")
    SHUTDOWN = True

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def process_job(job):
    job_id = job['id']
    job_type = job['job_type']
    payload = job['payload']
    
    logger.info(f"Processing Job {job_id}: {job_type}")
    
    try:
        if job_type == 'fulfill_order':
            order_id = payload.get('order_id')
            if not order_id:
                raise ValueError("Missing order_id in payload")
                
            success = fulfill_order(order_id)
            if not success:
                raise RuntimeError("Fulfillment returned failure status")
                
        elif job_type == 'generate_listing_kit':
            order_id = payload.get('order_id')
            if not order_id:
                raise ValueError("Missing order_id in payload")
            
            # Fetch user/property to ensure Kit exists
            order = Order.get(order_id)
            if not order:
                raise ValueError(f"Order {order_id} not found")
                
            # Create/Get Kit Record
            kit = create_or_get_kit(order.user_id, order.property_id)
            
            # Generate
            generate_kit(kit['id'])
            
        else:
            raise ValueError(f"Unknown job_type: {job_type}")
            
        mark_done(job_id)
        
    except Exception as e:
        logger.error(f"Job {job_id} Failed: {e}")
        traceback.print_exc()
        mark_failed(job_id, error=str(e), can_retry=True)

def run_worker():
    app = create_app()
    
    with app.app_context():
        logger.info("Worker Started. Polling for jobs...")
        
        while not SHUTDOWN:
            try:
                # Claim jobs
                jobs = claim_batch(limit=10)
                
                if not jobs:
                    # Sleep if idle
                    time.sleep(5)
                    continue
                
                for job in jobs:
                    if SHUTDOWN: break
                    process_job(job)
                    
            except Exception as e:
                logger.error(f"Worker Loop Error: {e}")
                time.sleep(5) # Brief pause on crash loop
                
        logger.info("Worker Stopped.")

if __name__ == "__main__":
    # Robust DB Verification (Re-using wait_for_db logic or implementing retry)
    from scripts.wait_for_db import main as wait_main
    if wait_main() != 0:
        logger.critical("DB Not Reachable. Worker exiting.")
        sys.exit(1)
        
    run_worker()
