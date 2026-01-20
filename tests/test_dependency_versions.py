"""
Tests to verify Flask 3.x / Werkzeug 3.x dependency policy.

These tests ensure the project uses modern Flask/Werkzeug versions
that are compatible with Python 3.13+.
"""
import pytest
from importlib.metadata import version


class TestDependencyVersions:
    """Verify dependencies meet modern Python compatibility requirements."""

    def test_flask_version_is_3x(self):
        """Flask should be version 3.x for modern Python compatibility."""
        flask_version = version("flask")
        flask_major = int(flask_version.split(".")[0])
        
        assert flask_major >= 3, (
            f"Expected Flask 3.x, found {flask_version}. "
            f"Regenerate lockfiles with: pip-compile -o requirements.txt requirements.in"
        )

    def test_werkzeug_version_is_3x(self):
        """Werkzeug should be version 3.x to match Flask 3.x."""
        werkzeug_version = version("werkzeug")
        werkzeug_major = int(werkzeug_version.split(".")[0])
        
        assert werkzeug_major >= 3, (
            f"Expected Werkzeug 3.x for Flask 3.x, found {werkzeug_version}. "
            f"Regenerate lockfiles with: pip-compile -o requirements.txt requirements.in"
        )

    def test_flask_werkzeug_compatible(self):
        """Flask and Werkzeug major versions should be compatible."""
        flask_version = version("flask")
        werkzeug_version = version("werkzeug")
        
        flask_major = int(flask_version.split(".")[0])
        werkzeug_major = int(werkzeug_version.split(".")[0])
        
        # Flask 3.x requires Werkzeug 3.x
        if flask_major >= 3:
            assert werkzeug_major >= 3, (
                f"Flask {flask_version} requires Werkzeug 3.x, "
                f"but found Werkzeug {werkzeug_version}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
