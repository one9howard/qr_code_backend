
import time
import sys
import argparse
import traceback
import logging

# Bootstrap path
import os
sys.path.append(os.getcwd())

from app import create_app
from services.async_jobs import claim_batch, mark_done, mark_failed
from services.fulfillment import fulfill_order
from services.listing_kits import generate_kit, create_or_get_kit

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("worker")

def process_job(job):
    job_id = job['id']
    job_type = job['job_type']
    payload = job['payload']
    
    # Normalized payload loading
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
        
    logger.info(f"Processing Job {job_id}: {job_type}")
    
    try:
        if job_type == 'fulfill_order':
            order_id = payload.get('order_id')
            if not order_id:
                raise ValueError("Missing order_id")
            
            logger.info(f"Fulfilling order {order_id}...")
            # Ideally fulfill_order should raise exception on failure, 
            # but currently it returns bool.
            # We assume it handles its own internal logging?
            # Actually we want to know if it SUCCEEDED.
            success = fulfill_order(order_id)
            if not success:
                raise RuntimeError("Fulfillment service returned False")
                
        elif job_type == 'generate_listing_kit':
            kit_id = payload.get('kit_id')
            if not kit_id:
                 # Check for order_id/property_id fallback
                 # If webhook passes order_id, we need to resolve kit first?
                 # Webhook logic says: "if final_type == listing_kit -> enqueue ... payload:{order_id:<id>}"
                 # So we need to handle order_id to kit_id resolution here if kit_id missing.
                 order_id = payload.get('order_id')
                 if order_id:
                     from database import get_db
                     db = get_db()
                     # Resolve user/prop from order
                     row = db.execute("SELECT user_id, property_id FROM orders WHERE id = %s", (order_id,)).fetchone()
                     if not row:
                         raise ValueError(f"Order {order_id} not found")
                     kit = create_or_get_kit(row['user_id'], row['property_id'])
                     kit_id = kit['id']
                     logger.info(f"Resolved Kit {kit_id} from Order {order_id}")
            
            if not kit_id:
                 raise ValueError("Missing kit_id or order_id")
                 
            logger.info(f"Generating Kit {kit_id}...")
            generate_kit(kit_id)
            # generate_kit captures its own errors in DB 'status', 
            # but we should check if it "threw" or handled safely.
            # Current generate_kit swallows excep and updates DB. 
            # So job is technically "done" (attempt finished).
            
        else:
            raise ValueError(f"Unknown job type: {job_type}")
            
        mark_done(job_id)
        
    except Exception as e:
        logger.error(f"Job {job_id} Failed: {e}")
        traceback.print_exc()
        mark_failed(job_id, str(e))

def run_worker(once=False, batch_size=10, sleep_interval=5):
    app = create_app()
    
    with app.app_context():
        logger.info("Worker started.")
        while True:
            try:
                jobs = claim_batch(limit=batch_size)
                if not jobs:
                    if once:
                        logger.info("No jobs found. Exiting (--once).")
                        break
                    time.sleep(sleep_interval)
                    continue
                
                for job in jobs:
                    process_job(job)
                    
            except KeyboardInterrupt:
                logger.info("Worker stopped by user.")
                break
            except Exception as e:
                logger.error(f"Worker Loop Error: {e}")
                traceback.print_exc()
                if once: break
                time.sleep(sleep_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--batch", type=int, default=10, help="Batch size")
    args = parser.parse_args()
    
    run_worker(once=args.once, batch_size=args.batch)
