"""
Tests for environment variable sanitization helper.
"""
import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGetEnvStr:
    """Tests for utils.env.get_env_str function."""

    def test_strips_whitespace_by_default(self, monkeypatch):
        """Leading/trailing whitespace should be stripped by default."""
        monkeypatch.setenv("TEST_STRIP_VAR", "  whsec_abc123  ")
        from utils.env import get_env_str
        
        result = get_env_str("TEST_STRIP_VAR")
        assert result == "whsec_abc123"
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_preserves_whitespace_when_strip_false(self, monkeypatch):
        """Whitespace should be preserved when strip=False."""
        monkeypatch.setenv("TEST_NOSTRIP_VAR", "  value  ")
        from utils.env import get_env_str
        
        result = get_env_str("TEST_NOSTRIP_VAR", strip=False)
        assert result == "  value  "

    def test_returns_none_when_missing(self, monkeypatch):
        """Should return None when variable is not set."""
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        from utils.env import get_env_str
        
        result = get_env_str("NONEXISTENT_VAR")
        assert result is None

    def test_returns_default_when_missing(self, monkeypatch):
        """Should return default value when variable is not set."""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        from utils.env import get_env_str
        
        result = get_env_str("MISSING_VAR", default="fallback")
        assert result == "fallback"

    def test_returns_default_when_empty_after_strip(self, monkeypatch):
        """Should return default when variable is whitespace-only."""
        monkeypatch.setenv("WHITESPACE_VAR", "   ")
        from utils.env import get_env_str
        
        result = get_env_str("WHITESPACE_VAR", default="fallback")
        assert result == "fallback"

    def test_required_raises_on_missing(self, monkeypatch):
        """required=True should raise ValueError when var is missing."""
        monkeypatch.delenv("REQUIRED_MISSING_VAR", raising=False)
        from utils.env import get_env_str
        
        with pytest.raises(ValueError) as exc_info:
            get_env_str("REQUIRED_MISSING_VAR", required=True)
        
        assert "not set" in str(exc_info.value)
        assert "REQUIRED_MISSING_VAR" in str(exc_info.value)

    def test_required_raises_on_empty_after_strip(self, monkeypatch):
        """required=True should raise ValueError when var is whitespace-only."""
        monkeypatch.setenv("REQUIRED_EMPTY_VAR", "   ")
        from utils.env import get_env_str
        
        with pytest.raises(ValueError) as exc_info:
            get_env_str("REQUIRED_EMPTY_VAR", required=True)
        
        assert "empty" in str(exc_info.value)
        assert "REQUIRED_EMPTY_VAR" in str(exc_info.value)

    def test_required_passes_with_valid_value(self, monkeypatch):
        """required=True should not raise when var has valid value."""
        monkeypatch.setenv("REQUIRED_VALID_VAR", "valid_value")
        from utils.env import get_env_str
        
        result = get_env_str("REQUIRED_VALID_VAR", required=True)
        assert result == "valid_value"

    def test_stripe_webhook_secret_scenario(self, monkeypatch):
        """Test real-world scenario: STRIPE_WEBHOOK_SECRET with whitespace."""
        # Simulate common copy-paste error with trailing space
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_1234567890abcdef ")
        from utils.env import get_env_str
        
        result = get_env_str("STRIPE_WEBHOOK_SECRET")
        assert result == "whsec_1234567890abcdef"
        assert not result.endswith(" ")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
