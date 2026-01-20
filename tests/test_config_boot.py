"""
Test: Config boots successfully in staging mode without SMTP.

This test verifies that config.py can be imported with:
- FLASK_ENV=production
- APP_STAGE=test
- SMTP_* vars NOT set

This proves the fix: SMTP is only required when APP_STAGE='prod'.
"""
import os
import sys
import pytest


class TestConfigStagingBoot:
    """Test config.py boots in staging mode without SMTP."""

    def test_staging_boot_without_smtp(self, monkeypatch):
        """Config should import successfully with APP_STAGE=test and no SMTP vars."""
        # Clear any existing SMTP vars
        for key in ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS']:
            monkeypatch.delenv(key, raising=False)

        # Set required staging vars
        monkeypatch.setenv('FLASK_ENV', 'production')
        monkeypatch.setenv('APP_STAGE', 'test')
        monkeypatch.setenv('SECRET_KEY', 'test-secret-key-1234567890')
        monkeypatch.setenv('BASE_URL', 'https://staging.example.com')
        monkeypatch.setenv('INSTANCE_DIR', './instance')
        monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_12345')
        monkeypatch.setenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_12345')
        monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', 'whsec_test123')
        monkeypatch.setenv('PRINT_SERVER_TOKEN', 'test-token')
        monkeypatch.setenv('STRIPE_PRICE_MONTHLY', 'price_test_monthly')
        monkeypatch.setenv('STRIPE_PRICE_SIGN', 'price_test_sign')

        # Remove config from sys.modules to force reimport
        for mod_name in list(sys.modules.keys()):
            if mod_name == 'config' or mod_name.startswith('config.'):
                del sys.modules[mod_name]

        # Import should NOT raise or sys.exit
        try:
            import config
            # If we get here, the import succeeded
            assert config.APP_STAGE == 'test'
            assert config.IS_PRODUCTION == True
        except SystemExit as e:
            pytest.fail(f"Config sys.exit({e.code}) - SMTP should NOT be required in APP_STAGE=test")
        except Exception as e:
            pytest.fail(f"Config raised exception: {e}")
