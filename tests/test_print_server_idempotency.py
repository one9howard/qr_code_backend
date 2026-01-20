"""
Test print server idempotency behavior.

Verifies that duplicate requests with the same Idempotency-Key return
'already_accepted' with the same job_id and don't create duplicate files.
"""
import os
import io
import sys
import importlib
import pytest


@pytest.fixture
def print_server_app(tmp_path):
    """Create a test client with isolated inbox directory."""
    # Set environment BEFORE import so the module initializes its inbox/DB in tmp_path
    os.environ["PRINT_INBOX_DIR"] = str(tmp_path)
    os.environ["PRINT_SERVER_DEV_MODE"] = "1"  # Skip auth for testing
    os.environ["FLASK_ENV"] = "development"

    # Ensure a clean import (other tests may have imported the module already)
    for mod in [
        "services.print_server.app",
        "services.print_server.__main__",
        "services.print_server",
    ]:
        sys.modules.pop(mod, None)

    import services.print_server.app as ps
    importlib.reload(ps)

    # Ensure DB/table exists in the new location
    ps.init_idemp_db()

    yield ps.app.test_client(), tmp_path


def test_idempotency_duplicate_requests_same_job_id(print_server_app):
    """Two identical POSTs with same Idempotency-Key return same job_id."""
    client, inbox_path = print_server_app
    
    # Create a small dummy PDF
    pdf_content = b"%PDF-1.4 dummy content for testing"
    
    idempotency_key = "order_12345"
    
    # First request
    response1 = client.post(
        "/print-jobs",
        data={
            "order_id": "12345",
            "property_id": "99",
            "sign_size": "18x24",
            "idempotency_key": idempotency_key,
            "file": (io.BytesIO(pdf_content), "test.pdf"),
        },
        headers={"Idempotency-Key": idempotency_key},
    )
    
    assert response1.status_code == 200
    data1 = response1.get_json()
    assert data1["status"] == "accepted"
    job_id = data1["job_id"]
    assert job_id.startswith("job_")
    
    # Second request with SAME idempotency key
    response2 = client.post(
        "/print-jobs",
        data={
            "order_id": "12345",
            "property_id": "99",
            "sign_size": "18x24",
            "idempotency_key": idempotency_key,
            "file": (io.BytesIO(pdf_content), "test.pdf"),
        },
        headers={"Idempotency-Key": idempotency_key},
    )
    
    assert response2.status_code == 200
    data2 = response2.get_json()
    assert data2["status"] == "already_accepted"
    assert data2["job_id"] == job_id  # Same job_id!


def test_idempotency_only_one_file_saved(print_server_app):
    """Duplicate requests should only save ONE file."""
    client, inbox_path = print_server_app
    
    pdf_content = b"%PDF-1.4 test content"
    idempotency_key = "order_99999"
    
    # First request
    response1 = client.post(
        "/print-jobs",
        data={
            "order_id": "99999",
            "property_id": "1",
            "sign_size": "24x36",
            "idempotency_key": idempotency_key,
            "file": (io.BytesIO(pdf_content), "sign.pdf"),
        },
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response1.status_code == 200
    
    # Second request (duplicate)
    response2 = client.post(
        "/print-jobs",
        data={
            "order_id": "99999",
            "property_id": "1",
            "sign_size": "24x36",
            "idempotency_key": idempotency_key,
            "file": (io.BytesIO(pdf_content), "sign.pdf"),
        },
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response2.status_code == 200
    assert response2.get_json()["status"] == "already_accepted"
    
    # Third request (duplicate)
    response3 = client.post(
        "/print-jobs",
        data={
            "order_id": "99999",
            "property_id": "1",
            "sign_size": "24x36",
            "idempotency_key": idempotency_key,
            "file": (io.BytesIO(pdf_content), "sign.pdf"),
        },
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response3.status_code == 200
    
    # Count PDF files in inbox (exclude .db files)
    pdf_files = [f for f in os.listdir(inbox_path) if f.endswith('.pdf')]
    assert len(pdf_files) == 1, f"Expected 1 PDF file, found {len(pdf_files)}: {pdf_files}"


def test_different_keys_create_different_jobs(print_server_app):
    """Different idempotency keys should create separate jobs."""
    client, inbox_path = print_server_app
    
    pdf_content = b"%PDF-1.4 test"
    
    # First order
    response1 = client.post(
        "/print-jobs",
        data={
            "order_id": "111",
            "property_id": "1",
            "idempotency_key": "order_111",
            "file": (io.BytesIO(pdf_content), "sign.pdf"),
        },
        headers={"Idempotency-Key": "order_111"},
    )
    assert response1.status_code == 200
    job_id_1 = response1.get_json()["job_id"]
    
    # Second order (different key)
    response2 = client.post(
        "/print-jobs",
        data={
            "order_id": "222",
            "property_id": "2",
            "idempotency_key": "order_222",
            "file": (io.BytesIO(pdf_content), "sign.pdf"),
        },
        headers={"Idempotency-Key": "order_222"},
    )
    assert response2.status_code == 200
    job_id_2 = response2.get_json()["job_id"]
    
    # Should have different job_ids
    assert job_id_1 != job_id_2
    
    # Should have 2 PDF files
    pdf_files = [f for f in os.listdir(inbox_path) if f.endswith('.pdf')]
    assert len(pdf_files) == 2
