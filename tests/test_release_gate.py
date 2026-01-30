import os
import sys
import subprocess
import pytest
import services.printing.layout_utils as lu

def test_release_gate_fails_on_forbidden(tmp_path):
    """
    Ensures scripts/release_gate.py exits non-zero if a forbidden file is present.
    """
    forbidden = os.path.join(os.getcwd(), "debug_test_forbidden.html")
    with open(forbidden, "w") as f:
        f.write("test")
    
    try:
        # Pass CWD to ensure it finds itself
        result = subprocess.run([sys.executable, "scripts/release_gate.py"], capture_output=True, text=True, cwd=os.getcwd())
        assert result.returncode != 0
        assert "CRITICAL FAILURE" in result.stdout
    finally:
        if os.path.exists(forbidden):
            os.remove(forbidden)

def test_font_registration():
    """
    Verifies that register_fonts() attempts to register Inter fonts.
    """
    lu.register_fonts()
    if os.path.exists("static/fonts/Inter-Regular.ttf"):
        assert lu.FONT_BODY == "Inter-Regular"
    else:
        # Fallback case
        assert lu.FONT_BODY == "Helvetica"
