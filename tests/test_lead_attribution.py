"""
Tests for SmartSign lead attribution and token validation.
"""
import pytest
import time

from utils.attrib import make_attrib_token, verify_attrib_token


def _seed_user_agent_property(db, suffix: str) -> dict:
    ts = int(time.time() * 1_000_000)
    email = f"lead_{suffix}_{ts}@example.com"
    slug = f"lead-{suffix}-{ts}"
    qr_code = f"LEAD{ts}"

    user_id = db.execute(
        """
        INSERT INTO users (email, password_hash, is_verified, subscription_status)
        VALUES (%s, 'x', true, 'active')
        RETURNING id
        """,
        (email,),
    ).fetchone()["id"]

    agent_id = db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone)
        VALUES (%s, 'Lead Agent', 'Lead Realty', %s, '555-111-2222')
        RETURNING id
        """,
        (user_id, email),
    ).fetchone()["id"]

    property_id = db.execute(
        """
        INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code)
        VALUES (%s, '123 Lead St', '3', '2', %s, %s)
        RETURNING id
        """,
        (agent_id, slug, qr_code),
    ).fetchone()["id"]
    db.commit()

    return {
        "user_id": user_id,
        "agent_id": agent_id,
        "property_id": property_id,
        "qr_code": qr_code,
    }


def _create_activated_asset(db, user_id: int, property_id: int | None, label: str):
    from services.smart_signs import SmartSignsService

    asset = SmartSignsService.create_asset_for_purchase(user_id, None, label)
    activation_order_id = db.execute(
        """
        INSERT INTO orders (user_id, status, order_type, paid_at, print_product, amount_total_cents, currency)
        VALUES (%s, 'paid', 'smart_sign', NOW(), 'smart_sign', 0, 'usd')
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]
    db.commit()

    SmartSignsService.activate_asset(asset["id"], activation_order_id)
    if property_id is not None:
        SmartSignsService.assign_asset(asset["id"], property_id, user_id)

    return db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset["id"],)).fetchone()


class TestAttribToken:
    def test_make_verify_token_roundtrip(self):
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())

        token = make_attrib_token(asset_id, issued_at, secret)
        result = verify_attrib_token(token, secret, max_age_seconds=60)

        assert result == asset_id

    def test_expired_token_rejected(self):
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time()) - 7200

        token = make_attrib_token(asset_id, issued_at, secret)
        result = verify_attrib_token(token, secret, max_age_seconds=3600)

        assert result is None

    def test_forged_signature_rejected(self):
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())

        token = make_attrib_token(asset_id, issued_at, secret)
        parts = token.split(".")
        parts[2] = "forgedsignature000000000000000"
        forged = ".".join(parts)

        result = verify_attrib_token(forged, secret, max_age_seconds=3600)
        assert result is None

    def test_forged_asset_id_rejected(self):
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())

        token = make_attrib_token(asset_id, issued_at, secret)
        parts = token.split(".")
        parts[0] = "99"
        forged = ".".join(parts)

        result = verify_attrib_token(forged, secret, max_age_seconds=3600)
        assert result is None

    def test_invalid_token_formats(self):
        secret = "test-secret"

        assert verify_attrib_token("", secret, 3600) is None
        assert verify_attrib_token("invalid", secret, 3600) is None
        assert verify_attrib_token("1.2", secret, 3600) is None
        assert verify_attrib_token("not.an.integer", secret, 3600) is None
        assert verify_attrib_token(None, secret, 3600) is None


class TestLeadValidation:
    @pytest.fixture
    def app(self):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @pytest.fixture
    def property_id(self, app):
        from database import get_db

        with app.app_context():
            db = get_db()
            seeded = _seed_user_agent_property(db, "lead-validation")
            return seeded["property_id"]

    def test_lead_with_email_only(self, client, property_id):
        response = client.post(
            "/api/leads/submit",
            json={
                "property_id": property_id,
                "buyer_email": "test@example.com",
                "consent": True,
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_lead_with_phone_and_email(self, client, property_id):
        response = client.post(
            "/api/leads/submit",
            json={
                "property_id": property_id,
                "buyer_email": "phone_preferred@example.com",
                "buyer_phone": "555-123-4567",
                "consent": True,
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_lead_without_contact_fails(self, client, property_id):
        response = client.post(
            "/api/leads/submit",
            json={
                "property_id": property_id,
                "buyer_name": "Test User",
                "consent": True,
            },
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "Email is required"


class TestAttributionCookie:
    @pytest.fixture
    def app(self):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_cookie_set_on_assigned_smartsign(self, client, app):
        from database import get_db

        with app.app_context():
            db = get_db()
            seeded = _seed_user_agent_property(db, "cookie-assigned")
            asset = _create_activated_asset(
                db,
                seeded["user_id"],
                seeded["property_id"],
                "Assigned Lead Sign",
            )

        response = client.get(f"/r/{asset['code']}", follow_redirects=False)

        assert response.status_code == 302
        assert client.get_cookie("smart_attrib") is not None

    def test_cookie_not_set_on_unassigned_smartsign(self, client, app):
        from database import get_db

        with app.app_context():
            db = get_db()
            seeded = _seed_user_agent_property(db, "cookie-unassigned")
            asset = _create_activated_asset(
                db,
                seeded["user_id"],
                None,
                "Unassigned Lead Sign",
            )

        response = client.get(f"/r/{asset['code']}", follow_redirects=False)

        assert response.status_code == 200
        assert client.get_cookie("smart_attrib") is None


class TestLeadAttribution:
    @pytest.fixture
    def app(self):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_lead_attributed_with_valid_token(self, client, app):
        from config import SECRET_KEY
        from database import get_db

        with app.app_context():
            db = get_db()
            seeded = _seed_user_agent_property(db, "attrib-valid")
            asset = _create_activated_asset(
                db,
                seeded["user_id"],
                seeded["property_id"],
                "Attribution Sign",
            )

            token = make_attrib_token(asset["id"], int(time.time()), SECRET_KEY)
            client.set_cookie("smart_attrib", token, domain="localhost")

            response = client.post(
                "/api/leads/submit",
                json={
                    "property_id": seeded["property_id"],
                    "buyer_email": f"test{int(time.time())}@example.com",
                    "consent": True,
                },
            )
            assert response.status_code == 200

            lead = db.execute(
                """
                SELECT sign_asset_id, source
                FROM leads
                WHERE property_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (seeded["property_id"],),
            ).fetchone()

            assert lead["sign_asset_id"] == asset["id"]
            assert lead["source"] == "smart_sign"

    def test_forged_token_ignored(self, client, app):
        from database import get_db

        with app.app_context():
            db = get_db()
            seeded = _seed_user_agent_property(db, "attrib-forged")

            client.set_cookie("smart_attrib", "999.12345.forgedsig0000000000000", domain="localhost")

            response = client.post(
                "/api/leads/submit",
                json={
                    "property_id": seeded["property_id"],
                    "buyer_email": f"forged{int(time.time())}@example.com",
                    "consent": True,
                },
            )
            assert response.status_code == 200

            lead = db.execute(
                """
                SELECT sign_asset_id, source
                FROM leads
                WHERE property_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (seeded["property_id"],),
            ).fetchone()

            assert lead["sign_asset_id"] is None
            assert lead["source"] == "direct"
