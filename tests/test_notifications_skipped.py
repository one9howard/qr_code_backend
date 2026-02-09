"""
Test: Notifications return 'skipped' when SMTP is not configured.

This test verifies that send_lead_notification_email returns:
- outcome_status == 'skipped' when SMTP_HOST/SMTP_USER are not set

This proves the fix: notifications no longer lie about being 'sent'.
"""
import os
import pytest


class TestNotificationSkipped:
    """Test notification skipping when SMTP is not configured."""

    def test_notification_returns_skipped_without_smtp(self, monkeypatch):
        """Notification should return outcome_status='skipped' when SMTP unset."""
        # Clear SMTP vars
        for key in ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS']:
            monkeypatch.delenv(key, raising=False)

        from services.notifications import send_lead_notification_email

        result = send_lead_notification_email(
            agent_email="test@example.com",
            lead_payload={
                "buyer_name": "Test Buyer",
                "buyer_email": "buyer@test.com",
                "property_address": "123 Test St"
            }
        )

        # Unpack the 3-tuple
        success, error_msg, outcome_status = result

        # Verify outcome_status is 'skipped' (NOT 'sent')
        assert outcome_status == 'skipped', f"Expected 'skipped', got '{outcome_status}'"
        assert success == False, "success should be False when skipping"
        assert error_msg == "SMTP not configured", f"Expected 'SMTP not configured', got '{error_msg}'"

    def test_notification_tuple_has_three_elements(self, monkeypatch):
        """Notification return value must be a 3-tuple."""
        for key in ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS']:
            monkeypatch.delenv(key, raising=False)

        from services.notifications import send_lead_notification_email

        result = send_lead_notification_email(
            agent_email="test@example.com",
            lead_payload={"buyer_name": "Test", "buyer_email": "t@t.com", "property_address": "123 St"}
        )

        assert isinstance(result, tuple), "Result should be a tuple"
        assert len(result) == 3, f"Result should have 3 elements, got {len(result)}"
