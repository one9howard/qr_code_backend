import os
from pathlib import Path


from utils.storage import get_storage

def test_claim_jobs_is_idempotent(client, db):
    # Setup dependencies
    user_id = db.execute("INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s) RETURNING id", ("pj@test.com", "hash", True)).fetchone()[0]
    agent_id = db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, %s, %s, %s) RETURNING id", (user_id, "PJ Agent", "Broker", "pj@test.com")).fetchone()[0]
    prop_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, %s, 3, 2, 'pj-slug', 'PJQR') RETURNING id", (agent_id, "PJ St")).fetchone()[0]
    
    order_id_1 = db.execute("INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'paid', 'sign') RETURNING id", (user_id, prop_id)).fetchone()[0]
    order_id_2 = db.execute("INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'paid', 'sign') RETURNING id", (user_id, prop_id)).fetchone()[0]

    # Insert two queued jobs
    db.execute(
        """INSERT INTO print_jobs (idempotency_key, job_id, order_id, filename, status, attempts)
           VALUES (%s, %s, %s, %s, 'queued', 0), (%s, %s, %s, %s, 'queued', 0)""",
        (
            "idemp_1", "job_1", order_id_1, "print-jobs/job_1.pdf",
            "idemp_2", "job_2", order_id_2, "print-jobs/job_2.pdf",
        ),
    )
    db.commit()

    from config import PRINT_JOBS_TOKEN
    headers = {"Authorization": f"Bearer {PRINT_JOBS_TOKEN}"}

    r1 = client.post("/api/print-jobs/claim?limit=1", headers=headers)
    assert r1.status_code == 200
    jobs1 = r1.get_json()["jobs"]
    assert len(jobs1) == 1

    # The next claim should return the other job, not the same one
    r2 = client.post("/api/print-jobs/claim?limit=1", headers=headers)
    assert r2.status_code == 200
    jobs2 = r2.get_json()["jobs"]
    assert len(jobs2) == 1
    assert jobs2[0]["job_id"] != jobs1[0]["job_id"]


def test_download_pdf_requires_auth_and_returns_bytes(client, db):
    pdf_key = "print-jobs/sample.pdf"
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    get_storage().put_file(pdf_bytes, pdf_key)

    # User/Agent/Prop/Order setup
    user_id = db.execute("INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s) RETURNING id", ("pj2@test.com", "hash", True)).fetchone()[0]
    agent_id = db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, %s, %s, %s) RETURNING id", (user_id, "PJ2 Agent", "Broker", "pj2@test.com")).fetchone()[0]
    prop_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, %s, 3, 2, 'pj2-slug', 'PJ2QR') RETURNING id", (agent_id, "PJ2 St")).fetchone()[0]
    order_id = db.execute("INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'paid', 'sign') RETURNING id", (user_id, prop_id)).fetchone()[0]

    db.execute(
        """INSERT INTO print_jobs (idempotency_key, job_id, order_id, filename, status, attempts)
           VALUES (%s, %s, %s, %s, 'queued', 0)""",
        ("idemp_pdf", "job_pdf", order_id, pdf_key),
    )
    db.commit()

    # Wrong token
    r0 = client.get("/api/print-jobs/job_pdf/pdf", headers={"Authorization": "Bearer wrong"})
    assert r0.status_code == 401

    from config import PRINT_JOBS_TOKEN
    # Right token
    r1 = client.get("/api/print-jobs/job_pdf/pdf", headers={"Authorization": f"Bearer {PRINT_JOBS_TOKEN}"})
    assert r1.status_code == 200
    assert r1.data.startswith(b"%PDF")
    assert r1.mimetype == "application/pdf"
